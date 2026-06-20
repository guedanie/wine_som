"""
Geraldine's Natural Wines — Shopify API scraper.

shopgeraldines.com runs on Shopify, which exposes a public /products.json
endpoint with no auth required. This gives us rich structured data:
  - Wine name (title, often includes vintage year)
  - Producer (vendor)
  - Wine type (product_type: "Red Wine", "White Wine", etc.)
  - Description + tasting notes (body_html, stripped)
  - Tags (certifications + style: Biodynamic, Organic, Natural, etc.)
  - Price and availability (variants)
  - Bottle size (variant options)

No Playwright needed — pure HTTP.
"""
import re
import urllib.request
import json
from typing import Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timezone

from scrapers.base import BaseScraper, RetailInventoryItem
from utils import infer_wine_type

BASE_URL = "https://shopgeraldines.com"
STORE_NAME = "Geraldine's Natural Wines"
STORE_ADDRESS = "7700 Broadway St, San Antonio, TX 78209"
STORE_ZIP = "78209"
STORE_ID = "shopgeraldines"

WINE_PRODUCT_TYPES = {
    "Red Wine", "White Wine", "Sparkling Wine", "Rosé Wine",
    "Orange Wine", "Vermouth", "Dessert Wine", "Fortified Wine",
}

VINTAGE_RE = re.compile(r'\b(19[5-9]\d|20[0-2]\d)\b')


@dataclass
class ShopifyProduct:
    """Richer than RetailInventoryItem — carries wine knowledge fields too."""
    product_id: str
    title: str
    vendor: str
    product_type: str
    tags: List[str]
    description: Optional[str]       # first paragraph of body_html (tasting notes)
    description_long: Optional[str]  # full body_html stripped
    price: Optional[float]
    bottle_size: Optional[str]
    available: bool
    vintage_year: Optional[int]
    handle: str
    image_url: Optional[str] = None


def _strip_html(html: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _first_paragraph(html: str) -> Optional[str]:
    """Extract text of first <p> block — usually the tasting note."""
    match = re.search(r'<p[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    return _strip_html(match.group(1)).strip()


def _parse_vintage(title: str) -> Optional[int]:
    match = VINTAGE_RE.search(title)
    return int(match.group(0)) if match else None


def _parse_product(raw: dict) -> Optional[ShopifyProduct]:
    """Parse a Shopify product dict into a ShopifyProduct. Returns None for non-wine items."""
    product_type = raw.get("product_type", "")
    if product_type not in WINE_PRODUCT_TYPES:
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

    return ShopifyProduct(
        product_id=str(raw.get("id", "")),
        title=raw.get("title", ""),
        vendor=raw.get("vendor", ""),
        product_type=product_type,
        tags=raw.get("tags") or [],
        description=description,
        description_long=description_long,
        price=price,
        bottle_size=bottle_size,
        available=available,
        vintage_year=_parse_vintage(raw.get("title", "")),
        handle=raw.get("handle", ""),
        image_url=image_url,
    )


def _fetch_page_url(url: str, retries: int = 3) -> List[dict]:
    """Fetch products from an explicit URL (used for collection-scoped requests)."""
    import time
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
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


def _fetch_page(since_id: int = 0, limit: int = 250, retries: int = 3) -> List[dict]:
    """Fetch one page of products from Shopify. Uses since_id for pagination."""
    import time
    url = f"{BASE_URL}/products.json?limit={limit}"
    if since_id:
        url += f"&since_id={since_id}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
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


def fetch_all_wines() -> List[ShopifyProduct]:
    """
    Fetch all wine products from Geraldine's Shopify store.

    The public /products.json endpoint without a collection filter returns Shopify's
    broader product catalog (not just this store), so we do NOT paginate — we fetch
    each wine collection separately and deduplicate by handle.
    """
    WINE_COLLECTIONS = ["red", "white", "rose", "bubbles", "orange", "other-alcohol"]

    seen_handles = set()
    wines = []

    for collection in WINE_COLLECTIONS:
        url_path = f"/collections/{collection}/products.json?limit=250"
        raw_products = _fetch_page_url(f"{BASE_URL}{url_path}")
        for raw in raw_products:
            handle = raw.get("handle", "")
            if handle in seen_handles:
                continue
            seen_handles.add(handle)
            product = _parse_product(raw)
            if product:
                wines.append(product)

    return wines


class GeraldinesScraper(BaseScraper):
    """
    Scraper for Geraldine's Natural Wines (shopgeraldines.com).
    Uses Shopify's public product API — no Playwright, no auth, no bot protection.
    """

    def _shopify_products_to_inventory_items(
        self, products: List[ShopifyProduct]
    ) -> List[RetailInventoryItem]:
        return [
            RetailInventoryItem(
                wine_name=p.title,
                retailer_name=STORE_NAME,
                zip_code=STORE_ZIP,
                upc=f"shopify-geraldines-{p.handle}",  # stable unique ID per product
                price=p.price,
                store_name=STORE_NAME,
                store_id=STORE_ID,
                address=STORE_ADDRESS,
                city="San Antonio",
                state="TX",
                in_stock=p.available,
                varietal=p.product_type,
                brand=p.vendor,
                image_url=p.image_url,
            )
            for p in products
        ]

    def _upsert_wine_details(self, products: List[ShopifyProduct], upc_to_id: dict):
        """
        Write rich wine knowledge fields to wine_details from Shopify product data.
        These come pre-enriched from the store's own descriptions — no GrapeMinds call needed.
        """
        # Build wine name -> wine_id map (since Shopify wines have no UPC)
        result = self.supabase.table("wines").select("id,name").in_(
            "name", [p.title for p in products]
        ).execute()
        name_to_id = {w["name"]: w["id"] for w in (result.data or [])}

        records = []
        for p in products:
            wine_id = name_to_id.get(p.title)
            if not wine_id:
                continue
            if not (p.description or p.tags):
                continue

            records.append({k: v for k, v in {
                "wine_id": wine_id,
                "description": p.description,
                "description_long": p.description_long,
                "flavor_profile": p.tags,   # tags as style/flavor indicators
                "source": "scraped_shopify",
                "enriched_at": datetime.now(timezone.utc).isoformat(),
            }.items() if v is not None})

        if records:
            self.supabase.table("wine_details").upsert(
                records, on_conflict="wine_id"
            ).execute()

    async def search_by_zip(self, zip_code: str) -> List[RetailInventoryItem]:
        """Geraldine's has one location — zip filter is effectively a no-op."""
        products = fetch_all_wines()
        return self._shopify_products_to_inventory_items(products)

    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        products = [p for p in fetch_all_wines()
                    if wine_name.lower() in p.title.lower()]
        return self._shopify_products_to_inventory_items(products)

    async def run_full(self) -> dict:
        """
        Full scrape: fetch and commit one page at a time so progress is never lost.
        Each page is upserted immediately — if the job fails halfway, the DB keeps
        everything fetched so far.
        """
        import uuid
        import time

        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id,
            "retailer_name": STORE_NAME,
            "status": "running",
        }).execute()

        total_products = 0
        since_id = 0

        WINE_COLLECTIONS = ["red", "white", "rose", "bubbles", "orange", "other-alcohol"]
        seen_handles: set = set()

        try:
            for collection in WINE_COLLECTIONS:
                url = f"{BASE_URL}/collections/{collection}/products.json?limit=250"
                raw_page = _fetch_page_url(url)

                page_products = []
                for raw in raw_page:
                    handle = raw.get("handle", "")
                    if handle in seen_handles:
                        continue
                    seen_handles.add(handle)
                    product = _parse_product(raw)
                    if product:
                        page_products.append(product)

                if not page_products:
                    print(f"   {collection}: no wine products found, skipping")
                    continue

                page_items = self._shopify_products_to_inventory_items(page_products)

                # Commit this collection immediately
                upc_to_id = self._upsert_wines(page_items)
                self._upsert_inventory(page_items, upc_to_id)
                self._upsert_wine_details(page_products, upc_to_id)

                total_products += len(page_products)
                print(f"   {collection}: {len(page_products)} wines committed (total: {total_products})")
                time.sleep(2)

            self.supabase.table("scraper_runs").update({
                "status": "success",
                "records_updated": total_products,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()

            return {
                "wines_fetched": total_products,
                "inventory_records": total_products,
                "store": STORE_NAME,
            }

        except Exception as e:
            self.supabase.table("scraper_runs").update({
                "status": "failed",
                "error_message": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            raise
