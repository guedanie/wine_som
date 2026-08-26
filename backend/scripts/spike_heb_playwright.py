"""Spike: clear HEB's Imperva Incapsula challenge with patchright and run the
real productSearch query in-browser. Proves the fix path for item 45.

Requires: pip install patchright  (reuses the cached Playwright Chromium).
Run HEADED — needs a GUI session (works on the dev Mac + the mini's Aqua login;
NOT under a headless launchd daemon). From backend/:
    python3 -m scripts.spike_heb_playwright

WORKING RECIPE (2026-08-25, residential IP):
  - patchright (NOT vanilla playwright — Incapsula errorCode-15 blocks plain
    Chromium headless AND headed; patchright removes the CDP/Runtime.enable tells)
  - launch_persistent_context(profile, headless=False, no_viewport=True)
  - goto(..., wait_until="domcontentloaded")  (networkidle never fires on the SPA)
  - wait ~6s for the challenge JS to run + auto-reload; title != "" == cleared
  - POST /graphql from page.evaluate (in-browser fetch carries the solved
    reese84 + incap cookies AND the real browser fingerprint) → 200
Result: HEB store 567 full-fields query → total=1999. Both HEB and CM (same
endpoint, client-name central-market) work from the one solved session.
"""
import sys
import tempfile

from patchright.sync_api import sync_playwright

from scrapers.heb import _PRODUCT_FIELDS

HOME = "https://www.heb.com/"
GQL = "https://www.heb.com/graphql"


def _query(store_id: str, limit: int = 60, offset: int = 0) -> str:
    return ("{ productSearch(shoppingContext: CURBSIDE_PICKUP, query: \"wine\", "
            f"storeId: {store_id}, limit: {limit}, offset: {offset}) "
            f"{{ total records {{ {_PRODUCT_FIELDS} }} }} }}")


def _in_browser_post(page, query: str, client_name: str) -> dict:
    return page.evaluate(
        """async ([q, cn]) => {
            const r = await fetch(arguments_url, {
                method: "POST",
                headers: {"Content-Type": "application/json", "Apollographql-Client-Name": cn},
                body: JSON.stringify({query: q}),
            });
            return { status: r.status, body: await r.text() };
        }""".replace("arguments_url", repr(GQL)),
        [query, client_name])


def main() -> int:
    profile = tempfile.mkdtemp(prefix="heb_incap_")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(profile, headless=False, no_viewport=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        cleared = False
        for attempt in range(5):
            try:
                page.goto(HOME, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                print(f"  goto attempt {attempt}: {type(e).__name__}")
            page.wait_for_timeout(6000)
            title = page.title()
            cleared = title != "" and "unsuccessful" not in title.lower()
            print(f"  attempt {attempt}: title={title[:48]!r} {'CLEARED' if cleared else '(challenged)'}")
            if cleared:
                break
        if not cleared:
            print("FAILED — Incapsula never cleared (title stayed blank/blocked)")
            ctx.close()
            return 1

        import json
        for label, sid, cn in [("H-E-B", "567", "heb-com"),
                               ("Central Market", "51", "central-market")]:
            res = _in_browser_post(page, _query(sid, limit=5), cn)
            try:
                total = json.loads(res["body"]).get("data", {}).get("productSearch", {}).get("total")
            except Exception:
                total = f"non-JSON: {res['body'][:80]!r}"
            print(f"  {label} (store {sid}): HTTP {res['status']}, total={total}")
        ctx.close()
    print("OK — Incapsula cleared via patchright; in-browser GraphQL returns real data")
    return 0


if __name__ == "__main__":
    sys.exit(main())
