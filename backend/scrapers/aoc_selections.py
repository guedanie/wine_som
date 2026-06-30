"""
AOC Selections — Shopify API scraper.

aocselections.com runs on Shopify with ~6,186 wine products across two
locations (San Antonio + Houston). The store uses `Location_SanAntonio`
and `Location_Houston` tags to indicate per-location inventory. We filter
to SA-only products. product_type is never set; wine type is inferred from
colour tags ('White', 'Red', 'Sparkling', 'Rose', 'Orange', 'Fortified').
body_html is typically empty — tags provide the richest metadata.
"""
import re
import urllib.request
import json
from typing import Optional, List
from datetime import datetime, timezone

from scrapers.base import BaseScraper, RetailInventoryItem
from scrapers.geraldines import ShopifyProduct, _strip_html, _first_paragraph, _parse_vintage

BASE_URL = "https://aocselections.com"
STORE_NAME = "AOC Selections"
STORE_ADDRESS = "2810 North Flores St"
STORE_ZIP = "78212"
STORE_ID = "aoc-selections"
RETAILER_NAME = "AOC Selections"
CITY = "San Antonio"
STATE = "TX"

_COLOUR_TO_TYPE = {
    "White":     "White Wine",
    "Red":       "Red Wine",
    "Sparkling": "Sparkling Wine",
    "Rose":      "Rosé Wine",
    "Rosé":      "Rosé Wine",
    "Orange":    "Orange Wine",
    "Fortified": "Fortified Wine",
    "Dessert":   "Dessert Wine",
}

VINTAGE_RE = re.compile(r'\b(19[5-9]\d|20[0-2]\d)\b')


def _infer_wine_type_from_tags(tags: List[str]) -> Optional[str]:
    for tag in tags:
        if tag in _COLOUR_TO_TYPE:
            return _COLOUR_TO_TYPE[tag]
    return None


def _parse_product_aoc(raw: dict) -> Optional[ShopifyProduct]:
    """Parse an AOC Shopify product. Returns None if not SA inventory."""
    tags = raw.get("tags") or []

    # Only scrape products stocked at the SA location
    if "Location_SanAntonio" not in tags:
        return None

    variants = raw.get("variants") or []
    if not variants:
        return None

    variant = variants[0]
    price_str = variant.get("price")
    price = float(price_str) if price_str else None
    available = variant.get("available", True)
    bottle_size = None
    for tag in tags:
        if tag in ("750ml", "1.5L", "3L", "375ml", "500ml", "1L"):
            bottle_size = tag
            break

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
        product_type=_infer_wine_type_from_tags(tags) or "Wine",
        tags=tags,
        description=description,
        description_long=description_long,
        price=price,
        bottle_size=bottle_size,
        available=available,
        vintage_year=_parse_vintage(title),
        handle=raw.get("handle", ""),
        image_url=image_url,
    )


def _fetch_page_aoc(page: int = 1, limit: int = 250, retries: int = 3) -> List[dict]:
    """Fetch one page of products from AOC Selections using page-number pagination."""
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


class AOCSelectionsScraper(BaseScraper):
    """
    Scraper for AOC Selections (aocselections.com).
    Filters to Location_SanAntonio tagged products only.
    """

    def _products_to_inventory_items(
        self, products: List[ShopifyProduct]
    ) -> List[RetailInventoryItem]:
        return [
            RetailInventoryItem(
                wine_name=p.title,
                retailer_name=RETAILER_NAME,
                zip_code=STORE_ZIP,
                upc=f"shopify-aoc-{p.handle}",
                price=p.price,
                store_name=STORE_NAME,
                store_id=STORE_ID,
                address=STORE_ADDRESS,
                city=CITY,
                state=STATE,
                in_stock=p.available,
                varietal=p.product_type,
                brand=None,
                image_url=p.image_url,
            )
            for p in products
        ]

    def _upsert_wine_details(self, products: List[ShopifyProduct], upc_to_id: dict):
        """Write tags as flavor_profile to wine_details for enrichment."""
        name_to_id: dict = {}
        if any(not (f"shopify-aoc-{p.handle}" in upc_to_id) for p in products):
            result = self.supabase.table("wines").select("id,name").in_(
                "name", [p.title for p in products]
            ).execute()
            name_to_id = {w["name"]: w["id"] for w in (result.data or [])}

        records = []
        for p in products:
            wine_id = upc_to_id.get(f"shopify-aoc-{p.handle}") or name_to_id.get(p.title)
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
        products = self._fetch_all_sa()
        return self._products_to_inventory_items(products)

    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        products = [p for p in self._fetch_all_sa()
                    if wine_name.lower() in p.title.lower()]
        return self._products_to_inventory_items(products)

    def _fetch_all_sa(self) -> List[ShopifyProduct]:
        """Fetch all SA-inventory products, paginating until empty page."""
        import time
        wines = []
        page = 1
        while True:
            raw_products = _fetch_page_aoc(page=page)
            if not raw_products:
                break
            for raw in raw_products:
                product = _parse_product_aoc(raw)
                if product:
                    wines.append(product)
            page += 1
            time.sleep(0.5)
        return wines

    async def run_full(self) -> dict:
        """Full scrape: fetch and commit page by page."""
        import uuid
        import time

        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id,
            "retailer_name": RETAILER_NAME,
            "status": "running",
        }).execute()

        total_products = 0
        page = 1

        try:
            while True:
                raw_products = _fetch_page_aoc(page=page)
                if not raw_products:
                    break

                page_products = []
                for raw in raw_products:
                    product = _parse_product_aoc(raw)
                    if product:
                        page_products.append(product)

                if page_products:
                    items = self._products_to_inventory_items(page_products)
                    upc_to_id = self._upsert_wines(items)
                    self._upsert_inventory(items, upc_to_id)
                    self._upsert_wine_details(page_products, upc_to_id)
                    total_products += len(page_products)
                    print(f"   page {page}: {len(page_products)} SA wines committed (total: {total_products})")

                page += 1
                time.sleep(0.5)

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
