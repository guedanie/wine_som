"""
Pogo's Wine & Spirits (Dallas) — Shopify API scraper.

pogoswine.com is a well-regarded Dallas fine/natural wine shop (Inwood
Village) on Shopify with ~770 wines inside a broader beer/spirits/tobacco
catalog (1,500 products). Same public /products.json pattern as Harvest;
product_type is a capitalized single word (Red/White/Sparkling/Rose) that we
normalize, dropping non-wine types. vendor is a distributor, not the
producer, so brand is left null (extractor/Vivino fill it). Synthetic UPCs.
"""
import urllib.request
import json
import time
import uuid
from typing import Optional, List
from datetime import datetime, timezone

from scrapers.base import BaseScraper, RetailInventoryItem
from scrapers.geraldines import ShopifyProduct, _strip_html, _first_paragraph, _parse_vintage

BASE_URL = "https://pogoswine.com"
STORE_NAME = "Pogo's Wine & Spirits"
STORE_ADDRESS = "5360 W Lovers Ln Ste 200"
STORE_ZIP = "75209"
STORE_ID = "pogos-wine"
RETAILER_NAME = "Pogo's Wine & Spirits"
CITY = "Dallas"
STATE = "TX"

_TYPE_MAP = {
    "red":       "Red Wine",
    "white":     "White Wine",
    "sparkling": "Sparkling Wine",
    "champagne": "Sparkling Wine",
    "rose":      "Rosé Wine",
    "rosé":      "Rosé Wine",
    "orange":    "Orange Wine",
    "dessert":   "Dessert Wine",
    "fortified": "Fortified Wine",
    "port":      "Fortified Wine",
    "sherry":    "Fortified Wine",
    "vermouth":  "Fortified Wine",
    "sake":      "Sake",
}


def _normalize_type(raw_type: str) -> Optional[str]:
    """Canonical wine type, or None for non-wine (beer/spirits/tobacco/etc.)."""
    return _TYPE_MAP.get((raw_type or "").strip().lower())


def _parse_product_pogos(raw: dict) -> Optional[ShopifyProduct]:
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
        vendor="",                       # Pogo's vendor = distributor, not producer
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
    url = f"{BASE_URL}/products.json?limit={limit}&page={page}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read()).get("products", [])
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(10 * (attempt + 1))
            else:
                raise
    return []


class PogosScraper(BaseScraper):
    """Scraper for Pogo's Wine & Spirits (pogoswine.com) — Dallas, TX."""

    def _products_to_inventory_items(self, products: List[ShopifyProduct]) -> List[RetailInventoryItem]:
        return [
            RetailInventoryItem(
                wine_name=p.title,
                retailer_name=RETAILER_NAME,
                zip_code=STORE_ZIP,
                upc=f"shopify-pogos-{p.handle}",
                price=p.price,
                store_name=STORE_NAME,
                store_id=STORE_ID,
                address=STORE_ADDRESS,
                city=CITY,
                state=STATE,
                in_stock=p.available,
                varietal=None,
                brand=None,                  # vendor is a distributor; leave brand for extraction
                image_url=p.image_url,
            )
            for p in products
        ]

    def _upsert_wine_details(self, products: List[ShopifyProduct], upc_to_id: dict):
        name_to_id: dict = {}
        missing = [p for p in products if f"shopify-pogos-{p.handle}" not in upc_to_id]
        if missing:
            result = self.supabase.table("wines").select("id,name").in_(
                "name", [p.title for p in missing]).execute()
            name_to_id = {w["name"]: w["id"] for w in (result.data or [])}
        records = []
        for p in products:
            wine_id = upc_to_id.get(f"shopify-pogos-{p.handle}") or name_to_id.get(p.title)
            if not wine_id or not (p.description or p.tags):
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
            self.supabase.table("wine_details").upsert(records, on_conflict="wine_id").execute()

    def _fetch_all(self) -> List[ShopifyProduct]:
        wines: List[ShopifyProduct] = []
        page = 1
        while True:
            raw = _fetch_page(page=page)
            if not raw:
                break
            wines.extend(p for p in (_parse_product_pogos(r) for r in raw) if p)
            page += 1
            time.sleep(0.5)
        return wines

    async def search_by_zip(self, zip_code: str) -> List[RetailInventoryItem]:
        return self._products_to_inventory_items(self._fetch_all())

    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        products = [p for p in self._fetch_all() if wine_name.lower() in p.title.lower()]
        return self._products_to_inventory_items(products)

    async def run_full(self) -> dict:
        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id, "retailer_name": RETAILER_NAME, "status": "running",
        }).execute()
        total = 0
        page = 1
        try:
            while True:
                raw = _fetch_page(page=page)
                if not raw:
                    break
                page_products = [p for p in (_parse_product_pogos(r) for r in raw) if p]
                if page_products:
                    items = self._products_to_inventory_items(page_products)
                    upc_to_id = self._upsert_wines(items)
                    self._upsert_inventory(items, upc_to_id)
                    self._upsert_wine_details(page_products, upc_to_id)
                    total += len(page_products)
                    print(f"   page {page}: {len(page_products)} wines committed (total: {total})")
                page += 1
                time.sleep(0.5)
            self.supabase.table("scraper_runs").update({
                "status": "success", "records_updated": total,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            return {"wines_fetched": total, "store": STORE_NAME}
        except Exception as e:
            self.supabase.table("scraper_runs").update({
                "status": "failed", "error_message": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            raise
