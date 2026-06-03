"""
HEB mobile/app API feasibility probe.

Two-pronged approach:
  1. Intercept every network request Playwright fires while loading HEB pages
     — API calls to internal endpoints happen BEFORE Cloudflare blocks the
     page render, so we can capture the URLs even on blocked pages.
  2. Try known HEB API endpoint patterns directly via curl (no browser needed).

Run from project root:
  python3 data/exploration/heb_api_probe.py
"""
import asyncio
import json
import subprocess
import re
from pathlib import Path
from playwright.async_api import async_playwright, Request

OUT_DIR = Path(__file__).parent / "heb_probe_output"
OUT_DIR.mkdir(exist_ok=True)

ZIP_CODE = "78209"

# ── Known / guessed HEB API endpoint patterns ─────────────────────────────────
# Derived from common patterns for grocery chain apps + HEB-specific guesses
CANDIDATE_ENDPOINTS = [
    # Search / product catalog
    "https://www.heb.com/commerce-api/v1/product/search?q=wine&store=78209",
    "https://www.heb.com/commerce-api/v1/search?q=wine&zip=78209",
    "https://api.heb.com/v1/products?q=wine&zip=78209",
    "https://api.heb.com/commerce/v1/search?query=wine",
    "https://www.heb.com/api/v1/products/search?query=wine",
    # Store lookup by zip
    "https://www.heb.com/commerce-api/v1/store/search?zip=78209",
    "https://api.heb.com/v1/stores?zip=78209",
    "https://www.heb.com/api/v1/stores?zipCode=78209",
    "https://www.heb.com/commerce-api/v1/store/list?zipCode=78209&radius=10",
    # Mobile app endpoints (common patterns from grocery apps)
    "https://mobile.heb.com/api/v1/search?q=wine",
    "https://api.heb.com/mobile/v1/products?category=wine",
]

BROWSER_PAGES = [
    "https://www.heb.com/search/?q=wine",
    "https://www.heb.com/product-category/beverages/wine",
]


def curl_get(url: str) -> dict:
    """Try a URL with curl and return status + first 500 chars of body."""
    result = subprocess.run(
        ["curl", "-s", "-o", "-", "-w", "\n__STATUS__%{http_code}",
         "-H", "Accept: application/json",
         "-H", "User-Agent: HEB/7.0 (iPhone; iOS 16.0; Scale/3.00)",
         "-H", "x-app-version: 7.0.0",
         "--max-time", "8",
         url],
        capture_output=True, text=True
    )
    output = result.stdout
    status = 0
    if "__STATUS__" in output:
        parts = output.rsplit("__STATUS__", 1)
        body = parts[0].strip()
        try:
            status = int(parts[1].strip())
        except ValueError:
            pass
    else:
        body = output
    return {"url": url, "status": status, "body": body[:600]}


async def intercept_requests():
    """
    Load HEB pages with Playwright and capture every network request.
    API calls fire early — before Cloudflare serves the block page —
    so we catch internal endpoint URLs in the request log.
    """
    captured = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},  # iPhone 14 dimensions
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Mobile/15E148 HEB/7.0"
            ),
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "x-app-version": "7.0.0",
            },
        )
        page = await context.new_page()

        def on_request(request: Request):
            url = request.url
            # Skip static assets — we only care about data/API calls
            if any(ext in url for ext in [
                ".js", ".css", ".png", ".jpg", ".svg", ".woff",
                ".ico", ".gif", "analytics", "tracking", "google",
                "facebook", "cdn-cgi",
            ]):
                return
            captured.append({
                "method": request.method,
                "url": url,
                "resource_type": request.resource_type,
            })

        page.on("request", on_request)

        for url in BROWSER_PAGES:
            print(f"   Loading: {url}")
            try:
                await page.goto(url, timeout=20000, wait_until="domcontentloaded")
            except Exception:
                pass
            await page.wait_for_timeout(4000)

        await browser.close()

    return captured


async def main():
    print("═" * 60)
    print("HEB API Feasibility Probe")
    print("═" * 60)

    # ── Part 1: Intercept browser requests ────────────────────────────────────
    print("\n── Part 1: Intercepting network requests during page load")
    print("   (loading pages with a mobile User-Agent to trigger app-style API calls)\n")

    captured = await intercept_requests()

    print(f"\n   Captured {len(captured)} non-asset requests:")
    api_looking = []
    for req in captured:
        url = req["url"]
        # Flag anything that looks like an API/data call
        is_api = any(kw in url for kw in [
            "/api/", "commerce", "search", "product", "store",
            "catalog", "inventory", "graphql", ".json",
        ])
        flag = "  ★ API" if is_api else "     "
        print(f"   {flag}  [{req['method']}] {url[:120]}")
        if is_api:
            api_looking.append(req)

    (OUT_DIR / "intercepted_requests.json").write_text(
        json.dumps(captured, indent=2)
    )
    print(f"\n   Full request log → heb_probe_output/intercepted_requests.json")

    # ── Part 2: Probe known endpoint patterns directly ─────────────────────────
    print("\n── Part 2: Probing candidate API endpoints directly with curl")
    print("   (using HEB iOS app User-Agent)\n")

    results = []
    for url in CANDIDATE_ENDPOINTS:
        r = curl_get(url)
        status = r["status"]
        snippet = r["body"][:120].replace("\n", " ")
        indicator = "✓" if status in (200, 201) else ("→" if status in (301, 302, 307, 308) else "✗")
        print(f"   {indicator} {status}  {url}")
        if status == 200:
            print(f"          Body: {snippet}")
        results.append(r)

    (OUT_DIR / "api_probe_results.json").write_text(
        json.dumps(results, indent=2)
    )
    print(f"\n   Full probe results → heb_probe_output/api_probe_results.json")

    # ── Summary ───────────────────────────────────────────────────────────────
    hits = [r for r in results if r["status"] == 200]
    print("\n═" * 60)
    if hits:
        print(f"  ACCESSIBLE ENDPOINTS FOUND: {len(hits)}")
        for h in hits:
            print(f"  ✓ {h['url']}")
            print(f"    {h['body'][:200]}")
    else:
        print("  No direct API endpoints responded with 200.")
        if api_looking:
            print(f"\n  But {len(api_looking)} API-looking URLs were observed in browser requests.")
            print("  These may require auth headers — check intercepted_requests.json")
        else:
            print("  HEB may rely entirely on session-authenticated endpoints.")
    print("═" * 60)


asyncio.run(main())
