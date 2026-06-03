"""
GrapeMinds API data probe — 6 targeted calls to map available fields.
Results saved as JSON to data/exploration/results/.
Run from project root: python data/exploration/grapeminds_probe.py
"""
import json
import os
import sys
import subprocess
from pathlib import Path

API_KEY = os.getenv("GRAPEMINDS_API_KEY")
if not API_KEY:
    sys.exit("GRAPEMINDS_API_KEY not set — source your .env first")

BASE_URL = "https://api.grapeminds.eu/public/v1"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

CALLS_MADE = 0

def get(path: str, label: str):
    # urllib/requests are blocked by Cloudflare TLS fingerprinting — must use curl
    global CALLS_MADE
    url = f"{BASE_URL}{path}"
    print(f"  [{CALLS_MADE + 1}] GET {path}")
    result = subprocess.run(
        ["curl", "-s", "-H", f"Authorization: Bearer {API_KEY}", url],
        capture_output=True, text=True, timeout=15
    )
    try:
        data = json.loads(result.stdout)
        CALLS_MADE += 1
        out = RESULTS_DIR / f"{label}.json"
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"      → saved to results/{label}.json")
        return data
    except json.JSONDecodeError:
        print(f"      ✗ Bad response: {result.stdout[:200]}")
        return None

# ── 1. Health check ──────────────────────────────────────────────────────────
print("\n── 1. Ping")
get("/ping", "01_ping")

# ── 2. Search for a well-known wine ─────────────────────────────────────────
print("\n── 2. Wine search (q='cabernet sauvignon', limit=5)")
search_results = get("/wines/search?q=cabernet+sauvignon&limit=5", "02_search_cabernet")

# ── 3. Full detail on first result ──────────────────────────────────────────
wine_id = None
if search_results:
    wines = search_results if isinstance(search_results, list) else search_results.get("data") or search_results.get("wines") or []
    if wines:
        wine_id = wines[0].get("id")
        print(f"\n── 3. Wine detail (id={wine_id})")
        get(f"/wines/{wine_id}", "03_wine_detail")

# ── 4. Drinking period for the same wine ─────────────────────────────────────
if wine_id:
    print(f"\n── 4. Drinking period (wine_id={wine_id})")
    get(f"/drinking-periods/{wine_id}", "04_drinking_period")

# ── 5. Region list (first page, 5 results) ──────────────────────────────────
print("\n── 5. Regions (first 5)")
region_results = get("/regions?per_page=5", "05_regions")

# ── 6. Region insight for first result ───────────────────────────────────────
region_id = None
if region_results:
    regions = region_results if isinstance(region_results, list) else region_results.get("data") or region_results.get("regions") or []
    if regions:
        region_id = regions[0].get("id")
        print(f"\n── 6. Region insight (id={region_id})")
        get(f"/region-insights/{region_id}", "06_region_insight")

print(f"\n✓ Done — {CALLS_MADE}/6 calls made. Results in data/exploration/results/")
