"""
Spec's Wines, Spirits & Finer Foods — API feasibility probe.

Approach:
  1. Load Spec's wine pages with Playwright, intercept every non-asset
     network request — API calls surface here before any bot block
  2. Target: store locator, wine category browse, product detail
  3. Directly test guessed REST/GraphQL endpoint patterns with curl
  4. Capture screenshots + HTML for fallback analysis

Run from project root:
  python3 data/exploration/specs_probe.py
"""
import asyncio
import json
import subprocess
import re
from pathlib import Path
from playwright.async_api import async_playwright, Response

OUT_DIR = Path(__file__).parent / "specs_probe_output"
OUT_DIR.mkdir(exist_ok=True)

ZIP_CODE = "78209"
BASE = "https://www.specs.com"

# Pages to intercept — store locator, wine browse, and a product detail
BROWSE_URLS = [
    f"{BASE}/wines",
    f"{BASE}/wines?zip={ZIP_CODE}",
    f"{BASE}/store-locator?zip={ZIP_CODE}",
    f"{BASE}/stores?zip={ZIP_CODE}",
    f"{BASE}/wines/red-wine",
    f"{BASE}/wines/white-wine",
]

# Candidate endpoints to probe directly
CANDIDATE_ENDPOINTS = [
    # Store locator
    f"{BASE}/api/stores?zip={ZIP_CODE}",
    f"{BASE}/api/store/search?zip={ZIP_CODE}",
    f"{BASE}/api/v1/stores?zipCode={ZIP_CODE}",
    f"{BASE}/api/locations?zip={ZIP_CODE}",
    # Product / search
    f"{BASE}/api/products?category=wine&zip={ZIP_CODE}",
    f"{BASE}/api/search?q=wine&zip={ZIP_CODE}",
    f"{BASE}/api/v1/products/search?q=wine&zip={ZIP_CODE}",
    f"{BASE}/api/v2/search?query=wine&zip={ZIP_CODE}",
    f"{BASE}/api/catalog?category=wine&storeZip={ZIP_CODE}",
    # GraphQL
    f"{BASE}/graphql",
    f"{BASE}/api/graphql",
    # Algolia (common for retail search)
    f"{BASE}/api/algolia/search?q=wine",
    # Next.js / SSR data
    f"{BASE}/_next/data/wine-page.json",
]


def curl_probe(url: str, method: str = "GET", body: str = None, extra_headers: list = None) -> dict:
    cmd = [
        "curl", "-s", "-o", "-", "-w", "\n__STATUS__%{http_code}",
        "-X", method,
        "-H", "Accept: application/json, text/plain, */*",
        "-H", f"Referer: {BASE}/",
        "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "--max-time", "10",
    ]
    if body:
        cmd += ["-H", "Content-Type: application/json", "-d", body]
    if extra_headers:
        for h in extra_headers:
            cmd += ["-H", h]
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout
    status, resp_body = 0, output
    if "__STATUS__" in output:
        parts = output.rsplit("__STATUS__", 1)
        resp_body = parts[0].strip()
        try:
            status = int(parts[1].strip())
        except ValueError:
            pass
    return {"url": url, "method": method, "status": status, "body": resp_body}


async def intercept_browser_requests():
    captured = []
    pages_html = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        async def on_response(response: Response):
            url = response.url
            if any(skip in url for skip in [
                ".js", ".css", ".png", ".jpg", ".svg", ".woff", ".ico", ".gif",
                "google", "facebook", "doubleclick", "analytics", "hotjar",
                "cdn-cgi", "sentry", "datadog", "newrelic", "segment",
            ]):
                return
            try:
                content_type = response.headers.get("content-type", "")
                body_preview = ""
                if "json" in content_type:
                    body_preview = (await response.text())[:800]
                captured.append({
                    "method": response.request.method,
                    "url": url,
                    "status": response.status,
                    "content_type": content_type,
                    "body_preview": body_preview,
                    "request_headers": dict(response.request.headers),
                })
            except Exception:
                captured.append({
                    "method": response.request.method,
                    "url": url,
                    "status": response.status,
                    "content_type": "",
                    "body_preview": "",
                    "request_headers": {},
                })

        page.on("response", on_response)

        for url in BROWSE_URLS:
            print(f"   Loading: {url}")
            try:
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)
                # Scroll to trigger lazy-loaded product grids
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, window.innerHeight)")
                    await page.wait_for_timeout(1000)
                title = await page.title()
                print(f"   Title: {title}")
                pages_html[url] = await page.content()
            except Exception as e:
                print(f"   Error loading {url}: {e}")
                pages_html[url] = ""

        # Screenshot of the wine browse page
        await page.screenshot(path=str(OUT_DIR / "specs_wine_page.png"), full_page=True)
        await browser.close()

    return captured, pages_html


async def main():
    print("═" * 60)
    print("Spec's Wines — API Feasibility Probe")
    print("═" * 60)

    # ── Part 1: Intercept browser requests ────────────────────────────────────
    print("\n── Part 1: Intercepting network requests during page load\n")
    captured, pages_html = await intercept_browser_requests()

    print(f"\n   Captured {len(captured)} non-asset responses")

    # Classify API-looking calls
    api_calls = []
    for r in captured:
        url = r["url"]
        is_api = (
            "json" in r["content_type"]
            or any(kw in url.lower() for kw in [
                "/api/", "search", "product", "catalog", "store", "location",
                "inventory", "graphql", ".json", "algolia", "wine",
            ])
        )
        if is_api:
            api_calls.append(r)

    print(f"\n   API-looking responses ({len(api_calls)}):")
    for r in api_calls:
        has_data = "★" if r["body_preview"] else " "
        print(f"   {has_data} [{r['status']}] {r['method']} {r['url'][:110]}")
        if r["body_preview"]:
            print(f"         └─ {r['body_preview'][:200]}")

    (OUT_DIR / "intercepted.json").write_text(
        json.dumps(captured, indent=2, ensure_ascii=False)
    )
    print(f"\n   Full log → specs_probe_output/intercepted.json")

    # ── Part 2: HTML analysis ──────────────────────────────────────────────────
    print("\n── Part 2: Analyzing HTML structure for product data")
    for page_url, html in pages_html.items():
        if len(html) < 5000:
            print(f"\n   [{page_url}] HTML too small ({len(html)} bytes) — likely blocked or redirect")
            continue

        print(f"\n   [{page_url}] {len(html):,} bytes")

        # __NEXT_DATA__ (Next.js)
        next_data = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if next_data:
            print("   ★ __NEXT_DATA__ found (Next.js — product data likely embedded)")
            try:
                data = json.loads(next_data.group(1))
                slug = page_url.split("/")[-1] or "index"
                out_path = OUT_DIR / f"next_data_{slug}.json"
                out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                print(f"   Saved → specs_probe_output/{out_path.name}")
                print(f"   Preview: {json.dumps(data, indent=2)[:400]}")
            except Exception as e:
                print(f"   Could not parse __NEXT_DATA__: {e}")

        # JSON-LD structured data
        json_ld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
        if json_ld:
            print(f"   JSON-LD blocks: {len(json_ld)}")
            for i, block in enumerate(json_ld[:2]):
                try:
                    data = json.loads(block.strip())
                    print(f"   Block {i+1}: {json.dumps(data)[:300]}")
                except Exception:
                    pass

        # Product-related CSS classes (reveals frontend framework + data shape)
        all_classes = re.findall(r'class="([^"]+)"', html)
        freq: dict = {}
        for group in all_classes:
            for cls in group.split():
                freq[cls] = freq.get(cls, 0) + 1
        product_kws = ["product", "item", "card", "tile", "price", "wine",
                       "result", "listing", "sku", "bottle", "inventory"]
        relevant = {c: n for c, n in freq.items()
                    if any(kw in c.lower() for kw in product_kws)}
        if relevant:
            top = sorted(relevant.items(), key=lambda x: -x[1])[:15]
            print(f"   Product-related CSS classes:")
            for cls, count in top:
                print(f"     {count:4d}x  .{cls}")

        # Save HTML for manual inspection
        slug = re.sub(r'[^a-z0-9]', '_', page_url.lower())[-40:]
        (OUT_DIR / f"page_{slug}.html").write_text(html, encoding="utf-8")

    # ── Part 3: Direct endpoint probes ────────────────────────────────────────
    print("\n── Part 3: Direct endpoint probes with curl\n")
    probe_results = []

    for url in CANDIDATE_ENDPOINTS:
        r = curl_probe(url)
        body = r["body"]
        is_json = body.strip().startswith(("{", "["))
        indicator = (
            "★" if (r["status"] == 200 and is_json)
            else "✓" if r["status"] == 200
            else "→" if r["status"] in (301, 302, 308)
            else "✗"
        )
        print(f"   {indicator} {r['status']}  {url}")
        if is_json and r["status"] == 200:
            print(f"         └─ JSON: {body[:300]}")
        probe_results.append(r)

    # Also probe GraphQL with a basic introspection query
    print("\n   Testing GraphQL introspection...")
    gql_body = json.dumps({"query": "{ __typename }"})
    for gql_url in [f"{BASE}/graphql", f"{BASE}/api/graphql"]:
        r = curl_probe(gql_url, method="POST", body=gql_body)
        is_json = r["body"].strip().startswith(("{", "["))
        indicator = "★" if (r["status"] == 200 and is_json) else "✗"
        print(f"   {indicator} {r['status']} POST {gql_url}")
        if is_json:
            print(f"         └─ {r['body'][:200]}")
        probe_results.append(r)

    (OUT_DIR / "endpoint_probes.json").write_text(
        json.dumps(probe_results, indent=2, ensure_ascii=False)
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    json_hits = [r for r in probe_results if r["status"] == 200 and r["body"].strip().startswith(("{", "["))]
    browser_hits = [r for r in api_calls if r["body_preview"]]

    print("\n" + "═" * 60)
    print("SUMMARY")
    print("═" * 60)
    print(f"  Browser API calls with JSON body : {len(browser_hits)}")
    print(f"  Direct JSON endpoint hits        : {len(json_hits)}")
    if browser_hits:
        print("\n  Browser API hits:")
        for r in browser_hits:
            print(f"    ★ [{r['status']}] {r['url'][:100]}")
    if json_hits:
        print("\n  Direct endpoint hits:")
        for r in json_hits:
            print(f"    ★ {r['url']}")
    print(f"\n  Screenshot → specs_probe_output/specs_wine_page.png")
    print(f"  Full log   → specs_probe_output/intercepted.json")
    print("═" * 60)


asyncio.run(main())
