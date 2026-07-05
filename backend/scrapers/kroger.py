"""
Kroger — official Developer API scraper (NOT a scrape).

Kroger runs a free public Developer Program (developer.kroger.com) with a
Products API that returns per-location pricing — the one thing Wine-Searcher
and Whole Foods denied us. OAuth2 client_credentials; the products endpoint
requires the `product.compact` scope.

- Auth:      POST /v1/connect/oauth2/token  (Basic base64(id:secret), scope=product.compact)
- Locations: GET  /v1/locations?filter.zipCode.near={zip}
- Products:  GET  /v1/products?filter.term={t}&filter.locationId={id}&filter.limit=50&filter.start={n}

The public Products API caps pagination (~250 offset), so a single "wine"
term can't cover a store. We search a spread of wine terms + varietals and
dedup by UPC — the documented workaround. Category is always "Adult Beverage"
(covers beer/spirits too), so we lean on wine-specific search terms plus a
non-wine keyword guard.

UPCs are real 13-digit barcodes → cross-retailer dedup works via upc_canonical.
Rate limit: 10,000 calls/day (public tier). Nashville = 4 stores × ~17 terms
× ~1-5 pages ≈ well under budget.
"""
import base64
import json
import time
import urllib.request
import urllib.parse
import uuid
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timezone

from scrapers.base import BaseScraper, RetailInventoryItem
from utils.upc import canonical_upc
from config import settings

API_BASE = "https://api.kroger.com/v1"
RETAILER_NAME = "Kroger"

# Nashville grocery stores near the beta tester (zip 37210). locationId, name,
# address, zip — BaseScraper auto-geocodes on seed.
NASHVILLE_STORES = [
    {"id": "02600511", "name": "Kroger - Melrose",          "address": "2615 8th Ave S",   "zip": "37204"},
    {"id": "02600542", "name": "Kroger - Briley Pkwy",      "address": "61 E Thompson Ln",  "zip": "37211"},
    {"id": "02600880", "name": "Kroger - East Nashville",   "address": "711 Gallatin Ave",  "zip": "37206"},
    {"id": "02600567", "name": "Kroger - Hillsboro Village", "address": "2201 21st Ave S",   "zip": "37212"},
]
CITY = "Nashville"
STATE = "TN"

# Wine-specific search terms (broad types + common varietals). Dedup by UPC
# collapses the overlap. Covers the store far better than one "wine" query.
WINE_TERMS = [
    "red wine", "white wine", "rose wine", "sparkling wine", "champagne",
    "cabernet sauvignon", "merlot", "pinot noir", "malbec", "syrah", "zinfandel",
    "chardonnay", "sauvignon blanc", "pinot grigio", "riesling", "prosecco", "moscato",
]

# Description keywords that mean it isn't wine (the term search occasionally
# pulls beer/spirits/mixers named with a wine word).
_NON_WINE = (
    "beer", "vodka", "whiskey", "whisky", "bourbon", "tequila", "gin", "rum",
    "seltzer", "hard cider", "cooking wine", "wine vinegar", "vinegar",
    "spritzer", "sake bomb", "margarita mix", "bloody mary",
)


@dataclass
class KrogerProduct:
    upc: str
    name: str
    brand: Optional[str]
    price: Optional[float]
    in_stock: bool
    image_url: Optional[str]
    size: Optional[str]


class KrogerClient:
    """OAuth2 client for the Kroger public API. Caches the bearer token
    (30-min TTL) and refreshes lazily."""

    def __init__(self, client_id: str = None, client_secret: str = None):
        self.client_id = client_id or settings.kroger_client_id
        self.client_secret = client_secret or settings.kroger_client_secret
        self._token: Optional[str] = None
        self._token_exp: float = 0.0

    def _fetch_token(self) -> str:
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "scope": "product.compact",
        }).encode()
        req = urllib.request.Request(
            f"{API_BASE}/connect/oauth2/token", data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Authorization": f"Basic {auth}"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        self._token = data["access_token"]
        # Refresh 60s early to avoid mid-call expiry.
        self._token_exp = time.monotonic() + data.get("expires_in", 1800) - 60
        return self._token

    def _token_value(self) -> str:
        if not self._token or time.monotonic() >= self._token_exp:
            return self._fetch_token()
        return self._token

    def _get(self, path: str, retries: int = 5) -> dict:
        for attempt in range(retries):
            req = urllib.request.Request(
                f"{API_BASE}{path}",
                headers={"Authorization": f"Bearer {self._token_value()}",
                         "Accept": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                if e.code == 401:              # token expired/revoked — force refresh
                    self._token = None
                    continue
                # 429 rate limit + transient 5xx — back off and retry
                if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise
            except urllib.error.URLError:      # transient network blip
                if attempt < retries - 1:
                    time.sleep(3 * (attempt + 1))
                    continue
                raise
        return {}

    def locations_near(self, zip_code: str, limit: int = 10) -> List[dict]:
        d = self._get(f"/locations?filter.zipCode.near={zip_code}&filter.limit={limit}")
        return d.get("data", [])

    def search(self, term: str, location_id: str, start: int = 0, limit: int = 50) -> List[dict]:
        q = urllib.parse.urlencode({
            "filter.term": term,
            "filter.locationId": location_id,
            "filter.limit": limit,
            "filter.start": start,
        })
        d = self._get(f"/products?{q}")
        return d.get("data", [])


def _front_image(product: dict) -> Optional[str]:
    """Largest front-perspective image URL, if any."""
    imgs = product.get("images") or []
    front = next((i for i in imgs if i.get("perspective") == "front"), imgs[0] if imgs else None)
    if not front:
        return None
    sizes = front.get("sizes") or []
    for want in ("xlarge", "large", "medium"):
        m = next((s for s in sizes if s.get("size") == want), None)
        if m and m.get("url"):
            return m["url"]
    return (sizes[0].get("url") if sizes else None)


def parse_product(product: dict) -> Optional[KrogerProduct]:
    """Parse a Kroger API product into a KrogerProduct. Drops non-wine items."""
    desc = (product.get("description") or "").strip()
    if not desc:
        return None
    low = desc.lower()
    if any(k in low for k in _NON_WINE):
        return None

    upc = product.get("upc")
    if not upc:
        return None

    item = (product.get("items") or [{}])[0]
    price_obj = item.get("price") or {}
    # promo beats regular when present
    price = price_obj.get("promo") or price_obj.get("regular")
    fulfillment = item.get("fulfillment") or {}
    in_stock = bool(fulfillment.get("inStore") or fulfillment.get("curbside")
                    or fulfillment.get("delivery"))

    return KrogerProduct(
        upc=upc,
        name=desc,
        brand=product.get("brand") or None,
        price=float(price) if price else None,
        in_stock=in_stock,
        image_url=_front_image(product),
        size=item.get("size"),
    )


class KrogerScraper(BaseScraper):
    """Kroger official-API scraper. Nashville stores by default."""

    def __init__(self, *args, client: KrogerClient = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = client or KrogerClient()

    def _fetch_store_wines(self, location_id: str) -> List[KrogerProduct]:
        """All wine products at one store: multi-term search, deduped by
        CANONICAL upc. Two distinct raw Kroger UPCs can normalize to the same
        canonical core (barcode variants of one wine); keying on canonical
        keeps the upsert batch free of duplicate constrained values."""
        by_canon: Dict[str, KrogerProduct] = {}
        for term in WINE_TERMS:
            start = 0
            while True:
                raw = self.client.search(term, location_id, start=start)
                if not raw:
                    break
                for r in raw:
                    p = parse_product(r)
                    if p:
                        key = canonical_upc(p.upc)
                        if key not in by_canon:
                            by_canon[key] = p
                if len(raw) < 50 or start >= 200:   # public API caps ~250 offset
                    break
                start += 50
                time.sleep(0.3)
            time.sleep(0.3)
        return list(by_canon.values())

    def _to_inventory_items(self, products: List[KrogerProduct], store: dict) -> List[RetailInventoryItem]:
        return [
            RetailInventoryItem(
                wine_name=p.name,
                retailer_name=RETAILER_NAME,
                zip_code=store["zip"],
                upc=p.upc,                       # real barcode → cross-retailer dedup
                price=p.price,
                store_name=store["name"],
                store_id=store["id"],
                address=store["address"],
                city=CITY,
                state=STATE,
                in_stock=p.in_stock,
                varietal=None,                   # extractor/Vivino fill varietal
                brand=p.brand,
                image_url=p.image_url,
            )
            for p in products
        ]

    async def search_by_zip(self, zip_code: str) -> List[RetailInventoryItem]:
        items: List[RetailInventoryItem] = []
        for store in NASHVILLE_STORES:
            items.extend(self._to_inventory_items(self._fetch_store_wines(store["id"]), store))
        return items

    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        store = NASHVILLE_STORES[0]
        raw = self.client.search(wine_name, store["id"])
        products = [p for p in (parse_product(r) for r in raw) if p]
        return self._to_inventory_items(products, store)

    async def run_full(self, store_ids: Optional[List[str]] = None) -> dict:
        """Scrape wine from each Nashville Kroger store; commit per store."""
        stores = ([s for s in NASHVILLE_STORES if s["id"] in store_ids]
                  if store_ids else NASHVILLE_STORES)

        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id, "retailer_name": RETAILER_NAME, "status": "running",
        }).execute()

        total = 0
        try:
            for store in stores:
                products = self._fetch_store_wines(store["id"])
                if products:
                    items = self._to_inventory_items(products, store)
                    upc_to_id = self._upsert_wines(items)
                    self._upsert_inventory(items, upc_to_id)
                    total += len(products)
                    print(f"   {store['name']}: {len(products)} wines committed (total: {total})")

            self.supabase.table("scraper_runs").update({
                "status": "success", "records_updated": total,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            return {"wines_fetched": total, "stores": len(stores), "retailer": RETAILER_NAME}

        except Exception as e:
            self.supabase.table("scraper_runs").update({
                "status": "failed", "error_message": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            raise
