"""
Antonelli's Cheese Shop (Austin) — Shopify API scraper.

antonellischeese.com carries 391 wines alongside cheese and other products.
We filter to product_type=Wine. Title format: "WINE NAME / Producer / Region / Wine"
— producer and region are extractable from the title string.
"""
import re
import urllib.request
import json
from typing import Optional, List, Tuple
from datetime import datetime, timezone

from scrapers.base import BaseScraper, RetailInventoryItem
from scrapers.geraldines import ShopifyProduct, _strip_html, _first_paragraph, _parse_vintage

BASE_URL = "https://antonellischeese.com"
STORE_NAME = "Antonelli's Cheese Shop"
STORE_ADDRESS = "4220 Duval St"
STORE_ZIP = "78751"
STORE_ID = "antonellis"
RETAILER_NAME = "Antonelli's Cheese Shop"
CITY = "Austin"
STATE = "TX"

VINTAGE_RE = re.compile(r'\b(19[5-9]\d|20[0-2]\d)\b')
# Match "WINE NAME / Producer / Region / Wine" (or any trailing component)
_SLASH_RE = re.compile(r'^(.+?)\s*/\s*(.+?)\s*/\s*(.+?)(?:\s*/.*)?$')


def _parse_title_parts(title: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract (producer, region) from Antonelli's slash-separated title format."""
    m = _SLASH_RE.match(title)
    if not m:
        return None, None
    producer = m.group(2).strip() or None
    region = m.group(3).strip() or None
    # Drop trailing "Wine" if that's all region is
    if region and region.lower() == "wine":
        region = None
    return producer, region


def _parse_product_antonellis(raw: dict) -> Optional[ShopifyProduct]:
    """Parse an Antonelli's product. Only returns wine products."""
    product_type = raw.get("product_type") or ""
    if product_type.lower() != "wine":
        return None

    variants = raw.get("variants") or []
    if not variants:
        return None

    variant = variants[0]
    price_str = variant.get("price")
    price = float(price_str) if price_str else None
    available = variant.get("available", True)
    bottle_size = variant.get("option1") or None

    body_html = raw.get("body_html") or ""
    description = _first_paragraph(body_html) if body_html else None
    description_long = _strip_html(body_html) if body_html else None

    images = raw.get("images") or []
    image_url = images[0].get("src") if images else None

    title = raw.get("title", "")
    return ShopifyProduct(
        product_id=str(raw.get("id", "")),
        title=title,
        vendor=raw.get("vendor", ""),
        product_type="Wine",
        tags=raw.get("tags") or [],
        description=description,
        description_long=description_long,
        price=price,
        bottle_size=bottle_size,
        available=available,
        vintage_year=_parse_vintage(title),
        handle=raw.get("handle", ""),
        image_url=image_url,
    )


def _fetch_page_antonellis(page: int = 1, limit: int = 250, retries: int = 3) -> List[dict]:
    """Fetch one page of wine products from Antonelli's."""
    import time
    url = f"{BASE_URL}/products.json?limit={limit}&page={page}&product_type=Wine"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            return data.get("products", [])
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"   Rate limited — waiting {wait}s before retry {attempt + 2}/{retries}")
                time.sleep(wait)
            else:
                raise
    return []


class AntonellisScraper(BaseScraper):
    """Scraper for Antonelli's Cheese Shop wine section (antonellischeese.com)."""

    def _products_to_inventory_items(
        self, products: List[ShopifyProduct]
    ) -> List[RetailInventoryItem]:
        return [
            RetailInventoryItem(
                wine_name=p.title,
                retailer_name=RETAILER_NAME,
                zip_code=STORE_ZIP,
                upc=f"shopify-antonellis-{p.handle}",
                price=p.price,
                store_name=STORE_NAME,
                store_id=STORE_ID,
                address=STORE_ADDRESS,
                city=CITY,
                state=STATE,
                in_stock=p.available,
                varietal=p.product_type,
                brand=p.vendor or None,
                image_url=p.image_url,
            )
            for p in products
        ]

    def _upsert_wine_details(self, products: List[ShopifyProduct], upc_to_id: dict):
        records = []
        for p in products:
            wine_id = upc_to_id.get(f"shopify-antonellis-{p.handle}")
            if not wine_id:
                continue
            if not (p.description or p.tags):
                continue
            records.append({k: v for k, v in {
                "wine_id": wine_id,
                "description": p.description,
                "description_long": p.description_long,
                "flavor_profile": p.tags,
                "source": "scraped_shopify",
                "enriched_at": datetime.now(timezone.utc).isoformat(),
            }.items() if v is not None})
        if records:
            self.supabase.table("wine_details").upsert(
                records, on_conflict="wine_id"
            ).execute()

    async def search_by_zip(self, zip_code: str) -> List[RetailInventoryItem]:
        """Antonelli's is a single Austin location — zip filter is a no-op."""
        products = [p for raw in _fetch_page_antonellis() if (p := _parse_product_antonellis(raw))]
        return self._products_to_inventory_items(products)

    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        products = [p for raw in _fetch_page_antonellis() if (p := _parse_product_antonellis(raw))
                    and wine_name.lower() in p.title.lower()]
        return self._products_to_inventory_items(products)

    async def run_full(self) -> dict:
        import uuid
        import time

        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id, "retailer_name": RETAILER_NAME, "status": "running",
        }).execute()

        total_products = 0
        page = 1

        try:
            while True:
                raw_products = _fetch_page_antonellis(page=page)
                if not raw_products:
                    break

                page_products = [
                    p for raw in raw_products if (p := _parse_product_antonellis(raw))
                ]

                if page_products:
                    items = self._products_to_inventory_items(page_products)
                    upc_to_id = self._upsert_wines(items)
                    self._upsert_inventory(items, upc_to_id)
                    self._upsert_wine_details(page_products, upc_to_id)
                    total_products += len(page_products)
                    print(f"   page {page}: {len(page_products)} wines committed (total: {total_products})")

                page += 1
                time.sleep(1)

            self.supabase.table("scraper_runs").update({
                "status": "success",
                "records_updated": total_products,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()

            return {"wines_fetched": total_products, "store": STORE_NAME}

        except Exception as e:
            self.supabase.table("scraper_runs").update({
                "status": "failed",
                "error_message": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            raise
