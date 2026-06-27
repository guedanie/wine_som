# Preference Filters & UX Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add wine-type multi-select and grape varietal advanced search to the preference screen, enrich the wine dossier with description text and store address, and persist recommendations when the user navigates back from a dossier.

**Architecture:** Tasks 1 and 2 both touch `PreferenceCapture.jsx` and `backend/api/schemas.py` — they must be implemented sequentially. Tasks 3 and 4 are independent and touch disjoint files. All four tasks have their own test cycles. No new dependencies are introduced.

**Tech Stack:** Python 3.9 / FastAPI / Pydantic v2 · Vite 5 / React 19 / React Router v7 / Vitest 4 · Supabase (cloud DB)

## Global Constraints

- Python 3.9 only — use `Optional[X]` / `List[X]` from `typing`, never `X | None` or `list[X]`
- Run all backend tests from `backend/` directory: `python3 -m pytest tests/ -m "not integration" -q`
- Run all frontend tests from `frontend/` directory: `npx vitest run`
- All 152 backend unit tests and 59 frontend tests must stay green after every task
- `beforeEach` callbacks in Vitest must use block bodies — `beforeEach(() => { fn(); })` not `beforeEach(() => fn())` — the concise form returns a value that Vitest v4 treats as a thenable and hangs
- No new npm packages; no new pip packages
- Design tokens via CSS vars (`var(--bordeaux)`, `var(--ink)`, etc.) — never hardcode hex
- `border-radius: 0` for all cards, chips, and buttons unless explicitly noted as pill/chat surface
- Keep every file under ~200 lines; do not restructure files beyond what the task requires

---

## File Map

| File | Tasks | Change |
|---|---|---|
| `backend/api/schemas.py` | 1, 2, 3 | Add `wine_types`, `grapes` to `RecommendRequest`; add `store_address` to `WinePick` |
| `backend/api/routers/recommend.py` | 1, 2, 3 | Wine-type pre-filter; grapes pass-through; store address in INVENTORY_SELECT + enriched_picks |
| `backend/recommendation/intent.py` | 2 | Add `grapes` param to `intent_from_request` |
| `backend/tests/test_recommend_api.py` | 1, 2, 3 | Keep green through schema additions |
| `frontend/src/lib/regions.js` | 1, 2 | Update `buildApiReq`; add `VARIETAL_OPTS` |
| `frontend/src/screens/PreferenceCapture.jsx` | 1, 2 | Wine-type chips; collapsible varietal picker |
| `frontend/src/screens/__tests__/PreferenceCapture.test.jsx` | 1, 2 | Tests for new UI state |
| `frontend/src/screens/RegionDossier.jsx` | 3, 4 | Show description + store address; smart back navigation |
| `frontend/src/screens/__tests__/RegionDossier.test.jsx` | 3, 4 | Tests for new fields + back nav |
| `frontend/src/screens/ChatRecommend.jsx` | 4 | Include chatState when navigating to dossier; restore on mount |
| `frontend/src/screens/__tests__/ChatRecommend.test.jsx` | 4 | Test no API call when _restored is present |

---

## Task 1: Wine Type Multi-Select

Add four wine-type chips (Red / White / Rosé / Sparkling) to `PreferenceCapture`. Multiple selection is allowed. The selection is sent to the backend as `wine_types: List[str]` and used to pre-filter candidates before scoring.

**Files:**
- Modify: `backend/api/schemas.py`
- Modify: `backend/api/routers/recommend.py`
- Modify: `backend/tests/test_recommend_api.py`
- Modify: `frontend/src/lib/regions.js`
- Modify: `frontend/src/screens/PreferenceCapture.jsx`
- Modify: `frontend/src/screens/__tests__/PreferenceCapture.test.jsx`

**Interfaces:**
- Produces: `RecommendRequest.wine_types: List[str]` (backend); `prefs.wineTypes: string[]` + `apiReq.wine_types: string[]` (frontend)

---

- [ ] **Step 1: Write failing backend schema test**

Add to `backend/tests/test_recommend_api.py` — insert after the existing imports:

```python
def test_recommend_request_accepts_wine_types():
    from api.schemas import RecommendRequest
    req = RecommendRequest(zip_code="78209", wine_types=["red", "white"])
    assert req.wine_types == ["red", "white"]

def test_recommend_request_wine_types_defaults_empty():
    from api.schemas import RecommendRequest
    req = RecommendRequest(zip_code="78209")
    assert req.wine_types == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python3 -m pytest tests/test_recommend_api.py::test_recommend_request_accepts_wine_types -v
```
Expected: FAIL with `ValidationError` — `wine_types` field does not exist yet.

- [ ] **Step 3: Add `wine_types` to `RecommendRequest` in `backend/api/schemas.py`**

Replace the existing `RecommendRequest` class with:

```python
class RecommendRequest(BaseModel):
    zip_code: str
    budget_min: float = 10.0
    budget_max: float = 50.0
    style_preferences: List[str] = []
    avoid: List[str] = []
    wine_type: Optional[str] = None          # legacy single-type (kept for compat)
    wine_types: List[str] = []               # multi-select; takes precedence over wine_type
    message: str = "Recommend wines based on my preferences"
    conversation_history: Optional[List[Dict[str, Any]]] = None
```

- [ ] **Step 4: Add wine-type pre-filter in `backend/api/routers/recommend.py`**

In `recommend.py`, after the existing retailer pre-filter block (around line 182), add:

```python
    # Wine type filter (multi-select). wine_types takes precedence; fall back to legacy wine_type.
    effective_types = req.wine_types or ([req.wine_type] if req.wine_type else [])
    if effective_types:
        type_pool = [c for c in candidates if c.get("wine_type") in effective_types]
        if type_pool:
            candidates = type_pool
            logger.info("TYPE FILTER | %s → %d candidates", effective_types, len(candidates))
```

Place this block immediately after the retailer pre-filter block and before the `top = score_candidates(...)` call.

- [ ] **Step 5: Run backend tests to verify they pass**

```bash
cd backend
python3 -m pytest tests/ -m "not integration" -q
```
Expected: 154 passed (152 original + 2 new).

- [ ] **Step 6: Write failing frontend test for wine type chips**

Add to `frontend/src/screens/__tests__/PreferenceCapture.test.jsx`:

```javascript
it('renders wine type chips for Red, White, Rosé, Sparkling', () => {
  renderScreen();
  expect(screen.getByRole('button', { name: /^red$/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /^white$/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /rosé/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /sparkling/i })).toBeInTheDocument();
});

it('selecting a wine type chip includes it in apiReq.wine_types', () => {
  renderScreen();
  fireEvent.click(screen.getByRole('button', { name: /^red$/i }));
  fireEvent.click(screen.getByRole('button', { name: /find wines/i }));
  expect(mockNavigate).toHaveBeenCalledWith('/recommend', expect.objectContaining({
    state: expect.objectContaining({
      apiReq: expect.objectContaining({ wine_types: ['red'] }),
    }),
  }));
});
```

- [ ] **Step 7: Run frontend tests to verify they fail**

```bash
cd frontend
npx vitest run src/screens/__tests__/PreferenceCapture.test.jsx
```
Expected: 2 new tests FAIL — no wine type chips exist yet.

- [ ] **Step 8: Update `buildApiReq` in `frontend/src/lib/regions.js`**

Replace the existing `buildApiReq` function:

```javascript
export function buildApiReq(prefs) {
  const tags = [...new Set(prefs.styles.flatMap(s => STYLE_TAG_MAP[s] ?? []))];
  // wine_types from explicit chip selection; fall back to style-derived type if none selected
  const wineTypes = (prefs.wineTypes ?? []).length > 0
    ? prefs.wineTypes
    : [prefs.styles.map(s => STYLE_WINE_TYPE[s]).find(Boolean)].filter(Boolean);
  return {
    zip_code:          prefs.zip,
    budget_min:        10,
    budget_max:        prefs.budget,
    style_preferences: tags,
    wine_types:        wineTypes,
    message:           occasionMessage(prefs.occasion),
  };
}
```

- [ ] **Step 9: Add wine type chips to `frontend/src/screens/PreferenceCapture.jsx`**

Add `WINE_TYPES` constant near the top of the file (after `STYLE_OPTS`):

```javascript
const WINE_TYPES = ['Red', 'White', 'Rosé', 'Sparkling'];
```

Add `wineTypes` state in the component body (after the existing `useState` calls):

```javascript
const [wineTypes, setWineTypes] = useState([]);
const toggleType = t => setWineTypes(p => p.includes(t) ? p.filter(x => x !== t) : [...p, t]);
```

Update `handleSubmit` to include `wineTypes` in prefs and `buildApiReq`:

```javascript
const handleSubmit = () => {
  const prefs  = { zip, budget, styles, occasion, wineTypes };
  const apiReq = buildApiReq(prefs);
  navigate('/recommend', { state: { prefs, apiReq } });
};
```

Add the wine type chip row to the JSX — insert it between the zip/budget row and the style cards section (`<div style={{ marginTop: 32 }}>`):

```jsx
      <div style={{ marginTop: 28 }}>
        <Eyebrow>Wine type</Eyebrow>
        <div style={{ display: 'flex', gap: 10, marginTop: 12, flexWrap: 'wrap' }}>
          {WINE_TYPES.map(t => {
            const on = wineTypes.includes(t.toLowerCase());
            return (
              <button key={t} onClick={() => toggleType(t.toLowerCase())}
                style={{ cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 500, padding: '8px 18px', borderRadius: 0, border: on ? '1.5px solid var(--bordeaux)' : '1.5px solid var(--border)', background: on ? 'var(--bordeaux)' : 'var(--cream-raised)', color: on ? 'var(--cream)' : 'var(--ink)', transition: 'all .15s var(--ease)' }}>
                {t}
              </button>
            );
          })}
          <span style={{ alignSelf: 'center', fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--faded)' }}>
            {wineTypes.length === 0 ? 'Any type' : ''}
          </span>
        </div>
      </div>
```

- [ ] **Step 10: Run all frontend tests**

```bash
cd frontend
npx vitest run
```
Expected: 61 passed (59 original + 2 new).

- [ ] **Step 11: Commit**

```bash
git add backend/api/schemas.py backend/api/routers/recommend.py backend/tests/test_recommend_api.py \
        frontend/src/lib/regions.js frontend/src/screens/PreferenceCapture.jsx \
        frontend/src/screens/__tests__/PreferenceCapture.test.jsx
git commit -m "feat: wine type multi-select on PreferenceCapture"
```

---

## Task 2: Grape Varietal Advanced Search

Add a collapsible "Advanced search" section below the style cards showing 12 curated varietal chips. Selected varietals are sent to the backend as `grapes: List[str]` and boost candidate scoring via the existing knowledge-based scorer.

**Files:**
- Modify: `backend/api/schemas.py`
- Modify: `backend/api/routers/recommend.py`
- Modify: `backend/recommendation/intent.py`
- Modify: `backend/tests/test_recommend_api.py`
- Modify: `frontend/src/lib/regions.js`
- Modify: `frontend/src/screens/PreferenceCapture.jsx`
- Modify: `frontend/src/screens/__tests__/PreferenceCapture.test.jsx`

**Interfaces:**
- Consumes: `RecommendRequest.wine_types` from Task 1
- Produces: `RecommendRequest.grapes: List[str]`; `intent_from_request(grapes=...)` passes list to scorer's `want_grapes`

---

- [ ] **Step 1: Write failing backend schema test**

Add to `backend/tests/test_recommend_api.py`:

```python
def test_recommend_request_accepts_grapes():
    from api.schemas import RecommendRequest
    req = RecommendRequest(zip_code="78209", grapes=["Cabernet Sauvignon", "Merlot"])
    assert req.grapes == ["Cabernet Sauvignon", "Merlot"]

def test_recommend_request_grapes_defaults_empty():
    from api.schemas import RecommendRequest
    req = RecommendRequest(zip_code="78209")
    assert req.grapes == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python3 -m pytest tests/test_recommend_api.py::test_recommend_request_accepts_grapes -v
```
Expected: FAIL — `grapes` field does not exist yet.

- [ ] **Step 3: Add `grapes` to `RecommendRequest` in `backend/api/schemas.py`**

In the `RecommendRequest` class (already has `wine_types` from Task 1), add the `grapes` field after `wine_types`:

```python
class RecommendRequest(BaseModel):
    zip_code: str
    budget_min: float = 10.0
    budget_max: float = 50.0
    style_preferences: List[str] = []
    avoid: List[str] = []
    wine_type: Optional[str] = None
    wine_types: List[str] = []
    grapes: List[str] = []                   # explicit varietal filter from advanced search
    message: str = "Recommend wines based on my preferences"
    conversation_history: Optional[List[Dict[str, Any]]] = None
```

- [ ] **Step 4: Update `intent_from_request` in `backend/recommendation/intent.py`**

Replace the existing `intent_from_request` function:

```python
def intent_from_request(wine_type: Optional[str], style_preferences: List[str],
                        avoid: List[str], budget_min: float, budget_max: float,
                        grapes: Optional[List[str]] = None) -> Dict[str, Any]:
    """Build a resolved-intent dict from explicit request fields only."""
    return {
        "wine_type": wine_type,
        "body": None,
        "flavors": list(style_preferences or []),
        "grapes": list(grapes or []),
        "region": None,
        "avoid": list(avoid or []),
        "budget_min": budget_min,
        "budget_max": budget_max,
    }
```

- [ ] **Step 5: Pass `grapes` in the recommend router**

In `backend/api/routers/recommend.py`, find the `intent_from_request` call (around line 164) and update it:

```python
    explicit = intent_from_request(
        wine_type=req.wine_type,
        style_preferences=req.style_preferences,
        avoid=req.avoid,
        budget_min=req.budget_min,
        budget_max=req.budget_max,
        grapes=req.grapes,
    )
```

- [ ] **Step 6: Run backend tests**

```bash
cd backend
python3 -m pytest tests/ -m "not integration" -q
```
Expected: 156 passed.

- [ ] **Step 7: Write failing frontend tests for varietal advanced search**

Add to `frontend/src/screens/__tests__/PreferenceCapture.test.jsx`:

```javascript
it('does not show varietal chips until Advanced search is expanded', () => {
  renderScreen();
  expect(screen.queryByRole('button', { name: /cabernet sauvignon/i })).not.toBeInTheDocument();
});

it('shows varietal chips after clicking Advanced search toggle', () => {
  renderScreen();
  fireEvent.click(screen.getByRole('button', { name: /advanced search/i }));
  expect(screen.getByRole('button', { name: /cabernet sauvignon/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /chardonnay/i })).toBeInTheDocument();
});

it('selected varietals are included in apiReq.grapes', () => {
  renderScreen();
  fireEvent.click(screen.getByRole('button', { name: /advanced search/i }));
  fireEvent.click(screen.getByRole('button', { name: /cabernet sauvignon/i }));
  fireEvent.click(screen.getByRole('button', { name: /find wines/i }));
  expect(mockNavigate).toHaveBeenCalledWith('/recommend', expect.objectContaining({
    state: expect.objectContaining({
      apiReq: expect.objectContaining({ grapes: ['Cabernet Sauvignon'] }),
    }),
  }));
});
```

- [ ] **Step 8: Run frontend tests to verify they fail**

```bash
cd frontend
npx vitest run src/screens/__tests__/PreferenceCapture.test.jsx
```
Expected: 3 new tests FAIL.

- [ ] **Step 9: Add `VARIETAL_OPTS` to `frontend/src/lib/regions.js`**

Add this constant anywhere in `regions.js` (e.g., after `STYLE_WINE_TYPE`):

```javascript
export const VARIETAL_OPTS = [
  'Cabernet Sauvignon', 'Merlot', 'Pinot Noir', 'Malbec', 'Syrah',
  'Zinfandel', 'Sangiovese', 'Chardonnay', 'Sauvignon Blanc',
  'Riesling', 'Pinot Grigio', 'Albariño',
];
```

Also update `buildApiReq` to pass `grapes` through:

```javascript
export function buildApiReq(prefs) {
  const tags = [...new Set(prefs.styles.flatMap(s => STYLE_TAG_MAP[s] ?? []))];
  const wineTypes = (prefs.wineTypes ?? []).length > 0
    ? prefs.wineTypes
    : [prefs.styles.map(s => STYLE_WINE_TYPE[s]).find(Boolean)].filter(Boolean);
  return {
    zip_code:          prefs.zip,
    budget_min:        10,
    budget_max:        prefs.budget,
    style_preferences: tags,
    wine_types:        wineTypes,
    grapes:            prefs.grapes ?? [],
    message:           occasionMessage(prefs.occasion),
  };
}
```

- [ ] **Step 10: Add varietal advanced search to `frontend/src/screens/PreferenceCapture.jsx`**

Add import at the top:

```javascript
import { buildApiReq, VARIETAL_OPTS } from '../lib/regions.js';
```

Add state in the component body (after the `wineTypes` state from Task 1):

```javascript
const [grapes,      setGrapes]      = useState([]);
const [advancedOpen, setAdvancedOpen] = useState(false);
const toggleGrape = g => setGrapes(p => p.includes(g) ? p.filter(x => x !== g) : [...p, g]);
```

Update `handleSubmit` to include `grapes`:

```javascript
const handleSubmit = () => {
  const prefs  = { zip, budget, styles, occasion, wineTypes, grapes };
  const apiReq = buildApiReq(prefs);
  navigate('/recommend', { state: { prefs, apiReq } });
};
```

Add the collapsible section to the JSX — insert it between the style cards section and the occasion/submit row:

```jsx
      <div style={{ marginTop: 24 }}>
        <button
          onClick={() => setAdvancedOpen(o => !o)}
          style={{ cursor: 'pointer', background: 'none', border: 'none', padding: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Eyebrow>Advanced search</Eyebrow>
          <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)' }}>
            {advancedOpen ? '▲' : '▼'}
          </span>
        </button>

        {advancedOpen && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--faded)', marginBottom: 10 }}>
              Filter by grape varietal — any that match
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {VARIETAL_OPTS.map(g => {
                const on = grapes.includes(g);
                return (
                  <button key={g} onClick={() => toggleGrape(g)}
                    style={{ cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 12, padding: '6px 14px', borderRadius: 0, border: on ? '1.5px solid var(--bordeaux)' : '1.5px solid var(--border)', background: on ? 'var(--bordeaux)' : 'var(--cream-raised)', color: on ? 'var(--cream)' : 'var(--ink)', transition: 'all .15s var(--ease)' }}>
                    {g}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
```

- [ ] **Step 11: Run all frontend tests**

```bash
cd frontend
npx vitest run
```
Expected: 64 passed (61 from Task 1 + 3 new).

- [ ] **Step 12: Commit**

```bash
git add backend/api/schemas.py backend/api/routers/recommend.py backend/recommendation/intent.py \
        backend/tests/test_recommend_api.py frontend/src/lib/regions.js \
        frontend/src/screens/PreferenceCapture.jsx \
        frontend/src/screens/__tests__/PreferenceCapture.test.jsx
git commit -m "feat: grape varietal advanced search on PreferenceCapture"
```

---

## Task 3: Wine Dossier Enhancements — Description + Store Address

Show the wine's producer description (already in `wine_details.description` from the API) and the store's street address on the dossier page. The address requires a one-line change to the backend's `INVENTORY_SELECT` and a new `store_address` field on the pick.

**Files:**
- Modify: `backend/api/routers/recommend.py`
- Modify: `backend/api/schemas.py`
- Modify: `backend/tests/test_recommend_api.py`
- Modify: `frontend/src/screens/RegionDossier.jsx`
- Modify: `frontend/src/screens/__tests__/RegionDossier.test.jsx`

**Interfaces:**
- Produces: `WinePick.store_address: Optional[str]` — available as `pick.store_address` in the frontend

---

- [ ] **Step 1: Write failing backend test for store_address in picks**

Add to `backend/tests/test_recommend_api.py` (use `@pytest.mark.asyncio` like all other tests in this file):

```python
_WINE_ROW_WITH_ADDRESS = {
    "price": 22.0,
    "curbside_price": None,
    "wine_id": "abc-123",
    "stores": {
        "retailer_name": "Spec's",
        "zip_code": "78209",
        "address": "1000 Austin Hwy, San Antonio, TX 78209",
    },
    "wines": {
        "id": "abc-123", "name": "Test Malbec", "varietal": "Malbec",
        "region": "Mendoza", "country": "Argentina", "wine_type": "red",
        "grapes": ["Malbec"], "body": "full",
        "wine_details": {
            "tasting_notes": "dark fruit",
            "flavor_profile": ["dark fruit"],
            "structure_profile": {},
            "grapeminds_enriched_at": "2026-06-03T00:00:00Z",
        },
    },
}

@pytest.mark.asyncio
async def test_recommend_picks_include_store_address():
    """store_address should flow through from the stores join to the pick."""
    with patch("recommendation.claude_client.anthropic.Anthropic", _make_anthropic_mock()), \
         patch("api.routers.recommend.get_supabase_client",
               return_value=_make_db_mock([_WINE_ROW_WITH_ADDRESS])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 15.0, "budget_max": 35.0})
    assert response.status_code == 200
    pick = response.json()["picks"][0]
    assert pick["store_address"] == "1000 Austin Hwy, San Antonio, TX 78209"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
python3 -m pytest tests/test_recommend_api.py::test_recommend_picks_include_store_address -v
```
Expected: FAIL — `store_address` key not in pick.

- [ ] **Step 3: Add `store_address` to `WinePick` in `backend/api/schemas.py`**

In `schemas.py`, update `WinePick`:

```python
class WinePick(BaseModel):
    wine_id: str
    name: str
    price: float
    retailer: str
    why: str
    store_address: Optional[str] = None
```

- [ ] **Step 4: Update `INVENTORY_SELECT` and candidate-building in `backend/api/routers/recommend.py`**

**4a.** In the `INVENTORY_SELECT` constant, add `address` to the stores fields:

```python
INVENTORY_SELECT = (
    "price, curbside_price, wine_id,"
    "stores!inner(retailer_name, zip_code, address),"
    "wines(id, name, varietal, region, country, wine_type, grapes, abv, body,"
    "wine_details(tasting_notes, flavor_profile, structure_profile, grapeminds_enriched_at))"
)
```

**4b.** In the candidate-building loop (the `by_retailer.setdefault(retailer, []).append({...})` block), add `store_address`:

```python
        retailer = (row.get("stores") or {}).get("retailer_name") or "unknown"
        store_address = (row.get("stores") or {}).get("address") or None
        by_retailer.setdefault(retailer, []).append({
            "wine_id": wine.get("id"),
            "name": wine.get("name"),
            "varietal": wine.get("varietal"),
            "region": wine.get("region"),
            "country": wine.get("country"),
            "wine_type": wine.get("wine_type"),
            "grapes": wine.get("grapes") or [],
            "body": wine.get("body"),
            "tasting_notes": details.get("tasting_notes"),
            "flavor_profile": details.get("flavor_profile") or [],
            "structure_profile": details.get("structure_profile") or {},
            "price": row.get("price"),
            "retailer": retailer,
            "store_address": store_address,
            "tier": 1 if enriched else 2,
        })
```

**4c.** In `enriched_picks` assembly, include `store_address`:

```python
        enriched_picks.append({
            "wine_id": cand["wine_id"],
            "name": cand.get("name") or p.get("name"),
            "price": cand.get("price") if cand.get("price") is not None else p.get("price"),
            "retailer": cand.get("retailer") or p.get("retailer"),
            "store_address": cand.get("store_address"),
            "why": p.get("why", ""),
        })
```

- [ ] **Step 5: Update `_make_db_mock` in `backend/tests/test_recommend_api.py` and existing `WINE_ROW`**

The `WINE_ROW` constant needs a `stores.address` field so existing tests keep working:

```python
WINE_ROW = {
    "price": 22.0,
    "curbside_price": None,
    "wine_id": "abc-123",
    "stores": {
        "retailer_name": "Geraldine's",
        "store_name": "Geraldine's",
        "zip_code": "78209",
        "address": "7700 Broadway St, San Antonio, TX 78209",
    },
    "wines": {
        "id": "abc-123",
        "name": "Test Malbec",
        "varietal": "Malbec",
        "region": "Mendoza",
        "country": "Argentina",
        "wine_type": "red",
        "wine_details": [{
            "tasting_notes": "dark fruit, plum, chocolate",
            "flavor_profile": ["dark fruit", "plum"],
            "structure_profile": {"body": 8, "tannins": 7, "acidity": 5},
            "grapeminds_enriched_at": "2026-06-03T00:00:00Z",
        }],
    },
}
```

Also update `_wine_row()` to include address in the stores dict:

```python
def _wine_row(name="Test Malbec", wine_id="abc-123", enriched=True, varietal="Malbec",
              region="Mendoza", grapes=None, body="full", price=22.0):
    return {
        "price": price, "curbside_price": None, "wine_id": wine_id,
        "stores": {
            "retailer_name": "Spec's",
            "store_name": "Spec's",
            "zip_code": "78209",
            "address": "1000 Austin Hwy, San Antonio, TX 78209",
        },
        "wines": {
            "id": wine_id, "name": name, "varietal": varietal, "region": region,
            "country": "Argentina", "wine_type": "red", "grapes": grapes or ["Malbec"],
            "body": body,
            "wine_details": [{
                "tasting_notes": "dark fruit, plum",
                "flavor_profile": ["dark fruit"],
                "structure_profile": {},
                "grapeminds_enriched_at": "2026-06-03T00:00:00Z" if enriched else None,
            }],
        },
    }
```

- [ ] **Step 6: Run backend tests**

```bash
cd backend
python3 -m pytest tests/ -m "not integration" -q
```
Expected: 157 passed.

- [ ] **Step 7: Write failing frontend tests for dossier enhancements**

In `frontend/src/screens/__tests__/RegionDossier.test.jsx`, add these tests. Also update the `wineDetail` fixture to include `description`, and update `pick` to include `store_address`:

```javascript
const pick = {
  wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's",
  why: 'Great structure.', region: 'Paso Robles',
  tagline: 'PASO ROBLES', coord: '35.6°N · 120.7°W',
  store_address: '1000 Austin Hwy, San Antonio, TX 78209',
};

const wineDetail = {
  id: 'uuid-1', name: 'Esprit de Tablas', brand: 'Tablas Creek',
  varietal: 'GSM Blend', region: 'Paso Robles', vintage_year: 2021,
  wine_details: {
    description: 'A classic Paso Robles blend of Grenache, Syrah and Mourvèdre.',
    tasting_notes: 'Dark cherry, garrigue and leather.',
    flavor_profile: ['dark cherry', 'garrigue', 'leather'],
    structure_profile: { body: 8, tannins: 7, acidity: 5, finish: 8 },
    grapeminds_enriched_at: '2026-01-01',
  },
};
```

Add new tests:

```javascript
it('shows wine description after getWine resolves', async () => {
  getWine.mockResolvedValue(wineDetail);
  renderScreen();
  await waitFor(() =>
    expect(screen.getByText('A classic Paso Robles blend of Grenache, Syrah and Mourvèdre.')).toBeInTheDocument()
  );
});

it('shows store address in the availability section', async () => {
  getWine.mockResolvedValue(wineDetail);
  renderScreen();
  await waitFor(() => screen.getByText('Structure'));
  expect(screen.getByText('1000 Austin Hwy, San Antonio, TX 78209')).toBeInTheDocument();
});
```

- [ ] **Step 8: Run frontend tests to verify they fail**

```bash
cd frontend
npx vitest run src/screens/__tests__/RegionDossier.test.jsx
```
Expected: 2 new tests FAIL.

- [ ] **Step 9: Update `RegionDossier.jsx` to show description and store address**

**9a.** Show description — add after the `{details.tasting_notes && ...}` block (around line 69):

```jsx
          {details.description && (
            <p className="t-body" style={{ marginTop: 14, maxWidth: 540, color: 'var(--ink-2)' }}>
              {details.description}
            </p>
          )}
```

**9b.** Show store address in the "Available near you" block. The current retailer row in `RegionDossier.jsx` (inside the `{detail && ...}` block) shows only the retailer name. Update it to include the address line below:

```jsx
                  <div style={{ flex: 1 }}>
                    <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>
                      {pick.retailer}
                    </div>
                    {pick.store_address && (
                      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--faded)', marginTop: 2 }}>
                        {pick.store_address}
                      </div>
                    )}
                  </div>
```

- [ ] **Step 10: Run all frontend tests**

```bash
cd frontend
npx vitest run
```
Expected: 66 passed (64 from Task 2 + 2 new).

- [ ] **Step 11: Commit**

```bash
git add backend/api/schemas.py backend/api/routers/recommend.py backend/tests/test_recommend_api.py \
        frontend/src/screens/RegionDossier.jsx \
        frontend/src/screens/__tests__/RegionDossier.test.jsx
git commit -m "feat: dossier shows wine description and store address"
```

---

## Task 4: Persist Recommendations on Back Navigation

When the user taps a wine card in `ChatRecommend` and then presses "← Back" on the dossier, the recommendation screen should restore its previous state (messages + wine cards) instead of firing a new API call.

**Mechanism:** When navigating to the dossier, `ChatRecommend` embeds the current chat state (`messages`, `picks`, `prefs`, `apiReq`) in the navigation state. The dossier's back button reads this and navigates to `/recommend` with a `_restored` key. `ChatRecommend` on mount checks for `_restored` and initialises from it instead of calling the API.

**Files:**
- Modify: `frontend/src/screens/ChatRecommend.jsx`
- Modify: `frontend/src/screens/RegionDossier.jsx`
- Modify: `frontend/src/screens/__tests__/ChatRecommend.test.jsx`
- Modify: `frontend/src/screens/__tests__/RegionDossier.test.jsx`

**Interfaces:**
- `navigate('/wine/:id', { state: { pick, chatState: { messages, picks, prefs, apiReq } } })`
- `navigate('/recommend', { state: { prefs, apiReq, _restored: { messages, picks } } })`
- ChatRecommend reads `state._restored?.messages` and `state._restored?.picks` on mount

---

- [ ] **Step 1: Write failing frontend test — no API call on restore**

Add to `frontend/src/screens/__tests__/ChatRecommend.test.jsx`:

```javascript
it('does not call recommend when _restored state is provided', async () => {
  const restoredMessages = [
    { role: 'user', text: 'bold · under $60 · tonight' },
    { role: 'sommelier', text: 'Here are my top picks.' },
  ];
  const restoredPicks = [
    { wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's",
      why: 'Great.', tagline: 'PASO ROBLES', coord: null, flavors: [] },
  ];
  renderScreen({
    prefs,
    apiReq,
    _restored: { messages: restoredMessages, picks: restoredPicks },
  });
  // API should never be called — state is restored
  await new Promise(r => setTimeout(r, 50));
  expect(recommend).not.toHaveBeenCalled();
  expect(screen.getByText('Here are my top picks.')).toBeInTheDocument();
  expect(screen.getByText('Esprit de Tablas')).toBeInTheDocument();
});
```

- [ ] **Step 2: Write failing test — dossier back button navigates to /recommend when chatState is present**

`RegionDossier.test.jsx` currently has no `useNavigate` mock. Add the following at the **top of the file**, before the `vi.mock('../../lib/api.js', ...)` line, so the mock is in scope for all tests. Also replace the existing `beforeEach(() => { getWine.mockClear(); })` with the version below that also clears `mockNavigate`:

```javascript
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

// Replace the existing beforeEach:
beforeEach(() => { getWine.mockClear(); mockNavigate.mockClear(); });

it('back button calls navigate(-1) when no chatState', () => {
  getWine.mockReturnValue(new Promise(() => {}));
  renderScreen();
  fireEvent.click(screen.getByText(/← back/i));
  expect(mockNavigate).toHaveBeenCalledWith(-1);
});

it('back button navigates to /recommend with _restored when chatState is present', () => {
  getWine.mockReturnValue(new Promise(() => {}));
  const chatState = {
    messages: [{ role: 'user', text: 'bold' }],
    picks: [],
    prefs: { zip: '78209', budget: 60, styles: [], occasion: 'Tonight', wineTypes: [], grapes: [] },
    apiReq: { zip_code: '78209', budget_min: 10, budget_max: 60, style_preferences: [] },
  };
  renderScreen('uuid-1', { pick: { ...pick, chatState } });
  fireEvent.click(screen.getByText(/← back/i));
  expect(mockNavigate).toHaveBeenCalledWith('/recommend', {
    state: expect.objectContaining({ _restored: chatState }),
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd frontend
npx vitest run src/screens/__tests__/ChatRecommend.test.jsx src/screens/__tests__/RegionDossier.test.jsx
```
Expected: 3 new tests FAIL (1 ChatRecommend + 2 RegionDossier).

- [ ] **Step 4: Update `ChatRecommend.jsx` — restore from state and embed chatState on navigate**

Replace the state destructuring and `useState` initializers near the top of the component (keep the hooks in the same order — React rules):

```javascript
export default function ChatRecommend() {
  const { state }  = useLocation();
  const navigate   = useNavigate();
  const { prefs, apiReq, _restored } = state ?? {};

  const [messages, setMessages] = useState(() => _restored?.messages ?? []);
  const [picks,    setPicks]    = useState(() => _restored?.picks    ?? []);
  const [loading,  setLoading]  = useState(() => !_restored);
  const [error,    setError]    = useState(null);
  const [input,    setInput]    = useState('');

  // All hooks must be called before any early return
  useEffect(() => {
    if (!prefs || _restored) return;   // skip if no prefs or state is restored
    setMessages([{ role: 'user', text: prefs.styles.join(', ') + ' · under $' + prefs.budget + ' · ' + prefs.occasion.toLowerCase() }]);
    callRecommend(apiReq);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
```

Update the WineCard click handler to embed `chatState` in the navigate state (find the `onClick` on WineCard):

```jsx
                <WineCard
                  key={pick.wine_id}
                  wine={pick}
                  onClick={() => navigate('/wine/' + pick.wine_id, {
                    state: {
                      pick,
                      chatState: { messages, picks, prefs, apiReq },
                    },
                  })}
                />
```

- [ ] **Step 5: Update `RegionDossier.jsx` — smart back navigation**

In `RegionDossier.jsx`, update the state reading and back button:

```javascript
  const pick      = state?.pick ?? {};
  const chatState = state?.pick?.chatState ?? state?.chatState ?? null;
```

Replace the back button's `onClick`:

```jsx
      <button onClick={() => {
        if (chatState) {
          navigate('/recommend', {
            state: {
              prefs:     chatState.prefs,
              apiReq:    chatState.apiReq,
              _restored: chatState,
            },
          });
        } else {
          navigate(-1);
        }
      }}
        style={{ cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)', padding: 0, marginBottom: 22 }}>
        ← Back to recommendations
      </button>
```

- [ ] **Step 6: Run all frontend tests**

```bash
cd frontend
npx vitest run
```
Expected: 69 passed (66 from Task 3 + 3 new).

- [ ] **Step 7: Run full backend test suite to confirm no regressions**

```bash
cd backend
python3 -m pytest tests/ -m "not integration" -q
```
Expected: 157 passed.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/screens/ChatRecommend.jsx frontend/src/screens/RegionDossier.jsx \
        frontend/src/screens/__tests__/ChatRecommend.test.jsx \
        frontend/src/screens/__tests__/RegionDossier.test.jsx
git commit -m "feat: persist recommendations on dossier back navigation"
```
