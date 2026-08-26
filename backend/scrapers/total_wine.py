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
from typing import Any, Dict, List, Optional

from scrapers.base import BaseScraper, RetailInventoryItem

RETAILER_NAME = "Total Wine & More"
WINE_CATEGORY = "https://www.totalwine.com/wine/c/c0020"

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

_PAGE_SIZE = 200          # measured ceiling that still returns cleanly (3.3 MB/page)
_PACE_SECONDS = 5.0       # measured: ~10 rapid requests trips a 403
_BACKOFF_SECONDS = 120.0  # measured: a 120s pause restores correct behaviour
_MAX_PAGES = 60           # 5,947 wines / 200 ≈ 30; cap guards a pagination bug
_MAX_EMPTY = 3            # a single empty page is transient, not the end (measured:
                          # page 2 returned 0 while pages 1 and 3 returned 200 each)

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
            time.sleep(_PACE_SECONDS if isinstance(last, RuntimeError) else _BACKOFF_SECONDS)
    if isinstance(last, RuntimeError):
        return []            # genuinely empty after retries — let the caller decide
    raise last if last else RuntimeError("fetch failed")


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

    async def run_full(self, store_ids: Optional[List[str]] = None) -> dict:
        import uuid
        stores = store_ids or list(TW_STORES)
        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id, "retailer_name": RETAILER_NAME, "status": "running",
        }).execute()

        total = 0
        try:
            for store_id in stores:
                s = TW_STORES[store_id]
                print(f"\n  Store {store_id} — {s['name']}")
                expected = total_results(store_id)
                # Iterate the page count the catalog implies rather than guessing at an
                # end sentinel — empty pages here are flaky renders, not termination.
                last_page = (min(_MAX_PAGES, -(-expected // _PAGE_SIZE))
                             if expected else _MAX_PAGES)
                print(f"    catalog claims {expected} wines -> {last_page} pages", flush=True)
                seen_ids = set()
                empty_streak = 0
                for page in range(1, last_page + 1):
                    products = fetch_page(store_id, page)
                    fresh = [p for p in products if p.product_id not in seen_ids]
                    if not fresh:
                        # ONE empty page is transient (a page whose JSON-LD didn't
                        # render), not the end of the catalog — measured: page 2 gave 0
                        # while pages 1 and 3 each gave 200. Only stop on a streak.
                        empty_streak += 1
                        print(f"    page {page}: still empty after retries "
                              f"({empty_streak} in a row)", flush=True)
                        time.sleep(_PACE_SECONDS)
                        continue          # keep going — the page count is known
                    empty_streak = 0
                    seen_ids.update(p.product_id for p in fresh)
                    items = self._to_items(fresh, store_id)
                    if items:
                        upc_to_id = self._upsert_wines(items)
                        self._upsert_stores(items)
                        self._upsert_inventory(items, upc_to_id)
                        total += len(items)
                    print(f"    page {page}: {len(fresh)} products "
                          f"({len(items)} priced, total {total})", flush=True)
                    if expected and len(seen_ids) >= expected:
                        break
                    time.sleep(_PACE_SECONDS)

            self.supabase.table("scraper_runs").update({
                "status": "success", "records_updated": total,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            return {"wines_committed": total, "stores": len(stores)}

        except Exception as e:
            # Record what landed — commits are per page, so a mid-run failure still
            # leaves real inventory behind (the lesson from item 45's first live run).
            self.supabase.table("scraper_runs").update({
                "status": "failed", "records_updated": total,
                "error_message": f"[{total} rows committed before failure] {e}",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            raise
