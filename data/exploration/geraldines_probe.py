"""
Geraldine's wine shop (shopgeraldines.com) scraping feasibility probe.

Smaller local shops often use off-the-shelf e-commerce platforms
(Shopify, WooCommerce, Magento, CommerceHub) which have predictable
HTML structure and no enterprise bot protection.

What this probe does:
  1. Loads the site and takes screenshots at each stage
  2. Identifies the e-commerce platform from HTML/headers
  3. Intercepts all network requests — looks for product API calls
  4. Extracts product HTML structure (CSS classes, data attributes)
  5. Attempts to find a product listing page and parse sample items
  6. Checks for JSON-LD, __NEXT_DATA__, or other embedded product data
  7. Tries platform-specific API endpoints (Shopify, WooCommerce, etc.)

Run from project root:
  python3 data/exploration/geraldines_probe.py
"""
import asyncio
import json
import re
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright, Response

OUT_DIR = Path(__file__).parent / "geraldines_probe_output"
OUT_DIR.mkdir(exist_ok=True)

BASE_URL = "https://shopgeraldines.com"

PAGES_TO_TRY = [
    f"{BASE_URL}",
    f"{BASE_URL}/collections/wine",
    f"{BASE_URL}/collections/all",
    f"{BASE_URL}/collections/red-wine",
    f"{BASE_URL}/shop",
    f"{BASE_URL}/wine",
]

# Platform-specific API endpoints to try directly
PLATFORM_ENDPOINTS = {
    "Shopify": [
        f"{BASE_URL}/products.json?limit=5",
        f"{BASE_URL}/collections/wine/products.json?limit=5",
        f"{BASE_URL}/collections/all/products.json?limit=5",
        f"{BASE_URL}/search.json?q=wine&type=product",
    ],
    "WooCommerce": [
        f"{BASE_URL}/wp-json/wc/v3/products?per_page=5&category=wine",
        f"{BASE_URL}/wp-json/wc/v2/products?per_page=5",
        f"{BASE_URL}/?wc-ajax=get_refreshed_fragments",
    ],
    "Generic": [
        f"{BASE_URL}/api/products?limit=5",
        f"{BASE_URL}/api/v1/products?q=wine",
        f"{BASE_URL}/catalog/products?format=json",
    ],
}


def curl_get(url: str) -> dict:
    result = subprocess.run(
        ["curl", "-s", "-o", "-", "-w", "\n__STATUS__%{http_code}",
         "-H", "Accept: application/json, text/html, */*",
         "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
         "--max-time", "10", "-L", url],
        capture_output=True, text=True
    )
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


def detect_platform(html: str, headers: dict) -> str:
    """Identify the e-commerce platform from HTML content and response headers."""
    html_lower = html.lower()
    if "shopify" in html_lower or "cdn.shopify.com" in html_lower or "Shopify.theme" in html:
        return "Shopify"
    if "woocommerce" in html_lower or "wp-content" in html_lower:
        return "WooCommerce"
    if "magento" in html_lower or "mage/" in html_lower:
        return "Magento"
    if "bigcommerce" in html_lower or "cdn11.bigcommerce.com" in html_lower:
        return "BigCommerce"
    if "squarespace" in html_lower:
        return "Squarespace"
    if "wix.com" in html_lower:
        return "Wix"
    powered = headers.get("x-powered-by", "").lower()
    if "php" in powered:
        return "PHP/Custom (likely WooCommerce or custom)"
    return "Unknown"


async def probe():
    captured_responses = []
    best_html = ""
    best_url = ""
    platform = "Unknown"

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

        # Capture response headers from the main page for platform detection
        main_headers = {}

        async def on_response(response: Response):
            url = response.url
            if any(skip in url for skip in [
                ".js", ".css", ".png", ".jpg", ".svg", ".woff",
                ".ico", ".gif", "google", "facebook", "analytics",
                "cdn-cgi", "fonts.googleapis",
            ]):
                return
            try:
                content_type = response.headers.get("content-type", "")
                body_preview = ""
                if "json" in content_type and response.status == 200:
                    body_preview = (await response.text())[:800]
                captured_responses.append({
                    "url": url, "status": response.status,
                    "content_type": content_type,
                    "body_preview": body_preview,
                })
                if response.url == page.url and response.status == 200:
                    main_headers.update(dict(response.headers))
            except Exception:
                pass

        page.on("response", on_response)

        # ── Try each page URL ──────────────────────────────────────────────────
        print("── Step 1: Loading pages")
        for url in PAGES_TO_TRY:
            print(f"   Trying: {url}")
            try:
                await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2500)
                title = await page.title()
                html = await page.content()
                print(f"   Title: {title} | HTML: {len(html):,} bytes")

                if len(html) > len(best_html):
                    best_html = html
                    best_url = url

                # Scroll to trigger lazy loading
                for _ in range(2):
                    await page.evaluate("window.scrollBy(0, window.innerHeight)")
                    await page.wait_for_timeout(800)

                # Take screenshot on first substantial page
                screenshot_path = OUT_DIR / f"page_{len(captured_responses):02d}.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"   Screenshot: {screenshot_path.name}")

                if len(html) > 20000:
                    break  # Found a real page — stop trying URLs

            except Exception as e:
                print(f"   Error: {e}")

        await browser.close()

    print(f"\n── Best page: {best_url} ({len(best_html):,} bytes)")

    # ── Save full HTML ─────────────────────────────────────────────────────────
    (OUT_DIR / "page.html").write_text(best_html, encoding="utf-8")

    # ── Platform detection ────────────────────────────────────────────────────
    print("\n── Step 2: Platform detection")
    platform = detect_platform(best_html, main_headers)
    print(f"   Platform: {platform}")

    # ── Network requests analysis ─────────────────────────────────────────────
    print(f"\n── Step 3: Network requests ({len(captured_responses)} captured)")
    json_responses = [r for r in captured_responses if r["body_preview"]]
    for r in json_responses:
        print(f"   ★ [{r['status']}] {r['url'][:100]}")
        print(f"         {r['body_preview'][:150]}")
    (OUT_DIR / "network_requests.json").write_text(json.dumps(captured_responses, indent=2))

    # ── HTML structure analysis ───────────────────────────────────────────────
    print("\n── Step 4: HTML structure — product-related CSS classes")
    all_classes = re.findall(r'class="([^"]+)"', best_html)
    freq = {}
    for group in all_classes:
        for cls in group.split():
            freq[cls] = freq.get(cls, 0) + 1
    product_kws = ["product", "item", "card", "price", "title", "name",
                   "wine", "collection", "grid", "sku", "variant", "add-to-cart"]
    relevant = {c: n for c, n in freq.items()
                if any(kw in c.lower() for kw in product_kws)}
    for cls, count in sorted(relevant.items(), key=lambda x: -x[1])[:25]:
        print(f"   {count:4d}x  .{cls}")

    # ── Embedded data extraction ──────────────────────────────────────────────
    print("\n── Step 5: Embedded data extraction")

    # Shopify window.Shopify or __st/productJSON
    shopify_product = re.findall(r'var meta = ({.*?});', best_html, re.DOTALL)
    if shopify_product:
        print(f"   Shopify meta object found: {shopify_product[0][:300]}")

    # JSON-LD
    json_ld_blocks = re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        best_html, re.DOTALL
    )
    if json_ld_blocks:
        print(f"   JSON-LD blocks: {len(json_ld_blocks)}")
        for block in json_ld_blocks[:3]:
            try:
                data = json.loads(block.strip())
                dtype = data.get("@type", "unknown")
                print(f"     Type: {dtype} — {json.dumps(data)[:200]}")
                (OUT_DIR / f"jsonld_{dtype}.json").write_text(json.dumps(data, indent=2))
            except Exception:
                pass

    # Next.js embedded data
    next_data = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', best_html, re.DOTALL
    )
    if next_data:
        print("   __NEXT_DATA__ found (Next.js)")
        try:
            data = json.loads(next_data.group(1))
            (OUT_DIR / "next_data.json").write_text(json.dumps(data, indent=2))
            print(f"   Saved → next_data.json ({len(next_data.group(1))} bytes)")
        except Exception:
            pass

    # Shopify product data embedded as JSON
    shopify_data = re.findall(r'window\.__st=({.*?});', best_html, re.DOTALL)
    if shopify_data:
        print(f"   window.__st (Shopify analytics): {shopify_data[0][:200]}")

    # ── Platform-specific API probes ──────────────────────────────────────────
    print(f"\n── Step 6: Platform API probes ({platform})")
    endpoints = PLATFORM_ENDPOINTS.get(platform, []) + PLATFORM_ENDPOINTS["Generic"]
    api_hits = []
    for url in endpoints:
        r = curl_get(url)
        body = r["body"]
        is_json = body.strip().startswith(("{", "["))
        indicator = "★" if (r["status"] == 200 and is_json) else ("✓" if r["status"] == 200 else "✗")
        print(f"   {indicator} {r['status']}  {url}")
        if is_json:
            print(f"         └─ {body[:200]}")
            api_hits.append(r)
            (OUT_DIR / f"api_{url.split('/')[-1].split('?')[0]}.json").write_text(body)

    # ── Sample product extraction ─────────────────────────────────────────────
    print("\n── Step 7: Sample product extraction from HTML")
    # Try to find wine names and prices in the HTML
    # Shopify product titles often appear in <h2> or specific data attributes
    price_pattern = re.findall(r'\$\s*(\d+\.?\d*)', best_html)
    if price_pattern:
        unique_prices = sorted(set(float(p) for p in price_pattern[:50]))
        print(f"   Prices found on page: {unique_prices[:20]}")

    # Product names — look for common patterns
    product_titles = re.findall(
        r'data-product-title="([^"]+)"|'
        r'"title"\s*:\s*"([^"]+wine[^"]*)"',
        best_html, re.IGNORECASE
    )
    if product_titles:
        names = [t[0] or t[1] for t in product_titles[:10]]
        print(f"   Product titles found: {names}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n═" * 60)
    print(f"  Platform:          {platform}")
    print(f"  HTML size:         {len(best_html):,} bytes")
    print(f"  JSON API hits:     {len(api_hits)}")
    print(f"  JSON-LD blocks:    {len(json_ld_blocks)}")
    print(f"  Network JSON:      {len(json_responses)} responses")
    print(f"  Output dir:        {OUT_DIR}/")
    if api_hits:
        print("\n  ★ ACCESSIBLE JSON ENDPOINTS:")
        for h in api_hits:
            print(f"    {h['url']}")
    print("═" * 60)


asyncio.run(probe())
