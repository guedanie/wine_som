"""
Harvest Wine Market (Nashville) — Shopify API scraper.

harvestwinemarket.com is a Belle Meade wine shop on Shopify with ~750 wines
in a broader beer/spirits catalog. product_type casing is inconsistent
('Rosé' / 'Rose wine' / 'rose') so we normalize on ingest and skip the
non-wine types (Bourbon, Gin, Tequila, Events, etc.). Single Nashville
location — our first Tennessee retailer.

Same public /products.json pattern as Geraldine's/AOC/USNW — no auth, no
bot protection. Synthetic UPCs (natural/boutique wines rarely list barcodes).
"""
import re
import urllib.request
import json
import time
import uuid
from typing import Optional, List
from datetime import datetime, timezone

from scrapers.base import BaseScraper, RetailInventoryItem
from scrapers.geraldines import ShopifyProduct, _strip_html, _first_paragraph, _parse_vintage

BASE_URL = "https://harvestwinemarket.com"
STORE_NAME = "Harvest Wine Market"
STORE_ADDRESS = "6043 TN-100"
STORE_ZIP = "37205"
STORE_ID = "harvest-wine-market"
RETAILER_NAME = "Harvest Wine Market"
CITY = "Nashville"
STATE = "TN"

# Normalize inconsistent product_type casing/wording → canonical wine types.
_TYPE_MAP = {
    "red wine":       "Red Wine",
    "white wine":     "White Wine",
    "rose":           "Rosé Wine",
    "rosé":           "Rosé Wine",
    "rose wine":      "Rosé Wine",
    "rosé wine":      "Rosé Wine",
    "sparkling":      "Sparkling Wine",
    "sparkling wine": "Sparkling Wine",
    "champagne":      "Sparkling Wine",
    "orange":         "Orange Wine",
    "orange wine":    "Orange Wine",
    "dessert":        "Dessert Wine",
    "dessert wine":   "Dessert Wine",
    "fortified":      "Fortified Wine",
    "fortified wine": "Fortified Wine",
    "port":           "Fortified Wine",
    "sherry":         "Fortified Wine",
    "vermouth":       "Fortified Wine",
    "sake":           "Sake",
}

# Explicit non-wine product types to drop.
_SKIP_TYPES = {
    "bourbon", "gin", "tequila", "whiskey", "whisky", "mezcal", "rum",
    "vodka", "brandy", "cognac", "liqueur", "beer", "cider", "seltzer",
    "non alcoholic", "non-alcoholic", "ready to drink", "event", "gift card",
    "gift", "accessories", "merchandise", "glassware", "cocktail",
}


def _normalize_type(raw_type: str) -> Optional[str]:
    """Return a canonical wine type, or None for non-wine / unknown."""
    key = (raw_type or "").strip().lower()
    if not key or key in _SKIP_TYPES:
        return None
    return _TYPE_MAP.get(key)


def _parse_product_harvest(raw: dict) -> Optional[ShopifyProduct]:
    """Parse a Harvest Shopify product. Returns None for non-wine items."""
    wine_type = _normalize_type(raw.get("product_type") or "")
    if wine_type is None:
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
        product_type=wine_type,
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


def _fetch_page(page: int = 1, limit: int = 250, retries: int = 3) -> List[dict]:
    """Fetch one page of products using page-number pagination."""
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


class HarvestWineScraper(BaseScraper):
    """Scraper for Harvest Wine Market (harvestwinemarket.com) — Nashville, TN."""

    def _products_to_inventory_items(
        self, products: List[ShopifyProduct]
    ) -> List[RetailInventoryItem]:
        return [
            RetailInventoryItem(
                wine_name=p.title,
                retailer_name=RETAILER_NAME,
                zip_code=STORE_ZIP,
                upc=f"shopify-harvest-{p.handle}",
                price=p.price,
                store_name=STORE_NAME,
                store_id=STORE_ID,
                address=STORE_ADDRESS,
                city=CITY,
                state=STATE,
                in_stock=p.available,
                varietal=None,   # extractor/Vivino fill varietal; product_type is wine_type
                brand=p.vendor or None,
                image_url=p.image_url,
            )
            for p in products
        ]

    def _upsert_wine_details(self, products: List[ShopifyProduct], upc_to_id: dict):
        """Write store descriptions + tags to wine_details for enrichment."""
        name_to_id: dict = {}
        missing = [p for p in products if f"shopify-harvest-{p.handle}" not in upc_to_id]
        if missing:
            result = self.supabase.table("wines").select("id,name").in_(
                "name", [p.title for p in missing]
            ).execute()
            name_to_id = {w["name"]: w["id"] for w in (result.data or [])}

        records = []
        for p in products:
            wine_id = upc_to_id.get(f"shopify-harvest-{p.handle}") or name_to_id.get(p.title)
            if not wine_id:
                continue
            if not (p.description or p.tags):
                continue
            records.append({k: v for k, v in {
                "wine_id": wine_id,
                "description": p.description,
                "description_long": p.description_long,
                "flavor_profile": p.tags or None,
                "source": "scraped_shopify",
                "enriched_at": datetime.now(timezone.utc).isoformat(),
            }.items() if v is not None})

        if records:
            self.supabase.table("wine_details").upsert(
                records, on_conflict="wine_id"
            ).execute()

    def _fetch_all(self) -> List[ShopifyProduct]:
        wines: List[ShopifyProduct] = []
        page = 1
        while True:
            raw_products = _fetch_page(page=page)
            if not raw_products:
                break
            for raw in raw_products:
                product = _parse_product_harvest(raw)
                if product:
                    wines.append(product)
            page += 1
            time.sleep(0.5)
        return wines

    async def search_by_zip(self, zip_code: str) -> List[RetailInventoryItem]:
        return self._products_to_inventory_items(self._fetch_all())

    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        products = [p for p in self._fetch_all() if wine_name.lower() in p.title.lower()]
        return self._products_to_inventory_items(products)

    async def run_full(self) -> dict:
        """Full scrape: fetch and commit page by page."""
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
                raw_products = _fetch_page(page=page)
                if not raw_products:
                    break

                page_products = [p for p in (_parse_product_harvest(r) for r in raw_products) if p]

                if page_products:
                    items = self._products_to_inventory_items(page_products)
                    upc_to_id = self._upsert_wines(items)
                    self._upsert_inventory(items, upc_to_id)
                    self._upsert_wine_details(page_products, upc_to_id)
                    total_products += len(page_products)
                    print(f"   page {page}: {len(page_products)} wines committed (total: {total_products})")

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
