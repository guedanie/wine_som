"""One-off probe: is heb.com/graphql reachable from here?

H-E-B has returned "HTTP Error 502: Bad Gateway" from GitHub Actions on every
weekly run since at least 2026-07-19 (last success); Central Market (same
endpoint, different client header) returns 0 products every store in the same
window. Matches the pattern already seen with Spec's/Twin Liquors/Vivino —
datacenter IPs blocked, residential IPs fine. This probe calls the real
scraper code (not a simplified reimplementation) from wherever it's run, so a
clean result here on a residential IP (e.g. the mac mini) is strong evidence
of an IP block rather than a broken query/schema change.

Run from backend/:
    python3 -m scripts.probe_heb_graphql
"""
import sys

from scrapers.heb import fetch_wine_page
from scrapers.central_market import fetch_cm_wine_page


def main() -> None:
    print("Probing H-E-B GraphQL (store 567, offset 0, limit 5)...")
    try:
        total, products = fetch_wine_page(offset=0, limit=5, store_id="567")
        print(f"  H-E-B: OK — server_total={total}, parsed={len(products)} products")
        for p in products[:3]:
            print(f"    - {p.name!r} (${p.price})")
    except Exception as e:
        print(f"  H-E-B: FAILED — {type(e).__name__}: {e}")

    print("\nProbing Central Market GraphQL (store 61, offset 0, limit 5)...")
    try:
        total, products = fetch_cm_wine_page(offset=0, limit=5, store_id="61")
        print(f"  Central Market: OK — server_total={total}, parsed={len(products)} products")
        for p in products[:3]:
            print(f"    - {p.name!r} (${p.price})")
    except Exception as e:
        print(f"  Central Market: FAILED — {type(e).__name__}: {e}")


if __name__ == "__main__":
    sys.exit(main())
