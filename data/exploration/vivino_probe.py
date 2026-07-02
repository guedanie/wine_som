"""
Vivino API probe — explore endpoints, response shape, and rate limits.
Run from project root: python3 data/exploration/vivino_probe.py
"""

import json
import subprocess
import sys
import time

BASE = "https://www.vivino.com/api"

HEADERS = [
    "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "-H", "Accept: application/json",
    "-H", "Accept-Language: en-US,en;q=0.9",
    "-H", "Referer: https://www.vivino.com/",
    "-H", "Origin: https://www.vivino.com",
]


def curl(url, extra_args=None):
    cmd = ["curl", "-s", "-L", "--max-time", "15"] + HEADERS
    if extra_args:
        cmd += extra_args
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None, f"curl error: {result.stderr}"
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError:
        return None, f"non-JSON ({len(result.stdout)} chars): {result.stdout[:300]}"


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── 1. Wine search ──────────────────────────────────────────────
section("1. Wine search — 'esprit de tablas'")
data, err = curl(f"{BASE}/wines/search?q=esprit+de+tablas&country_codes[]=us&min_rating=1")
if err:
    print("ERROR:", err)
else:
    wines = data.get("explore_vintage", {}).get("matches", []) or data.get("records", [])
    print(f"Top-level keys: {list(data.keys())}")
    if wines:
        w = wines[0]
        print(f"First match keys: {list(w.keys())}")
        print(json.dumps(w, indent=2)[:2000])
    else:
        print(json.dumps(data, indent=2)[:2000])

time.sleep(1)

# ── 2. Explore vintages endpoint ────────────────────────────────
section("2. Explore vintages — wine search via explore endpoint")
params = "q=malbec&country_codes[]=ar&price_range_min=15&price_range_max=50&min_rating=3.5&order_by=ratings_count&order=desc"
data, err = curl(f"{BASE}/explore/explore?{params}")
if err:
    print("ERROR:", err)
else:
    print(f"Top-level keys: {list(data.keys())}")
    matches = data.get("explore_vintage", {}).get("matches", [])
    print(f"Match count: {len(matches)}")
    if matches:
        m = matches[0]
        print(f"Match keys: {list(m.keys())}")
        vintage = m.get("vintage", {})
        wine = vintage.get("wine", {})
        print(f"\nvintage keys: {list(vintage.keys())}")
        print(f"wine keys: {list(wine.keys())}")
        print(f"\nSample:")
        print(f"  name:    {wine.get('name')}")
        print(f"  winery:  {wine.get('winery', {}).get('name')}")
        print(f"  year:    {vintage.get('year')}")
        print(f"  rating:  {vintage.get('statistics', {}).get('ratings_average')}")
        print(f"  reviews: {vintage.get('statistics', {}).get('ratings_count')}")
        print(f"  region:  {wine.get('region', {}).get('name')}")
        print(f"  country: {wine.get('region', {}).get('country', {}).get('name')}")
        flavor_groups = vintage.get("wine", {}).get("taste", {}).get("flavor", [])
        if flavor_groups:
            print(f"  flavors: {[f.get('primary_keywords', [{}])[0].get('name') for f in flavor_groups[:3]]}")

time.sleep(1)

# ── 3. Single wine detail ────────────────────────────────────────
section("3. Single wine detail — Esprit de Tablas (wine_id from search)")
# Esprit de Tablas Paso Robles — known Vivino wine ID
WINE_ID = 1140843
data, err = curl(f"{BASE}/wines/{WINE_ID}")
if err:
    print("ERROR:", err)
else:
    print(f"Top-level keys: {list(data.keys())}")
    wine = data.get("wine", {})
    if wine:
        print(f"wine keys: {list(wine.keys())}")
        print(f"  name:       {wine.get('name')}")
        print(f"  winery:     {wine.get('winery', {}).get('name')}")
        print(f"  region:     {wine.get('region', {}).get('name')}")
        print(f"  country:    {wine.get('region', {}).get('country', {}).get('name')}")
        print(f"  type:       {wine.get('type_id')}")
        taste = wine.get("taste", {})
        print(f"  structure:  {taste.get('structure')}")
        flavors = taste.get("flavor", [])
        print(f"  flavor grp: {len(flavors)} groups")
        if flavors:
            for g in flavors[:3]:
                kws = [k.get("name") for k in g.get("primary_keywords", [])[:3]]
                print(f"    {g.get('group')}: {kws}")
    else:
        print(json.dumps(data, indent=2)[:1500])

time.sleep(1)

# ── 4. Vintage detail with price ─────────────────────────────────
section("4. Vintage detail — Esprit de Tablas 2021")
VINTAGE_ID = 1140843  # sometimes same as wine_id for current vintage
data, err = curl(f"{BASE}/vintages/{VINTAGE_ID}")
if err:
    print("ERROR:", err)
else:
    print(f"Top-level keys: {list(data.keys())}")
    vintage = data.get("vintage", {})
    if vintage:
        stats = vintage.get("statistics", {})
        print(f"  rating:      {stats.get('ratings_average')}")
        print(f"  reviews:     {stats.get('ratings_count')}")
        price = vintage.get("price", {})
        print(f"  price amt:   {price.get('amount')}")
        print(f"  price curr:  {price.get('currency', {}).get('code')}")
        print(f"  vintage yr:  {vintage.get('year')}")
    else:
        print(json.dumps(data, indent=2)[:1000])

time.sleep(1)

# ── 5. Match by wine name (what we'd use for our catalog) ────────
section("5. Fuzzy match — 'Brunello di Montalcino Altesino'")
data, err = curl(f"{BASE}/wines/search?q=brunello+altesino&min_rating=1")
if err:
    print("ERROR:", err)
else:
    matches = data.get("explore_vintage", {}).get("matches", []) or []
    print(f"Matches: {len(matches)}")
    for m in matches[:3]:
        v = m.get("vintage", {})
        w = v.get("wine", {})
        s = v.get("statistics", {})
        print(f"  [{w.get('id')}] {w.get('name')} {v.get('year')} "
              f"— {s.get('ratings_average')} ({s.get('ratings_count')} reviews)")

time.sleep(1)

# ── 6. Check rate limiting ───────────────────────────────────────
section("6. Rate-limit check — 5 rapid requests")
for i in range(5):
    data, err = curl(f"{BASE}/wines/search?q=cabernet+sauvignon&min_rating=1")
    if err:
        print(f"  req {i+1}: ERROR — {err[:80]}")
    else:
        count = len(data.get("explore_vintage", {}).get("matches", []))
        print(f"  req {i+1}: OK ({count} matches)")

print("\nDone.")
