"""
HEB wine scraper — pure-curl GraphQL.

HEB's storefront HTML/REST routes are behind Imperva, but the Apollo GraphQL
endpoint (POST /graphql) is reachable server-side with no auth, cookies, or
browser. We reconstructed the productSearch query by reading Apollo validation
errors (introspection is disabled). See docs and CLAUDE.md for the recipe.

Each wine record carries:
  - id, displayName, brand.name, productPageURL
  - productDescription (embeds Type/Blend/Tasting Notes/ABV as light HTML)
  - inventory.quantity (live per-store stock)
  - SKUs[].twelveDigitUPC, customerFriendlySize
  - SKUs[].contextPrices: ONLINE (in-store, canonical) + CURBSIDE
"""
import re
import json
import csv as _csv
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any
from pathlib import Path as _Path
from dataclasses import dataclass

from scrapers.base import BaseScraper, RetailInventoryItem
from utils import infer_wine_type

GRAPHQL_URL = "https://www.heb.com/graphql"
RETAILER_NAME = "H-E-B"

_CSV_PATH = _Path(__file__).parents[2] / "data" / "heb-stores.csv"


def _load_store_registry() -> Dict[str, Dict[str, str]]:
    """Load active HEB stores from data/heb-stores.csv.

    To add a new store: set active=true in the CSV. No code change needed.
    """
    registry: Dict[str, Dict[str, str]] = {}
    with open(_CSV_PATH, newline="") as f:
        for row in _csv.DictReader(f):
            if row["active"].strip().lower() == "true":
                registry[row["store_id"].strip()] = {
                    "name":    row["name"].strip(),
                    "address": row["address"].strip(),
                    "zip":     row["zip"].strip(),
                    "city":    row["city"].strip(),
                    "state":   row["state"].strip(),
                }
    return registry


# All active HEB stores, keyed by store_id string.
# To add a store: flip active=true in data/heb-stores.csv.
STORE_REGISTRY: Dict[str, Dict[str, str]] = _load_store_registry()

# Kept for backward compatibility — callers that imported SA_STORES directly still work.
SA_STORES = {k: v for k, v in STORE_REGISTRY.items() if v["city"] == "San Antonio"}

_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 Mobile/15E148",
    "Apollographql-Client-Name": "heb-com",
    "Origin": "https://www.heb.com",
    "Referer": "https://www.heb.com/",
}

_PRODUCT_FIELDS = """
  id
  displayName
  brand { name }
  productPageURL
  productDescription
  inventory { quantity }
  SKUs { twelveDigitUPC customerFriendlySize
    contextPrices { context isOnSale listPrice { amount } salePrice { amount } } }
"""


@dataclass
class HEBProduct:
    product_id: str
    name: str
    brand: Optional[str]
    upc: Optional[str]
    bottle_size: Optional[str]
    price: Optional[float]            # ONLINE context (in-store, canonical)
    curbside_price: Optional[float]   # CURBSIDE context
    in_stock: bool
    wine_type: Optional[str]
    description: Optional[str]


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def _price_for_context(context_prices: List[Dict[str, Any]], context: str) -> Optional[float]:
    """Return the sale price for a context, falling back to list price."""
    for cp in context_prices or []:
        if cp.get("context") == context:
            sale = cp.get("salePrice") or {}
            if sale.get("amount") is not None:
                return float(sale["amount"])
            listp = cp.get("listPrice") or {}
            if listp.get("amount") is not None:
                return float(listp["amount"])
    return None


def _parse_record(raw: Dict[str, Any]) -> Optional[HEBProduct]:
    """Parse a productSearch record into an HEBProduct. Returns None for non-wine / unusable rows."""
    name = raw.get("displayName") or ""
    if not name:
        return None

    skus = raw.get("SKUs") or []
    if not skus:
        return None
    sku = skus[0]  # MVP: use first SKU only; multi-pack/size products lose secondary SKUs

    brand = (raw.get("brand") or {}).get("name")
    wine_type = infer_wine_type(name)
    if wine_type is None:
        # Not identifiably a wine — filter out (glasses, mixers, etc.)
        return None

    context_prices = sku.get("contextPrices") or []
    price = _price_for_context(context_prices, "ONLINE")
    curbside_price = _price_for_context(context_prices, "CURBSIDE")

    quantity = (raw.get("inventory") or {}).get("quantity") or 0

    return HEBProduct(
        product_id=str(raw.get("id", "")),
        name=name,
        brand=brand,
        upc=sku.get("twelveDigitUPC"),
        bottle_size=sku.get("customerFriendlySize"),
        price=price,
        curbside_price=curbside_price,
        in_stock=quantity > 0,
        wine_type=wine_type,
        description=_strip_html(raw.get("productDescription") or "") or None,
    )


def _graphql_post(query: str, timeout: int = 20, retries: int = 3) -> Dict[str, Any]:
    """POST a GraphQL query to HEB and return the parsed JSON. Retries on transient network errors."""
    import time
    body = json.dumps({"query": query}).encode("utf-8")
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(GRAPHQL_URL, data=body, headers=_HEADERS, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    raise last_err


def fetch_wine_page(offset: int = 0, limit: int = 60, store_id: str = "567"):
    """
    Fetch one page of wine products. Returns (server_total, [HEBProduct]).
    Non-wine rows are filtered out by _parse_record.
    """
    query = (
        "{ productSearch(shoppingContext: CURBSIDE_PICKUP, query: \"wine\", "
        f"storeId: {store_id}, limit: {limit}, offset: {offset}) {{ total records {{ {_PRODUCT_FIELDS} }} }} }}"
    )
    data = _graphql_post(query)
    ps = (data.get("data") or {}).get("productSearch") or {}
    total = ps.get("total") or 0
    products = []
    for raw in ps.get("records") or []:
        product = _parse_record(raw)
        if product:
            products.append(product)
    return total, products


class HebScraper(BaseScraper):
    """HEB scraper — pure-curl GraphQL, iterates all SA_STORES."""

    def _products_to_inventory_items(
        self,
        products: List[HEBProduct],
        store_id: str = "567",
        store_name: str = "H-E-B",
        store_zip: str = "78209",
        store_address: str = "999 East Basse Rd",
        city: str = "San Antonio",
        state: str = "TX",
        retailer_name: str = RETAILER_NAME,
    ) -> List[RetailInventoryItem]:
        return [
            RetailInventoryItem(
                wine_name=p.name,
                retailer_name=retailer_name,
                zip_code=store_zip,
                upc=p.upc,
                price=p.price,
                store_name=store_name,
                store_id=store_id,
                address=store_address,
                city=city,
                state=state,
                in_stock=p.in_stock,
                varietal=None,
                brand=p.brand,
            )
            for p in products
        ]

    async def search_by_zip(self, zip_code: str) -> List[RetailInventoryItem]:
        """MVP: single hardcoded store. Paginate the full wine catalog."""
        products = self._fetch_all()
        return self._products_to_inventory_items(products)

    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        _total, products = fetch_wine_page(offset=0, limit=60)
        matches = [p for p in products if wine_name.lower() in p.name.lower()]
        return self._products_to_inventory_items(matches)

    def _fetch_all(self, page_size: int = 60, max_pages: int = 60) -> List[HEBProduct]:
        """Paginate productSearch via offset until all records are fetched."""
        all_products: List[HEBProduct] = []
        offset = 0
        total = None
        for _ in range(max_pages):
            page_total, products = fetch_wine_page(offset=offset, limit=page_size)
            if total is None:
                total = page_total
            all_products.extend(products)
            offset += page_size
            if total is not None and offset >= total:
                break
        return all_products

    def _upsert_inventory_with_curbside(
        self,
        products: List[HEBProduct],
        store_id: str = "567",
        store_name: str = "H-E-B",
        store_zip: str = "78209",
        store_address: str = "999 East Basse Rd",
        city: str = "San Antonio",
        state: str = "TX",
        retailer_name: str = RETAILER_NAME,
    ):
        """Like base._upsert_inventory but includes curbside_price; references store_ref."""
        from datetime import datetime, timezone
        items = self._products_to_inventory_items(products, store_id, store_name, store_zip, store_address, city, state, retailer_name)
        upc_to_id = self._upsert_wines(items)
        store_map = self._upsert_stores(items)
        now = datetime.now(timezone.utc).isoformat()
        curbside_by_upc = {p.upc: p.curbside_price for p in products if p.upc}
        records = []
        for item in items:
            store_ref = store_map.get((item.retailer_name, item.store_id))
            if not store_ref:
                continue
            records.append({k: v for k, v in {
                "wine_id": upc_to_id.get(item.upc) if item.upc else None,
                "upc": item.upc,
                "store_ref": store_ref,
                "price": item.price,
                "curbside_price": curbside_by_upc.get(item.upc),
                "in_stock": item.in_stock,
                "last_scraped_at": now,
            }.items() if v is not None})
        if records:
            self.supabase.table("retail_inventory").upsert(
                records, on_conflict="upc,store_ref"
            ).execute()
        return upc_to_id

    def _upsert_wine_details(self, products: List[HEBProduct], upc_to_id: dict):
        """Write HEB productDescription into wine_details as scraped enrichment."""
        from datetime import datetime, timezone
        records = []
        for p in products:
            wine_id = upc_to_id.get(p.upc) if p.upc else None
            if not wine_id or not p.description:
                continue
            records.append({
                "wine_id": wine_id,
                "description": p.description,
                "source": "scraped_heb",
                "enriched_at": datetime.now(timezone.utc).isoformat(),
            })
        if records:
            self.supabase.table("wine_details").upsert(
                records, on_conflict="wine_id"
            ).execute()

    async def run_full(self, city: Optional[str] = None, store_ids: Optional[List[str]] = None) -> dict:
        """Full scrape across STORE_REGISTRY with per-page commit.

        Args:
            city: If set, only scrape stores in that city (e.g. "Austin").
            store_ids: If set, only scrape those specific store IDs.
            If neither is set, scrapes all registered stores.
        """
        import uuid
        import time
        from datetime import datetime, timezone

        stores = {
            k: v for k, v in STORE_REGISTRY.items()
            if (city is None or v["city"] == city)
            and (store_ids is None or k in store_ids)
        }

        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id, "retailer_name": RETAILER_NAME, "status": "running",
        }).execute()

        total_committed = 0
        page_size = 60

        try:
            for store_id, store_info in stores.items():
                store_name    = store_info["name"]
                store_zip     = store_info["zip"]
                store_address = store_info["address"]
                store_city    = store_info["city"]
                store_state   = store_info["state"]
                print(f"\n  Store {store_id} — {store_name} ({store_city})")

                offset = 0
                server_total = None

                for _ in range(60):  # safety cap per store
                    page_total, products = fetch_wine_page(offset=offset, limit=page_size, store_id=store_id)
                    if server_total is None:
                        server_total = page_total
                    if products:
                        upc_to_id = self._upsert_inventory_with_curbside(
                            products, store_id, store_name, store_zip, store_address,
                            city=store_city, state=store_state,
                        )
                        self._upsert_wine_details(products, upc_to_id)
                        total_committed += len(products)
                        print(f"    offset {offset}: {len(products)} wines (total: {total_committed})")
                    offset += page_size
                    if server_total is not None and offset >= server_total:
                        break
                    time.sleep(0.3)

            self.supabase.table("scraper_runs").update({
                "status": "success",
                "records_updated": total_committed,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()

            return {"wines_committed": total_committed, "stores": len(stores)}

        except Exception as e:
            self.supabase.table("scraper_runs").update({
                "status": "failed",
                "error_message": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            raise
