"""Nashville independents on City Hive — Frugal MacDoogal + Corkdorks (×2).

**Why these three, specifically.** Nashville has volume but almost no depth: 35 Kroger
stores + Harvest give ~25,900 in-stock rows of which only **8.8% are $30+** (San
Antonio/Austin: 14.6%). Kroger serves value shoppers; a sommelier app's users skew upscale,
so the market looked covered on a store count and was not covered on the axis that matters.
These three are wine specialists — a first probe put a $184.99 Cabernet at the top of
Corkdorks Midtown's very first result page.

**Why it works.** Same City Hive bypass as Twin Liquors: the per-merchant `/products`
route is login-gated, but the top-level search route is anonymous given the `api_key` +
`client_origin` from the storefront widget config. Confirmed 2026-08-01 and re-verified
2026-08-26 (all three return 30 priced products/term).

**Why the mini.** City Hive Cloudflare-1015s datacenter IPs on sustained sweeps — the same
wall as Twin Liquors and Vivino. One-off probes from CI succeed; a 40-term × 3-store sweep
will not.

**Deliberately reuses `scrapers/twin_liquors.py`** for parsing (`_parse_product`), the term
sweep (`WINE_SEARCH_TERMS`) and rate-limit handling, rather than cloning three
near-identical files. Two things genuinely differ and are NOT reusable:

  * `client_origin` is **per site, not per store** — Corkdorks' two branches share one,
    Frugal has its own. Twin's `_fetch` hardcodes a module-level origin, so this module
    needs its own request layer. Sending the wrong origin returns an empty result set
    rather than an error, which is exactly the kind of silent-wrong we keep getting bitten
    by, so `_search_url` takes the origin explicitly.
  * UPCs use a shared `cityhive-` namespace. NOTE: Twin Liquors writes `twinliquors-{id}`
    for the same City Hive catalogue, so a wine stocked by both markets lands as two `wines`
    rows. A dedup miss, not corruption (each row keeps its own store's price); migrating
    Twin's prefix would orphan live rows, so it is left alone and recorded here instead.
"""
import json
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from scrapers.base import BaseScraper, RetailInventoryItem, _execute_with_retry
from scrapers.twin_liquors import (
    API_KEY, SEARCH_URL, WINE_SEARCH_TERMS, TwinProduct, TwinRateLimited,
    _CURL_HEADERS, _parse_product,
)
from utils.upc import canonical_upc

RETAILER_NAME = "Nashville Wine Merchants"

# Verified 2026-08-26: all three return 30 priced products/term with these values.
# Re-grep `window.cityHiveWidgetLoaderConfig` from each storefront if a run returns
# nothing — a rotated api_key/client_origin fails SILENTLY (empty results, not an error).
CH_STORES: Dict[str, Dict[str, str]] = {
    "6599a3f98893882b7f30798d": {
        "name": "Frugal MacDoogal", "client_origin": "app://sites.frugalmab9bcea1a",
        "address": "701 Division St", "zip": "37203", "city": "Nashville", "state": "TN"},
    "5c2a8cae7309395802faf15d": {
        "name": "Corkdorks - Midtown", "client_origin": "app://sites.corkdorks",
        "address": "1610 Church St", "zip": "37203", "city": "Nashville", "state": "TN"},
    "5b52b2903ff14a3c5d9cdd19": {
        "name": "Corkdorks - Green Hills", "client_origin": "app://sites.corkdorks",
        "address": "4009 Hillsboro Pike", "zip": "37215", "city": "Nashville", "state": "TN"},
}

_TERM_PAUSE = 1.2       # City Hive 1015s on sustained sweeps; self-pace like Twin
_DB_CHUNK = 200         # a 42-term sweep yields ~760 wines/store; a single upsert or
                        # IN-clause that size 400s ("Bad Request") on the URL length.
                        # Same limit twin_liquors uses.


def _cityhive_upc(product_id: str) -> str:
    return f"cityhive-{product_id}"


def _search_url(merchant_id: str, client_origin: str, term: str) -> str:
    """Search URL for ONE store. `client_origin` is explicit because it varies per
    site and a wrong one returns an empty list rather than an error."""
    return (f"{SEARCH_URL}?merchant_id={merchant_id}&new_style=true"
            f"&api_key={API_KEY}&client_origin={client_origin}&text={quote(term)}")


def _fetch(merchant_id: str, client_origin: str, term: str,
           retries: int = 4) -> List[dict]:
    """One term search against one store. Retries Cloudflare 1015 with backoff and
    raises TwinRateLimited only if it never clears, so the runner can pause/resume."""
    cmd = ["curl", "-s", "--max-time", "30"] + _CURL_HEADERS + [
        _search_url(merchant_id, client_origin, term)]
    for attempt in range(retries):
        out = subprocess.run(cmd, capture_output=True, text=True).stdout
        if "error code: 1015" in out[:60] or "rate limited" in out[:120].lower():
            time.sleep(20 * (attempt + 1))
            continue
        try:
            return json.loads(out).get("data", {}).get("products") or []
        except Exception:
            time.sleep(3 * (attempt + 1))
            continue
    raise TwinRateLimited(f"{merchant_id}/{term}")


def _to_items(products: List[TwinProduct], merchant_id: str,
              store: Dict[str, str]) -> List[RetailInventoryItem]:
    """Store metadata comes from CH_STORES, not the API response: City Hive's
    `full_address` is inconsistent across these merchants, and we already know
    exactly where these three shops are."""
    return [RetailInventoryItem(
        wine_name=p.name, retailer_name=RETAILER_NAME,
        store_id=merchant_id, store_name=store["name"],
        upc=_cityhive_upc(p.product_id), price=p.price, in_stock=p.in_stock,
        varietal=p.varietal, brand=p.brand, image_url=p.image_url,
        address=store["address"], zip_code=store["zip"],
        city=store["city"], state=store["state"],
    ) for p in products]


def _wine_records(products: List[TwinProduct]) -> List[Dict[str, Any]]:
    """City Hive returns varietal/region/country/ABV already enriched — persist them
    directly rather than making the Vivino/LLM pipeline rediscover it later."""
    seen, records = set(), []
    for p in products:
        upc = _cityhive_upc(p.product_id)
        if not p.name or upc in seen:
            continue
        seen.add(upc)
        records.append({k: v for k, v in {
            "upc": upc,
            "upc_canonical": canonical_upc(upc),
            "name": p.name,
            "brand": p.brand,
            "varietal": p.varietal,
            "grapes": [p.varietal] if p.varietal else None,
            "wine_type": p.wine_type,
            "abv": p.abv,
            "region": p.region,
            "country": p.country,
            "image_url": p.image_url,
            "avg_price": p.price,
        }.items() if v is not None})
    return records


class NashvilleCityHiveScraper(BaseScraper):
    """Term-sweep over three Nashville wine shops. Wine-only (the shared parser's
    type gate drops the spirits and beer these shops also sell)."""

    async def search_by_zip(self, zip_code: str) -> List[RetailInventoryItem]:
        out: List[RetailInventoryItem] = []
        for mid, store in CH_STORES.items():
            if store["zip"] != zip_code:
                continue
            raw = _fetch(mid, store["client_origin"], "red wine")
            prods = [p for p in (_parse_product(r, mid) for r in raw) if p]
            out += _to_items(prods, mid, store)
        return out

    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        out: List[RetailInventoryItem] = []
        for mid, store in CH_STORES.items():
            raw = _fetch(mid, store["client_origin"], wine_name)
            prods = [p for p in (_parse_product(r, mid) for r in raw) if p]
            out += _to_items(prods, mid, store)
        return out

    def _upsert_wines_enriched(self, products: List[TwinProduct]) -> Dict[str, str]:
        records = _wine_records(products)
        if not records:
            return {}
        for i in range(0, len(records), _DB_CHUNK):
            _execute_with_retry(self.supabase.table("wines").upsert(
                records[i:i + _DB_CHUNK], on_conflict="upc_canonical"))
        canons = [r["upc_canonical"] for r in records]
        canon_to_id: Dict[str, str] = {}
        for i in range(0, len(canons), _DB_CHUNK):
            rows = _execute_with_retry(
                self.supabase.table("wines").select("id,upc_canonical")
                .in_("upc_canonical", canons[i:i + _DB_CHUNK])).data or []
            canon_to_id.update({r["upc_canonical"]: r["id"] for r in rows})
        return {r["upc"]: canon_to_id[r["upc_canonical"]]
                for r in records if r["upc_canonical"] in canon_to_id}

    async def run_full(self, merchant_ids: Optional[List[str]] = None) -> dict:
        import uuid
        stores = merchant_ids or list(CH_STORES)
        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id, "retailer_name": RETAILER_NAME, "status": "running",
        }).execute()

        total, throttled = 0, []
        try:
            for mid in stores:
                store = CH_STORES[mid]
                print(f"\n  {store['name']} ({mid[:8]}…)", flush=True)
                seen: Dict[str, TwinProduct] = {}
                for term in WINE_SEARCH_TERMS:
                    try:
                        raw = _fetch(mid, store["client_origin"], term)
                    except TwinRateLimited:
                        # Rate-limited: bank this store's haul and move on rather than
                        # losing the sweep. Same posture as Total Wine (item 46) —
                        # throttling is expected, not exceptional.
                        print(f"    1015 on {term!r} — banking {len(seen)} and skipping "
                              f"the rest of this store", flush=True)
                        throttled.append(store["name"])
                        break
                    fresh = 0
                    for r in raw:
                        p = _parse_product(r, mid)
                        if p and p.product_id not in seen:
                            seen[p.product_id] = p
                            fresh += 1
                    if fresh:
                        print(f"    {term:<18} +{fresh:>3} (unique {len(seen)})", flush=True)
                    time.sleep(_TERM_PAUSE)

                products = list(seen.values())
                if products:
                    upc_to_id = self._upsert_wines_enriched(products)
                    items = _to_items(products, mid, store)
                    self._upsert_stores(items)
                    self._upsert_inventory(items, upc_to_id)
                    total += len(items)
                    print(f"    committed {len(items)} wines", flush=True)

            note = f" (throttled: {sorted(set(throttled))})" if throttled else ""
            self.supabase.table("scraper_runs").update({
                "status": "success", "records_updated": total,
                "error_message": note.strip() or None,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            return {"wines_committed": total, "stores": len(stores),
                    "throttled": sorted(set(throttled))}

        except Exception as e:
            self.supabase.table("scraper_runs").update({
                "status": "failed", "records_updated": total,
                "error_message": f"[{total} rows committed before failure] {e}",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            raise
