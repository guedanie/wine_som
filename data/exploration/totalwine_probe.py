"""
Total Wine & More API feasibility probe.

Approach:
  1. Load Total Wine wine search pages with Playwright, intercept every
     non-asset network request — API calls show up here before any bot block
  2. Directly test guessed REST and search API endpoint patterns with curl
  3. Capture screenshots + raw HTML to assess scrapeability as fallback

Run from project root:
  python3 data/exploration/totalwine_probe.py
"""
import asyncio
import json
import subprocess
import re
from pathlib import Path
from playwright.async_api import async_playwright, Response

OUT_DIR = Path(__file__).parent / "totalwine_probe_output"
OUT_DIR.mkdir(exist_ok=True)

ZIP_CODE = "78209"

SEARCH_URLS = [
    "https://www.totalwine.com/search/white-page?text=cabernet+sauvignon&sta=TX",
    "https://www.totalwine.com/wine/red-wine/cabernet-sauvignon/l/1484",
    "https://www.totalwine.com/store/tx/san-antonio",
]

# Endpoint patterns to probe directly
CANDIDATE_ENDPOINTS = [
    # REST search
    f"https://www.totalwine.com/api/products/search?q=wine&zip={ZIP_CODE}",
    f"https://www.totalwine.com/api/search?q=wine&storeNumber=&zip={ZIP_CODE}",
    f"https://www.totalwine.com/search/api?q=wine&zip={ZIP_CODE}",
    # Algolia (common for retail search)
    f"https://www.totalwine.com/api/2.0/page/facets/wine/en/US",
    # Store lookup
    f"https://www.totalwine.com/api/store/byzip?zip={ZIP_CODE}",
    f"https://www.totalwine.com/api/stores?zipCode={ZIP_CODE}",
    f"https://www.totalwine.com/api/2.0/store/search?zip={ZIP_CODE}",
    # Product API
    f"https://www.totalwine.com/api/product/search?query=wine&zip={ZIP_CODE}&pageSize=5",
    f"https://www.totalwine.com/api/2.0/products?category=wine&zip={ZIP_CODE}",
    f"https://www.totalwine.com/catalog/search?q=wine&zip={ZIP_CODE}&format=json",
]


def curl_probe(url: str, extra_headers: list = None) -> dict:
    cmd = [
        "curl", "-s", "-o", "-", "-w", "\n__STATUS__%{http_code}",
        "-H", "Accept: application/json, text/plain, */*",
        "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "-H", "Referer: https://www.totalwine.com/",
        "--max-time", "10",
    ]
    if extra_headers:
        for h in extra_headers:
            cmd += ["-H", h]
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout
    status, body = 0, output
    if "__STATUS__" in output:
        parts = output.rsplit("__STATUS__", 1)
        body = parts[0].strip()
        try:
            status = int(parts[1].strip())
        except ValueError:
            pass
    return {"url": url, "status": status, "body": body}


async def intercept_browser_requests():
    captured = []
    html_on_success = ""

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
                ".js", ".css", ".png", ".jpg", ".svg", ".woff", ".ico",
                "google", "facebook", "doubleclick", "analytics",
                "cdn-cgi", "sentry", "datadog", "newrelic",
            ]):
                return
            try:
                content_type = response.headers.get("content-type", "")
                body_preview = ""
                if "json" in content_type:
                    body_preview = (await response.text())[:500]
                captured.append({
                    "method": response.request.method,
                    "url": url,
                    "status": response.status,
                    "content_type": content_type,
                    "body_preview": body_preview,
                })
            except Exception:
                captured.append({
                    "method": response.request.method,
                    "url": url,
                    "status": response.status,
                    "content_type": "",
                    "body_preview": "",
                })

        page.on("response", on_response)

        for url in SEARCH_URLS:
            print(f"   Loading: {url}")
            try:
                await page.goto(url, timeout=25000, wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)
                # Scroll to trigger lazy loads
                for _ in range(2):
                    await page.evaluate("window.scrollBy(0, window.innerHeight)")
                    await page.wait_for_timeout(1000)
                title = await page.title()
                print(f"   Title: {title}")
            except Exception as e:
                print(f"   Error: {e}")

        # Screenshot + HTML from last page
        await page.screenshot(path=str(OUT_DIR / "totalwine_page.png"))
        html_on_success = await page.content()
        (OUT_DIR / "totalwine_page.html").write_text(html_on_success, encoding="utf-8")

        await browser.close()

    return captured, html_on_success


async def main():
    print("═" * 60)
    print("Total Wine & More API Feasibility Probe")
    print("═" * 60)

    # ── Part 1: Intercept browser requests ────────────────────────────────────
    print("\n── Part 1: Intercepting network requests during page load\n")
    captured, html = await intercept_browser_requests()

    print(f"\n   Captured {len(captured)} non-asset responses")
    print(f"   HTML size: {len(html):,} bytes")

    # Classify responses
    api_calls = []
    for r in captured:
        url = r["url"]
        is_api = (
            "json" in r["content_type"]
            or any(kw in url for kw in [
                "/api/", "search", "product", "catalog", "store",
                "inventory", "graphql", ".json", "algolia",
            ])
        )
        if is_api:
            api_calls.append(r)

    print(f"\n   API-looking responses ({len(api_calls)}):")
    for r in api_calls:
        has_data = "★" if r["body_preview"] else " "
        print(f"   {has_data} [{r['status']}] {r['method']} {r['url'][:110]}")
        if r["body_preview"]:
            print(f"         └─ {r['body_preview'][:120]}")

    (OUT_DIR / "intercepted.json").write_text(json.dumps(captured, indent=2))
    print(f"\n   Full log → totalwine_probe_output/intercepted.json")

    # ── Part 2: HTML structure analysis ───────────────────────────────────────
    print("\n── Part 2: Analyzing HTML structure for product data")
    if len(html) > 10000:
        # Find product-related class names
        all_classes = re.findall(r'class="([^"]+)"', html)
        freq = {}
        for group in all_classes:
            for cls in group.split():
                freq[cls] = freq.get(cls, 0) + 1

        product_kws = ["product", "item", "card", "tile", "price", "name",
                       "wine", "result", "listing", "sku", "rating"]
        relevant = {c: n for c, n in freq.items()
                    if any(kw in c.lower() for kw in product_kws)}
        print(f"\n   Product-related CSS classes found ({len(relevant)}):")
        for cls, count in sorted(relevant.items(), key=lambda x: -x[1])[:30]:
            print(f"     {count:4d}x  .{cls}")

        # Look for JSON-LD or embedded data
        json_ld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
        if json_ld:
            print(f"\n   JSON-LD blocks found: {len(json_ld)}")
            for i, block in enumerate(json_ld[:2]):
                try:
                    data = json.loads(block.strip())
                    print(f"   Block {i+1}: {json.dumps(data, indent=2)[:300]}")
                except Exception:
                    pass

        # Look for __NEXT_DATA__ or window.__STATE__ (common in Next.js / React apps)
        next_data = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if next_data:
            print("\n   ★ __NEXT_DATA__ found (Next.js app — product data likely embedded)")
            try:
                data = json.loads(next_data.group(1))
                preview = json.dumps(data, indent=2)[:600]
                print(f"   {preview}")
                (OUT_DIR / "next_data.json").write_text(
                    json.dumps(data, indent=2, ensure_ascii=False)
                )
                print("   Saved → totalwine_probe_output/next_data.json")
            except Exception as e:
                print(f"   Could not parse: {e}")
    else:
        print(f"   HTML too small ({len(html)} bytes) — likely bot-blocked")

    # ── Part 3: Direct endpoint probes ────────────────────────────────────────
    print("\n── Part 3: Direct endpoint probes with curl\n")
    results = []
    for url in CANDIDATE_ENDPOINTS:
        r = curl_probe(url)
        status = r["status"]
        body = r["body"]
        is_json = body.strip().startswith(("{", "["))
        indicator = "★" if (status == 200 and is_json) else ("✓" if status == 200 else ("→" if status in (301, 302, 308) else "✗"))
        print(f"   {indicator} {status}  {url}")
        if is_json and status == 200:
            print(f"         └─ JSON: {body[:200]}")
        results.append(r)

    (OUT_DIR / "endpoint_probes.json").write_text(json.dumps(results, indent=2))

    # ── Summary ───────────────────────────────────────────────────────────────
    json_hits = [r for r in results if r["status"] == 200 and r["body"].strip().startswith(("{", "["))]
    print("\n═" * 60)
    print(f"  Browser API calls with JSON body: {sum(1 for r in api_calls if r['body_preview'])}")
    print(f"  Direct JSON endpoints: {len(json_hits)}")
    if json_hits:
        for h in json_hits:
            print(f"  ★ {h['url']}")
    print("  Screenshot → totalwine_probe_output/totalwine_page.png")
    print("═" * 60)


asyncio.run(main())
