# Aisle Mode Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the "Ask" face of the recommendation thread (aisle mode) per the design handoff `frontend/design-system/handoffs/aisle-mode/README.md` — two doors (header tabs + store strip), ask empty state, lazy zip, in-thread store picker, comparison frame, no-card closer, in-store failure states — on the existing ChatRecommend/PreferenceCapture pair.

**Architecture:** ChatRecommend gains an *ask mode* (arriving at `/recommend` without `prefs` state is now the Ask face, not a redirect). The mode switch renders inside the mobile TopBar; the Door-2 strip renders in App.jsx's mobile layout on `/`. Ask requests use the wide-budget sentinel (0–10000) and the structured `store_ref` field the backend already supports. Two small backend additions: a nearby-stores endpoint for the picker, and body/structure + a `comparison` flag on the picks payload so the comparison frame can render from data.

**Tech Stack:** React 19 + inline styles + design tokens (CSS vars), vitest + @testing-library (run from `frontend/`), FastAPI + pytest (run from `backend/`, Python 3.9 — `Optional[str]`, never `str | None`).

## Global Constraints

- **Never hardcode hexes** — CSS variables only (`var(--bordeaux)` etc.). `--border-strong` is `var(--ink)`; use `--border` for hairlines.
- **Radii:** sharp (0) everywhere except conversational surfaces (bubbles `4px 14px 14px 14px`, pills `999px`).
- **No emoji, no gradients.** Serif (`var(--font-serif)`) never below 17px in chat contexts; eyebrows are `.t-eyebrow`.
- **Store pills always read `◎ store · distance`. No aisle numbers anywhere** (no shelf data).
- **Voice:** somm speaks as **I**, addresses **you**; never "error", never "no results found". Copy strings below are verbatim from the handoff — do not paraphrase.
- **`PLAN A BOTTLE` stays the default landing** (`/`). Inactive tab label is `--faded` (NOT `--faded-2`).
- **Wide-budget sentinel:** ask requests send `budget_min: 0, budget_max: 10000` (backend `recommendation/budget.py` keys off `>= 1000`).
- Backend tests: `cd backend && python3 -m pytest tests/ -m "not integration" -q`. Frontend: `cd frontend && npx vitest run`.
- Commit after every task; message prefix `feat:`/`test:` as appropriate, Co-Authored-By Claude trailer.

**Deferred (explicitly out of scope, do not build):** horizontal-swipe face switching; strip dismissal persistence; top-bar `No signal` offline readout; the food row in the comparison frame (no data); warm-continuation empty state; desktop mode tabs (desktop keeps NavBar; ask mode must merely *work* on desktop).

---

### Task 1: Backend — GET /api/stores/nearby

**Files:**
- Create: `backend/api/routers/stores.py`
- Modify: `backend/api/main.py` (register router — mirror how other routers are included)
- Test: `backend/tests/test_stores_api.py`

**Interfaces:**
- Produces: `GET /api/stores/nearby?zip=78209` → `{"stores": [{"id", "retailer_name", "name", "address", "distance_miles"}], "zip": "78209"}` sorted by distance ascending. 400 on unknown zip or no nearby stores.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_stores_api.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport
from api.main import app

_STORES = [
    {"id": "s1", "retailer_name": "H-E-B", "name": "H-E-B Lincoln Heights",
     "address": "999 E Basse Rd", "latitude": 29.49, "longitude": -98.46},
    {"id": "s2", "retailer_name": "Spec's", "name": "Spec's Broadway",
     "address": "5219 Broadway", "latitude": 29.47, "longitude": -98.47},
]


def _mock_sb():
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.execute.return_value.data = _STORES
    return sb


@pytest.mark.asyncio
async def test_nearby_stores_sorted_by_distance():
    with patch("api.routers.stores.get_supabase_client", return_value=_mock_sb()), \
         patch("api.routers.stores.zip_to_centroid", return_value=(29.4889, -98.4646)), \
         patch("api.routers.stores.find_nearby_store_ids", return_value=["s1", "s2"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            resp = await ac.get("/api/stores/nearby?zip=78209")
    assert resp.status_code == 200
    body = resp.json()
    assert [s["id"] for s in body["stores"]] == ["s1", "s2"]  # s1 is nearer the centroid
    assert body["stores"][0]["distance_miles"] is not None
    assert body["stores"][0]["retailer_name"] == "H-E-B"


@pytest.mark.asyncio
async def test_nearby_stores_unknown_zip_400():
    with patch("api.routers.stores.zip_to_centroid", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            resp = await ac.get("/api/stores/nearby?zip=00000")
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_stores_api.py -q`
Expected: FAIL/ERROR — `api.routers.stores` does not exist.

- [ ] **Step 3: Write the router**

```python
# backend/api/routers/stores.py
"""Nearby stores for the aisle-mode store picker: 'Which one are you standing
in?' — branch name + address + miles, closest first."""
from fastapi import APIRouter, HTTPException, Query
from db import get_supabase_client
from utils.geo import zip_to_centroid, find_nearby_store_ids, haversine

router = APIRouter(prefix="/api", tags=["stores"])


@router.get("/stores/nearby")
def nearby_stores(zip: str = Query(..., description="User zip")):
    centroid = zip_to_centroid(zip)
    if centroid is None:
        raise HTTPException(status_code=400, detail="We don't recognize that zip code")
    supabase = get_supabase_client()
    ids = find_nearby_store_ids(zip, supabase, centroid=centroid)
    if not ids:
        raise HTTPException(status_code=400, detail="No stores found near your zip code.")
    rows = (supabase.table("stores")
            .select("id, retailer_name, name, address, latitude, longitude")
            .in_("id", ids).execute().data or [])
    out = []
    for s in rows:
        lat, lon = s.get("latitude"), s.get("longitude")
        dist = (round(haversine(centroid[0], centroid[1], float(lat), float(lon)), 1)
                if lat is not None and lon is not None else None)
        out.append({"id": s["id"], "retailer_name": s.get("retailer_name"),
                    "name": s.get("name"), "address": s.get("address"),
                    "distance_miles": dist})
    out.sort(key=lambda s: (s["distance_miles"] is None, s["distance_miles"] or 0))
    return {"zip": zip, "stores": out}
```

Register in `backend/api/main.py`: find where routers are included (`app.include_router(...)`) and add `from api.routers.stores import router as stores_router` + `app.include_router(stores_router)` following the same pattern.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_stores_api.py -q` → 2 passed.
Then the full fast suite: `python3 -m pytest tests/ -m "not integration" -q` → all green.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/stores.py backend/api/main.py backend/tests/test_stores_api.py
git commit -m "feat: GET /api/stores/nearby for the aisle-mode store picker"
```

---

### Task 2: Backend — comparison data on the picks payload

**Files:**
- Modify: `backend/api/routers/recommend.py` (`_enrich_picks`; the `picks` SSE yield)
- Test: `backend/tests/test_recommend_api.py` (append)

**Interfaces:**
- Consumes: candidates already carry `body` and `structure_profile` (dict with numeric `body`/`tannins`/`acidity`) from `_row_to_candidate`; `resolved["comparison_wines"]` is set (list of 2+ names, or None) from the aisle-mode backend deltas.
- Produces: each enriched pick gains `body` + `structure_profile`; the final picks SSE event gains `"comparison": <list|null>` — the frontend renders the comparison frame when `comparison` is non-null and ≥2 picks arrive.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_recommend_api.py`:

```python
# ---- comparison payload (aisle-mode frontend) ----

def test_enrich_picks_carries_body_and_structure():
    from api.routers.recommend import _enrich_picks
    by_id = {"w1": {"wine_id": "w1", "name": "Caymus", "price": 89.0, "retailer": "H-E-B",
                    "body": "full", "structure_profile": {"body": 5, "tannins": 4, "acidity": 3},
                    "store_address": None, "distance_miles": 1.2, "price_drop": None,
                    "image_url": None, "vivino_rating": 4.5, "vivino_ratings_count": 100}}
    out = _enrich_picks([{"wine_id": "w1", "why": "bold"}], by_id)
    assert out[0]["body"] == "full"
    assert out[0]["structure_profile"] == {"body": 5, "tannins": 4, "acidity": 3}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_recommend_api.py -q` — the new test FAILS with KeyError `'body'`.

- [ ] **Step 3: Implement**

In `_enrich_picks` (recommend.py), add to the `enriched.append({...})` dict:

```python
            "body": cand.get("body"),
            "structure_profile": cand.get("structure_profile") or {},
```

In `event_gen()`, change the final picks yield (the `elif event_type == "picks":` success branch) to include the flag:

```python
                    yield "data: " + json.dumps({
                        "type": "picks", "picks": enriched_picks,
                        "session_id": session_id,
                        "comparison": resolved.get("comparison_wines"),
                    }) + "\n\n"
```

- [ ] **Step 4: Run tests**

`python3 -m pytest tests/ -m "not integration" -q` → all green.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/recommend.py backend/tests/test_recommend_api.py
git commit -m "feat: picks payload carries body/structure + comparison flag for the aisle frame"
```

---

### Task 3: Frontend lib — ask-mode helpers + nearby-stores client

**Files:**
- Create: `frontend/src/lib/askMode.js`
- Modify: `frontend/src/lib/api.js` (add `getNearbyStores`)
- Modify: `frontend/src/lib/useIsMobile.js` (add `hasStoredZip`)
- Test: `frontend/src/lib/__tests__/askMode.test.js`

**Interfaces:**
- Produces: `buildAskReq({ zip, message, history, storeRef, conversational, taste })` → RecommendRequest body with the wide-budget sentinel. `ASK_INTENT_PILLS` — array of `{label, fill}`. `hasStoredZip()` → bool (true only when localStorage actually has `somm_zip`; `loadZip()`'s `'78209'` fallback does NOT count). `getNearbyStores(zip)` → `{zip, stores:[...]}`.

- [ ] **Step 1: Write the failing tests**

```js
// frontend/src/lib/__tests__/askMode.test.js
import { buildAskReq, ASK_INTENT_PILLS } from '../askMode.js';
import { hasStoredZip } from '../useIsMobile.js';

describe('buildAskReq', () => {
  it('sends the wide-budget sentinel and the message', () => {
    const req = buildAskReq({ zip: '78209', message: 'caymus or bonanza?' });
    expect(req).toMatchObject({
      zip_code: '78209', budget_min: 0, budget_max: 10000,
      message: 'caymus or bonanza?', conversational: false,
    });
    expect(req.store_ref).toBeUndefined();
  });
  it('carries store_ref, history and conversational when given', () => {
    const req = buildAskReq({
      zip: '78209', message: 'and under $30?', storeRef: 's1',
      history: [{ role: 'user', content: 'hi' }], conversational: true,
    });
    expect(req.store_ref).toBe('s1');
    expect(req.conversation_history).toHaveLength(1);
    expect(req.conversational).toBe(true);
  });
});

describe('ASK_INTENT_PILLS', () => {
  it('has the four handoff intents', () => {
    expect(ASK_INTENT_PILLS.map(p => p.label)).toEqual(
      ['Compare two', 'Is this good?', 'What is this?', 'Pair with dinner']);
    ASK_INTENT_PILLS.forEach(p => expect(p.fill.length).toBeGreaterThan(0));
  });
});

describe('hasStoredZip', () => {
  it('false when nothing stored, true after set', () => {
    localStorage.removeItem('somm_zip');
    expect(hasStoredZip()).toBe(false);
    localStorage.setItem('somm_zip', '78209');
    expect(hasStoredZip()).toBe(true);
    localStorage.removeItem('somm_zip');
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/lib/__tests__/askMode.test.js`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```js
// frontend/src/lib/askMode.js
// Aisle-mode ("Ask") request shape. Budget is a hard SQL filter that can't be
// omitted, so an unstated budget is the wide-range sentinel the backend's
// recommendation/budget.py treats as "no budget stated".
export function buildAskReq({ zip, message, history, storeRef, conversational = false, taste = null }) {
  const req = {
    zip_code: zip, budget_min: 0, budget_max: 10000,
    style_preferences: [], avoid: [],
    message, conversational, taste,
  };
  if (history?.length) req.conversation_history = history;
  if (storeRef) req.store_ref = storeRef;
  return req;
}

export const ASK_INTENT_PILLS = [
  { label: 'Compare two',      fill: 'Which is better: ' },
  { label: 'Is this good?',    fill: 'Is this any good: ' },
  { label: 'What is this?',    fill: 'What can you tell me about ' },
  { label: 'Pair with dinner', fill: "We're eating " },
];
```

In `useIsMobile.js`, next to `loadZip`/`saveZip`:

```js
export function hasStoredZip() {
  try { return localStorage.getItem('somm_zip') != null; } catch { return false; }
}
```

In `api.js`:

```js
export async function getNearbyStores(zip) {
  const res = await fetch(`${BASE}/api/stores/nearby?zip=${encodeURIComponent(zip)}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}
```

- [ ] **Step 4: Run tests** — `npx vitest run src/lib/__tests__/askMode.test.js` → pass; then full `npx vitest run` → green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/askMode.js frontend/src/lib/api.js frontend/src/lib/useIsMobile.js frontend/src/lib/__tests__/askMode.test.js
git commit -m "feat: ask-mode request helpers + nearby-stores client"
```

---

### Task 4: Mode tabs in the mobile TopBar

**Files:**
- Modify: `frontend/src/components/MobileChrome.jsx` (TopBar)
- Test: `frontend/src/components/__tests__/ModeTabs.test.jsx`

**Interfaces:**
- Consumes: react-router location; ask mode is signalled by `location.state?.mode === 'ask'` on `/recommend`.
- Produces: on `/`, and on `/recommend` in ask mode, the TopBar title area renders two tab labels `PLAN A BOTTLE` | `ASK`. Active: `color: var(--ink)`, `borderBottom: 2.5px solid var(--bordeaux)`; inactive: `color: var(--faded)`, no border. Tapping PLAN → `navigate('/')`; tapping ASK → `navigate('/recommend', { state: { mode: 'ask' } })`. Plan-launched `/recommend` (has `prefs` state) keeps today's "Tonight, near {zip}" title — no tabs.

- [ ] **Step 1: Write the failing test**

```jsx
// frontend/src/components/__tests__/ModeTabs.test.jsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { TopBar } from '../MobileChrome.jsx';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

beforeEach(() => mockNavigate.mockClear());

function renderAt(entry) {
  return render(<MemoryRouter initialEntries={[entry]}><TopBar /></MemoryRouter>);
}

it('shows both mode tabs on /, PLAN active', () => {
  renderAt('/');
  const plan = screen.getByText('PLAN A BOTTLE');
  const ask = screen.getByText('ASK');
  expect(plan).toBeInTheDocument();
  expect(ask).toBeInTheDocument();
  expect(plan.style.color).toBe('var(--ink)');
  expect(ask.style.color).toBe('var(--faded)');
});

it('shows ASK active on /recommend in ask mode', () => {
  renderAt({ pathname: '/recommend', state: { mode: 'ask' } });
  expect(screen.getByText('ASK').style.color).toBe('var(--ink)');
  expect(screen.getByText('PLAN A BOTTLE').style.color).toBe('var(--faded)');
});

it('keeps the plan-thread title (no tabs) on /recommend with prefs', () => {
  renderAt({ pathname: '/recommend', state: { prefs: { zip: '78209' } } });
  expect(screen.queryByText('PLAN A BOTTLE')).toBeNull();
  expect(screen.getByText(/Tonight, near 78209/)).toBeInTheDocument();
});

it('tapping ASK navigates to the ask face', async () => {
  renderAt('/');
  await userEvent.click(screen.getByText('ASK'));
  expect(mockNavigate).toHaveBeenCalledWith('/recommend', { state: { mode: 'ask' } });
});

it('tapping PLAN A BOTTLE navigates home', async () => {
  renderAt({ pathname: '/recommend', state: { mode: 'ask' } });
  await userEvent.click(screen.getByText('PLAN A BOTTLE'));
  expect(mockNavigate).toHaveBeenCalledWith('/');
});
```

- [ ] **Step 2: Run to verify failure** — `npx vitest run src/components/__tests__/ModeTabs.test.jsx` → FAIL (no tabs rendered).

- [ ] **Step 3: Implement**

In `MobileChrome.jsx` add a `ModeTabs` component and wire it into `TopBar`:

```jsx
// The two faces of the recommendation window (design handoff: aisle-mode).
// Underlined labels sharing the header's ink rule — tabs, not a toggle.
function ModeTabs({ active, navigate }) {
  const tab = (label, isActive, onTap) => (
    <button onClick={onTap} style={{
      cursor: 'pointer', background: 'none', border: 'none', padding: '0 2px 6px',
      fontFamily: 'var(--font-sans)', fontSize: 11, fontWeight: 600,
      letterSpacing: '0.22em', textTransform: 'uppercase',
      color: isActive ? 'var(--ink)' : 'var(--faded)',
      borderBottom: isActive ? '2.5px solid var(--bordeaux)' : '2.5px solid transparent',
      marginBottom: -2, minHeight: 44, display: 'flex', alignItems: 'flex-end',
    }}>{label}</button>
  );
  return (
    <div style={{ display: 'flex', gap: 18, alignItems: 'flex-end', height: '100%' }}>
      {tab('PLAN A BOTTLE', active === 'plan', () => navigate('/'))}
      {tab('ASK', active === 'ask', () => navigate('/recommend', { state: { mode: 'ask' } }))}
    </div>
  );
}
```

In `TopBar`, compute ask mode and branch the title area:

```jsx
  const askMode = pathname === '/recommend' && state?.mode === 'ask';
  const showTabs = pathname === '/' || askMode;
```

- In the `/recommend` branch of the title logic: only set `title = \`Tonight, near ${zip}\`` when NOT ask mode.
- In the JSX, where the title `<div style={{ flex: 1 ... }}>` renders: when `showTabs`, render `<div style={{ flex: 1, alignSelf: 'stretch', display: 'flex' }}><ModeTabs active={pathname === '/' ? 'plan' : 'ask'} navigate={navigate} /></div>` instead of the title/sub block. Keep the Stamp on the left and the `◎ {zip}` readout on the right unchanged.

- [ ] **Step 4: Run tests** — target file passes; full `npx vitest run` green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/MobileChrome.jsx frontend/src/components/__tests__/ModeTabs.test.jsx
git commit -m "feat: PLAN A BOTTLE | ASK mode tabs in the mobile header"
```

---

### Task 5: Door 2 — the standing-invitation strip

**Files:**
- Create: `frontend/src/components/AisleStrip.jsx`
- Modify: `frontend/src/App.jsx` (render in mobile layout on `/` only, between routes container and BottomTabs)
- Test: `frontend/src/components/__tests__/AisleStrip.test.jsx`

**Interfaces:**
- Produces: a strip that navigates to `/recommend` with `state: { mode: 'ask', openStorePicker: true }`. Task 8 consumes `openStorePicker`.

- [ ] **Step 1: Write the failing test**

```jsx
// frontend/src/components/__tests__/AisleStrip.test.jsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import AisleStrip from '../AisleStrip.jsx';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

it('renders the invitation and crosses to the ask face with the store picker open', async () => {
  render(<MemoryRouter><AisleStrip /></MemoryRouter>);
  const strip = screen.getByText(/In a store right now\? Just ask me instead\./);
  await userEvent.click(strip);
  expect(mockNavigate).toHaveBeenCalledWith('/recommend',
    { state: { mode: 'ask', openStorePicker: true } });
});
```

- [ ] **Step 2: Run to verify failure** — module not found.

- [ ] **Step 3: Implement**

```jsx
// frontend/src/components/AisleStrip.jsx
// Door 2 (aisle-mode handoff): a tab says *there is another view*; this strip
// says *here is when you'd want it*. Tapping is a declaration — "I'm here,
// now" — so it also opens the store picker.
import { useNavigate } from 'react-router-dom';

export default function AisleStrip() {
  const navigate = useNavigate();
  return (
    <button
      onClick={() => navigate('/recommend', { state: { mode: 'ask', openStorePicker: true } })}
      style={{
        display: 'flex', alignItems: 'center', gap: 10, width: '100%',
        background: 'var(--bordeaux-tint)', border: 'none',
        borderTop: '0.75px solid var(--brass)', cursor: 'pointer',
        padding: '11px 16px', flexShrink: 0, textAlign: 'left',
      }}>
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--bordeaux)" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" />
      </svg>
      <span style={{ flex: 1, fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--bordeaux)', fontWeight: 500 }}>
        In a store right now? Just ask me instead.
      </span>
      <span style={{ color: 'var(--bordeaux)', fontSize: 15 }}>›</span>
    </button>
  );
}
```

In `App.jsx` mobile layout, import AisleStrip and `useLocation` is already imported in AppRoutes — App itself needs pathname. Move the strip inside a small wrapper: render `{pathname === '/' && <AisleStrip />}` between the routes `<div>` and `<BottomTabs />`. Since `App` isn't inside the Router's location context in this file structure (it is — `AppRoutes` uses `useLocation`, so App is inside `<BrowserRouter>` from main.jsx), add `const { pathname } = useLocation();` in `App`.

- [ ] **Step 4: Run tests** — target + full suite green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AisleStrip.jsx frontend/src/App.jsx frontend/src/components/__tests__/AisleStrip.test.jsx
git commit -m "feat: aisle strip — the standing invitation above the tab bar"
```

---

### Task 6: ChatRecommend ask mode — empty state, intent pills, wide-budget send

**Files:**
- Modify: `frontend/src/screens/ChatRecommend.jsx`
- Test: `frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx` (new file)
- Modify: `frontend/src/screens/__tests__/ChatRecommend.test.jsx` (the `redirects to / when there is no prefs state` test changes meaning)

**Interfaces:**
- Consumes: `buildAskReq`, `ASK_INTENT_PILLS`, `hasStoredZip`, `loadZip`, `saveZip`.
- Produces: ask mode = `state?.mode === 'ask'` OR no `prefs`/`_restored` state. No auto-fire of the first recommendation; empty thread renders the ask empty state; composer sends via `buildAskReq` with `zip` from `loadZip()`. Ask context state: `askZip` (string), `storeRef`/`storeLabel` (Task 8 sets them; already threaded through `buildAskReq` here).

Key mechanics (implement inside ChatRecommend, before the mobile/desktop return blocks):

```jsx
  const askMode = (state?.mode === 'ask') || (!prefs && !_restored) || _restored?.mode === 'ask';
  const [askZip, setAskZip] = useState(() => _restored?.askZip ?? loadZip());
  const [storeRef, setStoreRef] = useState(() => _restored?.storeRef ?? null);
  const [storeLabel, setStoreLabel] = useState(() => _restored?.storeLabel ?? null);
```

- Replace `if (!prefs) return <Navigate to="/" replace />;` with `if (!prefs && !askMode) return <Navigate to="/" replace />;` (in practice askMode covers the no-prefs case — the redirect disappears; update the old test accordingly).
- The auto-fire `useEffect` must not run in ask mode (`if (!prefs || askMode || ...) return;` — it already guards on `!prefs`).
- Initial `loading` state must be `false` in ask mode: `useState(() => !_restored && !askMode)` — wait, `askMode` isn't defined before hooks; hoist the expression: compute `const askMode = ...` from `state` BEFORE the `useState` calls (it derives only from `state`, allowed).
- New send path:

```jsx
  const handleAskSend = (text) => {
    if (loading || streaming || !text.trim()) return;
    const history = messages.map(m => ({ role: m.role, content: m.text }));
    setMessages(prev => [...prev, { id: uuid(), role: 'user', text }]);
    tasteFor().then(taste => callRecommend(buildAskReq({
      zip: askZip, message: text, history: history.length ? history : undefined,
      storeRef, conversational: history.length > 0 && naturalChatMode(), taste,
    })));
  };
```

- Composer routing: in ask mode the composer submit calls `handleAskSend` instead of `handleFollowup`; placeholder `"Ask the sommelier…"` in ask mode.
- Empty state (renders in the thread scroll area when `askMode && messages.length === 0 && !loading`):

```jsx
  const askEmptyState = (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', padding: '48px 24px 24px', gap: 14 }}>
      <Stamp size={46} reversed />
      <div style={{ fontFamily: 'var(--font-serif)', fontSize: 26, color: 'var(--ink)' }}>
        What can I help you with?
      </div>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, lineHeight: 1.6, color: 'var(--faded)', maxWidth: 300 }}>
        Name a bottle, name two, ask what something is, or just tell me what you're eating. No sliders in here.
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', marginTop: 6 }}>
        {ASK_INTENT_PILLS.map(p => (
          <button key={p.label} onClick={() => setInput(p.fill)} style={{
            cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 12.5,
            color: 'var(--bordeaux)', background: 'var(--bordeaux-tint)', border: 'none',
            borderRadius: 999, padding: '8px 15px', minHeight: 36,
          }}>{p.label}</button>
        ))}
      </div>
    </div>
  );
```

- Render `{askMode && messages.length === 0 && !loading && askEmptyState}` at the top of BOTH the mobile chat scroll div and the desktop chat panel scroll div.
- Desktop header guard: `Tonight, near {prefs.zip}` → `{askMode ? 'Ask me anything' : \`Tonight, near ${prefs.zip}\`}`; also every other `prefs.` access must be optional (`prefs?.zip`) — grep the file (`postFeedback` zip: `prefs?.zip ?? askZip`).
- `navToWine` chatState must persist ask context: add `mode: askMode ? 'ask' : undefined, askZip, storeRef, storeLabel` into the `chatState` object.

- [ ] **Step 1: Write the failing tests**

```jsx
// frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import ChatRecommend from '../ChatRecommend.jsx';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});
vi.mock('../../lib/api.js', () => ({
  streamRecommend: vi.fn(), postFeedback: vi.fn(), getNearbyStores: vi.fn(),
}));
import { streamRecommend } from '../../lib/api.js';

function renderAsk(state = { mode: 'ask' }) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/recommend', state }]}>
      <Routes>
        <Route path="/recommend" element={<ChatRecommend />} />
        <Route path="/" element={<div>Home</div>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  mockNavigate.mockClear();
  streamRecommend.mockClear();
  localStorage.setItem('somm_zip', '78209');   // stored zip: lazy-zip flow stays out of these tests
});

it('renders the ask empty state instead of redirecting or auto-firing', async () => {
  renderAsk();
  expect(screen.getByText('What can I help you with?')).toBeInTheDocument();
  expect(screen.getByText('Compare two')).toBeInTheDocument();
  await new Promise(r => setTimeout(r, 30));
  expect(streamRecommend).not.toHaveBeenCalled();
});

it('arriving at /recommend with no state at all is the ask face too', () => {
  render(
    <MemoryRouter initialEntries={['/recommend']}>
      <Routes>
        <Route path="/recommend" element={<ChatRecommend />} />
        <Route path="/" element={<div>Home</div>} />
      </Routes>
    </MemoryRouter>
  );
  expect(screen.getByText('What can I help you with?')).toBeInTheDocument();
  expect(screen.queryByText('Home')).toBeNull();
});

it('an intent pill fills the composer', async () => {
  renderAsk();
  await userEvent.click(screen.getByText('Compare two'));
  expect(screen.getAllByRole('textbox')[0].value).toBe('Which is better: ');
});

it('sending asks with the wide-budget sentinel and stored zip', async () => {
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Both are solid.' };
  });
  renderAsk();
  const input = screen.getAllByRole('textbox')[0];
  await userEvent.type(input, 'caymus or bonanza?{Enter}');
  await waitFor(() => expect(streamRecommend).toHaveBeenCalledTimes(1));
  expect(streamRecommend.mock.calls[0][0]).toMatchObject({
    zip_code: '78209', budget_min: 0, budget_max: 10000, message: 'caymus or bonanza?',
  });
  await screen.findByText('Both are solid.');
});
```

Also in `ChatRecommend.test.jsx`, replace the `redirects to / when there is no prefs state` test body:

```jsx
it('renders the ask face when there is no prefs state (no redirect)', () => {
  localStorage.setItem('somm_zip', '78209');
  render(
    <MemoryRouter initialEntries={['/recommend']}>
      <Routes>
        <Route path="/recommend" element={<ChatRecommend />} />
        <Route path="/" element={<div>Home</div>} />
      </Routes>
    </MemoryRouter>
  );
  expect(screen.getByText('What can I help you with?')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure** — `npx vitest run src/screens/__tests__/ChatRecommendAsk.test.jsx` → FAILs (redirects to Home).

- [ ] **Step 3: Implement** per the mechanics above (imports: `buildAskReq`, `ASK_INTENT_PILLS` from `../lib/askMode.js`; `loadZip` from `../lib/useIsMobile.js`).

- [ ] **Step 4: Run tests** — both test files + full `npx vitest run` green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/screens/ChatRecommend.jsx frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx frontend/src/screens/__tests__/ChatRecommend.test.jsx
git commit -m "feat: ask face — empty state, intent pills, wide-budget conversational send"
```

---

### Task 7: Lazy zip — the in-conversation zip request

**Files:**
- Modify: `frontend/src/screens/ChatRecommend.jsx`
- Test: append to `frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx`

**Interfaces:**
- Consumes: `hasStoredZip`, `saveZip` — and the `handleAskSend` from Task 6, which gains a zip gate.
- Produces: when `askMode && !hasStoredZip()` and the user sends their first message, the message is held in `pendingAskText` and a zip-request bubble renders (somm line + `YOUR ZIP / CITY` field + `Set` button + "Asked once" footnote). `Set` saves the zip and fires the held question. Once a zip is stored the gate never appears.

Mechanics: add state `const [pendingAskText, setPendingAskText] = useState(null);` and `const [zipConfirmed, setZipConfirmed] = useState(hasStoredZip);`. In `handleAskSend`, before building the request:

```jsx
    if (askMode && !zipConfirmed) {
      setMessages(prev => [...prev, { id: uuid(), role: 'user', text }]);
      setPendingAskText(text);
      return;
    }
```

Zip-request bubble (rendered after `messageList` when `pendingAskText != null`):

```jsx
  const [zipDraft, setZipDraft] = useState('');
  const confirmZip = () => {
    if (zipDraft.length !== 5) return;
    saveZip(zipDraft);
    setAskZip(zipDraft);
    setZipConfirmed(true);
    const text = pendingAskText;
    setPendingAskText(null);
    const history = messages.slice(0, -1).map(m => ({ role: m.role, content: m.text }));
    tasteFor().then(taste => callRecommend(buildAskReq({
      zip: zipDraft, message: text, history: history.length ? history : undefined,
      storeRef, conversational: false, taste,
    })));
  };

  const zipRequestBubble = pendingAskText != null && (
    <SommelierBubble>
      <div>I can name bottles you'll actually find tonight if you tell me roughly where you are.</div>
      <div style={{ marginTop: 10 }}>
        <span className="t-eyebrow" style={{ display: 'block', marginBottom: 6 }}>YOUR ZIP / CITY</span>
        <div style={{ display: 'flex', border: '1.5px solid var(--ink)', background: 'var(--cream-raised)' }}>
          <input value={zipDraft} inputMode="numeric" maxLength={5} aria-label="Your zip"
            onChange={e => setZipDraft(e.target.value.replace(/\D/g, '').slice(0, 5))}
            onKeyDown={e => { if (e.key === 'Enter') confirmZip(); }}
            style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', fontFamily: 'var(--font-sans)', fontSize: 16, color: 'var(--ink)', padding: '10px 12px', minWidth: 0 }} />
          <button onClick={confirmZip} style={{ border: 'none', background: 'var(--bordeaux)', color: 'var(--cream)', padding: '0 16px', cursor: 'pointer', fontSize: 14 }}>Set</button>
        </div>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', marginTop: 6 }}>
          Asked once — I'll remember it from here on.
        </div>
      </div>
    </SommelierBubble>
  );
```

Render `{zipRequestBubble}` after `{messageList}` in the mobile scroll area and in the desktop message area.

- [ ] **Step 1: Write the failing tests** (append to ChatRecommendAsk.test.jsx)

```jsx
describe('lazy zip', () => {
  beforeEach(() => localStorage.removeItem('somm_zip'));

  it('holds the question and asks for zip when none is stored', async () => {
    renderAsk();
    const input = screen.getAllByRole('textbox')[0];
    await userEvent.type(input, 'a good red for tonight{Enter}');
    expect(streamRecommend).not.toHaveBeenCalled();
    expect(screen.getByText(/tell me roughly where you are/)).toBeInTheDocument();
    expect(screen.getByText(/Asked once — I'll remember it/)).toBeInTheDocument();
  });

  it('Set saves the zip and fires the held question', async () => {
    streamRecommend.mockImplementation(async function* () {
      yield { type: 'token', text: 'Here you go.' };
    });
    renderAsk();
    await userEvent.type(screen.getAllByRole('textbox')[0], 'a good red{Enter}');
    await userEvent.type(screen.getByLabelText('Your zip'), '78230');
    await userEvent.click(screen.getByText('Set'));
    await waitFor(() => expect(streamRecommend).toHaveBeenCalledTimes(1));
    expect(streamRecommend.mock.calls[0][0]).toMatchObject({ zip_code: '78230', message: 'a good red' });
    expect(localStorage.getItem('somm_zip')).toBe('78230');
  });
});
```

- [ ] **Step 2: Run to verify failure** — the first test fails (request fires immediately with the default zip).

- [ ] **Step 3: Implement** per mechanics above.

- [ ] **Step 4: Run tests** — file + full suite green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/screens/ChatRecommend.jsx frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx
git commit -m "feat: lazy zip — in-conversation zip request, asked once"
```

---

### Task 8: Store picker + context pills

**Files:**
- Modify: `frontend/src/screens/ChatRecommend.jsx`
- Test: append to `frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx`

**Interfaces:**
- Consumes: `getNearbyStores(zip)` (Task 3), `state?.openStorePicker` (Task 5), `storeRef`/`storeLabel` state (Task 6).
- Produces: an in-thread picker bubble; selection sets `storeRef`/`storeLabel`; subsequent `buildAskReq` calls carry `store_ref`. A context pill row above the composer shows `◎ {zip}` and, when set, `◎ {storeLabel}` (tap → reopen picker; the "Somewhere else — just use my zip" ghost clears it).

Mechanics: `const [pickerOpen, setPickerOpen] = useState(() => Boolean(state?.openStorePicker));` and `const [nearbyStores, setNearbyStores] = useState(null);`. Effect: when `pickerOpen && nearbyStores == null && askMode` → `getNearbyStores(askZip).then(r => setNearbyStores(r.stores)).catch(() => setNearbyStores([]))`.

Picker bubble (renders when `pickerOpen`, above the composer in the thread flow):

```jsx
  const storePickerBubble = pickerOpen && (
    <SommelierBubble>
      <div>Which one are you standing in? I'll keep my answers to what's on their shelves.</div>
      <div style={{ marginTop: 10, border: '1.5px solid var(--ink)', background: 'var(--cream-raised)' }}>
        {(nearbyStores ?? []).map((s, i) => (
          <button key={s.id} onClick={() => { setStoreRef(s.id); setStoreLabel(s.name); setPickerOpen(false); }}
            style={{ display: 'flex', width: '100%', alignItems: 'baseline', gap: 8, textAlign: 'left',
              cursor: 'pointer', background: 'none', border: 'none',
              borderTop: i ? '0.75px solid var(--border)' : 'none', padding: '11px 13px' }}>
            <span style={{ flex: 1, fontFamily: 'var(--font-sans)', fontSize: 13.5, color: 'var(--ink)', fontWeight: 500 }}>
              {s.name}
              {i === 0 && <span style={{ marginLeft: 8, fontFamily: 'var(--font-sans)', fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--bordeaux)', fontWeight: 600 }}>closest</span>}
            </span>
            {s.distance_miles != null && (
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', whiteSpace: 'nowrap' }}>{s.distance_miles} mi</span>
            )}
          </button>
        ))}
        {nearbyStores == null && (
          <div style={{ padding: '11px 13px', fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--faded)' }}>Finding stores near you…</div>
        )}
      </div>
      <button onClick={() => { setStoreRef(null); setStoreLabel(null); setPickerOpen(false); }}
        style={{ marginTop: 8, cursor: 'pointer', background: 'none', border: '1.5px solid var(--bordeaux)', color: 'var(--bordeaux)', fontFamily: 'var(--font-sans)', fontSize: 12.5, padding: '8px 13px' }}>
        Somewhere else — just use my zip
      </button>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', marginTop: 8 }}>
        Store is a soft filter, not a cage — I'll still name a better bottle down the road if there is one.
      </div>
    </SommelierBubble>
  );
```

Context pill row (ask mode only, sits directly above the composer border div):

```jsx
  const contextPills = askMode && (
    <div style={{ display: 'flex', gap: 6, padding: '0 14px 8px', flexWrap: 'wrap' }}>
      <span style={{ borderRadius: 999, border: '0.75px solid var(--border-strong)', color: 'var(--ink-2)', fontFamily: 'var(--font-sans)', fontSize: 10.5, padding: '3px 10px' }}>◎ {askZip}</span>
      {storeLabel && (
        <button onClick={() => setPickerOpen(true)} style={{ cursor: 'pointer', borderRadius: 999, border: '0.75px solid var(--sage)', color: 'var(--sage)', background: 'none', fontFamily: 'var(--font-sans)', fontSize: 10.5, padding: '3px 10px' }}>
          ◎ {storeLabel} · change
        </button>
      )}
    </div>
  );
```

- [ ] **Step 1: Write the failing tests** (append)

```jsx
describe('store picker', () => {
  it('opens from openStorePicker state, lists stores, selection scopes requests', async () => {
    const { getNearbyStores } = await import('../../lib/api.js');
    getNearbyStores.mockResolvedValue({ zip: '78209', stores: [
      { id: 's1', retailer_name: 'H-E-B', name: 'H-E-B Lincoln Heights', address: 'x', distance_miles: 0.8 },
      { id: 's2', retailer_name: "Spec's", name: "Spec's Broadway", address: 'y', distance_miles: 2.1 },
    ] });
    streamRecommend.mockImplementation(async function* () { yield { type: 'token', text: 'ok' }; });
    renderAsk({ mode: 'ask', openStorePicker: true });
    expect(await screen.findByText(/Which one are you standing in/)).toBeInTheDocument();
    await screen.findByText('H-E-B Lincoln Heights');
    expect(screen.getByText('closest')).toBeInTheDocument();
    await userEvent.click(screen.getByText('H-E-B Lincoln Heights'));
    // picker closes, pill shows
    expect(screen.queryByText(/Which one are you standing in/)).toBeNull();
    expect(screen.getByText(/H-E-B Lincoln Heights · change/)).toBeInTheDocument();
    // requests now carry store_ref
    await userEvent.type(screen.getAllByRole('textbox')[0], 'a bold red{Enter}');
    await waitFor(() => expect(streamRecommend).toHaveBeenCalled());
    expect(streamRecommend.mock.calls[0][0]).toMatchObject({ store_ref: 's1' });
  });

  it('the escape hatch clears the store', async () => {
    const { getNearbyStores } = await import('../../lib/api.js');
    getNearbyStores.mockResolvedValue({ zip: '78209', stores: [
      { id: 's1', retailer_name: 'H-E-B', name: 'H-E-B Lincoln Heights', address: 'x', distance_miles: 0.8 },
    ] });
    renderAsk({ mode: 'ask', openStorePicker: true });
    await screen.findByText('H-E-B Lincoln Heights');
    await userEvent.click(screen.getByText(/Somewhere else — just use my zip/));
    expect(screen.queryByText(/H-E-B Lincoln Heights · change/)).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement** per mechanics (import `getNearbyStores` in ChatRecommend).

- [ ] **Step 4: Run tests** — file + full suite green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/screens/ChatRecommend.jsx frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx
git commit -m "feat: in-thread store picker + editable context pills"
```

---

### Task 9: Comparison frame

**Files:**
- Create: `frontend/src/components/CompareFrame.jsx`
- Modify: `frontend/src/screens/ChatRecommend.jsx` (capture `comparison` from the picks event; render the frame)
- Test: `frontend/src/components/__tests__/CompareFrame.test.jsx` + one integration test appended to ChatRecommendAsk.test.jsx

**Interfaces:**
- Consumes: picks event now carries `comparison` (Task 2). Each pick may carry `body` (string) and `structure_profile` (`{body, tannins, acidity}` numeric 1–5).
- Produces: `<CompareFrame picks={[a, b]} />` — sharp `1.5px var(--ink)` two-column frame; rows for PRICE, BODY, TANNIN (row omitted when neither pick has the datum); column 0 (the somm's pick) washed `var(--bordeaux-tint)` with a `MINE` flag. Data is sharp, conversation is soft — frame has radius 0.

- [ ] **Step 1: Write the failing component test**

```jsx
// frontend/src/components/__tests__/CompareFrame.test.jsx
import { render, screen } from '@testing-library/react';
import CompareFrame from '../CompareFrame.jsx';

const A = { wine_id: 'a', name: 'Caymus Cabernet', price: 89,
            structure_profile: { body: 5, tannins: 4 } };
const B = { wine_id: 'b', name: 'Bonanza Cabernet', price: 21,
            structure_profile: { body: 4, tannins: 3 } };

it('renders both columns with price/body/tannin rows and flags the winner', () => {
  render(<CompareFrame picks={[A, B]} />);
  expect(screen.getByText('Caymus Cabernet')).toBeInTheDocument();
  expect(screen.getByText('Bonanza Cabernet')).toBeInTheDocument();
  expect(screen.getByText('$89')).toBeInTheDocument();
  expect(screen.getByText('$21')).toBeInTheDocument();
  expect(screen.getByText('MINE')).toBeInTheDocument();
  expect(screen.getAllByText('Full')).toHaveLength(2);   // body 5 and 4 both map Full
  expect(screen.getByText('Firm')).toBeInTheDocument();  // tannins 4
  expect(screen.getByText('Medium')).toBeInTheDocument();// tannins 3
});

it('omits a row when neither pick has the datum, renders nothing under 2 picks', () => {
  const { container } = render(<CompareFrame picks={[{ ...A, structure_profile: {} }, { ...B, structure_profile: {} }]} />);
  expect(screen.queryByText('BODY')).toBeNull();
  const solo = render(<CompareFrame picks={[A]} />);
  expect(solo.container.firstChild).toBeNull();
});
```

- [ ] **Step 2: Run to verify failure** — module not found.

- [ ] **Step 3: Implement**

```jsx
// frontend/src/components/CompareFrame.jsx
// The signature aisle moment (design handoff): the two-bottle comparison's
// DATA half. Sharp 1.5px ink frame — data is sharp, conversation is soft.
// The verdict lives in the somm's bubble; the winning column is column 0
// (the model's first pick) washed bordeaux-tint with a MINE flag.
const bodyLabel = v => (v == null ? null : v <= 2 ? 'Light' : v === 3 ? 'Medium' : 'Full');
const tanninLabel = v => (v == null ? null : v <= 2 ? 'Soft' : v === 3 ? 'Medium' : 'Firm');

export default function CompareFrame({ picks }) {
  if (!picks || picks.length < 2) return null;
  const [a, b] = picks;
  const sp = p => p.structure_profile || {};
  const rows = [
    ['PRICE', p => (p.price != null ? `$${Number(p.price).toFixed(0)}` : null)],
    ['BODY', p => bodyLabel(sp(p).body)],
    ['TANNIN', p => tanninLabel(sp(p).tannins)],
  ].filter(([, get]) => get(a) != null || get(b) != null);
  if (!rows.length) return null;

  const col = (p, mine) => (
    <div style={{ flex: 1, background: mine ? 'var(--bordeaux-tint)' : 'transparent', minWidth: 0 }}>
      <div style={{ padding: '10px 12px 8px', borderBottom: '0.75px solid var(--brass)' }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 15, lineHeight: 1.15, color: 'var(--ink)' }}>{p.name}</div>
        {mine && <span className="t-eyebrow" style={{ color: 'var(--bordeaux)', marginTop: 3, display: 'inline-block' }}>MINE</span>}
      </div>
      {rows.map(([label, get]) => (
        <div key={label} style={{ padding: '7px 12px', borderBottom: '0.75px solid var(--border)' }}>
          <span className="t-eyebrow" style={{ display: 'block' }}>{label}</span>
          <span style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--ink-2)' }}>{get(p) ?? '—'}</span>
        </div>
      ))}
    </div>
  );

  return (
    <div style={{ display: 'flex', border: '1.5px solid var(--ink)', background: 'var(--cream-raised)', marginBottom: 14, marginLeft: 43 }}>
      {col(a, true)}
      <div style={{ width: 1, background: 'var(--ink)' }} />
      {col(b, false)}
    </div>
  );
}
```

Wiring in ChatRecommend: in the `picks` event branch, capture the flag on the message: when `event.comparison?.length >= 2 && event.picks.length >= 2`, set `comparison: true` on the same sommelier message the picks attach to. In `messageList`, when `m.comparison && m.picks?.length >= 2`, render `<CompareFrame key={(m.id ?? i) + '-cmp'} picks={m.picks.slice(0, 2)} />` between the intro bubble and the pick messages.

Integration test (append to ChatRecommendAsk.test.jsx):

```jsx
it('renders the comparison frame when the picks event carries comparison', async () => {
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Caymus, if I am honest.' };
    yield { type: 'picks', comparison: ['Caymus', 'Bonanza'], picks: [
      { wine_id: 'a', name: 'Caymus Cabernet', price: 89, retailer: 'H-E-B', why: 'Plush.', structure_profile: { body: 5, tannins: 4 } },
      { wine_id: 'b', name: 'Bonanza Cabernet', price: 21, retailer: 'H-E-B', why: 'Value.', structure_profile: { body: 4, tannins: 3 } },
    ], session_id: 's' };
  });
  renderAsk();
  await userEvent.type(screen.getAllByRole('textbox')[0], 'caymus or bonanza?{Enter}');
  await screen.findByText('MINE');
  expect(screen.getByText('$89')).toBeInTheDocument();
});
```

- [ ] **Step 4: Run tests** — both files + full suite green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CompareFrame.jsx frontend/src/components/__tests__/CompareFrame.test.jsx frontend/src/screens/ChatRecommend.jsx frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx
git commit -m "feat: two-bottle comparison frame — facts sharp, verdict soft"
```

---

### Task 10: No-card closer — the single offer

**Files:**
- Modify: `frontend/src/screens/ChatRecommend.jsx`
- Test: append to `frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx`

**Interfaces:**
- Consumes: stream completion state inside `callRecommend`.
- Produces: in ask mode, when a stream finishes cleanly with zero picks for that turn, an offer renders under the answer: somm line "Want me to find you a good one here?" + `Yes, find one` / `No thanks`. Yes sends `"Yes — find me a good one nearby"` through `handleAskSend`; No dismisses. Never in plan mode; never after an error.

Mechanics: track picks-per-turn inside `callRecommend` (`let turnHadPicks = false;` set true in `pick`/non-empty `picks` branches). In `finally`, when `askMode && !turnHadPicks && !errored` (track `errored` in catch) append `{ id: uuid(), role: 'sommelier', offer: true, text: 'Want me to find you a good one here?', noFeedback: true }`. Render: in `messageList`, when `m.offer`, render the bubble text plus two buttons:

```jsx
      <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
        <button onClick={() => { setMessages(prev => prev.filter(x => x.id !== m.id)); handleAskSend('Yes — find me a good one nearby'); }}
          style={{ cursor: 'pointer', background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 12.5, padding: '8px 14px' }}>Yes, find one</button>
        <button onClick={() => setMessages(prev => prev.map(x => x.id === m.id ? { ...x, offer: false, dismissed: true } : x))}
          style={{ cursor: 'pointer', background: 'none', color: 'var(--bordeaux)', border: '1.5px solid var(--bordeaux)', fontFamily: 'var(--font-sans)', fontSize: 12.5, padding: '8px 14px' }}>No thanks</button>
      </div>
```

(Dismissed offer keeps the text line, drops the buttons.)

- [ ] **Step 1: Failing tests** (append)

```jsx
describe('no-card closer', () => {
  it('offers to find a bottle after a no-pick answer; Yes re-asks', async () => {
    streamRecommend.mockImplementation(async function* () {
      yield { type: 'token', text: 'Nebbiolo is lighter in color but grippier.' };
      yield { type: 'picks', picks: [] };
    });
    renderAsk();
    await userEvent.type(screen.getAllByRole('textbox')[0], 'is nebbiolo like pinot?{Enter}');
    expect(await screen.findByText('Want me to find you a good one here?')).toBeInTheDocument();
    await userEvent.click(screen.getByText('Yes, find one'));
    await waitFor(() => expect(streamRecommend).toHaveBeenCalledTimes(2));
    expect(streamRecommend.mock.calls[1][0].message).toMatch(/find me a good one/);
  });

  it('no offer when picks arrived', async () => {
    streamRecommend.mockImplementation(async function* () {
      yield { type: 'token', text: 'One pick.' };
      yield { type: 'picks', picks: [{ wine_id: 'a', name: 'Caymus', price: 89, retailer: 'H-E-B', why: 'x' }], session_id: 's' };
    });
    renderAsk();
    await userEvent.type(screen.getAllByRole('textbox')[0], 'a bold red{Enter}');
    await screen.findByText('Caymus');
    expect(screen.queryByText('Want me to find you a good one here?')).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** per mechanics.
- [ ] **Step 4: Run tests** — green.
- [ ] **Step 5: Commit**

```bash
git add frontend/src/screens/ChatRecommend.jsx frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx
git commit -m "feat: no-card closer — one offer converts an explanation into a pick"
```

---

### Task 11: In-store failure states

**Files:**
- Modify: `frontend/src/screens/ChatRecommend.jsx`
- Test: append to `frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx`

**Interfaces:**
- Consumes: the catch/finally in `callRecommend`; `pendingRetry` state.
- Produces: in ask mode, a failed request renders the somm apology (verbatim handoff copy), preserves the question, and offers one retry — `Ask again` when nothing streamed, `Finish the answer` when the answer half-arrived (some narrative streamed before the failure). What arrived stays. Plan mode keeps today's error UI.

Mechanics: in `callRecommend` track `let sawToken = false;` (set in token branch). Store the request on entry: `lastReqRef.current = req;` (a `useRef`). In catch, when `askMode`: `setError(null)` and append instead:

```jsx
      setMessages(prev => [...prev, {
        id: uuid(), role: 'sommelier', noFeedback: true,
        retry: sawToken ? 'finish' : 'again',
        text: "Lost you for a second — the signal in here is doing me no favors. Your question's saved; tap when you've got a bar or two.",
      }]);
```

Render in `messageList`: when `m.retry`, after the text add one button labeled `m.retry === 'finish' ? 'Finish the answer' : 'Ask again'`; onClick removes the retry message and calls `callRecommend(lastReqRef.current)` (the question is already in the thread — never re-append the user bubble).

- [ ] **Step 1: Failing tests** (append)

```jsx
describe('failure states', () => {
  it('dropped request: somm apology + Ask again resends the same request', async () => {
    streamRecommend
      .mockImplementationOnce(async function* () { throw new Error('network'); })
      .mockImplementationOnce(async function* () { yield { type: 'token', text: 'Back with you.' }; });
    renderAsk();
    await userEvent.type(screen.getAllByRole('textbox')[0], 'a good red{Enter}');
    expect(await screen.findByText(/Lost you for a second/)).toBeInTheDocument();
    expect(screen.getByText('a good red')).toBeInTheDocument();      // question preserved
    await userEvent.click(screen.getByText('Ask again'));
    await screen.findByText('Back with you.');
    expect(streamRecommend.mock.calls[1][0].message).toBe('a good red');
  });

  it('half-arrived answer keeps what arrived and offers Finish the answer', async () => {
    streamRecommend.mockImplementationOnce(async function* () {
      yield { type: 'token', text: 'The Caymus is plush and' };
      throw new Error('network');
    });
    renderAsk();
    await userEvent.type(screen.getAllByRole('textbox')[0], 'caymus?{Enter}');
    expect(await screen.findByText(/Lost you for a second/)).toBeInTheDocument();
    expect(screen.getByText(/The Caymus is plush and/)).toBeInTheDocument();  // partial stays
    expect(screen.getByText('Finish the answer')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** per mechanics.
- [ ] **Step 4: Run tests** — green.
- [ ] **Step 5: Commit**

```bash
git add frontend/src/screens/ChatRecommend.jsx frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx
git commit -m "feat: in-store failure states — apology in character, question preserved"
```

---

### Task 12: Full-suite verification + docs

**Files:**
- Modify: `CLAUDE.md` (item 37 — flip "NOT DONE (frontend)" to done, note deferred list)
- Modify: `docs/reference/recommendation.md` (short aisle-mode section: ask requests = wide budget + store_ref; picks event `comparison` field; /api/stores/nearby)

- [ ] **Step 1:** `cd frontend && npx vitest run` → all green. `cd backend && python3 -m pytest tests/ -m "not integration" -q` → all green.
- [ ] **Step 2:** Manual smoke via dev servers (backend `uvicorn api.main:app --reload`, frontend `npm run dev`): open mobile viewport → `/` shows tabs + strip → ASK → empty state → send "caymus or bonanza cabernet?" → comparison frame renders over live SSE.
- [ ] **Step 3:** Update the two docs. CLAUDE.md item 37: frontend shipped (tabs, strip, ask face, lazy zip, store picker, comparison frame, closer, failure states); deferred: swipe, strip dismissal, No-signal readout, desktop tabs, food row.
- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/reference/recommendation.md
git commit -m "docs: aisle-mode frontend shipped — item 37 flip + reference notes"
```

---

## Self-Review Notes

- **Spec coverage:** switch tabs (T4), Door-2 strip (T5), ask empty state + pills (T6), lazy zip (T7), store picker + pills-in-thread (T8, deviation: pills sit above the composer, not inline in the thread), streaming states (already existed, verified by existing tests), comparison frame (T9, deviation: no food row — no data; verdict-first variant is just narrative, no code needed), no-card closer (T10), failure states (T11, deviation: no `No signal` top-bar readout — deferred). Backend deltas for the mode were done previously (2026-07-30); T1/T2 add the two data gaps (store list, comparison payload).
- **Type consistency:** `buildAskReq` signature matches every call site shown; `storeRef`/`storeLabel`/`askZip` names consistent across T6–T9; picks event `comparison` name matches T2's backend field.
- **Test-behavior change:** the old `redirects to /` test is intentionally replaced in T6 — arriving without state is now the Ask face by design.
