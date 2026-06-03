"""
HEB wine page probe — maps the real page structure before we write the scraper.

What it does:
  1. Opens heb.com and sets store location to zip 78209
  2. Navigates to the wine category
  3. Takes screenshots at each stage so we can see what Playwright sees
  4. Dumps the HTML of the product listing section
  5. Prints every unique CSS class that appears on product cards

Run from project root:
  python3 data/exploration/heb_probe.py
"""
import asyncio
import json
import re
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

OUT_DIR = Path(__file__).parent / "heb_probe_output"
OUT_DIR.mkdir(exist_ok=True)

ZIP_CODE = "78209"

WINE_URLS = [
    "https://www.heb.com/product-category/beverages/wine",
    "https://www.heb.com/search/?q=wine&navtype=search",
]


async def safe_goto(page, url, timeout=30000):
    """Navigate and wait for load — tolerates SPAs that never reach networkidle."""
    try:
        await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
    except PWTimeout:
        print(f"   Warning: domcontentloaded timeout on {url} — continuing anyway")
    await page.wait_for_timeout(3000)  # let JS render


async def probe():
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

        # ── Step 1: Load homepage and check for a location/store picker ────────
        print("── Step 1: Loading heb.com homepage")
        await safe_goto(page, "https://www.heb.com")
        await page.screenshot(path=str(OUT_DIR / "01_homepage.png"))
        print("   Screenshot: 01_homepage.png")

        # Look for zip/store input on the page
        zip_selectors = [
            "input[placeholder*='zip']",
            "input[placeholder*='ZIP']",
            "input[placeholder*='store']",
            "input[name*='zip']",
            "[data-testid*='zip']",
            "[data-testid*='store']",
            "[aria-label*='zip']",
            "[aria-label*='store']",
        ]
        found_zip_input = None
        for sel in zip_selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    found_zip_input = sel
                    print(f"   Found zip/store input: {sel}")
                    break
            except Exception:
                pass
        if not found_zip_input:
            print("   No zip input found on homepage — will try URL approach")

        # ── Step 2: Try to set location via zip code ───────────────────────────
        print(f"\n── Step 2: Attempting to set location to {ZIP_CODE}")

        # Try clicking any "select store" or location button first
        location_triggers = [
            "[data-testid*='store-select']",
            "[data-testid*='location']",
            "button[aria-label*='store']",
            "button[aria-label*='location']",
            "text=Select a store",
            "text=Set your store",
            "text=Find a store",
            "[class*='StoreSelector']",
            "[class*='store-selector']",
        ]
        clicked_trigger = False
        for sel in location_triggers:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    await page.wait_for_timeout(1500)
                    print(f"   Clicked location trigger: {sel}")
                    clicked_trigger = True
                    await page.screenshot(path=str(OUT_DIR / "02_after_location_click.png"))
                    print("   Screenshot: 02_after_location_click.png")
                    break
            except Exception:
                pass

        # Now try to fill zip code
        zip_fill_selectors = [
            "input[placeholder*='zip' i]",
            "input[placeholder*='ZIP']",
            "input[name*='zip' i]",
            "input[type='text'][maxlength='5']",
            "[data-testid*='zip'] input",
            "[aria-label*='zip' i]",
        ]
        filled_zip = False
        for sel in zip_fill_selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.fill(ZIP_CODE)
                    await el.press("Enter")
                    await page.wait_for_timeout(2000)
                    print(f"   Filled zip code in: {sel}")
                    filled_zip = True
                    break
            except Exception:
                pass

        if not filled_zip:
            print("   Could not fill zip code — continuing without location set")

        await page.screenshot(path=str(OUT_DIR / "03_after_zip.png"))
        print("   Screenshot: 03_after_zip.png")

        # ── Step 3: Navigate to wine category ─────────────────────────────────
        print("\n── Step 3: Navigating to wine section")
        for url in WINE_URLS:
            try:
                print(f"   Trying: {url}")
                await safe_goto(page, url)
                await page.wait_for_timeout(2000)
                title = await page.title()
                print(f"   Page title: {title}")
                await page.screenshot(path=str(OUT_DIR / "04_wine_page.png"))
                print("   Screenshot: 04_wine_page.png")
                break
            except PWTimeout:
                print(f"   Timeout on {url}")
                continue

        # ── Step 4: Scroll to load more products ──────────────────────────────
        print("\n── Step 4: Scrolling to trigger lazy load")
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUT_DIR / "05_after_scroll.png"))
        print("   Screenshot: 05_after_scroll.png")

        # ── Step 5: Dump HTML and extract structure ────────────────────────────
        print("\n── Step 5: Extracting page structure")
        html = await page.content()
        (OUT_DIR / "wine_page.html").write_text(html, encoding="utf-8")
        print(f"   Full HTML saved ({len(html):,} bytes) → heb_probe_output/wine_page.html")

        # Find all unique class names on the page — sorted by frequency
        all_classes = re.findall(r'class="([^"]+)"', html)
        class_freq = {}
        for group in all_classes:
            for cls in group.split():
                class_freq[cls] = class_freq.get(cls, 0) + 1

        # Print classes that look product-related
        product_keywords = [
            "product", "item", "card", "tile", "result", "listing",
            "grid", "price", "name", "title", "brand", "wine",
        ]
        print("\n   Classes that look product/item related:")
        relevant = {
            cls: count for cls, count in class_freq.items()
            if any(kw in cls.lower() for kw in product_keywords)
        }
        for cls, count in sorted(relevant.items(), key=lambda x: -x[1])[:40]:
            print(f"     {count:4d}x  .{cls}")

        # ── Step 6: Try to extract actual product data ─────────────────────────
        print("\n── Step 6: Sampling product data from page")

        # Try multiple possible product container selectors
        container_selectors = [
            "[data-testid*='product']",
            "[class*='ProductCard']",
            "[class*='product-card']",
            "[class*='ProductTile']",
            "[class*='product-tile']",
            "[class*='ProductItem']",
            "[class*='product-item']",
            "[class*='SearchResult']",
            "article",
            "[class*='item-card']",
        ]

        products_found = []
        for sel in container_selectors:
            els = page.locator(sel)
            count = await els.count()
            if count > 0:
                print(f"   Found {count} elements matching: {sel}")
                # Sample first 3
                for i in range(min(3, count)):
                    try:
                        el = els.nth(i)
                        text = (await el.inner_text()).strip().replace("\n", " | ")[:200]
                        html_snippet = (await el.inner_html())[:400]
                        products_found.append({
                            "selector": sel,
                            "index": i,
                            "text": text,
                            "html_snippet": html_snippet,
                        })
                    except Exception:
                        pass
                if products_found:
                    break

        if products_found:
            out_file = OUT_DIR / "product_samples.json"
            out_file.write_text(json.dumps(products_found, indent=2, ensure_ascii=False))
            print(f"\n   Product samples saved → heb_probe_output/product_samples.json")
            for p in products_found[:2]:
                print(f"\n   [{p['selector']}] index {p['index']}:")
                print(f"     TEXT: {p['text'][:150]}")
                print(f"     HTML: {p['html_snippet'][:200]}")
        else:
            print("   No product containers found with any selector — site may require auth or JS interaction")

        # ── Step 7: Log all network requests to spot any useful API calls ──────
        print("\n── Step 7: Current URL and page metadata")
        print(f"   Final URL: {page.url}")
        print(f"   Page title: {await page.title()}")

        await browser.close()
        print(f"\n✓ Probe complete. All output in: {OUT_DIR}/")
        print("  Files: 01-05 screenshots, wine_page.html, product_samples.json")


asyncio.run(probe())
