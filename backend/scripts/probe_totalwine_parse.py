"""Total Wine catalog extractor — PROTOTYPE / feasibility probe (item 46).

Answers the last open question from `data/exploration/totalwine_findings.md`:
can we get product identity + price, scoped to a real Texas store, over plain HTTP?
Yes — with one non-negotiable guard.

TWO THINGS THIS ENCODES, both learned the hard way:

1. **Identity comes from JSON-LD, not the DOM.** Each category page carries a
   `<script data-rh="true" type="application/ld+json">` block with an `ItemList` of 24
   products, each with a canonical `url` (→ `/p/{productId}`) and `name`. The CSS-module
   class names in the markup are content-hashed (`price__ff218822`) and will churn on
   every Total Wine frontend build, so they are used ONLY to find the price *within* a
   tile whose boundaries were established from the JSON-LD anchors.

2. **Scope with `?storeId=` in the URL, NOT the cookie.** The cookie
   (`twm-userStoreInformation`) works but is silently dropped under load: Total Wine then
   serves the DEFAULT California store (1108) at 200 with no error — measured 8/8 correct
   when paced, 4/4 wrong right after a burst, correct again after 120s. The default is
   hard-coded, not geographic (a San Antonio residential IP with no cookie still gets
   Sacramento).

   `?storeId={id}` on the category URL scopes the same 24 products and reproduces every
   known price delta (Olema $12.99 vs $15.99, Caymus $68.99 vs $66.97, Mina Mesa $12.99
   vs $10.99 — 8 of 24 differ, identical to the cookie method). Because the store is in
   the URL it is part of the cache key, so a `?storeId=503` request structurally cannot be
   served a Sacramento response. Note `?s=` does NOT work here (it scopes product detail
   pages only), and the page still carries some unpersonalised `1108` chrome — so the
   guard below checks the store appears in the PRODUCT data rather than demanding 1108 be
   absent.

NOT a production scraper: no upserts, no store registry, no pagination beyond one page.
Run from backend/:
    python3 -m scripts.probe_totalwine_parse
"""
import json
import re
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
_CATEGORY = "https://www.totalwine.com/wine/c/c0020"

# Confirmed San Antonio stores, harvested via local_delivery_pages_sitemap.xml ->
# alcohol-delivery-near-me-San-Antonio-Texas -> /store-info/{state-city}/{id}
SA_STORES = {"503": "San Antonio Del Norte", "504": "San Antonio The Rim", "520": "Forum"}

_PACE_SECONDS = 8.0       # measured: bursts get silently de-scoped; pace, don't retry-storm
_BACKOFF_SECONDS = 120.0  # measured: a 120s pause restored correct scoping


class WrongStore(Exception):
    """The page came back scoped to a store we did not ask for."""


def _store_cookie(store_id: str, state: str) -> str:
    return (f"twm-userStoreInformation=ispStore~{store_id}:ifcStore~{store_id}"
            f"@ifcStoreState~{state}@method~INSTORE_PICKUP")


def _echoed_stores(html: str) -> set:
    return set(re.findall(r'"storeId"\s*:\s*"?(\d{3,5})', html))


def fetch_scoped(url: str, store_id: str, state: str, retries: int = 3) -> str:
    """GET `url` scoped to `store_id` via the URL, REFUSING any response that isn't.

    Store goes in the query string (cache-key safe); the cookie is sent too as a belt-and-
    braces measure. Raises WrongStore rather than returning plausible wrong-city data."""
    sep = "&" if "?" in url else "?"
    scoped = f"{url}{sep}storeId={store_id}"
    seen = set()
    for attempt in range(retries):
        req = urllib.request.Request(
            scoped, headers={"User-Agent": _UA, "Cookie": _store_cookie(store_id, state)})
        html = urllib.request.urlopen(req, timeout=35).read().decode("utf8", "ignore")
        seen = _echoed_stores(html)
        if store_id in seen:          # page chrome may still carry the 1108 default
            return html
        if attempt < retries - 1:
            print(f"    de-scoped (got {sorted(seen)}), backing off {_BACKOFF_SECONDS:.0f}s…")
            time.sleep(_BACKOFF_SECONDS)
    raise WrongStore(f"asked {store_id}, got {sorted(seen)} after {retries} attempts")


def _itemlist(html: str) -> List[Dict[str, Any]]:
    """The JSON-LD ItemList — canonical product identity for the page."""
    for blk in re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            doc = json.loads(blk)
        except (json.JSONDecodeError, ValueError):
            continue
        if doc.get("@type") == "ItemList":
            return doc.get("itemListElement") or []
    return []


def parse_products(html: str) -> List[Dict[str, Any]]:
    """Pair JSON-LD identity with the price rendered inside each product's tile.

    Tile boundaries come from where each product's canonical path appears as an
    `href` (it carries a `?s={storeId}` query string, which is why an exact-path
    match finds nothing). The price is then the first `price__*` in that span."""
    anchors: List[Tuple[int, str, str]] = []
    for item in _itemlist(html):
        url = item.get("url") or ""
        pid = re.search(r"/p/(\d+)", url)
        if not pid:
            continue
        path = re.sub(r"^https://www\.totalwine\.com", "", url)
        m = re.search(re.escape(path) + r"\?s=\d+", html)
        if m:
            anchors.append((m.start(), pid.group(1), item.get("name") or ""))
    anchors.sort()

    rows: List[Dict[str, Any]] = []
    for i, (start, pid, name) in enumerate(anchors):
        end = anchors[i + 1][0] if i + 1 < len(anchors) else len(html)
        m = re.search(r'price__[a-f0-9]+">\$([0-9]+\.[0-9]{2})', html[start:end])
        rows.append({"product_id": pid, "name": name,
                     "price": float(m.group(1)) if m else None})
    return rows


def main() -> None:
    results = {}
    for i, (store_id, label) in enumerate(list(SA_STORES.items())[:2] + [("1108", "CA Sacramento (control)")]):
        state = "US-CA" if store_id == "1108" else "US-TX"
        if i:
            time.sleep(_PACE_SECONDS)
        print(f"{label} (store {store_id})…")
        try:
            html = fetch_scoped(_CATEGORY, store_id, state)
        except WrongStore as e:
            print(f"    REFUSED: {e}")
            continue
        rows = parse_products(html)
        priced = [r for r in rows if r["price"] is not None]
        print(f"    {len(rows)} products, {len(priced)} priced")
        for r in rows[:3]:
            print(f"      {r['product_id']}  ${r['price']}  {r['name'][:46]}")
        results[store_id] = {r["product_id"]: r["price"] for r in rows}

    # The whole point: do the same products cost different amounts per store?
    if "503" in results and "1108" in results:
        shared = set(results["503"]) & set(results["1108"])
        diff = [p for p in shared if results["503"][p] != results["1108"][p]]
        print(f"\nproducts on both pages: {len(shared)} | priced differently: {len(diff)}")
        for p in list(diff)[:5]:
            print(f"  {p}: SA ${results['503'][p]}  vs  CA ${results['1108'][p]}")


if __name__ == "__main__":
    main()
