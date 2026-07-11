"""
Twin Liquors — wine scraper (TX chain, Austin/SA heavy).

Runs on City Hive (api.cityhive.net). The anonymous auth gate that blocks most
City Hive stores is bypassed with an api_key + client_origin lifted from the
storefront HTML — see data/exploration/twinliquors_findings.md.

WINE-ONLY: every product carries `additional_properties.type`; we keep only
`type == "wine"`, so spirits/beer/RTD/merchandise never enter inventory. That
same block hands us pre-enriched varietal / sub-type / ABV / region / country.

Shape (like specs.py): per-store × wine-search-terms, deduped by product id.
The search endpoint hard-caps at 30 results/term, so we sweep many terms.
Each store = its own merchant_id (like Spec's store numbers).
"""
import json
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List
from urllib.parse import quote

from scrapers.base import BaseScraper, RetailInventoryItem
from utils import infer_wine_type
from utils.upc import canonical_upc

RETAILER_NAME = "Twin Liquors"
SEARCH_URL = "https://api.cityhive.net/api/v1/products/search.json"
API_KEY = "7508df878a8c7566a880e4d3f7fa7972"       # public storefront key (window.cityHiveWidgetLoaderConfig.apiKey)
CLIENT_ORIGIN = "app://sites.twinliquors"

# Store merchant_ids (each store is its own merchant, like Spec's store numbers).
# Names/addresses/coords come back IN the response, so adding a store = add its id.
# Seed set validated 2026-07-09; ~90 TX stores total — expand from the
# store-locations page (data/exploration/twinliquors_findings.md).
STORE_MERCHANT_IDS = [
    "5af17c10c8852b44f5995fdc",  # McCreless Corner (SA)
    "5af17be4c8852b44f5995fbe",  # Bitters Marketplace (SA)
    "5af17c0ec8852b44f5995fd7",  # Bandera @ 1604 (SA)
    "5af17be2c8852b44f5995fb9",  # Stone Ridge Market (SA)
    "5af17bacc8852b44f5995f78",  # Springtown Center
    "5af17b1cc8852b44f5995f05",  # Bee Cave HEB Center (Austin)
    "5af17b54c8852b44f5995f46",  # University Marketplace (Austin)
    "5af17b52c8852b44f5995f41",  # The Parke (Austin)
    "546ba9ef3932330002910100",  # Four Points (Austin)
    "5af17ad1c8852b44f5995ed8",  # Emporium Duval/183 (Austin)
    "5af17a81c8852b44f5995ec4",  # The Village at Westlake (Austin)
    "5ada111597465774e9268c20",  # Balcones Drive (Austin)
]

# Broad term sweep to beat the 30-result/term cap — varietals, styles, regions.
# Results deduped by product id per store, so overlap is harmless.
WINE_SEARCH_TERMS = [
    "cabernet", "merlot", "pinot noir", "syrah", "shiraz", "zinfandel", "malbec",
    "tempranillo", "sangiovese", "nebbiolo", "grenache", "petite sirah", "red blend",
    "chardonnay", "sauvignon blanc", "pinot grigio", "pinot gris", "riesling",
    "chenin blanc", "viognier", "gewurztraminer", "albarino", "white blend",
    "rose wine", "champagne", "prosecco", "cava", "sparkling wine", "moscato",
    "port", "sherry", "madeira", "dessert wine",
    "bordeaux", "burgundy", "rioja", "chianti", "barolo", "napa", "sonoma",
    "red wine", "white wine",
]

_CURL_HEADERS = [
    "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "-H", "Origin: https://twinliquors.com",
    "-H", "Referer: https://twinliquors.com/shop/",
]

_ADDR_RE = re.compile(r"^(?P<street>.*?),\s*(?P<city>[^,]+),\s*(?P<state>[A-Z]{2})\s+(?P<zip>\d{5})")


@dataclass
class TwinProduct:
    product_id: str
    name: str
    brand: Optional[str]
    varietal: Optional[str]
    wine_type: Optional[str]
    abv: Optional[float]
    region: Optional[str]
    country: Optional[str]
    image_url: Optional[str]
    price: float
    in_stock: bool
    store_name: str
    address: Optional[str]
    city: str
    state: str
    zip_code: str

    @property
    def upc(self) -> str:
        return f"twinliquors-{self.product_id}"   # synthetic — no real barcode from City Hive


def _parse_abv(content) -> Optional[float]:
    if not content:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", str(content))
    return float(m.group(1)) if m else None


def _parse_address(full_address: str):
    """'3850 S New Braunfels Ave #113, San Antonio, TX 78223, USA' → (street, city, state, zip)."""
    m = _ADDR_RE.match(full_address or "")
    if not m:
        return (None, "Austin", "TX", "78701")
    return (m.group("street").strip(), m.group("city").strip(), m.group("state"), m.group("zip"))


def _pick_option(product_options: List[dict]) -> Optional[dict]:
    """The standard bottle: the default option (usually 750ml), else 750ml, else first priced one."""
    priced = [o for o in product_options if o.get("price") is not None]
    if not priced:
        return None
    for o in priced:
        if o.get("default_option"):
            return o
    for o in priced:
        sz = (o.get("option_params") or {}).get("size") or {}
        if str(sz.get("quantity")) == "750":
            return o
    return priced[0]


def _parse_product(raw: dict, merchant_id: str) -> Optional[TwinProduct]:
    """One product → TwinProduct, or None if not wine / no store offer."""
    ap = raw.get("additional_properties") or {}
    if (ap.get("type") or "").lower() != "wine":
        return None                                # THE wine gate — spirits/beer/merch dropped here

    # the offer for THIS store
    option = None
    store_name = full_address = None
    for m in raw.get("merchants") or []:
        opt = _pick_option(m.get("product_options") or [])
        if opt is None:
            continue
        if opt.get("merchant_id") == merchant_id or m.get("merchant_id") == merchant_id or option is None:
            option = opt
            store_name = opt.get("merchant_name") or m.get("merchant_name")
            full_address = opt.get("full_address") or m.get("full_address")
            if opt.get("merchant_id") == merchant_id:
                break
    if option is None or option.get("price") is None:
        return None

    street, city, state, zip_code = _parse_address(full_address or "")
    subtype = ap.get("subtype") or ap.get("varietal") or ""
    return TwinProduct(
        product_id=raw.get("id"),
        name=raw.get("name") or "",
        brand=ap.get("brands"),
        varietal=ap.get("varietal"),
        wine_type=infer_wine_type(subtype) or infer_wine_type(raw.get("name") or ""),
        abv=_parse_abv(ap.get("content")),
        region=ap.get("region"),
        country=ap.get("country"),
        image_url=((raw.get("images") or {}).get("primary") or {}).get("large")
                  or ((raw.get("images") or {}).get("primary") or {}).get("original"),
        price=float(option["price"]),
        in_stock=(option.get("quantity") or 0) > 0,
        store_name=store_name or f"Twin Liquors {merchant_id[:6]}",
        address=street, city=city, state=state, zip_code=zip_code,
    )


class TwinRateLimited(Exception):
    """Cloudflare 1015 — the endpoint is throttling this IP."""


def _fetch(merchant_id: str, term: str, retries: int = 4) -> List[dict]:
    """One term search. Retries Cloudflare 1015 rate-limits with backoff; raises
    TwinRateLimited only if it never clears (so the runner can pause + resume)."""
    import time
    url = (f"{SEARCH_URL}?merchant_id={merchant_id}&new_style=true"
           f"&api_key={API_KEY}&client_origin={CLIENT_ORIGIN}"
           f"&text={quote(term)}")
    cmd = ["curl", "-s", "--max-time", "30"] + _CURL_HEADERS + [url]
    for attempt in range(retries):
        out = subprocess.run(cmd, capture_output=True, text=True).stdout
        if "error code: 1015" in out[:60] or "rate limited" in out[:120].lower():
            time.sleep(20 * (attempt + 1))          # 20s, 40s, 60s, 80s
            continue
        try:
            return json.loads(out).get("data", {}).get("products") or []
        except Exception:
            time.sleep(3 * (attempt + 1))           # transient/network blip
            continue
    raise TwinRateLimited(f"{merchant_id}/{term}")


class TwinLiquorsScraper(BaseScraper):
    """City Hive wine scraper for Twin Liquors — per-store × term sweep, wine-only."""

    def _upsert_wines(self, products: List[TwinProduct]) -> dict:
        """Custom upsert: City Hive gives varietal/region/country/ABV pre-enriched,
        so persist them directly (no post-hoc extraction needed). Dedup by
        canonical (synthetic) UPC; return {upc -> wine_id}."""
        seen, records = set(), []
        for p in products:
            if not p.name or p.upc in seen:
                continue
            seen.add(p.upc)
            records.append({k: v for k, v in {
                "upc": p.upc,
                "upc_canonical": canonical_upc(p.upc),
                "name": p.name,
                "brand": p.brand,
                "varietal": p.varietal,
                "grapes": [p.varietal] if p.varietal else None,
                "wine_type": p.wine_type,
                "region": p.region,
                "country": p.country,
                "abv": p.abv,
                "avg_price": p.price,
                "image_url": p.image_url,
            }.items() if v is not None})

        if records:
            self.supabase.table("wines").upsert(records, on_conflict="upc_canonical").execute()

        canons = list({r["upc_canonical"] for r in records if r.get("upc_canonical")})
        if not canons:
            return {}
        # Chunk to keep the PostgREST URL under its request-line limit — a single
        # in_() of ~2k UPCs returned 400 Bad Request from the gateway during the
        # 2026-07-09 smoke test. 200/chunk is comfortably under any known limit.
        canon_to_id: dict = {}
        for i in range(0, len(canons), 200):
            chunk = canons[i:i + 200]
            rows = self.supabase.table("wines").select("id,upc_canonical").in_("upc_canonical", chunk).execute().data
            for w in rows:
                if w.get("upc_canonical"):
                    canon_to_id[w["upc_canonical"]] = w["id"]
        return {p.upc: canon_to_id.get(canonical_upc(p.upc))
                for p in products if canon_to_id.get(canonical_upc(p.upc))}

    def _to_items(self, products: List[TwinProduct], merchant_id: str) -> List[RetailInventoryItem]:
        return [RetailInventoryItem(
            wine_name=p.name, retailer_name=RETAILER_NAME,
            store_id=merchant_id, store_name=p.store_name,
            upc=p.upc, price=p.price, in_stock=p.in_stock,
            varietal=p.varietal, brand=p.brand, image_url=p.image_url,
            address=p.address, zip_code=p.zip_code, city=p.city, state=p.state,
        ) for p in products]

    async def run_full(self, merchant_ids: Optional[List[str]] = None) -> dict:
        import time
        stores = merchant_ids if merchant_ids is not None else STORE_MERCHANT_IDS

        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id, "retailer_name": RETAILER_NAME, "status": "running",
        }).execute()

        total = 0
        stores_ok = 0
        stores_failed: List[str] = []
        try:
            for mid in stores:
                by_id: dict = {}
                for term in WINE_SEARCH_TERMS:
                    try:
                        raws = _fetch(mid, term)
                    except TwinRateLimited:
                        print(f"    rate-limited on '{term}' — skipping remaining terms for this store")
                        break
                    for raw in raws:
                        p = _parse_product(raw, mid)
                        if p and p.product_id and p.product_id not in by_id:
                            by_id[p.product_id] = p
                    time.sleep(1.0)   # ~1 req/s — stays under Cloudflare's 1015 threshold

                products = list(by_id.values())
                store_label = products[0].store_name if products else mid
                # Per-store isolation: one store's DB commit failure must not nuke
                # the rest of the run (learned 2026-07-09 — a PostgREST 400 on
                # store N took down stores N+1..12 in the smoke test).
                try:
                    if products:
                        items = self._to_items(products, mid)
                        upc_to_id = self._upsert_wines(products)
                        self._upsert_inventory(items, upc_to_id)
                        total += len(products)
                    stores_ok += 1
                    print(f"  {store_label}: {len(products)} wines committed (total: {total})")
                except Exception as store_err:
                    stores_failed.append(mid)
                    print(f"  {store_label}: COMMIT FAILED — {store_err}")

            # scraper_runs.status CHECK enum only allows success|failed|running.
            # A run that committed *some* wines is called "success" so the row
            # writes cleanly; partial failures are recorded via error_message.
            # A migration to add 'partial' to the enum is a future improvement.
            status = "failed" if total == 0 else "success"
            self.supabase.table("scraper_runs").update({
                "status": status, "records_updated": total,
                "error_message": (f"failed stores: {','.join(stores_failed)}" if stores_failed else None),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            print(f"  DONE — {stores_ok}/{len(stores)} stores OK, {total} wines committed"
                  + (f", failed: {stores_failed}" if stores_failed else ""))
            return {"wines_committed": total, "stores": len(stores),
                    "stores_ok": stores_ok, "stores_failed": stores_failed}

        except Exception as e:
            self.supabase.table("scraper_runs").update({
                "status": "failed", "error_message": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            raise

    async def search_by_zip(self, zip_code: str) -> List[RetailInventoryItem]:
        return []

    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        return []
