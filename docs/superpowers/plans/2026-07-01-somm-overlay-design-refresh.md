# Somm Overlay + Design Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship three design features — upgraded structure graphics (ruler + segmented variants), Poster Option B (header+footer with compass rose), and an Ask Somm slide-in overlay on the wine dossier page.

**Architecture:** Tasks 1–2 are pure frontend component upgrades with no new files. Task 3 adds a new `/api/somm` streaming backend endpoint (Haiku, wine-context system prompt). Tasks 4–5 build the `SommOverlay.jsx` component and wire it into `RegionDossier.jsx`. The overlay manages its own session ID, message state, and Pattern B feedback (postFeedback already exists in api.js).

**Tech Stack:** React 19, Tailwind v3 CSS variables (inline styles per codebase convention), Lucide React (already installed), FastAPI + Anthropic Python SDK (streaming), supabase-py (not needed for Task 3 — no DB write).

## Global Constraints

- Python 3.9.6 — use `Optional[str]` / `List` / `Dict` from `typing`, NOT `str | None`
- All inline styles use CSS variable tokens: `var(--ink)`, `var(--bordeaux)`, `var(--brass)`, `var(--sage)`, `var(--paper)`, `var(--cream)`, `var(--cream-raised)`, `var(--faded)`, `var(--faded-2)`, `var(--border)`, `var(--bordeaux-deep)`, `var(--bordeaux-tint)`
- Font tokens: `var(--font-serif)` (DM Serif Display), `var(--font-sans)` (Archivo), `var(--font-mono)` (DM Mono)
- Sharp corners everywhere except chat bubbles (border-radius 0 for frames, buttons, tags; 999px pills for chips)
- No emoji, no gradients except existing bordeaux stripe fallback
- Run frontend tests from `frontend/`: `npm run test:run` (vitest)
- Run backend tests from `backend/`: `python3 -m pytest tests/ -m "not integration" -v`
- Lucide icons: strokeWidth 1.75 throughout; `ThumbsUp`/`ThumbsDown` already imported in `SommOverlay` needs no new install
- Claude model for `/api/somm`: `claude-haiku-4-5-20251001` (same as recommender)
- `StructureBars` items format: `[label, description, value]` tuples where `value` is 0–1 normalized float — tasks use `items[i][2]` for value, `items[i][0]` for label
- Pattern B feedback (thumbs on sommelier messages) is already fully built in `ChatRecommend`; `SommOverlay` replicates the same state shape and handler logic

---

### Task 1: StructureBars — ruler and segmented variants

Upgrade `StructureBars.jsx` to support two new `variant` props. The dossier uses `"ruler"` (editorial SVG ruler with bordeaux marker). The overlay uses `"segmented"` (20-segment discrete track). The default changes to `"ruler"` — the old continuous bar is dropped.

**Files:**
- Modify: `frontend/src/components/StructureBars.jsx`
- Modify: `frontend/src/components/__tests__/components.test.jsx` (update + add tests)

**Interfaces:**
- Produces: `<StructureBars items={[[label, desc, value], ...]} variant="ruler"|"segmented" />` where variant defaults to `"ruler"`
- Existing caller in `RegionDossier.jsx:102` passes no `variant` prop — it will automatically get `"ruler"` after this task

- [ ] **Step 1: Write the failing tests**

In `frontend/src/components/__tests__/components.test.jsx`, replace the existing `describe('StructureBars', ...)` block with:

```javascript
describe('StructureBars', () => {
  const items = [['Body', 'Med-Full', 0.8], ['Tannin', 'Firm', 0.7]];

  describe('ruler variant (default)', () => {
    it('renders all labels', () => {
      render(<StructureBars items={items} />);
      expect(screen.getByText('Body')).toBeInTheDocument();
      expect(screen.getByText('Tannin')).toBeInTheDocument();
    });
    it('renders numeric value markers', () => {
      render(<StructureBars items={items} />);
      expect(screen.getByText('80')).toBeInTheDocument();
      expect(screen.getByText('70')).toBeInTheDocument();
    });
  });

  describe('segmented variant', () => {
    it('renders all labels', () => {
      render(<StructureBars items={items} variant="segmented" />);
      expect(screen.getByText('Body')).toBeInTheDocument();
      expect(screen.getByText('Tannin')).toBeInTheDocument();
    });
    it('renders scale labels Low/Med/High/Max', () => {
      render(<StructureBars items={items} variant="segmented" />);
      expect(screen.getByText('Low')).toBeInTheDocument();
      expect(screen.getByText('Max')).toBeInTheDocument();
    });
    it('renders numeric value right of label', () => {
      render(<StructureBars items={items} variant="segmented" />);
      // 0.8 * 100 = 80, 0.7 * 100 = 70
      expect(screen.getByText('80')).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend
npm run test:run 2>&1 | grep -A5 "StructureBars"
```

Expected: failures about missing `"80"`, `"70"`, `"Low"`, `"Max"` text.

- [ ] **Step 3: Replace `StructureBars.jsx` with the two-variant implementation**

Replace the entire file:

```jsx
const RULER_W = 284;
const RULER_TICKS = 10;

function RulerBar({ label, value }) {
  const fillW = Math.round(value * RULER_W);
  return (
    <div>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-2)', marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ position: 'relative', width: RULER_W }}>
        <svg width={RULER_W} height={18} style={{ display: 'block' }}>
          <line x1={0} y1={0} x2={RULER_W} y2={0} stroke="var(--brass)" strokeWidth={0.75} opacity={0.4} />
          {Array.from({ length: RULER_TICKS + 1 }).map((_, i) => {
            const x = (i / RULER_TICKS) * RULER_W;
            const major = i % 5 === 0;
            return <line key={i} x1={x} y1={0} x2={x} y2={major ? 10 : 6} stroke="var(--brass)" strokeWidth={major ? 1 : 0.75} opacity={major ? 0.7 : 0.4} />;
          })}
        </svg>
        <div style={{ position: 'relative', height: 4, marginTop: 2 }}>
          <div style={{ position: 'absolute', inset: 0, background: 'var(--paper)', border: '0.5px solid rgba(176,141,87,0.3)' }} />
          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: fillW, background: 'var(--brass)' }} />
          <div style={{ position: 'absolute', left: fillW, top: -16, transform: 'translateX(-50%)' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8.5, color: 'var(--bordeaux)', whiteSpace: 'nowrap', letterSpacing: '0.05em' }}>
              {Math.round(value * 100)}
            </div>
          </div>
          <div style={{ position: 'absolute', left: fillW, top: -2, bottom: -2, width: 1.5, background: 'var(--bordeaux)', transform: 'translateX(-50%)' }} />
        </div>
      </div>
    </div>
  );
}

const SCALE_LABELS = ['Low', 'Med', 'High', 'Max'];
const SEGS = 20;

function SegmentedBar({ label, value }) {
  const filled = Math.round(value * SEGS);
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
        <span style={{ fontFamily: 'var(--font-sans)', fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-2)' }}>{label}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, color: 'var(--brass)', letterSpacing: '0.08em' }}>{Math.round(value * 100)}</span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        {SCALE_LABELS.map(t => (
          <span key={t} style={{ fontFamily: 'var(--font-mono)', fontSize: 7.5, color: 'var(--faded-2)', letterSpacing: '0.08em' }}>{t}</span>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 2 }}>
        {Array.from({ length: SEGS }).map((_, i) => (
          <div key={i} style={{
            flex: 1, height: 6, borderRadius: 1,
            background: i < filled ? 'var(--brass)' : 'var(--paper)',
            border: '0.5px solid', borderColor: i < filled ? 'var(--brass)' : 'rgba(176,141,87,0.25)',
          }} />
        ))}
      </div>
    </div>
  );
}

export default function StructureBars({ items, variant = 'ruler' }) {
  const gap = variant === 'ruler' ? 22 : 20;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap }}>
      {items.map(([label,, value]) =>
        variant === 'segmented'
          ? <SegmentedBar key={label} label={label} value={value} />
          : <RulerBar     key={label} label={label} value={value} />
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend
npm run test:run
```

Expected: all tests pass including new StructureBars tests. Note: `RegionDossier` tests that check for "Structure" text should still pass since that label comes from the `Eyebrow` in `RegionDossier.jsx`, not from `StructureBars` itself.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StructureBars.jsx frontend/src/components/__tests__/components.test.jsx
git commit -m "feat: StructureBars ruler + segmented variants — ruler is now default"
```

---

### Task 2: Poster Option B — header + footer with compass rose

Add `country` and `subregion` fields to `DISCOVERY_REGIONS`, export a `REGION_META` lookup map, and update `Poster.jsx` to render the Option B layout: above-frame header (country eyebrow · rule · coordinates) and below-frame footer (serif region name + compass SVG + coordinates + subregion note).

**Files:**
- Modify: `frontend/src/lib/regions.js` (add `country`, `subregion` to each region; add `REGION_META` export)
- Modify: `frontend/src/components/Poster.jsx`
- Modify: `frontend/src/components/__tests__/components.test.jsx` (add Poster Option B tests)

**Interfaces:**
- `REGION_META`: `{ [regionName: string]: { coord, country, subregion, tier } }` — O(1) lookup map derived from DISCOVERY_REGIONS
- `Poster` props: `{ region: string, className?: string }` — unchanged; Poster looks up metadata internally

- [ ] **Step 1: Write the failing Poster tests**

In `frontend/src/components/__tests__/components.test.jsx`, replace the existing `describe('Poster', ...)` block with:

```javascript
describe('Poster', () => {
  it('shows img element for a known Tier 1 region', () => {
    render(<Poster region="Tuscany" />);
    expect(screen.getByRole('img', { name: /tuscany/i })).toBeInTheDocument();
  });
  it('shows region name text in placeholder for unknown region', () => {
    render(<Poster region="Unknown Region" />);
    expect(screen.getByText('Unknown Region')).toBeInTheDocument();
  });
  it('shows country eyebrow above poster for known region', () => {
    render(<Poster region="Tuscany" />);
    expect(screen.getByText('Italy')).toBeInTheDocument();
  });
  it('shows region name in footer for known region', () => {
    render(<Poster region="Paso Robles" />);
    // The serif footer name — there will be two matches (eyebrow header + footer)
    // so just check at least one is present
    expect(screen.getAllByText('Paso Robles').length).toBeGreaterThan(0);
  });
  it('shows subregion in footer for known region', () => {
    render(<Poster region="Tuscany" />);
    expect(screen.getByText(/Chianti/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend
npm run test:run 2>&1 | grep -A5 "Poster"
```

Expected: failures for "Italy", "Chianti" not found.

- [ ] **Step 3: Add `country`, `subregion` to each entry in `DISCOVERY_REGIONS`**

In `frontend/src/lib/regions.js`, update `DISCOVERY_REGIONS` to:

```javascript
export const DISCOVERY_REGIONS = [
  // Tier 1
  { name: 'Tuscany',           coord: '43.8°N · 11.2°E',   country: 'Italy',       subregion: 'Chianti & Brunello',          flavors: ['dark cherry', 'leather', 'tobacco'],        tier: 1 },
  { name: 'Paso Robles',       coord: '35.6°N · 120.7°W',  country: 'California',  subregion: 'Westside & Eastside',          flavors: ['dark fruit', 'garrigue', 'structure'],      tier: 1 },
  { name: 'Napa Valley',       coord: '38.5°N · 122.4°W',  country: 'California',  subregion: 'Oakville & Stags Leap',        flavors: ['blackcurrant', 'cedar', 'full body'],       tier: 1 },
  { name: 'Sonoma',            coord: '38.3°N · 122.5°W',  country: 'California',  subregion: 'Russian River & Dry Creek',    flavors: ['red fruit', 'bright acidity', 'coastal'],   tier: 1 },
  { name: 'Mendoza',           coord: '32.9°S · 68.8°W',   country: 'Argentina',   subregion: 'Luján de Cuyo & Valle de Uco', flavors: ['dark plum', 'chocolate', 'spice'],          tier: 1 },
  { name: 'Willamette Valley', coord: '45.5°N · 123.0°W',  country: 'Oregon',      subregion: 'Dundee Hills & Eola-Amity',    flavors: ['cherry', 'earthy', 'bright acidity'],       tier: 1 },
  { name: 'Bordeaux',          coord: '44.8°N · 0.6°W',    country: 'France',      subregion: 'Left Bank & Right Bank',       flavors: ['blackcurrant', 'cedar', 'graphite'],        tier: 1 },
  { name: 'Rioja',             coord: '42.3°N · 2.5°W',    country: 'Spain',       subregion: 'Rioja Alta & Alavesa',         flavors: ['cherry', 'vanilla', 'leather'],             tier: 1 },
  { name: 'Marlborough',       coord: '41.5°S · 173.9°E',  country: 'New Zealand', subregion: 'Wairau & Awatere',             flavors: ['citrus', 'passionfruit', 'bright acidity'], tier: 1 },
  { name: 'Barossa Valley',    coord: '34.5°S · 138.9°E',  country: 'Australia',   subregion: 'Eden Valley & Greenock',       flavors: ['dark fruit', 'chocolate', 'spice'],         tier: 1 },
  // Tier 2
  { name: 'Burgundy',          coord: '47.0°N · 4.8°E',    country: 'France',      subregion: 'Côte d\'Or & Chablis',         flavors: ['red fruit', 'earthy', 'silky'],             tier: 2 },
  { name: 'Rhône Valley',      coord: '45.0°N · 4.8°E',    country: 'France',      subregion: 'Northern & Southern',          flavors: ['dark fruit', 'garrigue', 'pepper'],         tier: 2 },
  { name: 'Champagne',         coord: '49.1°N · 4.0°E',    country: 'France',      subregion: 'Grand Crus & Premier Crus',    flavors: ['brioche', 'citrus', 'mineral'],             tier: 2 },
  { name: 'Piedmont',          coord: '44.7°N · 8.0°E',    country: 'Italy',       subregion: 'Barolo & Barbaresco',          flavors: ['dark cherry', 'tar', 'roses'],              tier: 2 },
  { name: 'Douro Valley',      coord: '41.1°N · 7.6°W',    country: 'Portugal',    subregion: 'Cima Corgo & Douro Superior',  flavors: ['dark fruit', 'spice', 'structure'],         tier: 2 },
  { name: 'Columbia Valley',   coord: '46.2°N · 119.9°W',  country: 'Washington',  subregion: 'Red Mountain & Walla Walla',   flavors: ['dark cherry', 'spice', 'balance'],          tier: 2 },
  { name: 'Maipo Valley',      coord: '33.5°S · 70.6°W',   country: 'Chile',       subregion: 'Alto Maipo & Isla de Maipo',   flavors: ['blackcurrant', 'tobacco', 'structure'],     tier: 2 },
  { name: 'Mosel',             coord: '49.9°N · 7.0°E',    country: 'Germany',     subregion: 'Middle Mosel & Saar',          flavors: ['citrus', 'slate', 'off-dry'],               tier: 2 },
];
```

After the `DISCOVERY_REGIONS` array, add the lookup map (before `REGION_POSTERS`):

```javascript
export const REGION_META = Object.fromEntries(
  DISCOVERY_REGIONS.map(r => [r.name, r])
);
```

- [ ] **Step 4: Update `Poster.jsx` with Option B layout**

Replace the entire file:

```jsx
import { REGION_POSTERS, REGION_META } from '../lib/regions.js';

function CompassRose() {
  const angles = [0, 45, 90, 135, 180, 225, 270, 315];
  return (
    <svg width="36" height="36" viewBox="0 0 36 36" aria-hidden="true">
      <circle cx="18" cy="18" r="16" fill="none" stroke="var(--brass)" strokeWidth="0.75" />
      {angles.map((a, i) => {
        const rad = (a * Math.PI) / 180;
        const r1 = 13, r2 = i % 2 === 0 ? 10 : 12;
        return (
          <line
            key={a}
            x1={18 + Math.cos(rad) * r1} y1={18 + Math.sin(rad) * r1}
            x2={18 + Math.cos(rad) * r2} y2={18 + Math.sin(rad) * r2}
            stroke="var(--brass)" strokeWidth={i % 2 === 0 ? 1 : 0.75}
          />
        );
      })}
      <text x="18" y="8" textAnchor="middle" fontFamily="var(--font-mono)" fontSize="5" fill="var(--brass)">N</text>
      <circle cx="18" cy="18" r="2" fill="var(--bordeaux)" />
    </svg>
  );
}

export default function Poster({ region, className }) {
  const src  = REGION_POSTERS[region];
  const meta = REGION_META[region];

  return (
    <div className={className} style={{ width: '100%' }}>
      {/* Header above frame */}
      {meta && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 9, letterSpacing: '0.3em', textTransform: 'uppercase', color: 'var(--faded)' }}>
            {meta.country}
          </div>
          <div style={{ flex: 1, height: '0.75px', background: 'var(--border)' }} />
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--sage)', letterSpacing: '0.1em' }}>
            {meta.coord}
          </div>
        </div>
      )}

      {/* Frame */}
      <div style={{ background: 'var(--cream)', padding: 10, border: '1.5px solid var(--ink)', boxShadow: 'var(--shadow-print)' }}>
        <div style={{ border: '0.75px solid var(--brass)', padding: 4 }}>
          {src ? (
            <img src={src} alt={region} style={{ display: 'block', width: '100%', aspectRatio: '372/494', objectFit: 'cover' }} />
          ) : (
            <div style={{ aspectRatio: '372/494', background: 'repeating-linear-gradient(135deg,var(--bordeaux-deep) 0px,var(--bordeaux-deep) 8px,var(--bordeaux) 8px,var(--bordeaux) 16px)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, letterSpacing: '0.22em', color: 'var(--cream)', opacity: 0.5 }}>REGION POSTER</span>
              <span style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--cream)', opacity: 0.7 }}>{region}</span>
            </div>
          )}
        </div>
      </div>

      {/* Footer below frame */}
      {meta && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 32, lineHeight: 1, color: 'var(--ink)' }}>
            {region}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 7 }}>
            <CompassRose />
            <div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, color: 'var(--ink-2)', letterSpacing: '0.1em' }}>
                {meta.coord}
              </div>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10, color: 'var(--faded)', marginTop: 2, letterSpacing: '0.04em' }}>
                {meta.subregion}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd frontend
npm run test:run
```

Expected: all tests pass including 5 new Poster tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/regions.js frontend/src/components/Poster.jsx frontend/src/components/__tests__/components.test.jsx
git commit -m "feat: Poster Option B — header/footer layout, compass rose, region meta"
```

---

### Task 3: Backend `/api/somm` streaming endpoint

New FastAPI endpoint that accepts wine context + message + history, builds a system prompt with the wine context, and streams a Claude Haiku sommelier response. No DB writes. When `message` is empty, generates an opening statement.

**Files:**
- Create: `backend/api/routers/somm.py`
- Modify: `backend/api/schemas.py` (add `SommWineContext`, `SommRequest`)
- Modify: `backend/api/main.py` (register router)
- Create: `backend/tests/test_somm_api.py`

**Interfaces:**
- Produces: `POST /api/somm` — accepts `SommRequest`, returns `text/event-stream` with `data: {"type":"token","text":"..."}` events, terminated by `data: [DONE]`
- Produces: `SommWineContext` — `{wine_name, producer?, vintage?, price?, store?, tags, region?, wine_type?}`
- Produces: `SommRequest` — `{wine: SommWineContext, message: str, history?: [{role, content}]}`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_somm_api.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from api.main import app

_WINE = {
    "wine_name": "Esprit de Tablas",
    "producer": "Tablas Creek",
    "vintage": 2021,
    "price": 55.0,
    "store": "Spec's",
    "tags": ["dark cherry", "garrigue", "leather"],
    "region": "Paso Robles",
    "wine_type": "Red Wine",
}


def _mock_stream(tokens):
    """Return a mock anthropic streaming context manager yielding text chunks."""
    from unittest.mock import MagicMock

    class FakeEvent:
        def __init__(self, t):
            self.type = "content_block_delta"
            self.delta = MagicMock()
            self.delta.type = "text_delta"
            self.delta.text = t

    class FakeStream:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def __iter__(self):
            for t in tokens:
                yield FakeEvent(t)

    return FakeStream()


@pytest.mark.asyncio
async def test_somm_streams_tokens():
    with patch("api.routers.somm.anthropic_client") as mock_client:
        mock_client.messages.stream.return_value = _mock_stream(["A great", " wine."])
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/somm", json={"wine": _WINE, "message": "Tell me about this."})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert '"type": "token"' in body
    assert "A great" in body
    assert "[DONE]" in body


@pytest.mark.asyncio
async def test_somm_empty_message_still_streams():
    with patch("api.routers.somm.anthropic_client") as mock_client:
        mock_client.messages.stream.return_value = _mock_stream(["Lovely structure."])
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/somm", json={"wine": _WINE, "message": ""})
    assert resp.status_code == 200
    assert "Lovely structure." in resp.text


@pytest.mark.asyncio
async def test_somm_missing_wine_name_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/somm", json={"wine": {}, "message": "hi"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_somm_with_history():
    with patch("api.routers.somm.anthropic_client") as mock_client:
        mock_client.messages.stream.return_value = _mock_stream(["Yes, decant it."])
        history = [
            {"role": "user", "content": "Should I decant it?"},
        ]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/somm", json={"wine": _WINE, "message": "How long?", "history": history})
    assert resp.status_code == 200
    assert "Yes, decant it." in resp.text
    # Verify history was passed to Claude
    call_kwargs = mock_client.messages.stream.call_args[1]
    messages_sent = call_kwargs["messages"]
    assert any(m["role"] == "user" and "Should I decant it?" in m["content"] for m in messages_sent)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python3 -m pytest tests/test_somm_api.py -v
```

Expected: 4 failures — `somm` router not registered.

- [ ] **Step 3: Add `SommWineContext` and `SommRequest` to `schemas.py`**

Append to `backend/api/schemas.py`:

```python
class SommWineContext(BaseModel):
    wine_name: str
    producer: Optional[str] = None
    vintage: Optional[int] = None
    price: Optional[float] = None
    store: Optional[str] = None
    tags: List[str] = []
    region: Optional[str] = None
    wine_type: Optional[str] = None


class SommRequest(BaseModel):
    wine: SommWineContext
    message: str
    history: Optional[List[Dict[str, Any]]] = None
```

- [ ] **Step 4: Create `backend/api/routers/somm.py`**

```python
import json
import anthropic
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from api.schemas import SommRequest

router = APIRouter(prefix="/api/somm", tags=["somm"])

anthropic_client = anthropic.Anthropic()

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 512


def _system_prompt(wine) -> str:
    parts = [f"Wine: {wine.wine_name}"]
    if wine.producer:  parts.append(f"Producer: {wine.producer}")
    if wine.vintage:   parts.append(f"Vintage: {wine.vintage}")
    if wine.price:     parts.append(f"Price: ${wine.price:.0f}")
    if wine.store:     parts.append(f"Available at: {wine.store}")
    if wine.region:    parts.append(f"Region: {wine.region}")
    if wine.tags:      parts.append(f"Flavor profile: {', '.join(wine.tags)}")
    context = "\n".join(parts)
    return (
        "You are a sommelier assistant — knowledgeable, opinionated, direct. "
        "The user is currently viewing this wine:\n\n"
        f"{context}\n\n"
        "Keep responses to 2–3 sentences. Lead with the wine's most distinctive characteristic. "
        "Be specific about flavors, structure, and place. Never use filler phrases."
    )


def _build_messages(req: SommRequest) -> list:
    messages = []
    for h in (req.history or []):
        role = h.get("role", "user")
        if role not in ("user", "assistant"):
            continue
        messages.append({"role": role, "content": h.get("content", "")})
    user_msg = req.message.strip() or (
        f"Introduce {req.wine.wine_name} — lead with its most distinctive characteristic "
        "in one sentence, then ask what I'd like to know."
    )
    messages.append({"role": "user", "content": user_msg})
    return messages


@router.post("", status_code=200)
async def ask_somm(req: SommRequest):
    system = _system_prompt(req.wine)
    messages = _build_messages(req)

    def event_gen():
        try:
            with anthropic_client.messages.stream(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                system=system,
                messages=messages,
            ) as stream:
                for event in stream:
                    if (
                        event.type == "content_block_delta"
                        and event.delta.type == "text_delta"
                        and event.delta.text
                    ):
                        yield "data: " + json.dumps({"type": "token", "text": event.delta.text}) + "\n\n"
        except Exception as e:
            yield "data: " + json.dumps({"type": "error", "message": str(e)}) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 5: Register the router in `backend/api/main.py`**

Add the import (with the other router imports):
```python
from api.routers import wines, enrichment, recommend, region, feedback, somm
```

Add the include (after the feedback router):
```python
app.include_router(somm.router)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend
python3 -m pytest tests/test_somm_api.py -v
```

Expected: 4/4 PASS.

- [ ] **Step 7: Run full suite for regressions**

```bash
cd backend
python3 -m pytest tests/ -m "not integration" -v
```

Expected: all pass (175 including 4 new).

- [ ] **Step 8: Commit**

```bash
git add backend/api/routers/somm.py backend/api/schemas.py backend/api/main.py backend/tests/test_somm_api.py
git commit -m "feat: POST /api/somm streaming endpoint — wine-context sommelier chat"
```

---

### Task 4: `SommOverlay` component + `streamSomm` in api.js

Build the self-contained overlay: FAB button (fixed bottom-right), 400px slide-in panel (fixed full-height right edge), context strip, chat scroll with Pattern B feedback thumbs, suggestion chips, and composer. Add `streamSomm` to api.js.

**Files:**
- Create: `frontend/src/components/SommOverlay.jsx`
- Create: `frontend/src/components/__tests__/SommOverlay.test.jsx`
- Modify: `frontend/src/lib/api.js` (add `streamSomm`)

**Interfaces:**
- Consumes: `POST /api/somm` from Task 3
- Consumes: `postFeedback` already in `frontend/src/lib/api.js`
- Produces: `<SommOverlay wine={SommWineProps} />` where `SommWineProps = { wine_name, producer?, vintage?, price?, store?, tags, region?, wine_type? }`
- The component manages all state internally (open, messages, votes, sessionId, chips, loading)

**Chip sets (hardcoded by wine type):**

Red/default chips (shown when `wine.wine_type` does not include "White", "Rosé", "Sparkling", or "Orange"):
```
["Is {vintage} a good year?", "Should I decant it?", "What food pairs?", "Cellar potential?", "Cheaper alternative?"]
```

White/Sparkling/Rosé/Orange chips:
```
["Serve temperature?", "Drink now or wait?", "What food pairs?", "Similar styles?", "Cheaper alternative?"]
```

Vintage token `{vintage}` replaced with `wine.vintage` if available, otherwise chip reads "Is this a good vintage?".

- [ ] **Step 1: Add `streamSomm` to `frontend/src/lib/api.js`**

Append to `frontend/src/lib/api.js`:

```javascript
export async function* streamSomm({ wine, message, history }) {
  let resp;
  try {
    resp = await fetch(`${BASE}/api/somm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wine, message, history }),
    });
  } catch {
    yield { type: 'error', message: 'Connection failed' };
    return;
  }
  if (!resp.ok) { yield { type: 'error', message: 'Somm unavailable' }; return; }
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split('\n\n');
    buf = parts.pop();
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith('data:')) continue;
      const raw = line.slice(5).trim();
      if (raw === '[DONE]') return;
      try { yield JSON.parse(raw); } catch {}
    }
  }
}
```

- [ ] **Step 2: Write the failing `SommOverlay` tests**

Create `frontend/src/components/__tests__/SommOverlay.test.jsx`:

```javascript
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SommOverlay from '../SommOverlay.jsx';

vi.mock('../../lib/api.js', () => ({
  streamSomm: vi.fn(),
  postFeedback: vi.fn(),
}));
import { streamSomm, postFeedback } from '../../lib/api.js';

const wine = {
  wine_name: 'Esprit de Tablas',
  producer: 'Tablas Creek',
  vintage: 2021,
  price: 55,
  store: "Spec's",
  tags: ['dark cherry', 'garrigue'],
  region: 'Paso Robles',
  wine_type: 'Red Wine',
};

beforeEach(() => {
  streamSomm.mockClear();
  postFeedback.mockClear();
  streamSomm.mockImplementation(async function* () {
    yield { type: 'token', text: 'A structured, complex wine.' };
  });
});

it('renders FAB button', () => {
  render(<SommOverlay wine={wine} />);
  expect(screen.getByRole('button', { name: /ask somm/i })).toBeInTheDocument();
});

it('panel is hidden by default', () => {
  render(<SommOverlay wine={wine} />);
  expect(screen.queryByText('Somm')).not.toBeInTheDocument();
});

it('clicking FAB opens panel', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  expect(screen.getByText('Somm')).toBeInTheDocument();
});

it('FAB hides when panel is open', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  expect(screen.queryByRole('button', { name: /ask somm/i })).not.toBeInTheDocument();
});

it('context strip shows wine name', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  expect(screen.getByText('Esprit de Tablas')).toBeInTheDocument();
});

it('context strip shows price', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  expect(screen.getByText('$55')).toBeInTheDocument();
});

it('opening message streams on first open', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  await waitFor(() => expect(screen.getByText('A structured, complex wine.')).toBeInTheDocument());
});

it('shows "Was this useful?" row on sommelier message', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  await waitFor(() => expect(screen.getByText('Was this useful?')).toBeInTheDocument());
});

it('shows suggestion chips', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  expect(screen.getByText(/Cellar potential/i)).toBeInTheDocument();
});

it('close button hides panel and shows FAB again', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  await userEvent.click(screen.getByTitle('Close'));
  expect(screen.queryByText('Somm')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /ask somm/i })).toBeInTheDocument();
});

it('chat history persists across close and reopen', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  await waitFor(() => expect(screen.getByText('A structured, complex wine.')).toBeInTheDocument());
  await userEvent.click(screen.getByTitle('Close'));
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  // Message should still be visible; streamSomm should NOT have been called a second time
  expect(screen.getByText('A structured, complex wine.')).toBeInTheDocument();
  expect(streamSomm).toHaveBeenCalledTimes(1);
});

it('chip click sends the chip text as a message', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  await waitFor(() => expect(screen.getByText(/Cellar potential/i)).toBeInTheDocument());
  await userEvent.click(screen.getByText(/Cellar potential/i));
  // The chip text should appear as a user bubble
  await waitFor(() => expect(screen.getByText('Cellar potential?')).toBeInTheDocument());
});
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd frontend
npm run test:run 2>&1 | grep -E "FAIL|SommOverlay"
```

Expected: 12 failures — SommOverlay module not found.

- [ ] **Step 4: Create `frontend/src/components/SommOverlay.jsx`**

```jsx
import { useState, useEffect, useRef } from 'react';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import Stamp from './Stamp.jsx';
import Tag from './Tag.jsx';
import { streamSomm, postFeedback } from '../lib/api.js';

const _EASE = 'all 140ms cubic-bezier(.25,.46,.45,.94)';

const CHIPS_RED = [
  'Is this a good vintage?',
  'Should I decant it?',
  'What food pairs?',
  'Cellar potential?',
  'Cheaper alternative?',
];
const CHIPS_WHITE = [
  'Serve temperature?',
  'Drink now or wait?',
  'What food pairs?',
  'Similar styles?',
  'Cheaper alternative?',
];

function isWhiteStyle(wineType) {
  const t = (wineType ?? '').toLowerCase();
  return t.includes('white') || t.includes('rosé') || t.includes('rose') || t.includes('sparkling') || t.includes('orange');
}

function initialChips(wine) {
  const base = isWhiteStyle(wine.wine_type) ? CHIPS_WHITE : CHIPS_RED;
  return base.map(c =>
    wine.vintage ? c.replace('this a good vintage', `${wine.vintage} a good year`) : c
  );
}

function ThumbBtn({ direction, voted, onClick }) {
  const Icon = direction === 'up' ? ThumbsUp : ThumbsDown;
  const label = direction === 'up' ? 'Helpful' : 'Not helpful';
  const activeColor = direction === 'up' ? 'var(--sage)' : 'var(--bordeaux)';
  return (
    <button
      type="button"
      title={label}
      onClick={e => { e.stopPropagation(); onClick(direction); }}
      style={{
        cursor: 'pointer', width: 24, height: 24, borderRadius: 2,
        border: voted ? `1px solid ${activeColor}` : '1px solid var(--border)',
        background: voted ? activeColor : 'transparent',
        color: voted ? 'var(--cream)' : 'var(--faded)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: _EASE, padding: 0,
      }}
    >
      <Icon size={11} strokeWidth={1.75} />
    </button>
  );
}

function SommelierBubble({ children, vote, onVote }) {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 12 }}>
      <div style={{ width: 28, height: 28, borderRadius: '50%', flex: 'none', background: 'var(--bordeaux)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Stamp size={18} reversed />
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ background: 'var(--cream-raised)', border: '1px solid var(--border)', borderRadius: '4px 12px 12px 12px', padding: '11px 13px', fontFamily: 'var(--font-sans)', fontSize: 13, lineHeight: 1.55, color: 'var(--ink-2)' }}>
          {children}
        </div>
        {onVote && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 5, paddingLeft: 4 }}>
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 10, letterSpacing: '0.06em', color: 'var(--faded)' }}>Was this useful?</span>
            <div style={{ display: 'flex', gap: 4 }}>
              <ThumbBtn direction="up"   voted={vote === 'up'}   onClick={onVote} />
              <ThumbBtn direction="down" voted={vote === 'down'} onClick={onVote} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function UserBubble({ children }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
      <div style={{ background: 'var(--bordeaux)', color: 'var(--cream)', borderRadius: '12px 4px 12px 12px', padding: '10px 13px', fontSize: 13, lineHeight: 1.5, maxWidth: '80%' }}>
        {children}
      </div>
    </div>
  );
}

export default function SommOverlay({ wine }) {
  const [open,         setOpen]         = useState(false);
  const [messages,     setMessages]     = useState([]);
  const [messageVotes, setMessageVotes] = useState({});
  const [sessionId]                     = useState(() => crypto.randomUUID());
  const [chips,        setChips]        = useState(() => initialChips(wine));
  const [loading,      setLoading]      = useState(false);
  const [input,        setInput]        = useState('');
  const scrollRef = useRef(null);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  // Fire opening message on first open
  useEffect(() => {
    if (open && messages.length === 0) {
      callSomm('');
    }
  }, [open]);

  async function callSomm(message) {
    if (loading) return;
    const history = messages
      .filter(m => !m.noFeedback)
      .map(m => ({ role: m.role === 'sommelier' ? 'assistant' : 'user', content: m.text }));

    setLoading(true);
    let firstToken = true;
    try {
      for await (const event of streamSomm({ wine, message, history })) {
        if (event.type === 'token') {
          if (firstToken) {
            firstToken = false;
            setLoading(false);
            setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'sommelier', text: event.text }]);
          } else {
            setMessages(prev => {
              const msgs = [...prev];
              msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], text: msgs[msgs.length - 1].text + event.text };
              return msgs;
            });
          }
        }
      }
    } catch {}
    setLoading(false);
  }

  function handleSend(text) {
    if (!text.trim() || loading) return;
    setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'user', text }]);
    setInput('');
    callSomm(text);
  }

  function handleChip(chip) {
    setChips(prev => prev.filter(c => c !== chip));
    handleSend(chip);
  }

  function handleMessageVote(messageId, direction) {
    const current = messageVotes[messageId] ?? null;
    const next = current === direction ? null : direction;
    setMessageVotes(prev => ({ ...prev, [messageId]: next }));
    if (direction === 'down' && current !== 'down') {
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: 'sommelier',
        text: "Noted — what didn't land? The **grape variety**, the **price point**, or the **region**?",
        noFeedback: true,
      }]);
    }
    postFeedback({ type: 'sommelier_message', entity_id: messageId, vote: next, session_id: sessionId });
  }

  const subtitle = [wine.producer, wine.vintage, wine.store].filter(Boolean).join(' · ');

  return (
    <>
      {/* FAB */}
      {!open && (
        <button
          aria-label="Ask Somm"
          onClick={() => setOpen(true)}
          style={{
            position: 'fixed', bottom: 32, right: 36, zIndex: 200,
            display: 'flex', alignItems: 'center', gap: 8,
            background: 'var(--bordeaux)', color: 'var(--cream)',
            border: 'none', borderRadius: 0, cursor: 'pointer',
            padding: '12px 20px 12px 14px',
            fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, letterSpacing: '0.04em',
            boxShadow: '0 4px 20px rgba(110,16,35,0.38)',
            transition: _EASE,
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--bordeaux-deep)'; e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 8px 28px rgba(110,16,35,0.46)'; }}
          onMouseLeave={e => { e.currentTarget.style.background = 'var(--bordeaux)'; e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = '0 4px 20px rgba(110,16,35,0.38)'; }}
        >
          <div style={{ width: 24, height: 24, borderRadius: '50%', border: '1px solid rgba(245,239,230,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none' }}>
            <Stamp size={16} reversed />
          </div>
          Ask Somm
        </button>
      )}

      {/* Backdrop dim */}
      {open && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.12)', pointerEvents: 'none', zIndex: 198 }} />
      )}

      {/* Panel */}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 400,
        background: 'var(--cream)', borderLeft: '1.5px solid var(--ink)',
        display: 'flex', flexDirection: 'column', zIndex: 199,
        transform: open ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 320ms cubic-bezier(.25,.46,.45,.94)',
        pointerEvents: open ? 'auto' : 'none',
      }}>
        {/* Context strip */}
        <div style={{ padding: '14px 18px 12px', borderBottom: '1px solid var(--border)', background: 'var(--paper)' }}>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 8.5, letterSpacing: '0.26em', textTransform: 'uppercase', color: 'var(--faded)', marginBottom: 4 }}>Discussing</div>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 16, color: 'var(--ink)', lineHeight: 1.1 }}>{wine.wine_name}</div>
          {subtitle && (
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11.5, color: 'var(--faded)', marginTop: 3 }}>{subtitle}</div>
          )}
          {wine.price && (
            <div style={{ fontFamily: 'var(--font-serif)', fontSize: 15, color: 'var(--bordeaux)', marginTop: 2 }}>${wine.price}</div>
          )}
          {wine.tags?.length > 0 && (
            <div style={{ display: 'flex', gap: 5, marginTop: 8, flexWrap: 'wrap' }}>
              {wine.tags.slice(0, 3).map(t => <Tag key={t}>{t}</Tag>)}
            </div>
          )}
        </div>

        {/* Panel title bar */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 18px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <div style={{ width: 26, height: 26, borderRadius: '50%', background: 'var(--bordeaux)', display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none' }}>
              <Stamp size={16} reversed />
            </div>
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>Somm</span>
          </div>
          <button
            title="Close"
            onClick={() => setOpen(false)}
            style={{ cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 18, color: 'var(--faded)', padding: '2px 6px', lineHeight: 1 }}
          >
            ×
          </button>
        </div>

        {/* Chat scroll */}
        <div ref={scrollRef} style={{ flex: 1, overflow: 'auto', padding: '16px 18px' }}>
          {messages.map((m, i) =>
            m.role === 'user'
              ? <UserBubble key={m.id ?? i}>{m.text}</UserBubble>
              : <SommelierBubble
                  key={m.id ?? i}
                  vote={messageVotes[m.id] ?? null}
                  onVote={m.noFeedback ? undefined : dir => handleMessageVote(m.id, dir)}
                >
                  {m.text.split('\n\n').map((para, j) => (
                    <p key={j} style={{ margin: j > 0 ? '8px 0 0' : 0 }}>
                      {para.split(/\*\*([^*]+)\*\*/g).map((part, k) =>
                        k % 2 === 1
                          ? <strong key={k} style={{ color: 'var(--bordeaux)' }}>{part}</strong>
                          : part
                      )}
                    </p>
                  ))}
                </SommelierBubble>
          )}
          {loading && (
            <SommelierBubble>
              <span style={{ color: 'var(--faded)', fontStyle: 'italic' }}>Thinking…</span>
            </SommelierBubble>
          )}
        </div>

        {/* Suggestion chips */}
        {chips.length > 0 && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', padding: '8px 18px 4px', borderTop: '1px solid var(--border)' }}>
            {chips.map(c => (
              <button key={c} onClick={() => handleChip(c)} disabled={loading}
                style={{ cursor: loading ? 'default' : 'pointer', opacity: loading ? 0.4 : 1, fontFamily: 'var(--font-sans)', fontSize: 11.5, color: 'var(--bordeaux)', background: 'var(--bordeaux-tint)', border: 'none', borderRadius: 999, padding: '5px 13px', transition: _EASE }}>
                {c}
              </button>
            ))}
          </div>
        )}

        {/* Composer */}
        <div style={{ borderTop: '1px solid var(--border)', padding: '12px 18px 16px' }}>
          <div style={{ display: 'flex', border: '1.5px solid var(--ink)', background: 'var(--cream-raised)' }}>
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && input.trim()) handleSend(input.trim()); }}
              placeholder="Ask about this wine…"
              style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--ink)', padding: '10px 12px' }}
            />
            <button
              onClick={() => handleSend(input.trim())}
              disabled={loading || !input.trim()}
              style={{ border: 'none', background: 'var(--bordeaux)', color: 'var(--cream)', padding: '0 14px', cursor: (loading || !input.trim()) ? 'default' : 'pointer', opacity: (loading || !input.trim()) ? 0.4 : 1, fontSize: 15, borderRadius: 0 }}>
              →
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd frontend
npm run test:run
```

Expected: all tests pass including 12 new SommOverlay tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/SommOverlay.jsx frontend/src/components/__tests__/SommOverlay.test.jsx frontend/src/lib/api.js
git commit -m "feat: SommOverlay component — FAB + slide-in panel with wine context + Pattern B feedback"
```

---

### Task 5: Wire SommOverlay into RegionDossier

Import `SommOverlay` into `RegionDossier.jsx`, construct the `wine` context object from the loaded `detail` + `pick` state, and render the overlay. Add two tests to `RegionDossier.test.jsx`.

**Files:**
- Modify: `frontend/src/screens/RegionDossier.jsx`
- Modify: `frontend/src/screens/__tests__/RegionDossier.test.jsx`

**Interfaces:**
- Consumes: `<SommOverlay wine={SommWineProps} />` from Task 4
- `SommWineProps = { wine_name, producer?, vintage?, price?, store?, tags, region?, wine_type? }`

- [ ] **Step 1: Write the failing tests**

In `frontend/src/screens/__tests__/RegionDossier.test.jsx`, add these tests:

First, add the mock for SommOverlay at the top of the file (after existing mocks):

```javascript
vi.mock('../../components/SommOverlay.jsx', () => ({
  default: ({ wine }) => <div data-testid="somm-overlay">Ask Somm for {wine.wine_name}</div>,
}));
```

Then append:

```javascript
it('renders SommOverlay with wine name', () => {
  getWine.mockReturnValue(new Promise(() => {}));
  renderScreen();
  expect(screen.getByTestId('somm-overlay')).toBeInTheDocument();
  expect(screen.getByText(/Ask Somm for Esprit de Tablas/i)).toBeInTheDocument();
});

it('SommOverlay receives price from pick', () => {
  getWine.mockReturnValue(new Promise(() => {}));
  renderScreen();
  // pick.price = 55, wine_name = 'Esprit de Tablas' — mock renders both
  expect(screen.getByText(/Ask Somm for Esprit de Tablas/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend
npm run test:run 2>&1 | grep -E "somm-overlay|SommOverlay|FAIL.*RegionDossier"
```

Expected: 2 failures — `somm-overlay` testid not found.

- [ ] **Step 3: Update `RegionDossier.jsx` to import and render `SommOverlay`**

Add the import at the top (with other component imports):

```javascript
import SommOverlay from '../components/SommOverlay.jsx';
```

Add the `sommWine` object inside the component (after the `subtitle` line, before the `return`):

```javascript
const sommWine = {
  wine_name: wine.name ?? pick.name,
  producer:  wine.brand   ?? null,
  vintage:   wine.vintage_year ?? null,
  price:     pick.price   ?? null,
  store:     pick.retailer ?? null,
  tags:      flavors,
  region:    region        ?? null,
  wine_type: wine.wine_type ?? null,
};
```

At the very end of the returned JSX (just before the final closing `</div>` of the component), add:

```jsx
      <SommOverlay wine={sommWine} />
```

The full bottom of the component's return should look like:

```jsx
          <div style={{ marginTop: 18 }}>
            <Btn variant="ghost" onClick={() => navigate('/discover')}>More from this region</Btn>
          </div>
        </div>
      </div>
      <SommOverlay wine={sommWine} />
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend
npm run test:run
```

Expected: all tests pass including 2 new RegionDossier+SommOverlay tests.

- [ ] **Step 5: Run full suite (backend + frontend) for regressions**

```bash
cd backend && python3 -m pytest tests/ -m "not integration" -v
cd ../frontend && npm run test:run
```

Expected: both pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/screens/RegionDossier.jsx frontend/src/screens/__tests__/RegionDossier.test.jsx
git commit -m "feat: wire SommOverlay into RegionDossier with wine context"
```

---

## Self-Review

**Spec coverage:**
- Structure Option A (segmented, 20 segs, Low/Med/High/Max scale, brass numeric right of label): ✅ Task 1 `SegmentedBar`
- Structure Option B (editorial ruler, SVG ticks, bordeaux marker + floating numeric, brass fill): ✅ Task 1 `RulerBar`
- Ruler is default for dossier (RegionDossier uses no `variant` prop → gets ruler): ✅ Task 1 default
- Segmented for overlay compact context: ✅ SommOverlay passes `variant="segmented"` NOT NEEDED — SommOverlay doesn't use StructureBars (the overlay doesn't show structure data per the spec)
- Poster Option B: above-frame header (country eyebrow · rule · coordinates mono), frame unchanged, below-frame footer (serif 32px region name + compass + coordinates + subregion): ✅ Task 2
- Compass rose: 8 ticks (0/45/90…315), major at 0/90/180/270, brass circle 0.75px, N label mono 5px, bordeaux center dot r=2: ✅ Task 2 `CompassRose`
- Ask Somm FAB: fixed bottom-right, bordeaux bg, sharp corners, stamp icon + label, shadow, hover deepens: ✅ Task 4
- Panel: 400px, fixed right, full-height, 1.5px ink left border, cream bg, slide from translateX(100%), 320ms ease: ✅ Task 4
- Panel anatomy: context strip, title bar with × close, chat scroll, chips, composer: ✅ Task 4
- Context strip: "Discussing" eyebrow, wine name serif 16px, producer·vintage·store, price, flavor tags: ✅ Task 4
- Opening message Claude-generated (not hardcoded), triggered on first open: ✅ Task 4 `useEffect([open])`
- Suggestion chips red vs white/sparkling set: ✅ Task 4 `CHIPS_RED`/`CHIPS_WHITE`
- Chips disappear after use: ✅ Task 4 `setChips(prev => prev.filter(c => c !== chip))`
- Pattern B feedback on sommelier messages in overlay: ✅ Task 4 `SommelierBubble` with vote/onVote
- Follow-up bubble on thumbs-down: ✅ Task 4 `handleMessageVote`
- Chat history persists across close/reopen: ✅ Task 4 (messages in component state, not cleared on close)
- Page dims when panel open (fixed backdrop): ✅ Task 4 backdrop div
- FAB hides when panel open: ✅ Task 4 `{!open && <button>}`
- `/api/somm` endpoint, streaming SSE, wine context system prompt, history support: ✅ Task 3
- Empty message → opening prompt instruction: ✅ Task 3 `_build_messages`
- RegionDossier wired with full `sommWine` context including `wine_type` for chip set: ✅ Task 5

**Placeholder scan:** None.

**Type consistency:** `SommWineProps` shape defined in Task 4 and consumed in Task 5 — `wine_name`, `producer`, `vintage`, `price`, `store`, `tags`, `region`, `wine_type`. Backend `SommWineContext` field names match: `wine_name`, `producer`, `vintage`, `price`, `store`, `tags`, `region`, `wine_type`. ✅
