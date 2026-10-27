# Bottle Identify Frontend v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real, tappable screen in the Somm app (`/identify`) that lets a tester snap or upload a bottle photo and see the identification result — reachable from both the mobile bottom tab bar and the desktop nav — so a small group of real users can test bottle identification through the live app this week.

**Architecture:** One new API client function (`identifyBottle`), one new screen component (`Identify.jsx`) implementing a 4-state state machine (`idle` → `identifying` → `result` | `error`), and two small additions to existing nav components (a 6th tab, a 6th desktop link). On a successful match, the screen hands off to the already-built `/wine/:id` dossier route rather than re-implementing price/availability/save logic.

**Tech Stack:** React 19, Vite, react-router-dom, Vitest + Testing Library (existing project conventions).

**Design doc:** `docs/superpowers/specs/2026-10-26-bottle-identify-frontend-v1-design.md`

---

## Task 1: API client — `identifyBottle`

**Files:**
- Modify: `frontend/src/lib/api.js`
- Test: `frontend/src/lib/__tests__/api.test.js`

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/lib/__tests__/api.test.js`:

```js
describe('identifyBottle', () => {
  it('POSTs the photo as multipart form data to /api/identify', async () => {
    const file = new File(['fake-bytes'], 'bottle.jpg', { type: 'image/jpeg' });
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'exact', wine: { id: 'w1', name: 'Esprit de Tablas' } }),
    });

    const result = await identifyBottle(file);

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/identify'),
      expect.objectContaining({ method: 'POST' })
    );
    const [, options] = fetch.mock.calls[0];
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.body.get('photo')).toBe(file);
    expect(result).toEqual({ status: 'exact', wine: { id: 'w1', name: 'Esprit de Tablas' } });
  });

  it('throws with the API detail message on a non-ok response', async () => {
    const file = new File(['fake-bytes'], 'bottle.jpg', { type: 'image/jpeg' });
    fetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'Upload an image file (jpeg/png/heic).' }),
    });

    await expect(identifyBottle(file)).rejects.toThrow('Upload an image file (jpeg/png/heic).');
  });

  it('falls back to an HTTP-status message when the error body has no detail', async () => {
    const file = new File(['fake-bytes'], 'bottle.jpg', { type: 'image/jpeg' });
    fetch.mockResolvedValueOnce({
      ok: false,
      status: 502,
      json: async () => { throw new Error('not json'); },
    });

    await expect(identifyBottle(file)).rejects.toThrow('HTTP 502');
  });
});
```

Add the import at the top of that test file (it currently imports `{ streamRecommend, getWine }` from `'../api.js'` — extend that same import line):

```js
import { streamRecommend, getWine, identifyBottle } from '../api.js';
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/__tests__/api.test.js`
Expected: FAIL — `identifyBottle is not a function` (or a named-export import error)

- [ ] **Step 3: Write the implementation**

In `frontend/src/lib/api.js`, add this function. Place it near the end of the file, after the existing `postFeedback`/`streamSomm` functions (exact position doesn't matter — it's a standalone export, not dependent on anything above it):

```js
export async function identifyBottle(photoFile) {
  const form = new FormData();
  form.append('photo', photoFile);
  const res = await fetch(`${BASE}/api/identify`, { method: 'POST', body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/__tests__/api.test.js`
Expected: PASS (3 new tests + existing tests in that file all green)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielguerrero/dev/wine_app
git add frontend/src/lib/api.js frontend/src/lib/__tests__/api.test.js
git commit -m "feat: identifyBottle API client for POST /api/identify"
```

---

## Task 2: The Identify screen component

**Files:**
- Create: `frontend/src/screens/Identify.jsx`
- Test: `frontend/src/screens/__tests__/Identify.test.jsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/screens/__tests__/Identify.test.jsx`:

```jsx
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import Identify from '../Identify.jsx';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../lib/api.js', () => ({ identifyBottle: vi.fn() }));
import { identifyBottle } from '../../lib/api.js';

beforeEach(() => {
  identifyBottle.mockReset();
  mockNavigate.mockClear();
});

function renderScreen() {
  return render(
    <MemoryRouter initialEntries={['/identify']}>
      <Routes>
        <Route path="/identify" element={<Identify />} />
      </Routes>
    </MemoryRouter>
  );
}

function selectPhoto(file = new File(['bytes'], 'bottle.jpg', { type: 'image/jpeg' })) {
  const input = screen.getByTestId('identify-file-input');
  fireEvent.change(input, { target: { files: [file] } });
  return file;
}

describe('Identify screen', () => {
  it('shows an idle upload prompt initially', () => {
    renderScreen();
    expect(screen.getByTestId('identify-file-input')).toBeInTheDocument();
  });

  it('shows the identifying state immediately after a photo is selected', async () => {
    identifyBottle.mockReturnValue(new Promise(() => {})); // never resolves — stay in-flight
    renderScreen();
    selectPhoto();
    expect(await screen.findByText(/Let me get a look at it/i)).toBeInTheDocument();
  });

  it('renders an exact match with a link to the dossier', async () => {
    identifyBottle.mockResolvedValue({
      status: 'exact',
      wine: { id: 'w1', name: 'Esprit de Tablas', brand: 'Tablas Creek', vintage_year: 2021, region: 'Paso Robles' },
    });
    renderScreen();
    selectPhoto();
    expect(await screen.findByText('Esprit de Tablas')).toBeInTheDocument();
    fireEvent.click(screen.getByText(/See where to buy/i));
    expect(mockNavigate).toHaveBeenCalledWith('/wine/w1');
  });

  it('renders a vintage mismatch with the soft-confirm line', async () => {
    identifyBottle.mockResolvedValue({
      status: 'vintage_mismatch',
      wine: { id: 'w1', name: 'Esprit de Tablas', brand: 'Tablas Creek', vintage_year: 2021, region: 'Paso Robles' },
      read_vintage: '2019',
    });
    renderScreen();
    selectPhoto();
    expect(await screen.findByText('Esprit de Tablas')).toBeInTheDocument();
    expect(screen.getByText(/2021/)).toBeInTheDocument();
    expect(screen.getByText(/2019/)).toBeInTheDocument();
  });

  it('renders a candidates list and navigates on tapping one', async () => {
    identifyBottle.mockResolvedValue({
      status: 'candidates',
      candidates: [
        { id: 'w1', name: 'Bramare Malbec', vintage_year: 2022, region: 'Uco Valley' },
        { id: 'w2', name: 'Bramare Malbec', vintage_year: 2023, region: 'Uco Valley' },
      ],
    });
    renderScreen();
    selectPhoto();
    await screen.findByText(/2022/);
    fireEvent.click(screen.getByText(/2023/));
    expect(mockNavigate).toHaveBeenCalledWith('/wine/w2');
  });

  it('renders the unstocked state with no card and no dead end', async () => {
    identifyBottle.mockResolvedValue({ status: 'unstocked', read: { producer: 'Cobos', wine_name: 'Volturno' } });
    renderScreen();
    selectPhoto();
    expect(await screen.findByText(/Volturno/i)).toBeInTheDocument();
    expect(screen.getByTestId('identify-retake')).toBeInTheDocument();
  });

  it('renders the unreadable state with a retake tip', async () => {
    identifyBottle.mockResolvedValue({ status: 'unreadable' });
    renderScreen();
    selectPhoto();
    expect(await screen.findByText(/whole front label/i)).toBeInTheDocument();
  });

  it('renders the not_wine state', async () => {
    identifyBottle.mockResolvedValue({ status: 'not_wine' });
    renderScreen();
    selectPhoto();
    expect(await screen.findByText(/not.*wine/i)).toBeInTheDocument();
  });

  it('renders an error state on a rejected call, with retry resetting to idle', async () => {
    identifyBottle.mockRejectedValue(new Error('Couldn’t reach the vision service — try again.'));
    renderScreen();
    selectPhoto();
    expect(await screen.findByText(/try again/i)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('identify-retake'));
    expect(screen.getByTestId('identify-file-input')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/screens/__tests__/Identify.test.jsx`
Expected: FAIL — `Failed to resolve import "../Identify.jsx"`

- [ ] **Step 3: Write the implementation**

Create `frontend/src/screens/Identify.jsx`:

```jsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { identifyBottle } from '../lib/api.js';

// v1 scope: no barcode tier, no save/cellar actions, no sign-in nudge, no
// camera-FAB visual treatment, no desktop modal — see the design doc
// (docs/superpowers/specs/2026-10-26-bottle-identify-frontend-v1-design.md)
// for what's deferred and why. A found wine hands off to the existing
// dossier screen for anything deeper (price, availability, save).

const WRAP = { padding: 24, maxWidth: 480, margin: '0 auto', fontFamily: 'var(--font-sans)' };
const PROMPT = { fontFamily: 'var(--font-serif)', fontSize: 23, color: 'var(--ink)', marginBottom: 16 };
const SOMM_LINE = { fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--ink-2)', marginBottom: 20, lineHeight: 1.5 };
const BTN = {
  cursor: 'pointer', background: 'var(--bordeaux)', color: 'var(--cream)',
  border: 'none', borderRadius: 0, padding: '12px 20px',
  fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 500,
};
const GHOST_BTN = {
  cursor: 'pointer', background: 'none', color: 'var(--bordeaux)',
  border: '1.5px inset var(--bordeaux)', borderRadius: 0, padding: '12px 20px',
  fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 500,
};
const CARD = {
  border: '1.5px solid var(--ink)', padding: 16, marginBottom: 12, cursor: 'pointer',
};
const WINE_NAME = { fontFamily: 'var(--font-serif)', fontSize: 23, color: 'var(--ink)', marginBottom: 4 };
const WINE_META = { fontFamily: 'var(--font-sans)', fontSize: 11.5, color: 'var(--faded)' };

function wineLine(w) {
  return [w.brand, w.vintage_year, w.region].filter(Boolean).join(' · ');
}

export default function Identify() {
  const navigate = useNavigate();
  const [state, setState] = useState('idle'); // idle | identifying | result | error
  const [result, setResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');

  async function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setState('identifying');
    try {
      const data = await identifyBottle(file);
      setResult(data);
      setState('result');
    } catch (err) {
      setErrorMessage(err.message || 'Something went wrong.');
      setState('error');
    } finally {
      e.target.value = '';
    }
  }

  function reset() {
    setState('idle');
    setResult(null);
    setErrorMessage('');
  }

  function goToWine(id) {
    navigate(`/wine/${id}`);
  }

  const fileInput = (testId) => (
    <label style={BTN}>
      Show me the bottle
      <input
        type="file"
        accept="image/*"
        capture="environment"
        data-testid={testId}
        onChange={handleFile}
        style={{ display: 'none' }}
      />
    </label>
  );

  if (state === 'idle') {
    return (
      <div style={WRAP}>
        <div style={PROMPT}>Show me the bottle</div>
        <div style={SOMM_LINE}>Snap the label and I'll tell you what it is.</div>
        {fileInput('identify-file-input')}
      </div>
    );
  }

  if (state === 'identifying') {
    return (
      <div style={WRAP}>
        <div style={SOMM_LINE}>Let me get a look at it…</div>
      </div>
    );
  }

  if (state === 'error') {
    return (
      <div style={WRAP}>
        <div style={SOMM_LINE}>{errorMessage}</div>
        <button style={GHOST_BTN} data-testid="identify-retake" onClick={reset}>Try again</button>
      </div>
    );
  }

  // state === 'result'
  const { status } = result;

  if (status === 'exact' || status === 'vintage_mismatch') {
    const w = result.wine;
    return (
      <div style={WRAP}>
        <div style={CARD} onClick={() => goToWine(w.id)}>
          <div style={WINE_NAME}>{w.name}</div>
          <div style={WINE_META}>{wineLine(w)}</div>
        </div>
        {status === 'vintage_mismatch' && (
          <div style={SOMM_LINE}>
            I see the {w.vintage_year} nearby — yours looks like the {result.read_vintage}.
          </div>
        )}
        <button style={BTN} onClick={() => goToWine(w.id)}>See where to buy</button>
        <div style={{ marginTop: 12 }}>
          <button style={GHOST_BTN} data-testid="identify-retake" onClick={reset}>Scan another</button>
        </div>
      </div>
    );
  }

  if (status === 'candidates') {
    return (
      <div style={WRAP}>
        <div style={SOMM_LINE}>A few bottles match — which one is it?</div>
        {(result.candidates || []).map(c => (
          <div key={c.id} style={CARD} onClick={() => goToWine(c.id)}>
            <div style={WINE_NAME}>{c.name}</div>
            <div style={WINE_META}>{wineLine(c)}</div>
          </div>
        ))}
        <button style={GHOST_BTN} data-testid="identify-retake" onClick={reset}>Scan another</button>
      </div>
    );
  }

  if (status === 'unstocked') {
    const read = result.read || {};
    const named = [read.producer, read.wine_name].filter(Boolean).join(' ');
    return (
      <div style={WRAP}>
        <div style={SOMM_LINE}>
          {named ? `Nobody near you stocks ${named} right now` : 'Nobody near you stocks that one right now'}
          — hang tight, this list grows every week.
        </div>
        <button style={GHOST_BTN} data-testid="identify-retake" onClick={reset}>Scan another</button>
      </div>
    );
  }

  if (status === 'unreadable') {
    return (
      <div style={WRAP}>
        <div style={SOMM_LINE}>I couldn't quite make that out. Try getting the whole front label in frame.</div>
        <button style={GHOST_BTN} data-testid="identify-retake" onClick={reset}>Scan another</button>
      </div>
    );
  }

  // status === 'not_wine'
  return (
    <div style={WRAP}>
      <div style={SOMM_LINE}>That doesn't look like a wine bottle to me.</div>
      <button style={GHOST_BTN} data-testid="identify-retake" onClick={reset}>Scan another</button>
    </div>
  );
}
```

Note: the `result`'s `_debug` field (present on every real backend response) is simply never read here — matches the design doc's explicit decision to ignore it, not strip it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/screens/__tests__/Identify.test.jsx`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielguerrero/dev/wine_app
git add frontend/src/screens/Identify.jsx frontend/src/screens/__tests__/Identify.test.jsx
git commit -m "feat: Identify screen — bottle photo upload and result rendering"
```

---

## Task 3: Route registration

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/App.test.jsx` (check first whether a `src/__tests__/` directory already exists at that level — if not, this creates it; if `App.jsx` already has tests elsewhere, add to that file instead and skip creating a new one):

```jsx
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '../App.jsx';

describe('App routing', () => {
  it('renders the Identify screen at /identify', () => {
    render(
      <MemoryRouter initialEntries={['/identify']}>
        <App />
      </MemoryRouter>
    );
    expect(screen.getByTestId('identify-file-input')).toBeInTheDocument();
  });
});
```

This pattern is already proven in this codebase: `frontend/src/__tests__/mobile.test.jsx` renders `<App />` wrapped in `<MemoryRouter>` successfully (App.jsx has no router of its own — `main.jsx` supplies `BrowserRouter` in production, so `MemoryRouter` in tests is a drop-in swap). No mocking of `lib/api.js` is needed for this specific test since it never triggers `identifyBottle` (it only asserts the idle state renders) — if a future edit to this test exercises the identifying/result states, mock `lib/api.js` the way `mobile.test.jsx` does.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/App.test.jsx`
Expected: FAIL — no route matches `/identify`, so `identify-file-input` is not found

- [ ] **Step 3: Write the implementation**

In `frontend/src/App.jsx`, add the import (alongside the other screen imports):

```js
import Identify from './screens/Identify.jsx';
```

Add the route inside `<Routes>` (position doesn't matter among siblings — add it near the end, e.g. after the `/taste` route):

```jsx
<Route path="/identify" element={<Identify />} />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/__tests__/App.test.jsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/danielguerrero/dev/wine_app
git add frontend/src/App.jsx frontend/src/__tests__/App.test.jsx
git commit -m "feat: register /identify route"
```

---

## Task 4: Mobile bottom-tab entry point

**Files:**
- Modify: `frontend/src/components/MobileChrome.jsx`
- Test: find/extend the existing test file covering `BottomTabs` (check `frontend/src/components/__tests__/` for a `MobileChrome.test.jsx`; if none exists, create one)

- [ ] **Step 1: Write the failing test**

First check: `ls frontend/src/components/__tests__/ | grep -i mobilechrome`. If a test file already exists for `MobileChrome.jsx`, add the test below into it instead of creating a new file; otherwise create `frontend/src/components/__tests__/MobileChrome.test.jsx`:

```jsx
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { BottomTabs } from '../MobileChrome.jsx';

describe('BottomTabs', () => {
  it('includes a Scan tab linking to /identify', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <BottomTabs />
      </MemoryRouter>
    );
    expect(screen.getByText('Scan')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/__tests__/MobileChrome.test.jsx`
Expected: FAIL — no element with text "Scan"

- [ ] **Step 3: Write the implementation**

In `frontend/src/components/MobileChrome.jsx`, add a new entry to the `TABS` array. Insert it between `'discover'` and `'search'` (so Scan sits roughly centered among the six, closest to where the full design's raised FAB would eventually go — this is a plain icon for v1, not the raised treatment):

```js
  {
    id: 'scan', label: 'Scan', to: '/identify',
    match: p => p === '/identify',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
        <circle cx="12" cy="13" r="4" />
      </svg>
    ),
  },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/__tests__/MobileChrome.test.jsx`
Expected: PASS

- [ ] **Step 5: Run the full frontend suite to confirm no regressions**

Run: `cd frontend && npx vitest run`
Expected: PASS, all tests (305 existing + new tests from Tasks 1-4)

- [ ] **Step 6: Commit**

```bash
cd /Users/danielguerrero/dev/wine_app
git add frontend/src/components/MobileChrome.jsx frontend/src/components/__tests__/MobileChrome.test.jsx
git commit -m "feat: add Scan tab to the mobile bottom tab bar"
```

---

## Task 5: Desktop nav entry point

**Files:**
- Modify: `frontend/src/components/NavBar.jsx`
- Test: `frontend/src/components/__tests__/NavBar.test.jsx` (already exists — add to it, following its existing pattern exactly: `render(<MemoryRouter><NavBar /></MemoryRouter>)` with no mocking of `AuthNav` or any provider, which the file's three existing tests already prove works standalone)

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/components/__tests__/NavBar.test.jsx` (matching its existing un-nested `it(...)` style, not a new `describe` block, to stay consistent with the file's current convention):

```jsx
it('renders a Scan nav link', () => {
  render(<MemoryRouter><NavBar /></MemoryRouter>);
  expect(screen.getByRole('link', { name: /scan/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/__tests__/NavBar.test.jsx`
Expected: FAIL — no link named "Scan"

- [ ] **Step 3: Write the implementation**

In `frontend/src/components/NavBar.jsx`, extend the existing mapped links array from:

```jsx
{[['Recommend', '/'], ['Discover', '/discover']].map(([label, to]) => (
```

to:

```jsx
{[['Recommend', '/'], ['Discover', '/discover'], ['Scan', '/identify']].map(([label, to]) => (
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/__tests__/NavBar.test.jsx`
Expected: PASS

- [ ] **Step 5: Run the full frontend suite one more time**

Run: `cd frontend && npx vitest run`
Expected: PASS, all tests, no regressions anywhere (this change touches a shared nav component every desktop screen renders)

- [ ] **Step 6: Commit**

```bash
cd /Users/danielguerrero/dev/wine_app
git add frontend/src/components/NavBar.jsx frontend/src/components/__tests__/NavBar.test.jsx
git commit -m "feat: add Scan link to the desktop nav bar"
```

---

## Task 6: Manual live validation (not automated — this is the owner's job)

This task has no code changes. It exists in the plan so the workflow is explicit:

- [ ] Start the backend locally (or confirm the Railway deploy has picked up `main`'s latest commit via `/health`'s reported commit SHA) and the frontend dev server: `cd frontend && npm run dev`
- [ ] Open the app, tap "Scan" in the bottom tab bar (mobile) or nav (desktop)
- [ ] Try a few real bottle photos — varying lighting/angle per `frontend/design-system/handoffs/bottle-scan/PHOTO-GUIDELINES.md`'s difficulty tiers if more than a couple are tried
- [ ] Confirm each of the six states renders sensibly with real backend responses, not just the mocked test fixtures
- [ ] Share with the small tester group once satisfied
- [ ] Report back in conversation with anything that needs iterating before considering this done
