"""Total Wine & More scraper — plain HTTP, store-scoped by URL (item 46).

Unlike H-E-B (item 45), Total Wine needs NO browser: plain urllib reads it fine, and
an automated browser is actively refused (403 fingerprint). The three things that make
this work, all measured — full evidence in `data/exploration/totalwine_findings.md`:

1. **Scope with `?storeId=` in the URL, never the cookie.** The `twm-userStoreInformation`
   cookie works until you push, at which point Total Wine silently serves its hard-coded
   DEFAULT store (1108, Sacramento CA) at HTTP 200 with clean, parseable, wrong-city data.
   Putting the store in the URL makes it part of the CDN cache key (Fastly's `Vary` does
   NOT include `Cookie`), so a `?storeId=503` request cannot be served the default.
   Belt and braces: `_assert_store` still refuses any page that doesn't carry the store
   we asked for. A wrong price is worse than no price — see items 39/40/44.

2. **Identity from JSON-LD, price from the tile.** Each page carries an `ItemList` with
   canonical url + name per product. The CSS-module class names are content-hashed
   (`price__ff218822`) and churn on every Total Wine frontend build, so they are used only
   to find a price WITHIN a tile already bounded by JSON-LD anchors — a markup change
   degrades a price to None rather than mis-pairing it with the wrong wine.

3. **`pageSize` scales to 200.** Default is 24; 200 works and turns ~248 requests/store
   into ~30. The rate limit (~10 rapid requests → 403) still applies, hence the pacing.

Bonus: the product URL encodes colour + varietal (`/wine/red-wine/cabernet-sauvignon/...`),
so every row arrives with a varietal already — directly useful against the varietal-null
gap in items 13/34.

No barcodes are exposed, so UPCs are synthetic: `totalwine-{productId}` (same convention
as `shopify-`/`twinliquors-`; `canonical_upc` passes anything with a letter through).
"""
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scrapers.base import BaseScraper, RetailInventoryItem

RETAILER_NAME = "Total Wine & More"
WINE_CATEGORY = "https://www.totalwine.com/wine/c/c0020"

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

_PAGE_SIZE = 200          # measured ceiling that still returns cleanly (3.3 MB/page)
_MAX_PAGES = 60           # 5,947 wines / 200 ≈ 30; cap guards a pagination bug

# Two modes, because Total Wine throttles hard (see below).
#   SEED  — first N pages per store, quick, to get usable coverage the same day.
#   CRAWL — resume where the last run stopped, slowly, a few pages at a time.
# Rationale: a single run CANNOT finish a store. Measured — pages 1,3,4 fine, then a
# 4-page empty streak, then intermittent, then HTTP 403 at page ~11 of 30. Those empty
# pages are the throttle serving a STRIPPED page (no JSON-LD), not flakiness: degradation
# tracks request volume. So partial progress is the design, not a failure mode.
_SEED_PAGES = 5           # 5 x 200 = ~1,000 wines/store, the fast first pass
_SEED_PACE = 8.0
_CRAWL_PAGES = 6          # per slow run; several runs/week finish a store
_CRAWL_PACE = 45.0        # measured: fast pacing is what triggers the strip-then-403
_EMPTY_BACKOFF = 150.0    # an empty page means "you are being throttled" — wait, do not
                          # retry fast. Retrying at 5s burned ~4 requests per empty page
                          # and accelerated the 403 that killed the first full run.

_CURSOR_PATH = Path(__file__).parents[2] / "data" / "totalwine_cursor.json"

# Verified store metadata. Harvested via local_delivery_pages_sitemap.xml ->
# alcohol-delivery-near-me-{City}-{State} -> /store-info/{state-city}/{id}.
# Starting with one store deliberately; the same route enumerates TX + NC.
TW_STORES: Dict[str, Dict[str, str]] = {
    "503": {"name": "Total Wine - San Antonio (Del Norte)",
            "address": "125 NW Loop 410 Ste260", "zip": "78216",
            "city": "San Antonio", "state": "TX"},
}


class WrongStore(Exception):
    """The page came back without the store we asked for — refuse it."""


class Blocked(Exception):
    """PerimeterX is refusing this IP. Not a bug and not a transient failure —
    the expected state since 2026-08-27."""


def is_blocked() -> Optional[str]:
    """Canary: ONE cheap request to see whether PerimeterX still refuses us.

    Returns a reason string when blocked, None when the path looks open. This runs
    BEFORE any crawl so a scheduled probe costs a single request rather than
    charging into the block and refreshing our risk score — PX scores behaviour
    over time, so a blind monthly retry would keep the block alive rather than
    letting it decay."""
    try:
        html = _get(WINE_CATEGORY, timeout=25)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            body = ""
            try:
                body = e.read().decode("utf8", "ignore")[:400]
            except Exception:
                pass
            vendor = "PerimeterX" if "px-captcha" in body or "_pxAppId" in body else "unknown"
            return f"HTTP {e.code} ({vendor})"
        return f"HTTP {e.code}"
    except Exception as e:
        return f"{type(e).__name__}"
    if "px-captcha" in html[:2000]:
        return "px-captcha interstitial"
    return None


@dataclass
class TotalWineProduct:
    product_id: str
    name: str
    price: Optional[float]
    varietal: Optional[str]

    @property
    def upc(self) -> str:
        return f"totalwine-{self.product_id}"


def _titleize(slug: str) -> str:
    return " ".join(w.capitalize() for w in slug.split("-"))


def _varietal_from_url(url: str) -> Optional[str]:
    """Varietal from the product path: /wine/{colour}/{varietal}/…/{slug}/p/{id}.

    Segment 0 is the colour/category, segment 1 the varietal. A path with only a
    colour and a slug has no varietal — return None rather than mislabelling every
    such wine 'Red Wine'."""
    m = re.search(r"/wine/([a-z0-9\-/]+)/p/\d+", url or "")
    if not m:
        return None
    segs = [s for s in m.group(1).split("/") if s]
    if len(segs) < 3:          # colour + slug only -> no varietal to take
        return None
    return _titleize(segs[1])


def _itemlist(html: str) -> List[Dict[str, Any]]:
    for blk in re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            doc = json.loads(blk)
        except (json.JSONDecodeError, ValueError):
            continue
        if doc.get("@type") == "ItemList":
            return doc.get("itemListElement") or []
    return []


def _parse_products(html: str) -> List[TotalWineProduct]:
    """JSON-LD identity + the price inside each product's own tile."""
    anchors = []
    for item in _itemlist(html):
        url = item.get("url") or ""
        pid = re.search(r"/p/(\d+)", url)
        if not pid:
            continue
        path = re.sub(r"^https://www\.totalwine\.com", "", url)
        # hrefs carry a ?s={storeId} query string, so match the path plus that
        m = re.search(re.escape(path) + r"\?s=\d+", html)
        if m:
            anchors.append((m.start(), pid.group(1), item.get("name") or "", url))
    anchors.sort()

    out: List[TotalWineProduct] = []
    for i, (start, pid, name, url) in enumerate(anchors):
        end = anchors[i + 1][0] if i + 1 < len(anchors) else len(html)
        m = re.search(r'price__[a-f0-9]+">\$([0-9]+\.[0-9]{2})', html[start:end])
        out.append(TotalWineProduct(
            product_id=pid, name=name,
            price=float(m.group(1)) if m else None,
            varietal=_varietal_from_url(url)))
    return out


def _scoped_url(base: str, store_id: str, page_size: int, page: int = 1) -> str:
    sep = "&" if "?" in base else "?"
    url = f"{base}{sep}storeId={store_id}&pageSize={page_size}"
    return url if page <= 1 else f"{url}&page={page}"


def _assert_store(html: str, store_id: str) -> None:
    """Refuse a page that doesn't carry the requested store.

    Page chrome can still carry the 1108 default, so this checks the store is
    PRESENT rather than demanding it be the only one."""
    seen = set(re.findall(r'"storeId"\s*:\s*"?(\d{3,5})', html))
    if store_id not in seen:
        raise WrongStore(f"asked store {store_id}, page carries {sorted(seen) or 'none'}")


def _get(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf8", "ignore")


def total_results(store_id: str) -> Optional[int]:
    """How many wines the category claims for this store — lets pagination stop on a
    number rather than on a guess."""
    try:
        html = _get(_scoped_url(WINE_CATEGORY, store_id, _PAGE_SIZE))
        m = re.search(r'"totalResults"\s*:\s*(\d+)', html)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def fetch_page(store_id: str, page: int = 1, retries: int = 4,
               expect_products: bool = True) -> List[TotalWineProduct]:
    """One store-scoped page of the wine category.

    Retries an EMPTY result, not just errors. Total Wine intermittently renders a page
    without its JSON-LD — measured: page 2 empty while 1 and 3 returned 200 each; page 9
    empty, page 10 fine, page 11 empty. Those are flaky renders, NOT the end of the
    catalog, and treating them as terminal silently truncated a 5,947-wine category to
    596 rows. Raises WrongStore rather than returning another city's prices."""
    url = _scoped_url(WINE_CATEGORY, store_id, _PAGE_SIZE, page)
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            html = _get(url)
            _assert_store(html, store_id)
            products = _parse_products(html)
            if products or not expect_products:
                return products
            last = RuntimeError(f"page {page} rendered without products")
        except (WrongStore, urllib.error.HTTPError) as e:
            last = e
        if attempt < retries - 1:
            # short pause for a flaky render; long one only after a real block
            # empty page == throttle signal; wait properly rather than retry-storm
            time.sleep(_EMPTY_BACKOFF)
    if isinstance(last, RuntimeError):
        return []            # genuinely empty after retries — let the caller decide
    raise last if last else RuntimeError("fetch failed")


def load_cursor() -> Dict[str, Dict[str, Any]]:
    """Per-store crawl progress. A plain JSON file, not a table: this job only ever
    runs on the mini, and a local file avoids a prod migration for what is really
    just a bookmark. Swap for a table if it ever needs to run in two places."""
    try:
        return json.loads(_CURSOR_PATH.read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def save_cursor(cursor: Dict[str, Dict[str, Any]]) -> None:
    try:
        _CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CURSOR_PATH.write_text(json.dumps(cursor, indent=2, sort_keys=True))
    except OSError as e:
        print(f"    WARN: could not persist cursor ({e}) — next crawl restarts this store")


def _next_page(cursor: Dict[str, Dict[str, Any]], store_id: str, last_page: int) -> int:
    """Where the slow crawl resumes. Wraps to page 1 once a store is exhausted so a
    weekly job keeps prices fresh instead of stopping forever."""
    done = int((cursor.get(store_id) or {}).get("last_page", 0))
    return 1 if done >= last_page else done + 1


class TotalWineScraper(BaseScraper):
    """HTTP-only, store-scoped by URL. No browser (see module docstring)."""

    async def search_by_zip(self, zip_code: str) -> List[RetailInventoryItem]:
        store = next((sid for sid, s in TW_STORES.items() if s["zip"] == zip_code), None)
        if not store:
            return []
        return self._to_items(fetch_page(store, 1), store)

    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        items = await self.search_by_zip(zip_code)
        return [i for i in items if wine_name.lower() in (i.wine_name or "").lower()]

    def _to_items(self, products: List[TotalWineProduct], store_id: str
                  ) -> List[RetailInventoryItem]:
        s = TW_STORES[store_id]
        return [RetailInventoryItem(
            wine_name=p.name, retailer_name=RETAILER_NAME, zip_code=s["zip"],
            upc=p.upc, price=p.price, store_name=s["name"], store_id=store_id,
            address=s["address"], city=s["city"], state=s["state"],
            in_stock=True, varietal=p.varietal,
        ) for p in products if p.name and p.price is not None]

    async def run_full(self, store_ids: Optional[List[str]] = None,
                       mode: str = "seed") -> dict:
        """mode='seed'  -> first _SEED_PAGES per store, quickly (same-day coverage)
           mode='crawl' -> resume from the cursor, _CRAWL_PAGES slowly (weekly depth)

        A 403 or an empty streak ENDS THE STORE CLEANLY rather than failing the run:
        being throttled is the expected outcome of asking for a 5,947-wine catalog,
        and the cursor means the next run picks up exactly where this one stopped."""
        import uuid
        if mode not in ("seed", "crawl"):
            raise ValueError("mode must be 'seed' or 'crawl'")
        stores = store_ids or list(TW_STORES)
        pace = _SEED_PACE if mode == "seed" else _CRAWL_PACE
        budget = _SEED_PAGES if mode == "seed" else _CRAWL_PAGES
        cursor = load_cursor()

        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id, "retailer_name": RETAILER_NAME, "status": "running",
        }).execute()

        total, throttled = 0, []
        try:
            for store_id in stores:
                s_meta = TW_STORES[store_id]
                expected = total_results(store_id)
                if expected:
                    last_page = min(_MAX_PAGES, -(-expected // _PAGE_SIZE))
                else:
                    # throttled out of the count — reuse what we learned last time
                    last_page = int((cursor.get(store_id) or {}).get("total_pages") or _MAX_PAGES)
                start = 1 if mode == "seed" else _next_page(cursor, store_id, last_page)
                stop = min(last_page, start + budget - 1)
                print(f"\n  Store {store_id} — {s_meta['name']} [{mode}] "
                      f"pages {start}-{stop} of {last_page} ({expected} wines)", flush=True)

                seen_ids, empties, reached = set(), 0, start - 1
                for page in range(start, stop + 1):
                    try:
                        products = fetch_page(store_id, page)
                    except urllib.error.HTTPError as e:
                        if e.code in (403, 429):
                            print(f"    page {page}: {e.code} — throttled, stopping this "
                                  f"store (resume here next run)", flush=True)
                            throttled.append(store_id)
                            break
                        raise
                    if not products:
                        empties += 1
                        print(f"    page {page}: stripped page ({empties} in a row) — "
                              f"throttle signal, waiting {_EMPTY_BACKOFF:.0f}s", flush=True)
                        if empties >= 2:
                            throttled.append(store_id)
                            break              # back off for real; resume next run
                        time.sleep(_EMPTY_BACKOFF)
                        continue
                    empties = 0
                    fresh = [p for p in products if p.product_id not in seen_ids]
                    seen_ids.update(p.product_id for p in fresh)
                    items = self._to_items(fresh, store_id)
                    if items:
                        upc_to_id = self._upsert_wines(items)
                        self._upsert_stores(items)
                        self._upsert_inventory(items, upc_to_id)
                        total += len(items)
                    reached = page
                    print(f"    page {page}: {len(fresh)} products "
                          f"({len(items)} priced, total {total})", flush=True)
                    time.sleep(pace)

                if mode == "crawl" and reached >= start:
                    cursor[store_id] = {"last_page": reached, "total_pages": last_page,
                                        "updated": datetime.now(timezone.utc).isoformat()}
                    save_cursor(cursor)

            note = f" (throttled: {sorted(set(throttled))})" if throttled else ""
            self.supabase.table("scraper_runs").update({
                "status": "success", "records_updated": total,
                "error_message": f"[{mode}]{note}" if note else f"[{mode}]",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            return {"wines_committed": total, "stores": len(stores),
                    "mode": mode, "throttled": sorted(set(throttled))}

        except Exception as e:
            self.supabase.table("scraper_runs").update({
                "status": "failed", "records_updated": total,
                "error_message": f"[{mode}] [{total} rows committed before failure] {e}",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            raise
