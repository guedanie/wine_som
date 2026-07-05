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
import socket
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

# The Kroger Developer API covers ALL Kroger-owned banners (Kroger, Harris
# Teeter, Ralphs, Fred Meyer, King Soopers, …) — same Products API + pricing,
# the banner is just cosmetic. Markets are config: to add a city, list its
# store IDs from
#   GET /locations?filter.zipCode.near={zip}&filter.chain={code}
# 'retailer' is the display banner; store locationIds are all the API needs.
# BaseScraper auto-geocodes stores from address/zip on seed.
MARKETS: Dict[str, Dict[str, Any]] = {
    "nashville": {
        "city": "Nashville", "state": "TN", "retailer": "Kroger",
        "stores": [
            {"id": "02600511", "name": "Kroger - Melrose",           "address": "2615 8th Ave S",   "zip": "37204"},
            {"id": "02600542", "name": "Kroger - Briley Pkwy",       "address": "61 E Thompson Ln", "zip": "37211"},
            {"id": "02600880", "name": "Kroger - East Nashville",    "address": "711 Gallatin Ave", "zip": "37206"},
            {"id": "02600567", "name": "Kroger - Hillsboro Village", "address": "2201 21st Ave S",   "zip": "37212"},
        ],
    },
    "charlotte": {
        "city": "Charlotte", "state": "NC", "retailer": "Harris Teeter",
        "stores": [
            {"id": "09700205", "name": "Harris Teeter - Fifth and Poplar",   "address": "325 W 6th St",    "zip": "28202"},
            {"id": "09700061", "name": "Harris Teeter - Kenilworth Commons", "address": "1227 East Blvd",  "zip": "28203"},
            {"id": "09700401", "name": "Harris Teeter - Central Avenue",     "address": "1704 Central Ave", "zip": "28205"},
            {"id": "09700305", "name": "Harris Teeter - Sedgefield",         "address": "2717 South Blvd", "zip": "28209"},
            {"id": "09700412", "name": "Harris Teeter - Myers Park Center",  "address": "1015 Providence Rd", "zip": "28207"},
        ],
    },
    "winston-salem": {
        "city": "Winston-Salem", "state": "NC", "retailer": "Harris Teeter",
        "stores": [
            {"id": "09700216", "name": "Harris Teeter - Cloverdale Plaza",  "address": "2281 Cloverdale Ave",  "zip": "27103"},
            {"id": "09700155", "name": "Harris Teeter - Thruway Center",    "address": "420 S Stratford Rd",   "zip": "27103"},
            {"id": "09700127", "name": "Harris Teeter - Whitaker Square",   "address": "1955 N Peace Haven Rd", "zip": "27106"},
            {"id": "09700346", "name": "Harris Teeter - Pine Ridge Plaza",  "address": "2835 Reynolda Rd",     "zip": "27106"},
            {"id": "09700037", "name": "Harris Teeter - Harper Hill Common", "address": "150 Grant Hill Ln",   "zip": "27104"},
        ],
    },
    "dallas": {
        "city": "Dallas", "state": "TX", "retailer": "Kroger",
        "stores": [
            {"id": "03500529", "name": "Kroger Fresh Fare - Capitol Ave",   "address": "4241 Capitol Ave",      "zip": "75204"},
            {"id": "03500528", "name": "Kroger Fresh Fare - Cedar Springs", "address": "4142 Cedar Springs Rd", "zip": "75219"},
            {"id": "03500509", "name": "Kroger Fresh Fare - Maple Ave",     "address": "4901 Maple Ave",        "zip": "75235"},
            {"id": "03500518", "name": "Kroger - Mockingbird",             "address": "5665 E Mockingbird Ln", "zip": "75206"},
            {"id": "03500511", "name": "Kroger - Northview Plaza",          "address": "10677 E Northwest Hwy", "zip": "75238"},
        ],
    },
}

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
            except (urllib.error.URLError, socket.timeout, TimeoutError):
                # transient network blip / read timeout (bare socket.timeout
                # is NOT a URLError, so it must be named explicitly)
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
    """Kroger official-API scraper across all configured MARKETS (Kroger +
    Harris Teeter banners). run_full(markets=[...]) to scope to specific cities."""

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

    def _to_inventory_items(self, products: List[KrogerProduct], store: dict,
                            market: dict) -> List[RetailInventoryItem]:
        return [
            RetailInventoryItem(
                wine_name=p.name,
                retailer_name=market["retailer"],   # banner: Kroger / Harris Teeter / …
                zip_code=store["zip"],
                upc=p.upc,                           # real barcode → cross-retailer dedup
                price=p.price,
                store_name=store["name"],
                store_id=store["id"],
                address=store["address"],
                city=market["city"],
                state=market["state"],
                in_stock=p.in_stock,
                varietal=None,                       # extractor/Vivino fill varietal
                brand=p.brand,
                image_url=p.image_url,
            )
            for p in products
        ]

    async def search_by_zip(self, zip_code: str) -> List[RetailInventoryItem]:
        items: List[RetailInventoryItem] = []
        for market in MARKETS.values():
            for store in market["stores"]:
                items.extend(self._to_inventory_items(
                    self._fetch_store_wines(store["id"]), store, market))
        return items

    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        market = MARKETS["nashville"]
        store = market["stores"][0]
        raw = self.client.search(wine_name, store["id"])
        products = [p for p in (parse_product(r) for r in raw) if p]
        return self._to_inventory_items(products, store, market)

    async def run_full(self, markets: Optional[List[str]] = None) -> dict:
        """Scrape wine per store across the given markets (all by default);
        commit per store. `markets` is a list of MARKETS keys, e.g. ['charlotte']."""
        keys = markets or list(MARKETS.keys())

        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id, "retailer_name": "Kroger (multi-banner)", "status": "running",
        }).execute()

        total, failed = 0, []
        for key in keys:
            market = MARKETS[key]
            for store in market["stores"]:
                try:
                    products = self._fetch_store_wines(store["id"])
                    if products:
                        items = self._to_inventory_items(products, store, market)
                        upc_to_id = self._upsert_wines(items)
                        self._upsert_inventory(items, upc_to_id)
                        total += len(products)
                        print(f"   [{market['city']}] {store['name']}: "
                              f"{len(products)} wines (total: {total})")
                except Exception as e:
                    # One store's transient failure shouldn't sink the rest.
                    failed.append(f"{market['city']}/{store['name']}")
                    print(f"   [{market['city']}] {store['name']}: FAILED — {e}")

        status = "success" if not failed else "partial"
        self.supabase.table("scraper_runs").update({
            "status": status, "records_updated": total,
            "error_message": ("stores failed: " + ", ".join(failed)) if failed else None,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()
        return {"wines_fetched": total, "markets": keys, "failed": failed}
