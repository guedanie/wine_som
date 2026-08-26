"""Live acceptance for the HEB/CM Incapsula browser-session fix (item 45).
Run from backend/ (HEADED — needs a GUI session): python3 -m scripts.verify_heb_session

Exercises the real code path INSIDE an asyncio loop (how run_full calls it): the
patchright session solves Incapsula once on a worker thread, and fetch_wine_page /
fetch_cm_wine_page return parsed wines. Also probes the configured CM_STORES so a
stale store id (61 → 0) is caught."""
import asyncio

from scrapers.heb import fetch_wine_page, _session
from scrapers.central_market import fetch_cm_wine_page, CM_STORES


async def run() -> None:
    print("HEB store 567 (San Antonio-adjacent canonical)…")
    total, products = fetch_wine_page(offset=0, limit=60, store_id="567")
    assert total > 0 and products, "HEB returned no wines — Incapsula not cleared?"
    print(f"  total={total}, page1 parsed={len(products)}, "
          f"e.g. {products[0].name[:44]!r} ${products[0].price}")
    _t2, page2 = fetch_wine_page(offset=60, limit=60, store_id="567")
    print(f"  page2 parsed={len(page2)} (one solved session reused across pages)")

    print("Central Market configured stores…")
    for sid, meta in CM_STORES.items():
        ct, cp = fetch_cm_wine_page(offset=0, limit=5, store_id=sid)
        flag = "  <-- returns 0, revisit id" if ct == 0 else ""
        print(f"  store {sid} {meta['name'][:26]:26s} total={ct}{flag}")

    print("OK — HEB/CM GraphQL restored via the Incapsula-solving browser session")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    finally:
        _session().close()
