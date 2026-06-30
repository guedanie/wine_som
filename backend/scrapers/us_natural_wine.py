"""
US Natural Wine (Austin) — Shopify API scraper.

usnaturalwine.com is an Austin natural wine bottle shop with ~560 products.
product_type values are inconsistent ('Red' vs 'Red Wine') — we normalize on
ingest. No UPCs expected (natural wines often have no barcodes). Single
Austin location with local pickup + delivery.
"""
import re
import urllib.request
import json
from typing import Optional, List
from datetime import datetime, timezone

from scrapers.base import BaseScraper, RetailInventoryItem
from scrapers.geraldines import ShopifyProduct, _strip_html, _first_paragraph, _parse_vintage

BASE_URL = "https://usnaturalwine.com"
STORE_NAME = "US Natural Wine"
STORE_ADDRESS = "9705 Burnet Rd, Ste 406"
STORE_ZIP = "78758"
STORE_ID = "us-natural-wine"
RETAILER_NAME = "US Natural Wine"
CITY = "Austin"
STATE = "TX"

# Normalize inconsistent product_type values to canonical wine type strings
_TYPE_MAP = {
    "Red":            "Red Wine",
    "Red Wine":       "Red Wine",
    "White":          "White Wine",
    "White Wine":     "White Wine",
    "Orange":         "Orange Wine",
    "Orange Wine":    "Orange Wine",
    "Deep Orange":    "Orange Wine",
    "Rose":           "Rosé Wine",
    "Rosé":           "Rosé Wine",
    "Sparkling":      "Sparkling Wine",
    "Sparkling Wine": "Sparkling Wine",
    "Light Red":      "Red Wine",
    "Dark Rose":      "Rosé Wine",
}

_SKIP_TYPES = {"Non-Alcoholic", "Cider & Fruit Wine"}

VINTAGE_RE = re.compile(r'\b(19[5-9]\d|20[0-2]\d)\b')


def _normalize_type(raw_type: str) -> Optional[str]:
    if raw_type in _SKIP_TYPES:
        return None
    return _TYPE_MAP.get(raw_type, "Wine" if raw_type else None)


def _parse_product_usnw(raw: dict) -> Optional[ShopifyProduct]:
    """Parse a US Natural Wine product. Skips non-alcoholic and cider."""
    product_type = raw.get("product_type") or ""
    normalized = _normalize_type(product_type)
    if normalized is None and product_type:
        return None  # explicit non-wine type

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
        product_type=normalized or "Wine",
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


def _fetch_page_usnw(page: int = 1, limit: int = 250, retries: int = 3) -> List[dict]:
    """Fetch one page of products from US Natural Wine."""
    import time
    url = f"{BASE_URL}/products.json?limit={limit}&page={page}"
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


class USNaturalWineScraper(BaseScraper):
    """Scraper for US Natural Wine (usnaturalwine.com), Austin TX."""

    def _products_to_inventory_items(
        self, products: List[ShopifyProduct]
    ) -> List[RetailInventoryItem]:
        return [
            RetailInventoryItem(
                wine_name=p.title,
                retailer_name=RETAILER_NAME,
                zip_code=STORE_ZIP,
                upc=f"shopify-usnw-{p.handle}",
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
            wine_id = upc_to_id.get(f"shopify-usnw-{p.handle}")
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
                raw_products = _fetch_page_usnw(page=page)
                if not raw_products:
                    break

                page_products = [p for raw in raw_products if (p := _parse_product_usnw(raw))]

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
