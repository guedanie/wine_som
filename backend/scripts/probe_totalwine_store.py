"""Exploration probe: how does totalwine.com select a store, and where are the
store ids? (see data/exploration/totalwine_findings.md §4 — the real blocker).

Reading the storefront needs no challenge-solving, so this uses a browser purely
to WATCH: it logs every XHR/fetch the store-finder fires and diffs cookies +
localStorage across a store selection. That names the mechanism in one run
instead of guessing cookie names.

Uses its OWN profile dir so it can't disturb the H-E-B Incapsula session.
Run from backend/ (HEADED — needs a GUI session):
    python3 -m scripts.probe_totalwine_store
"""
import json
import os
import tempfile

_PROFILE = os.path.join(tempfile.gettempdir(), "totalwine_probe_profile")
_HOME = "https://www.totalwine.com/store-finder"
_INTERESTING = ("store", "location", "api", "search", "graphql")


def _state(page):
    """Cookies + localStorage as comparable dicts."""
    cookies = {c["name"]: c["value"] for c in page.context.cookies()}
    try:
        ls = page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
    except Exception:
        ls = {}
    return cookies, ls


def _diff(label, before, after):
    added = {k: v for k, v in after.items() if k not in before}
    changed = {k: (before[k], v) for k, v in after.items()
               if k in before and before[k] != v}
    print(f"  {label}: +{len(added)} new, {len(changed)} changed")
    for k, v in list(added.items())[:12]:
        print(f"    + {k} = {str(v)[:90]}")
    for k, (o, n) in list(changed.items())[:12]:
        print(f"    ~ {k}: {str(o)[:38]} -> {str(n)[:38]}")


def main() -> None:
    from patchright.sync_api import sync_playwright

    calls = []
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            _PROFILE, headless=False, no_viewport=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(res):
            u = res.url
            if any(t in u.lower() for t in _INTERESTING) and "totalwine.com" in u:
                if not any(u.endswith(x) for x in (".js", ".css", ".svg", ".png", ".woff2")):
                    calls.append((res.status, res.request.method, u))

        page.on("response", on_response)

        print("Loading the store finder…")
        page.goto(_HOME, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        ck_before, ls_before = _state(page)
        print(f"  baseline: {len(ck_before)} cookies, {len(ls_before)} localStorage keys")

        # Ask the finder for San Antonio. Selector is best-effort across markup
        # changes — any visible text/search input on the page will do.
        print("Searching for San Antonio, TX…")
        typed = False
        for sel in ('input[type="search"]', 'input[name*="earch" i]',
                    'input[placeholder*="zip" i]', 'input[placeholder*="city" i]',
                    'input[type="text"]'):
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=2500):
                    el.click()
                    el.fill("78209")
                    page.keyboard.press("Enter")
                    typed = True
                    print(f"  typed into {sel!r}")
                    break
            except Exception:
                continue
        if not typed:
            print("  !! no search input found — markup may have changed")
        page.wait_for_timeout(9000)

        ck_after, ls_after = _state(page)
        print("\nState diff across the search:")
        _diff("cookies", ck_before, ck_after)
        _diff("localStorage", ls_before, ls_after)

        print(f"\nNetwork calls captured ({len(calls)}):")
        seen = set()
        for status, method, u in calls:
            key = u.split("?")[0]
            if key in seen:
                continue
            seen.add(key)
            print(f"  {status} {method} {u[:150]}")

        # Anything on the page that looks like a Texas store id
        html = page.content()
        import re
        tx = re.findall(r'\{[^{}]{0,120}?"(?:storeId|storeNumber)"\s*:\s*"?(\d{3,5})"?[^{}]{0,160}\}', html)
        print(f"\nstore-id-shaped objects in DOM: {len(tx)} | sample: {sorted(set(tx))[:12]}")
        print("SA mentions in DOM:", len(re.findall(r"San Antonio", html)))

        ctx.close()


if __name__ == "__main__":
    main()
