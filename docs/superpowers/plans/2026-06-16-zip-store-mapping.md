# Zip→Store Radius Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded single-store zip filter in `/api/recommend` with a retailer-agnostic radius-based store lookup using offline zip centroids and haversine distance.

**Architecture:** A new `backend/utils/geo.py` module provides three pure functions: `zip_to_centroid`, `haversine`, and `find_nearby_store_ids`. `BaseScraper._upsert_stores` is updated to auto-populate lat/lon when seeding stores. The recommend endpoint swaps its `eq("stores.zip_code")` filter for `in_("store_id", nearby_ids)`.

**Tech Stack:** `pgeocode` (offline US zip centroid dataset, no API key), Python `math` (haversine), Supabase Python client.

---

## File Map

| Action | File | Purpose |
|---|---|---|
| Create | `backend/utils/geo.py` | `zip_to_centroid`, `haversine`, `find_nearby_store_ids` |
| Create | `backend/tests/test_geo.py` | Unit tests for all three geo functions |
| Modify | `backend/scrapers/base.py` | Auto-populate lat/lon in `_upsert_stores` |
| Modify | `backend/tests/test_base_scraper.py` | Test lat/lon population |
| Modify | `backend/api/routers/recommend.py` | Use `find_nearby_store_ids`, add two new 400 cases |
| Modify | `backend/tests/test_recommend_api.py` | Test unknown zip and no-stores-nearby |
| Create | `backend/scripts/backfill_store_coords.py` | One-time lat/lon backfill for existing stores |
| Modify | `pyproject.toml` | Add `pgeocode` dependency |

---

## Task 1: Install pgeocode

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Install pgeocode**

```bash
cd /path/to/wine_app
pip3 install pgeocode
```

Expected: `Successfully installed pgeocode-...`

- [ ] **Step 2: Add to pyproject.toml dependencies**

In `pyproject.toml`, add to `[tool.poetry.dependencies]`:

```toml
pgeocode = "^0.4"
```

- [ ] **Step 3: Verify import works**

```bash
cd backend
python3 -c "import pgeocode; n = pgeocode.Nominatim('us'); print(n.query_postal_code('78209'))"
```

Expected: a pandas Series with `latitude` and `longitude` values around `29.47`, `-98.46`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pgeocode dependency"
```

---

## Task 2: `utils/geo.py` — zip_to_centroid and haversine (TDD)

**Files:**
- Create: `backend/utils/geo.py`
- Create: `backend/tests/test_geo.py`

- [ ] **Step 1: Write failing tests for zip_to_centroid and haversine**

Create `backend/tests/test_geo.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from utils.geo import zip_to_centroid, haversine


def test_zip_to_centroid_known_sa_zip():
    result = zip_to_centroid("78209")
    assert result is not None
    lat, lon = result
    # San Antonio centroid should be roughly 29.4, -98.4
    assert 29.0 < lat < 30.0
    assert -99.0 < lon < -98.0


def test_zip_to_centroid_unknown_returns_none():
    result = zip_to_centroid("00000")
    assert result is None


def test_zip_to_centroid_garbage_returns_none():
    result = zip_to_centroid("notazip")
    assert result is None


def test_haversine_same_point_is_zero():
    assert haversine(29.47, -98.46, 29.47, -98.46) == 0.0


def test_haversine_known_distance():
    # 78209 centroid to 78208 centroid — both SA, should be under 5 miles
    c1 = zip_to_centroid("78209")
    c2 = zip_to_centroid("78208")
    assert c1 is not None and c2 is not None
    dist = haversine(c1[0], c1[1], c2[0], c2[1])
    assert dist < 5.0


def test_haversine_sa_to_austin_is_roughly_80_miles():
    sa = zip_to_centroid("78209")    # San Antonio
    atx = zip_to_centroid("78701")   # Austin
    assert sa is not None and atx is not None
    dist = haversine(sa[0], sa[1], atx[0], atx[1])
    assert 70.0 < dist < 90.0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend
python3 -m pytest tests/test_geo.py -v
```

Expected: `ModuleNotFoundError: No module named 'utils.geo'`

- [ ] **Step 3: Create `backend/utils/__init__.py`**

```bash
touch backend/utils/__init__.py
```

(The `utils` directory may not have an `__init__.py` — check with `ls backend/utils/` and create if missing.)

- [ ] **Step 4: Implement `backend/utils/geo.py`**

Create `backend/utils/geo.py`:

```python
import math
from typing import Optional, Tuple, List
import pgeocode

_nomi: Optional[pgeocode.Nominatim] = None


def _get_nomi() -> pgeocode.Nominatim:
    global _nomi
    if _nomi is None:
        _nomi = pgeocode.Nominatim("us")
    return _nomi


def zip_to_centroid(zip_code: str) -> Optional[Tuple[float, float]]:
    """Return (lat, lon) centroid for a US zip code, or None if unrecognized."""
    try:
        result = _get_nomi().query_postal_code(zip_code)
    except Exception:
        return None
    if result is None:
        return None
    lat, lon = result.latitude, result.longitude
    # pgeocode returns NaN for unknown zips
    if lat != lat or lon != lon:
        return None
    return (float(lat), float(lon))


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in miles between two lat/lon points."""
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearby_store_ids(zip_code: str, db, radius_miles: float = 10.0) -> List[str]:
    """Return store UUIDs within radius_miles of zip_code. Empty list if zip unknown or no stores nearby."""
    centroid = zip_to_centroid(zip_code)
    if centroid is None:
        return []
    lat, lon = centroid
    stores = db.table("stores").select("id,latitude,longitude").execute()
    result = []
    for s in stores.data:
        slat, slon = s.get("latitude"), s.get("longitude")
        if slat is None or slon is None:
            continue
        if haversine(lat, lon, float(slat), float(slon)) <= radius_miles:
            result.append(s["id"])
    return result
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd backend
python3 -m pytest tests/test_geo.py -v
```

Expected: 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/utils/__init__.py backend/utils/geo.py backend/tests/test_geo.py
git commit -m "feat: geo utils — zip_to_centroid, haversine, find_nearby_store_ids"
```

---

## Task 3: `utils/geo.py` — find_nearby_store_ids (TDD)

**Files:**
- Modify: `backend/tests/test_geo.py`
- (No new implementation — `find_nearby_store_ids` already written in Task 2)

- [ ] **Step 1: Add failing tests for find_nearby_store_ids**

Append to `backend/tests/test_geo.py`:

```python
from unittest.mock import MagicMock
from utils.geo import find_nearby_store_ids


def _make_db(stores):
    """Return a mock DB client whose stores table returns the given list."""
    db = MagicMock()
    db.table.return_value.select.return_value.execute.return_value = MagicMock(data=stores)
    return db


def test_find_nearby_store_ids_sa_zip_returns_nearby_store():
    # A store at HEB 78208 centroid should be within 10 miles of 78209
    heb_centroid = zip_to_centroid("78208")
    assert heb_centroid is not None
    stores = [{"id": "store-1", "latitude": heb_centroid[0], "longitude": heb_centroid[1]}]
    db = _make_db(stores)
    result = find_nearby_store_ids("78209", db, radius_miles=10.0)
    assert "store-1" in result


def test_find_nearby_store_ids_distant_zip_returns_empty():
    # Austin store is ~80 miles from SA zip — should be excluded at 10-mile radius
    atx_centroid = zip_to_centroid("78701")
    assert atx_centroid is not None
    stores = [{"id": "store-atx", "latitude": atx_centroid[0], "longitude": atx_centroid[1]}]
    db = _make_db(stores)
    result = find_nearby_store_ids("78209", db, radius_miles=10.0)
    assert result == []


def test_find_nearby_store_ids_unknown_zip_returns_empty():
    db = _make_db([{"id": "store-1", "latitude": 29.47, "longitude": -98.46}])
    result = find_nearby_store_ids("00000", db)
    assert result == []


def test_find_nearby_store_ids_store_missing_coords_is_skipped():
    stores = [{"id": "no-coords", "latitude": None, "longitude": None}]
    db = _make_db(stores)
    result = find_nearby_store_ids("78209", db)
    assert result == []
```

- [ ] **Step 2: Run tests to confirm they pass (implementation already exists)**

```bash
cd backend
python3 -m pytest tests/test_geo.py -v
```

Expected: 10 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_geo.py
git commit -m "test: find_nearby_store_ids coverage"
```

---

## Task 4: BaseScraper — auto-populate lat/lon on store seed (TDD)

**Files:**
- Modify: `backend/scrapers/base.py` (lines 85–112)
- Modify: `backend/tests/test_base_scraper.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_base_scraper.py`:

```python
def test_upsert_stores_populates_lat_lon():
    """Stores upserted with a valid zip should have latitude/longitude populated."""
    upserted = {}

    class FakeStoresDB:
        def table(self, name):
            return self
        def upsert(self, records, on_conflict=None):
            for r in records:
                upserted[r["store_id"]] = r
            return self
        def select(self, cols):
            return self
        def in_(self, col, vals):
            return self
        def execute(self):
            return MagicMock(data=[
                {"id": "uuid-1", "retailer_name": "H-E-B", "store_id": "567"}
            ])

    scraper = HebScraper.__new__(HebScraper)
    scraper.supabase = FakeStoresDB()

    items = [RetailInventoryItem(
        wine_name="Test Wine",
        retailer_name="H-E-B",
        store_id="567",
        store_name="H-E-B",
        zip_code="78208",
        price=15.0,
        in_stock=True,
    )]
    scraper._upsert_stores(items)

    assert "567" in upserted
    assert upserted["567"]["latitude"] is not None
    assert upserted["567"]["longitude"] is not None
    # Should be San Antonio coordinates
    assert 29.0 < upserted["567"]["latitude"] < 30.0
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd backend
python3 -m pytest tests/test_base_scraper.py::test_upsert_stores_populates_lat_lon -v
```

Expected: FAIL — `latitude` key not present or is `None`.

- [ ] **Step 3: Update `_upsert_stores` in `backend/scrapers/base.py`**

Add import at top of file (after existing imports):

```python
from utils.geo import zip_to_centroid
```

Replace the `seen[key] = {...}` block (lines ~91–99) with:

```python
coords = zip_to_centroid(item.zip_code) if item.zip_code else None
seen[key] = {k: v for k, v in {
    "retailer_name": item.retailer_name,
    "store_id": item.store_id,
    "name": item.store_name,
    "address": item.address,
    "city": item.city,
    "state": item.state,
    "zip_code": item.zip_code,
    "latitude": coords[0] if coords else None,
    "longitude": coords[1] if coords else None,
}.items() if v is not None}
```

- [ ] **Step 4: Run all base scraper tests**

```bash
cd backend
python3 -m pytest tests/test_base_scraper.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scrapers/base.py backend/tests/test_base_scraper.py
git commit -m "feat: auto-populate store lat/lon from zip on seed"
```

---

## Task 5: Backfill lat/lon for existing stores

**Files:**
- Create: `backend/scripts/backfill_store_coords.py`

- [ ] **Step 1: Create backfill script**

Create `backend/scripts/__init__.py` (if `scripts/` dir doesn't exist, create it):

```bash
mkdir -p backend/scripts && touch backend/scripts/__init__.py
```

Create `backend/scripts/backfill_store_coords.py`:

```python
"""
One-time script: populate latitude/longitude for stores that have a zip_code but no coords.

Usage:
    cd backend
    python3 scripts/backfill_store_coords.py
"""
from db import get_service_client
from utils.geo import zip_to_centroid


def main():
    db = get_service_client()
    stores = db.table("stores").select("id,name,zip_code,latitude").execute()
    updated = 0
    for s in stores.data:
        if s.get("latitude") is not None:
            print(f"  skip {s['name']} (already has coords)")
            continue
        coords = zip_to_centroid(s["zip_code"])
        if coords is None:
            print(f"  warn: unknown zip {s['zip_code']} for {s['name']}")
            continue
        db.table("stores").update({
            "latitude": coords[0],
            "longitude": coords[1],
        }).eq("id", s["id"]).execute()
        print(f"  updated {s['name']}: {coords}")
        updated += 1
    print(f"\nDone — {updated} stores updated")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the backfill**

```bash
cd backend
python3 scripts/backfill_store_coords.py
```

Expected output:
```
  updated H-E-B: (29.47..., -98.46...)
  updated Geraldine's Natural Wines: (29.48..., -98.45...)

Done — 2 stores updated
```

- [ ] **Step 3: Verify in DB**

```bash
python3 - << 'EOF'
from db import get_service_client
db = get_service_client()
stores = db.table("stores").select("name,zip_code,latitude,longitude").execute()
for s in stores.data:
    print(s)
EOF
```

Expected: both stores show non-null `latitude` and `longitude`.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/__init__.py backend/scripts/backfill_store_coords.py
git commit -m "feat: backfill lat/lon for existing stores"
```

---

## Task 6: Update `/api/recommend` to use radius lookup (TDD)

**Files:**
- Modify: `backend/api/routers/recommend.py`
- Modify: `backend/tests/test_recommend_api.py`

- [ ] **Step 1: Write failing tests for new 400 cases**

Open `backend/tests/test_recommend_api.py` and append:

```python
@pytest.mark.asyncio
async def test_recommend_unknown_zip_returns_400():
    with patch("api.routers.recommend.zip_to_centroid", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "00000",
                "budget_min": 15.0,
                "budget_max": 35.0,
            })
    assert response.status_code == 400
    assert "don't recognize" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_recommend_no_stores_nearby_returns_400():
    with patch("api.routers.recommend.zip_to_centroid", return_value=(29.47, -98.46)), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=[]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
            })
    assert response.status_code == 400
    assert "no stores found" in response.json()["detail"].lower()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend
python3 -m pytest tests/test_recommend_api.py::test_recommend_unknown_zip_returns_400 tests/test_recommend_api.py::test_recommend_no_stores_nearby_returns_400 -v
```

Expected: both FAIL — `api.routers.recommend` has no `zip_to_centroid` to patch yet.

- [ ] **Step 3: Update `backend/api/routers/recommend.py`**

Add import at the top (after existing imports):

```python
from utils.geo import zip_to_centroid, find_nearby_store_ids
```

Replace the existing `result = (supabase.table("retail_inventory")...` block with the following (the select columns and in_stock/price filters stay identical — only the zip filter changes):

```python
centroid = zip_to_centroid(req.zip_code)
if centroid is None:
    raise HTTPException(status_code=400, detail="We don't recognize that zip code")

nearby_ids = find_nearby_store_ids(req.zip_code, supabase)
if not nearby_ids:
    raise HTTPException(
        status_code=400,
        detail="No stores found near your zip code. We currently serve San Antonio, TX.",
    )

result = (
    supabase.table("retail_inventory")
    .select(
        "price, curbside_price, wine_id,"
        "stores!inner(retailer_name, store_name, zip_code),"
        "wines(id, name, varietal, region, country, wine_type,"
        "wine_details(tasting_notes, flavor_profile, structure_profile, grapeminds_enriched_at))"
    )
    .in_("store_id", nearby_ids)
    .eq("in_stock", True)
    .gte("price", req.budget_min)
    .lte("price", req.budget_max)
    .execute()
)
```

- [ ] **Step 4: Fix existing passing tests**

The existing tests that expect 200 (`test_recommend_returns_200`, `test_recommend_picks_have_required_fields`) will now fail because `find_nearby_store_ids` runs against the mocked DB which has no store coords. Patch `find_nearby_store_ids` in those tests to return a fake store ID, and add `.in_` to `_make_db_mock`:

In `_make_db_mock`, add:
```python
qb.in_.return_value = qb
```

Then add `find_nearby_store_ids` patch to the two existing 200 tests:

```python
patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]),
```

Example — `test_recommend_returns_200` becomes:
```python
@pytest.mark.asyncio
async def test_recommend_returns_200():
    with patch("recommendation.claude_client.anthropic.Anthropic", _make_anthropic_mock()), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([WINE_ROW])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
                "style_preferences": ["bold", "earthy"],
                "avoid": [],
            })
    assert response.status_code == 200
```

Apply the same `find_nearby_store_ids` patch to `test_recommend_picks_have_required_fields` and `test_recommend_claude_failure_returns_500`.

- [ ] **Step 5: Run all recommend tests**

```bash
cd backend
python3 -m pytest tests/test_recommend_api.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
cd backend
python3 -m pytest tests/ -v
```

Expected: all 85+ tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/recommend.py backend/tests/test_recommend_api.py
git commit -m "feat: radius-based zip→store lookup in recommend endpoint"
```
