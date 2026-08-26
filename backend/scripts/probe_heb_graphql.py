"""One-off probe: is heb.com/graphql reachable from here?

H-E-B has returned "HTTP Error 502: Bad Gateway" from GitHub Actions on every
weekly run since at least 2026-07-19 (last success); Central Market (same
endpoint, different client header) returns 0 products every store in the same
window. CORRECTED 2026-08-25: this is NOT the datacenter-IP block first assumed — the
probe fails from residential IPs too (so the mini won't fix it). Root cause is
an Imperva Incapsula JavaScript challenge on the real product query (a light
query slips through with a primed cookie; the full-fields query gets a 502
`_Incapsula_Resource` JS-challenge page consistently). Full write-up +
fix options: data/exploration/heb_incapsula_findings.md.

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
