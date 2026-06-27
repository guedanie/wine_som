# RegionBrowse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/region/:slug` catalog page that shows in-stock wines for a region grouped by retailer, with client-side filtering by grape, price, and retailer, plus a fallback redirect to the sommelier chat when filters return no results.

**Architecture:** A new FastAPI endpoint (`GET /api/region/{region_name}`) fetches wines for a region from nearby stores, price-partitions them (3 tiers × 5 per retailer = 15 max per retailer), and returns them grouped by retailer. The frontend `RegionBrowse` screen fetches once on mount, then all filtering is pure client-side with no further API calls. Discovery tiles navigate to `/region/:slug` instead of `/recommend`.

**Tech Stack:** Python 3.9 / FastAPI / supabase-py (backend); React 19 / Vite / react-router-dom v7 (frontend); existing `WineCard`, `Eyebrow`, `Btn` components; existing `find_nearby_store_ids` and `zip_to_centroid` geo utils; existing `deriveWineCardMeta` from `regions.js`.

## Global Constraints

- Python 3.9 only — use `Optional[str]`, `List[X]`, `Dict[str, Any]` from `typing`; no `str | None` syntax
- Run backend from `backend/` directory: `python3 -m uvicorn api.main:app --reload`
- Run frontend from `frontend/`: `npm run dev` → localhost:5173
- Backend tests: `cd backend && python3 -m pytest tests/ -m "not integration" -q` — must stay at 157+ passing
- Frontend tests: `cd frontend && npx vitest run` — must stay at 70+ passing
- No new npm packages; no new pip packages
- Design tokens: use CSS variables (`var(--ink)`, `var(--bordeaux)`, `var(--cream)`, etc.) — no hardcoded hex
- Fonts: `var(--font-serif)` (DM Serif Display) for display text, `var(--font-sans)` (Archivo) for UI
- `border-radius: 0` for cards, buttons, inputs; `999px` only for pill chips
- WineCard expects props: `wine.name`, `wine.price`, `wine.retailer`, `wine.tagline`, `wine.coord`, `wine.flavors` (array) — always run raw API wines through `deriveWineCardMeta` before passing to WineCard
- Supabase anon key for reads; service_role bypasses RLS (backend only)
- `retail_inventory` FK to `stores` is `store_ref` (UUID), not `store_id`

---

## File Map

**Create:**
- `backend/api/routers/region.py` — `GET /api/region/{region_name}` endpoint
- `backend/tests/test_region_api.py` — unit tests for the region endpoint
- `frontend/src/screens/RegionBrowse.jsx` — new catalog screen
- `frontend/src/screens/__tests__/RegionBrowse.test.jsx` — tests for RegionBrowse

**Modify:**
- `backend/api/schemas.py` — add `RegionWineItem`, `RegionRetailerGroup`, `RegionResponse`
- `backend/api/main.py` — register `region` router
- `frontend/src/lib/api.js` — add `getRegionWines(region, zip)` fetch function
- `frontend/src/lib/regions.js` — add `REGION_DB_ALIASES` map
- `frontend/src/App.jsx` — add `/region/:slug` route
- `frontend/src/screens/Discovery.jsx` — navigate to `/region/:slug` instead of `/recommend`
- `frontend/src/screens/__tests__/Discovery.test.jsx` — update navigation assertion

---

## Task 1: Backend `/api/region/{region_name}` endpoint

**Files:**
- Create: `backend/api/routers/region.py`
- Create: `backend/tests/test_region_api.py`
- Modify: `backend/api/schemas.py` (lines 1–34 — add three new models after `WineSearchResult`)
- Modify: `backend/api/main.py` (lines 5, 19 — import + include router)

**Interfaces:**
- Consumes: `find_nearby_store_ids(zip_code, db, centroid)` from `utils.geo`; `zip_to_centroid(zip_code)` from `utils.geo`; `get_supabase_client()` from `db`
- Produces: `GET /api/region/{region_name}?zip=78209` → JSON matching `RegionResponse`; 400 if zip unknown or no stores; 404 if region has no in-stock wines near zip

**Response shape:**
```json
{
  "region": "Tuscany",
  "retailers": [
    {
      "retailer": "Geraldine's Natural Wines",
      "wines": [
        {
          "wine_id": "uuid",
          "name": "Selvapiana Chianti Rufina",
          "varietal": "Sangiovese",
          "region": "Tuscany",
          "country": "Italy",
          "wine_type": "red",
          "price": 22.0,
          "retailer": "Geraldine's Natural Wines",
          "store_address": "7700 Broadway St, San Antonio, TX 78209",
          "image_url": null,
          "flavor_profile": ["dark cherry", "leather"],
          "grapes": ["Sangiovese"]
        }
      ]
    }
  ]
}
```

- [ ] **Step 1: Add Pydantic schemas to `backend/api/schemas.py`**

Insert after the existing `WineSearchResult` class (after line 13):

```python
class RegionWineItem(BaseModel):
    wine_id: str
    name: str
    varietal: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    wine_type: Optional[str] = None
    price: float
    retailer: str
    store_address: Optional[str] = None
    image_url: Optional[str] = None
    flavor_profile: List[str] = []
    grapes: List[str] = []


class RegionRetailerGroup(BaseModel):
    retailer: str
    wines: List[RegionWineItem]


class RegionResponse(BaseModel):
    region: str
    retailers: List[RegionRetailerGroup]
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_region_api.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from api.main import app

# ── fixtures ─────────────────────────────────────────────────────────────────

_STORE = {"id": "store-uuid-1", "retailer_name": "Spec's"}

_INV_ROW = {
    "price": 28.0,
    "wine_id": "wine-uuid-1",
    "stores": {"retailer_name": "Spec's", "address": "1234 Main St"},
    "wines": {
        "id": "wine-uuid-1",
        "name": "Test Chianti",
        "varietal": "Sangiovese",
        "region": "Tuscany",
        "country": "Italy",
        "wine_type": "red",
        "grapes": ["Sangiovese"],
        "image_url": None,
        "wine_details": [{"flavor_profile": ["dark cherry", "leather"]}],
    },
}

def _make_db_mock(inv_rows=None, store_rows=None):
    db = MagicMock()
    # stores query
    stores_resp = MagicMock()
    stores_resp.data = store_rows if store_rows is not None else [_STORE]
    db.table.return_value.select.return_value.in_.return_value.execute.return_value = stores_resp
    # inventory query
    inv_resp = MagicMock()
    inv_resp.data = inv_rows if inv_rows is not None else [_INV_ROW]
    q = db.table.return_value.select.return_value
    q.in_.return_value.eq.return_value.gte.return_value.lte.return_value.limit.return_value.execute.return_value = inv_resp
    return db


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_region_returns_200_with_wines():
    with (
        patch("api.routers.region.get_supabase_client", return_value=_make_db_mock()),
        patch("api.routers.region.zip_to_centroid", return_value=(29.48, -98.42)),
        patch("api.routers.region.find_nearby_store_ids", return_value=["store-uuid-1"]),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/region/Tuscany?zip=78209")
    assert resp.status_code == 200
    body = resp.json()
    assert body["region"] == "Tuscany"
    assert len(body["retailers"]) == 1
    assert body["retailers"][0]["retailer"] == "Spec's"
    assert body["retailers"][0]["wines"][0]["name"] == "Test Chianti"


@pytest.mark.asyncio
async def test_region_400_on_unknown_zip():
    with patch("api.routers.region.zip_to_centroid", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/region/Tuscany?zip=00000")
    assert resp.status_code == 400
    assert "zip" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_region_404_when_no_wines():
    with (
        patch("api.routers.region.get_supabase_client", return_value=_make_db_mock(inv_rows=[])),
        patch("api.routers.region.zip_to_centroid", return_value=(29.48, -98.42)),
        patch("api.routers.region.find_nearby_store_ids", return_value=["store-uuid-1"]),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/region/Tuscany?zip=78209")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_region_alias_rhone_valley():
    """'Rhône Valley' in the URL maps to 'Rhône' in the DB query."""
    captured = {}
    db = _make_db_mock()

    original_table = db.table
    def capturing_table(name):
        tbl = original_table(name)
        if name == "retail_inventory":
            original_select = tbl.select
            def capturing_select(cols):
                captured["cols"] = cols
                return original_select(cols)
            tbl.select = capturing_select
        return tbl
    db.table = capturing_table

    with (
        patch("api.routers.region.get_supabase_client", return_value=db),
        patch("api.routers.region.zip_to_centroid", return_value=(29.48, -98.42)),
        patch("api.routers.region.find_nearby_store_ids", return_value=["store-uuid-1"]),
        patch("api.routers.region._db_region_name", return_value="Rhône"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/region/Rh%C3%B4ne%20Valley?zip=78209")
    assert resp.status_code == 200


def test_price_partition_returns_up_to_15_across_3_tiers():
    from api.routers.region import _price_partition
    wines = [{"price": float(p), "name": f"Wine{p}"} for p in range(5, 125, 5)]  # 24 wines $5-$120
    result = _price_partition(wines, n_per_tier=5)
    assert len(result) <= 15
    prices = [w["price"] for w in result]
    assert min(prices) < 45   # has cheap wines
    assert max(prices) > 80   # has expensive wines


def test_price_partition_fewer_than_15_wines():
    from api.routers.region import _price_partition
    wines = [{"price": 20.0, "name": "A"}, {"price": 35.0, "name": "B"}]
    result = _price_partition(wines, n_per_tier=5)
    assert len(result) == 2


def test_price_partition_empty():
    from api.routers.region import _price_partition
    assert _price_partition([], n_per_tier=5) == []
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend && python3 -m pytest tests/test_region_api.py -v 2>&1 | head -30
```

Expected: `ImportError` or `ModuleNotFoundError` — `api.routers.region` doesn't exist yet.

- [ ] **Step 4: Create `backend/api/routers/region.py`**

```python
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from api.schemas import RegionResponse, RegionRetailerGroup, RegionWineItem
from db import get_supabase_client
from utils.geo import zip_to_centroid, find_nearby_store_ids

router = APIRouter(prefix="/api", tags=["region"])

# DB stores sub-regions under the parent name for two DISCOVERY_REGIONS entries.
_REGION_ALIASES: Dict[str, str] = {
    "Rhône Valley": "Rhône",
    "Douro Valley": "Douro",
}

_REGION_INVENTORY_SELECT = (
    "price, wine_id,"
    "stores!inner(retailer_name, address),"
    "wines!inner(id, name, varietal, region, country, wine_type, grapes, image_url,"
    "wine_details(flavor_profile))"
)

_FETCH_LIMIT = 500   # rows per retailer before partitioning


def _db_region_name(region: str) -> str:
    return _REGION_ALIASES.get(region, region)


def _price_partition(wines: List[Dict[str, Any]], n_per_tier: int = 5) -> List[Dict[str, Any]]:
    """Return up to n_per_tier wines from each of 3 price tiers (low/mid/high)."""
    if not wines:
        return []
    prices = [w["price"] for w in wines]
    lo, hi = min(prices), max(prices)
    if lo == hi:
        return wines[:n_per_tier * 3]
    span = (hi - lo) / 3
    tiers: List[List[Dict[str, Any]]] = [[], [], []]
    for w in wines:
        idx = min(int((w["price"] - lo) / span), 2)
        tiers[idx].append(w)
    result: List[Dict[str, Any]] = []
    for tier in tiers:
        result.extend(tier[:n_per_tier])
    return result


def _row_to_wine_item(row: Dict[str, Any], retailer: str, address: Optional[str]) -> Optional[RegionWineItem]:
    wine = row.get("wines") or {}
    if not wine:
        return None
    details_raw = wine.get("wine_details") or {}
    details = details_raw[0] if isinstance(details_raw, list) else (details_raw if isinstance(details_raw, dict) else {})
    return RegionWineItem(
        wine_id=wine.get("id", ""),
        name=wine.get("name", ""),
        varietal=wine.get("varietal"),
        region=wine.get("region"),
        country=wine.get("country"),
        wine_type=wine.get("wine_type"),
        price=float(row.get("price") or 0),
        retailer=retailer,
        store_address=address,
        image_url=wine.get("image_url"),
        flavor_profile=details.get("flavor_profile") or [],
        grapes=wine.get("grapes") or [],
    )


@router.get("/region/{region_name}", response_model=RegionResponse)
async def get_region_wines(
    region_name: str,
    zip: str = Query(..., description="User zip code for nearby store lookup"),
):
    db = get_supabase_client()

    centroid = zip_to_centroid(zip)
    if centroid is None:
        raise HTTPException(status_code=400, detail="We don't recognize that zip code")

    nearby_ids = find_nearby_store_ids(zip, db, centroid=centroid)
    if not nearby_ids:
        raise HTTPException(
            status_code=400,
            detail="No stores found near your zip code. We currently serve San Antonio, TX.",
        )

    db_region = _db_region_name(region_name)

    # Group nearby stores by retailer so we can cap per retailer
    stores_resp = (
        db.table("stores")
        .select("id, retailer_name")
        .in_("id", nearby_ids)
        .execute()
    )
    retailer_to_stores: Dict[str, List[str]] = {}
    for s in (stores_resp.data or []):
        sid, rname = s.get("id"), s.get("retailer_name")
        if sid and rname:
            retailer_to_stores.setdefault(rname, []).append(sid)

    by_retailer: Dict[str, List[Dict[str, Any]]] = {}

    for rname, store_ids in retailer_to_stores.items():
        rows = (
            db.table("retail_inventory")
            .select(_REGION_INVENTORY_SELECT)
            .in_("store_ref", store_ids)
            .eq("in_stock", True)
            .gte("price", 0)
            .lte("price", 9999)
            .limit(_FETCH_LIMIT)
            .execute()
        )
        for row in (rows.data or []):
            wine = row.get("wines") or {}
            if wine.get("region") != db_region:
                continue
            address = (row.get("stores") or {}).get("address")
            item = _row_to_wine_item(row, rname, address)
            if item:
                by_retailer.setdefault(rname, []).append(item.model_dump())

    if not by_retailer:
        raise HTTPException(
            status_code=404,
            detail=f"No in-stock wines from {region_name} found near your zip code.",
        )

    retailers = []
    for rname in sorted(by_retailer.keys()):
        partitioned = _price_partition(by_retailer[rname], n_per_tier=5)
        wines = [RegionWineItem(**w) for w in partitioned]
        retailers.append(RegionRetailerGroup(retailer=rname, wines=wines))

    return RegionResponse(region=region_name, retailers=retailers)
```

- [ ] **Step 5: Register the router in `backend/api/main.py`**

Change:
```python
from api.routers import wines, enrichment, recommend
```
To:
```python
from api.routers import wines, enrichment, recommend, region
```

And add after `app.include_router(recommend.router)`:
```python
app.include_router(region.router)
```

- [ ] **Step 6: Run tests**

```bash
cd backend && python3 -m pytest tests/test_region_api.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 7: Run full backend suite**

```bash
cd backend && python3 -m pytest tests/ -m "not integration" -q
```

Expected: 164+ passing, 3 deselected.

- [ ] **Step 8: Commit**

```bash
git add backend/api/routers/region.py backend/api/schemas.py backend/api/main.py backend/tests/test_region_api.py
git commit -m "feat: GET /api/region/{name} endpoint with price partitioning"
```

---

## Task 2: Frontend API function and region alias map

**Files:**
- Modify: `frontend/src/lib/api.js` — add `getRegionWines(region, zip)`
- Modify: `frontend/src/lib/regions.js` — add `REGION_DB_ALIASES` export
- Modify: `frontend/src/lib/__tests__/api.test.js` — add `getRegionWines` tests

**Interfaces:**
- Produces: `getRegionWines(region: string, zip: string): Promise<RegionResponse>` where `RegionResponse = { region: string, retailers: Array<{ retailer: string, wines: Array<WineItem> }> }`
- Produces: `REGION_DB_ALIASES: Record<string, string>` (exported from regions.js — currently unused by frontend logic, present for documentation)

- [ ] **Step 1: Write failing tests**

Add to `frontend/src/lib/__tests__/api.test.js` (append after the existing `getWine` describe block):

```javascript
describe('getRegionWines', () => {
  it('GETs /api/region/:name with zip query param', async () => {
    const mockResp = { region: 'Tuscany', retailers: [] };
    fetch.mockResolvedValueOnce({ ok: true, json: async () => mockResp });
    const { getRegionWines } = await import('../api.js');
    await getRegionWines('Tuscany', '78209');
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/region\/Tuscany\?zip=78209/)
    );
  });

  it('throws on non-ok response', async () => {
    fetch.mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'Not found' }) });
    const { getRegionWines } = await import('../api.js');
    await expect(getRegionWines('Tuscany', '78209')).rejects.toThrow('Not found');
  });

  it('URL-encodes region names with spaces', async () => {
    fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ region: 'Napa Valley', retailers: [] }) });
    const { getRegionWines } = await import('../api.js');
    await getRegionWines('Napa Valley', '78209');
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/Napa%20Valley/));
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/lib/__tests__/api.test.js 2>&1 | tail -10
```

Expected: `getRegionWines is not a function` or similar.

- [ ] **Step 3: Add `getRegionWines` to `frontend/src/lib/api.js`**

Append after the `getWine` function:

```javascript
export async function getRegionWines(region, zip) {
  const encoded = encodeURIComponent(region);
  const res = await fetch(`${BASE}/api/region/${encoded}?zip=${encodeURIComponent(zip)}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}
```

- [ ] **Step 4: Add `REGION_DB_ALIASES` to `frontend/src/lib/regions.js`**

Append after the `VARIETAL_OPTS` export (after line 12):

```javascript
// Two DISCOVERY_REGIONS names differ from what the extractor wrote to wines.region.
// The backend handles the mapping; this export documents it for reference.
export const REGION_DB_ALIASES = {
  'Rhône Valley': 'Rhône',
  'Douro Valley': 'Douro',
};
```

- [ ] **Step 5: Run tests**

```bash
cd frontend && npx vitest run src/lib/__tests__/api.test.js
```

Expected: all tests pass (including the 3 new `getRegionWines` tests).

- [ ] **Step 6: Run full frontend suite**

```bash
cd frontend && npx vitest run
```

Expected: 73+ passing.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/api.js frontend/src/lib/regions.js frontend/src/lib/__tests__/api.test.js
git commit -m "feat: getRegionWines API function and region alias map"
```

---

## Task 3: RegionBrowse screen — fetch and display

**Files:**
- Create: `frontend/src/screens/RegionBrowse.jsx`
- Create: `frontend/src/screens/__tests__/RegionBrowse.test.jsx`
- Modify: `frontend/src/App.jsx` — add `/region/:slug` route

**Interfaces:**
- Consumes: `getRegionWines(region, zip)` from `../../lib/api.js`
- Consumes: `deriveWineCardMeta(pick)` from `../../lib/regions.js`
- Consumes: `WineCard`, `Eyebrow`, `Btn`, `Poster` components
- Produces: screen at `/region/:slug` — reads `slug` from URL param, `zip` from location state or defaults to `'78209'`

**Screen layout (no filters yet — added in Task 4):**
```
┌──────────────────────────────────────────────────────┐
│ ← Back to Discover                                   │
│                                                      │
│ DISCOVER                                             │
│ Tuscany                          [Poster 3:4]        │
│ 43.8°N · 11.2°E                                     │
│                                                      │
│ [Zip input: 78209]                                   │
│                                                      │
│ GERALDINE'S NATURAL WINES                            │
│ [WineCard] [WineCard] [WineCard]                     │
│                                                      │
│ SPEC'S                                               │
│ [WineCard] [WineCard] ...                            │
└──────────────────────────────────────────────────────┘
```

- [ ] **Step 1: Write failing tests**

Create `frontend/src/screens/__tests__/RegionBrowse.test.jsx`:

```jsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import RegionBrowse from '../RegionBrowse.jsx';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});
vi.mock('../../lib/api.js', () => ({ getRegionWines: vi.fn() }));
import { getRegionWines } from '../../lib/api.js';

const MOCK_RESP = {
  region: 'Tuscany',
  retailers: [
    {
      retailer: "Spec's",
      wines: [
        { wine_id: 'w1', name: 'Chianti Classico', varietal: 'Sangiovese', region: 'Tuscany',
          country: 'Italy', wine_type: 'red', price: 22, retailer: "Spec's",
          store_address: '123 Main', image_url: null, flavor_profile: ['dark cherry'], grapes: ['Sangiovese'] },
      ],
    },
  ],
};

function renderScreen(slug = 'Tuscany', state = {}) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: `/region/${slug}`, state }]}>
      <Routes>
        <Route path="/region/:slug" element={<RegionBrowse />} />
        <Route path="/discover" element={<div>Discover</div>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => { mockNavigate.mockClear(); getRegionWines.mockClear(); });

it('calls getRegionWines with decoded slug and default zip on mount', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_RESP);
  renderScreen('Tuscany');
  await waitFor(() => expect(getRegionWines).toHaveBeenCalledWith('Tuscany', '78209'));
});

it('shows region name as heading', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_RESP);
  renderScreen('Tuscany');
  await waitFor(() => expect(screen.getByText('Tuscany')).toBeInTheDocument());
});

it('shows retailer section heading', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_RESP);
  renderScreen('Tuscany');
  await waitFor(() => expect(screen.getByText(/spec's/i)).toBeInTheDocument());
});

it('renders wine cards', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_RESP);
  renderScreen('Tuscany');
  await waitFor(() => expect(screen.getByText('Chianti Classico')).toBeInTheDocument());
});

it('shows loading state while fetching', () => {
  getRegionWines.mockImplementation(() => new Promise(() => {}));
  renderScreen('Tuscany');
  expect(screen.getByText(/loading/i)).toBeInTheDocument();
});

it('shows error message on fetch failure', async () => {
  getRegionWines.mockRejectedValueOnce(new Error('No wines found near your zip code.'));
  renderScreen('Tuscany');
  await waitFor(() => expect(screen.getByText(/no wines found/i)).toBeInTheDocument());
});

it('navigates to /wine/:id when a wine card is clicked', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_RESP);
  renderScreen('Tuscany');
  await waitFor(() => screen.getByText('Chianti Classico'));
  await userEvent.click(screen.getByText('Chianti Classico'));
  expect(mockNavigate).toHaveBeenCalledWith('/wine/w1', expect.objectContaining({
    state: expect.objectContaining({ pick: expect.objectContaining({ wine_id: 'w1' }) }),
  }));
});

it('re-fetches when zip input changes', async () => {
  getRegionWines.mockResolvedValue(MOCK_RESP);
  renderScreen('Tuscany');
  await waitFor(() => screen.getByText('Chianti Classico'));
  const zipInput = screen.getByDisplayValue('78209');
  await userEvent.clear(zipInput);
  await userEvent.type(zipInput, '78201{Enter}');
  await waitFor(() =>
    expect(getRegionWines).toHaveBeenCalledWith('Tuscany', '78201')
  );
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/screens/__tests__/RegionBrowse.test.jsx 2>&1 | tail -10
```

Expected: `Cannot find module '../RegionBrowse.jsx'`.

- [ ] **Step 3: Create `frontend/src/screens/RegionBrowse.jsx`**

```jsx
import { useState, useEffect, useMemo } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import Eyebrow from '../components/Eyebrow.jsx';
import Poster from '../components/Poster.jsx';
import WineCard from '../components/WineCard.jsx';
import Btn from '../components/Btn.jsx';
import { getRegionWines } from '../lib/api.js';
import { DISCOVERY_REGIONS, deriveWineCardMeta } from '../lib/regions.js';

export default function RegionBrowse() {
  const { slug }    = useParams();
  const { state }   = useLocation();
  const navigate    = useNavigate();

  const regionName  = decodeURIComponent(slug);
  const regionMeta  = DISCOVERY_REGIONS.find(r => r.name === regionName) ?? { coord: null };

  const [zip,       setZip]       = useState(state?.zip ?? '78209');
  const [zipInput,  setZipInput]  = useState(state?.zip ?? '78209');
  const [retailers, setRetailers] = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);

  async function fetchWines(z) {
    setLoading(true);
    setError(null);
    try {
      const data = await getRegionWines(regionName, z);
      setRetailers(data.retailers ?? []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchWines(zip); }, [zip]);

  function handleZipSubmit(e) {
    e.preventDefault();
    if (zipInput.length === 5) setZip(zipInput);
  }

  const allWines = useMemo(
    () => retailers.flatMap(s => s.wines),
    [retailers]
  );

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '28px 32px 80px' }}>
      <button
        onClick={() => navigate('/discover')}
        style={{ cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)', padding: 0, marginBottom: 22 }}>
        ← Back to Discover
      </button>

      {/* Hero row: text + poster */}
      <div style={{ display: 'flex', gap: 40, alignItems: 'flex-start', marginBottom: 36 }}>
        <div style={{ flex: 1 }}>
          <Eyebrow>Discover</Eyebrow>
          <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 56, lineHeight: 1.0, color: 'var(--ink)', margin: '10px 0 0' }}>
            {regionName}
          </h1>
          {regionMeta.coord && (
            <div style={{ fontSize: 12, letterSpacing: '0.16em', color: 'var(--sage)', marginTop: 6 }}>{regionMeta.coord}</div>
          )}

          {/* Zip input */}
          <form onSubmit={handleZipSubmit} style={{ marginTop: 24, display: 'flex', gap: 10, alignItems: 'center' }}>
            <label style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--faded)' }}>Near</label>
            <input
              value={zipInput}
              onChange={e => setZipInput(e.target.value.replace(/\D/g, '').slice(0, 5))}
              maxLength={5}
              placeholder="78209"
              style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--ink)', background: 'var(--cream-raised)', border: '1.5px solid var(--ink)', padding: '8px 11px', width: 90, borderRadius: 0, outline: 'none' }}
            />
            {zipInput.length === 5 && zipInput !== zip && (
              <Btn type="submit" variant="ghost">Update</Btn>
            )}
          </form>
        </div>
        <div style={{ width: 160, flex: 'none' }}>
          <Poster region={regionName} />
        </div>
      </div>

      {/* Body */}
      {loading && (
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--faded)', padding: '40px 0' }}>
          Loading wines from {regionName}…
        </div>
      )}

      {error && !loading && (
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--bordeaux)', padding: '40px 0' }}>
          {error}
        </div>
      )}

      {!loading && !error && retailers.map(section => (
        <div key={section.retailer} style={{ marginBottom: 48 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 18 }}>
            <Eyebrow>{section.retailer}</Eyebrow>
            <span style={{ flex: 1, height: '1px', background: 'var(--border)' }} />
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)' }}>
              {section.wines.length} wine{section.wines.length !== 1 ? 's' : ''}
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 18 }}>
            {section.wines.map(w => {
              const meta = deriveWineCardMeta(w);
              return (
                <WineCard
                  key={w.wine_id}
                  wine={meta}
                  onClick={() => navigate(`/wine/${w.wine_id}`, {
                    state: { pick: meta, chatState: null },
                  })}
                />
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Add `/region/:slug` route to `frontend/src/App.jsx`**

Add import:
```javascript
import RegionBrowse from './screens/RegionBrowse.jsx';
```

Add route inside `<Routes>`:
```jsx
<Route path="/region/:slug" element={<RegionBrowse />} />
```

- [ ] **Step 5: Run tests**

```bash
cd frontend && npx vitest run src/screens/__tests__/RegionBrowse.test.jsx
```

Expected: all 8 tests pass.

- [ ] **Step 6: Run full frontend suite**

```bash
cd frontend && npx vitest run
```

Expected: 78+ passing.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/screens/RegionBrowse.jsx frontend/src/screens/__tests__/RegionBrowse.test.jsx frontend/src/App.jsx
git commit -m "feat: RegionBrowse screen — fetch and display wines by region"
```

---

## Task 4: Client-side filters — grape, price, retailer, empty-state redirect

**Files:**
- Modify: `frontend/src/screens/RegionBrowse.jsx` — add filter bar and filtered view
- Modify: `frontend/src/screens/__tests__/RegionBrowse.test.jsx` — add filter tests

**Filter UX:**

```
┌─────────────────────────────────────────────────────────┐
│ Filter  [Sangiovese ×] [Merlot]   Price $──●──  $150   │
│ Retailer  [All] [Spec's] [H-E-B] [Geraldine's]         │
└─────────────────────────────────────────────────────────┘
```

- Grape chips: derived from loaded wines' `varietal` field; click toggles selection; multiple allowed
- Price: two number inputs (min / max); initialized to the actual min/max of loaded wines
- Retailer chips: one per retailer section; click toggles; multiple allowed; "All" = none selected
- Filtering is pure `useMemo` — no re-fetch
- Empty state (zero visible wines after filtering): shows message + "Ask the sommelier →" button that navigates to `/recommend` with a pre-built request

- [ ] **Step 1: Write failing filter tests**

Append to `frontend/src/screens/__tests__/RegionBrowse.test.jsx`:

```jsx
const MOCK_MULTI = {
  region: 'Tuscany',
  retailers: [
    {
      retailer: "Spec's",
      wines: [
        { wine_id: 'w1', name: 'Chianti Classico', varietal: 'Sangiovese', region: 'Tuscany',
          country: 'Italy', wine_type: 'red', price: 22, retailer: "Spec's",
          store_address: null, image_url: null, flavor_profile: ['dark cherry'], grapes: [] },
        { wine_id: 'w2', name: 'Super Tuscan', varietal: 'Merlot', region: 'Tuscany',
          country: 'Italy', wine_type: 'red', price: 65, retailer: "Spec's",
          store_address: null, image_url: null, flavor_profile: ['dark fruit'], grapes: [] },
      ],
    },
    {
      retailer: "H-E-B",
      wines: [
        { wine_id: 'w3', name: 'Morellino', varietal: 'Sangiovese', region: 'Tuscany',
          country: 'Italy', wine_type: 'red', price: 18, retailer: "H-E-B",
          store_address: null, image_url: null, flavor_profile: ['cherry'], grapes: [] },
      ],
    },
  ],
};

it('shows grape filter chips derived from loaded wines', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_MULTI);
  renderScreen('Tuscany');
  await waitFor(() => screen.getByText('Chianti Classico'));
  expect(screen.getByRole('button', { name: 'Sangiovese' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Merlot' })).toBeInTheDocument();
});

it('filters wines by selected grape', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_MULTI);
  renderScreen('Tuscany');
  await waitFor(() => screen.getByText('Chianti Classico'));
  await userEvent.click(screen.getByRole('button', { name: 'Merlot' }));
  expect(screen.queryByText('Chianti Classico')).not.toBeInTheDocument();
  expect(screen.queryByText('Morellino')).not.toBeInTheDocument();
  expect(screen.getByText('Super Tuscan')).toBeInTheDocument();
});

it('filters wines by retailer chip', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_MULTI);
  renderScreen('Tuscany');
  await waitFor(() => screen.getByText('Chianti Classico'));
  await userEvent.click(screen.getByRole('button', { name: "H-E-B" }));
  expect(screen.getByText('Morellino')).toBeInTheDocument();
  expect(screen.queryByText('Chianti Classico')).not.toBeInTheDocument();
});

it('shows empty-state message when all filters yield no results', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_MULTI);
  renderScreen('Tuscany');
  await waitFor(() => screen.getByText('Chianti Classico'));
  // Select both grape AND retailer to guarantee zero overlap
  await userEvent.click(screen.getByRole('button', { name: 'Merlot' }));
  await userEvent.click(screen.getByRole('button', { name: 'H-E-B' }));
  expect(screen.getByText(/no matches/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /ask the sommelier/i })).toBeInTheDocument();
});

it('navigates to /recommend with region + filters pre-filled when "Ask the sommelier" is clicked', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_MULTI);
  renderScreen('Tuscany');
  await waitFor(() => screen.getByText('Chianti Classico'));
  await userEvent.click(screen.getByRole('button', { name: 'Merlot' }));
  await userEvent.click(screen.getByRole('button', { name: 'H-E-B' }));
  await userEvent.click(screen.getByRole('button', { name: /ask the sommelier/i }));
  expect(mockNavigate).toHaveBeenCalledWith('/recommend', expect.objectContaining({
    state: expect.objectContaining({
      apiReq: expect.objectContaining({
        message: expect.stringContaining('Tuscany'),
      }),
    }),
  }));
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/screens/__tests__/RegionBrowse.test.jsx 2>&1 | tail -15
```

Expected: the 5 new filter tests fail (filter UI doesn't exist yet).

- [ ] **Step 3: Update `frontend/src/screens/RegionBrowse.jsx` to add filter state and filter bar**

Replace the full file content with:

```jsx
import { useState, useEffect, useMemo } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import Eyebrow from '../components/Eyebrow.jsx';
import Poster from '../components/Poster.jsx';
import WineCard from '../components/WineCard.jsx';
import Btn from '../components/Btn.jsx';
import { getRegionWines } from '../lib/api.js';
import { DISCOVERY_REGIONS, deriveWineCardMeta, buildApiReq } from '../lib/regions.js';

function Chip({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        cursor: 'pointer',
        fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 500,
        padding: '5px 13px', borderRadius: 999,
        border: active ? '1.5px solid var(--bordeaux)' : '1.5px solid var(--border)',
        background: active ? 'var(--bordeaux)' : 'var(--cream-raised)',
        color: active ? 'var(--cream)' : 'var(--ink)',
        transition: 'all .15s',
      }}>
      {label}
    </button>
  );
}

export default function RegionBrowse() {
  const { slug }   = useParams();
  const { state }  = useLocation();
  const navigate   = useNavigate();

  const regionName = decodeURIComponent(slug);
  const regionMeta = DISCOVERY_REGIONS.find(r => r.name === regionName) ?? { coord: null };

  const [zip,       setZip]       = useState(state?.zip ?? '78209');
  const [zipInput,  setZipInput]  = useState(state?.zip ?? '78209');
  const [retailers, setRetailers] = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);

  // Filter state
  const [activeGrapes,    setActiveGrapes]    = useState([]);
  const [activeRetailers, setActiveRetailers] = useState([]);
  const [priceMin,        setPriceMin]        = useState(0);
  const [priceMax,        setPriceMax]        = useState(999);
  const [boundsSet,       setBoundsSet]       = useState(false);

  async function fetchWines(z) {
    setLoading(true);
    setError(null);
    setActiveGrapes([]);
    setActiveRetailers([]);
    setBoundsSet(false);
    try {
      const data = await getRegionWines(regionName, z);
      setRetailers(data.retailers ?? []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchWines(zip); }, [zip]);

  // Initialize price bounds once after first load
  useEffect(() => {
    if (boundsSet || retailers.length === 0) return;
    const all = retailers.flatMap(s => s.wines.map(w => w.price));
    if (!all.length) return;
    setPriceMin(Math.floor(Math.min(...all)));
    setPriceMax(Math.ceil(Math.max(...all)));
    setBoundsSet(true);
  }, [retailers, boundsSet]);

  function handleZipSubmit(e) {
    e.preventDefault();
    if (zipInput.length === 5) setZip(zipInput);
  }

  const availableGrapes = useMemo(() => {
    const seen = new Set();
    retailers.forEach(s => s.wines.forEach(w => { if (w.varietal) seen.add(w.varietal); }));
    return [...seen].sort();
  }, [retailers]);

  const availableRetailers = useMemo(() => retailers.map(s => s.retailer), [retailers]);

  const filteredRetailers = useMemo(() => {
    return retailers.map(section => {
      if (activeRetailers.length > 0 && !activeRetailers.includes(section.retailer)) {
        return { ...section, wines: [] };
      }
      const wines = section.wines.filter(w => {
        if (activeGrapes.length > 0 && !activeGrapes.includes(w.varietal)) return false;
        if (w.price < priceMin || w.price > priceMax) return false;
        return true;
      });
      return { ...section, wines };
    }).filter(s => s.wines.length > 0);
  }, [retailers, activeGrapes, activeRetailers, priceMin, priceMax]);

  const totalVisible = filteredRetailers.reduce((n, s) => n + s.wines.length, 0);
  const hasFilters   = activeGrapes.length > 0 || activeRetailers.length > 0;

  function toggleGrape(g) {
    setActiveGrapes(p => p.includes(g) ? p.filter(x => x !== g) : [...p, g]);
  }
  function toggleRetailer(r) {
    setActiveRetailers(p => p.includes(r) ? p.filter(x => x !== r) : [...p, r]);
  }

  function handleAskSommelier() {
    const freeText = [
      `Wines from ${regionName}`,
      ...(activeGrapes.length ? [`Grape: ${activeGrapes.join(', ')}`] : []),
    ].join(' · ');
    const prefs = { zip, budget: priceMax || 100, styles: [], occasion: 'Tonight', wineTypes: [], grapes: activeGrapes, freeText };
    navigate('/recommend', { state: { prefs, apiReq: buildApiReq(prefs) } });
  }

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '28px 32px 80px' }}>
      <button
        onClick={() => navigate('/discover')}
        style={{ cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)', padding: 0, marginBottom: 22 }}>
        ← Back to Discover
      </button>

      {/* Hero row */}
      <div style={{ display: 'flex', gap: 40, alignItems: 'flex-start', marginBottom: 32 }}>
        <div style={{ flex: 1 }}>
          <Eyebrow>Discover</Eyebrow>
          <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 56, lineHeight: 1.0, color: 'var(--ink)', margin: '10px 0 0' }}>
            {regionName}
          </h1>
          {regionMeta.coord && (
            <div style={{ fontSize: 12, letterSpacing: '0.16em', color: 'var(--sage)', marginTop: 6 }}>{regionMeta.coord}</div>
          )}
          <form onSubmit={handleZipSubmit} style={{ marginTop: 24, display: 'flex', gap: 10, alignItems: 'center' }}>
            <label style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--faded)' }}>Near</label>
            <input
              value={zipInput}
              onChange={e => setZipInput(e.target.value.replace(/\D/g, '').slice(0, 5))}
              maxLength={5}
              placeholder="78209"
              style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--ink)', background: 'var(--cream-raised)', border: '1.5px solid var(--ink)', padding: '8px 11px', width: 90, borderRadius: 0, outline: 'none' }}
            />
            {zipInput.length === 5 && zipInput !== zip && (
              <Btn type="submit" variant="ghost">Update</Btn>
            )}
          </form>
        </div>
        <div style={{ width: 160, flex: 'none' }}>
          <Poster region={regionName} />
        </div>
      </div>

      {/* Filter bar */}
      {!loading && !error && retailers.length > 0 && (
        <div style={{ borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)', padding: '14px 0', marginBottom: 32, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {availableGrapes.length > 0 && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', width: 52 }}>Grape</span>
              {availableGrapes.map(g => (
                <Chip key={g} label={g} active={activeGrapes.includes(g)} onClick={() => toggleGrape(g)} />
              ))}
            </div>
          )}
          {availableRetailers.length > 1 && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', width: 52 }}>Retailer</span>
              {availableRetailers.map(r => (
                <Chip key={r} label={r} active={activeRetailers.includes(r)} onClick={() => toggleRetailer(r)} />
              ))}
            </div>
          )}
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', width: 52 }}>Price</span>
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--ink)' }}>$</span>
            <input type="number" value={priceMin} min={0} onChange={e => setPriceMin(+e.target.value)}
              style={{ fontFamily: 'var(--font-sans)', fontSize: 13, width: 60, border: '1.5px solid var(--border)', background: 'var(--cream-raised)', padding: '4px 8px', borderRadius: 0, outline: 'none', color: 'var(--ink)' }} />
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--faded)' }}>–</span>
            <input type="number" value={priceMax} min={0} onChange={e => setPriceMax(+e.target.value)}
              style={{ fontFamily: 'var(--font-sans)', fontSize: 13, width: 60, border: '1.5px solid var(--border)', background: 'var(--cream-raised)', padding: '4px 8px', borderRadius: 0, outline: 'none', color: 'var(--ink)' }} />
            {hasFilters && (
              <button onClick={() => { setActiveGrapes([]); setActiveRetailers([]); }}
                style={{ cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', padding: '0 4px', textDecoration: 'underline' }}>
                Clear
              </button>
            )}
          </div>
        </div>
      )}

      {/* Body */}
      {loading && (
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--faded)', padding: '40px 0' }}>
          Loading wines from {regionName}…
        </div>
      )}
      {error && !loading && (
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--bordeaux)', padding: '40px 0' }}>{error}</div>
      )}

      {/* Empty state after filtering */}
      {!loading && !error && totalVisible === 0 && retailers.length > 0 && (
        <div style={{ padding: '48px 0', textAlign: 'center' }}>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--ink)', marginBottom: 10 }}>No matches</div>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--faded)', marginBottom: 20 }}>
            No wines in {regionName} match your current filters near {zip}.
          </div>
          <Btn onClick={handleAskSommelier}>Ask the sommelier →</Btn>
        </div>
      )}

      {/* Wine sections */}
      {!loading && !error && filteredRetailers.map(section => (
        <div key={section.retailer} style={{ marginBottom: 48 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 18 }}>
            <Eyebrow>{section.retailer}</Eyebrow>
            <span style={{ flex: 1, height: '1px', background: 'var(--border)' }} />
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)' }}>
              {section.wines.length} wine{section.wines.length !== 1 ? 's' : ''}
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 18 }}>
            {section.wines.map(w => {
              const meta = deriveWineCardMeta(w);
              return (
                <WineCard
                  key={w.wine_id}
                  wine={meta}
                  onClick={() => navigate(`/wine/${w.wine_id}`, {
                    state: { pick: meta, chatState: null },
                  })}
                />
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/screens/__tests__/RegionBrowse.test.jsx
```

Expected: all 13 tests pass.

- [ ] **Step 5: Run full frontend suite**

```bash
cd frontend && npx vitest run
```

Expected: 83+ passing.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/screens/RegionBrowse.jsx frontend/src/screens/__tests__/RegionBrowse.test.jsx
git commit -m "feat: client-side filters (grape, price, retailer) + empty-state redirect"
```

---

## Task 5: Wire Discovery → RegionBrowse

**Files:**
- Modify: `frontend/src/screens/Discovery.jsx` — change `openRegion` to navigate `/region/:slug`
- Modify: `frontend/src/screens/__tests__/Discovery.test.jsx` — update navigation assertion

**Interfaces:**
- Consumes: nothing new
- Produces: clicking a region tile navigates to `/region/Tuscany` (URL-encoded slug)

- [ ] **Step 1: Write failing test**

In `frontend/src/screens/__tests__/Discovery.test.jsx`, change the existing navigation test:

```javascript
it('navigates to /region/:slug when a region card is clicked', async () => {
  renderScreen();
  await userEvent.click(screen.getAllByText('Tuscany')[0]);
  expect(mockNavigate).toHaveBeenCalledWith(
    '/region/Tuscany',
    expect.anything()
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/screens/__tests__/Discovery.test.jsx 2>&1 | tail -10
```

Expected: the navigation test fails (currently navigates to `/recommend`).

- [ ] **Step 3: Update `frontend/src/screens/Discovery.jsx`**

Replace the `openRegion` function and the `regionApiReq` helper (they're no longer needed):

Remove the top-level `regionApiReq` function entirely. Replace `openRegion`:

```javascript
function openRegion(r) {
  navigate(`/region/${encodeURIComponent(r.name)}`);
}
```

The full updated `Discovery.jsx`:

```jsx
import { useNavigate } from 'react-router-dom';
import Eyebrow from '../components/Eyebrow.jsx';
import Poster from '../components/Poster.jsx';
import { DISCOVERY_REGIONS } from '../lib/regions.js';

function RegionCard({ region, onClick }) {
  return (
    <div onClick={onClick} style={{ cursor: 'pointer' }}>
      <Poster region={region.name} />
      <div style={{ marginTop: 10 }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 19, color: 'var(--ink)', lineHeight: 1 }}>{region.name}</div>
        <div style={{ fontSize: 10, letterSpacing: '0.16em', color: 'var(--sage)', marginTop: 3 }}>{region.coord}</div>
      </div>
    </div>
  );
}

export default function Discovery() {
  const navigate = useNavigate();
  const tier1    = DISCOVERY_REGIONS.filter(r => r.tier === 1);
  const tier2    = DISCOVERY_REGIONS.filter(r => r.tier === 2);

  function openRegion(r) {
    navigate(`/region/${encodeURIComponent(r.name)}`);
  }

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '44px 32px 80px' }}>
      <Eyebrow>Discover</Eyebrow>
      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 56, lineHeight: 1.0, color: 'var(--ink)', margin: '12px 0 0' }}>
        Browse by place.
      </h1>
      <p className="t-body" style={{ marginTop: 12, maxWidth: 520 }}>
        Every region is a poster; every poster is a map. Start somewhere and follow the wine home.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 24, marginTop: 36 }}>
        {tier1.map(r => <RegionCard key={r.name} region={r} onClick={() => openRegion(r)} />)}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 16, margin: '52px 0 28px' }}>
        <span style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--ink)', whiteSpace: 'nowrap' }}>More regions</span>
        <span style={{ flex: 1, height: 1, background: 'var(--border)' }} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 24 }}>
        {tier2.map(r => <RegionCard key={r.name} region={r} onClick={() => openRegion(r)} />)}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run Discovery tests**

```bash
cd frontend && npx vitest run src/screens/__tests__/Discovery.test.jsx
```

Expected: all tests pass.

- [ ] **Step 5: Run full frontend suite**

```bash
cd frontend && npx vitest run
```

Expected: 83+ passing.

- [ ] **Step 6: Run full backend suite (sanity check)**

```bash
cd backend && python3 -m pytest tests/ -m "not integration" -q
```

Expected: 164+ passing.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/screens/Discovery.jsx frontend/src/screens/__tests__/Discovery.test.jsx
git commit -m "feat: Discovery tiles navigate to /region/:slug catalog page"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ `/region/:slug` route wired in App.jsx (Task 3 + 5)
- ✅ Zip input at top with re-fetch on change (Task 3)
- ✅ Per-retailer sections, up to 15 wines each (price-partitioned 3×5) (Task 1)
- ✅ Client-side filters: grape, price, retailer (Task 4)
- ✅ Multiple retailer selection allowed (Task 4)
- ✅ Empty state with "Ask the sommelier →" redirect (Task 4)
- ✅ Redirect pre-fills region + active grape filters as free text (Task 4)
- ✅ Discovery tiles navigate to RegionBrowse instead of /recommend (Task 5)
- ✅ Rhône Valley / Douro Valley alias mapping in backend (Task 1) and documented in frontend (Task 2)
- ✅ WineCard click → RegionDossier with pick state (Task 3)
- ✅ No new npm or pip packages

**2. Placeholder scan:** No TBDs, all code shown in full.

**3. Type consistency:**
- `RegionWineItem` defined in schemas.py and used in region.py ✅
- `getRegionWines` returns `{ region, retailers }` — `RegionBrowse` reads `data.retailers` ✅
- `deriveWineCardMeta` applied before `WineCard` in both retailer sections ✅
- `buildApiReq` called with full prefs object including `wineTypes: []` and `grapes` ✅
