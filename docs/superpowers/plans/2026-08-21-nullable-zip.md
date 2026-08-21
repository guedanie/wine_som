# Nullable Zip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "we don't know the user's location" an honest, representable state — fixing the reported bug where aisle mode asked for a zip that was already displayed and after a store was already selected.

**Architecture:** `loadZip()` stops fabricating `'78209'` and returns `null`. Screens that own a zip *input* coerce to `''` at the `useState` boundary (keeps inputs controlled, existing `.length === 5` validation already gates submission). Screens that *consume* a zip for API calls guard with `if (!zip) return;`. Display sites show a tappable "Set location" affordance. Aisle mode gates the store picker on a known zip, which eliminates the reported desync structurally.

**Tech Stack:** React 19 + Vite + Tailwind v3, vitest + @testing-library/react.

**Env:** ALL commands run from `/Users/danielguerrero/dev/wine_app/frontend` (running vitest from the repo root fails with "test is not defined" — a known cwd-drift trap in this repo). Run tests with `npx vitest run`.

**Reference:** design spec `docs/superpowers/specs/2026-08-20-nullable-zip-design.md`.

**Ordering rationale:** Task 1 changes the shared helper and WILL break things until Tasks 2-4 land. Do not stop midway — the suite is expected to be red between Task 1 and Task 4. Task 1's own tests pass; other suites go red and are repaired in order.

**CORRECTION (2026-08-21, from Task 1 code review):** Task 1 as originally written left the frontend
**unbuildable** (`npm run build` → `[MISSING_EXPORT] "hasStoredZip"`), because `ChatRecommend.jsx`
still imported the deleted symbol. A dead build is a different animal from a red suite: it masks
real breakage behind an "expected red" instruction. The two-line import swap (originally Task 5
Step 3) is therefore **pulled forward into Task 1** — it is a pure refactor
(`hasStoredZip() ≡ loadZip() != null`) and belongs in the commit that deletes the symbol it
consumes. Consequences:
- `npm run build` is now a **required gate on every task**, not just the test suite.
- The expected-red set after Task 1 is **4 suites** — `PreferenceCapture`, `SearchScreen`,
  `RegionBrowse`, `mobile` (all `.length`-on-null crashes) — not the 6 originally predicted, and
  `ModeTabs` does NOT fail (it passes its zip via router state).
- Task 4's "full suite green" gate is now actually satisfiable; before this correction it was not,
  since `ChatRecommend*` could not go green until Task 5.

**Deploy-safety note:** this repo has **no frontend CI** (`.github/workflows/` holds only the
scrape/enrich jobs) and no pre-commit hook, so nothing but Vercel's build step stands between a
push and production. The intermediate state failing at *build* time rather than runtime is what
keeps a mid-plan deploy from white-screening live beta testers — Vercel rejects the build and
keeps serving the last good bundle. Worth a follow-up roadmap item independent of this branch.

**File map:**
| File | Responsibility | Task |
|---|---|---|
| `src/lib/useIsMobile.js` | zip persistence helpers (`loadZip`/`saveZip`, `hasStoredZip` removed) | 1 |
| `src/lib/__tests__/useUserZip.test.jsx` | invert the "never null" invariant test | 1 |
| `src/screens/PreferenceCapture.jsx`, `SearchScreen.jsx`, `RegionBrowse.jsx` | zip-INPUT owners — coerce null→`''` | 2 |
| `src/screens/Deals.jsx`, `Discovery.jsx` | zip CONSUMERS — guard the fetch | 3 |
| `src/components/MobileChrome.jsx`, `src/screens/Account.jsx` | DISPLAY — "Set location" affordance | 4 |
| `src/screens/ChatRecommend.jsx` | aisle mode — gate picker on known zip | 5 |

---

### Task 1: Helper returns null; invert the invariant test

**Files:**
- Modify: `frontend/src/lib/useIsMobile.js:27-37`
- Modify: `frontend/src/lib/__tests__/useUserZip.test.jsx:46-50`
- Modify: `frontend/src/lib/__tests__/askMode.test.js:44-50`

- [ ] **Step 1: Invert the "never null" test**

In `frontend/src/lib/__tests__/useUserZip.test.jsx`, replace this test:

```js
  it('never returns null/undefined — inventory filters depend on it', () => {
    const v = renderWith(undefined);
    expect(v).toBeTruthy();
    expect(v).toMatch(/^\d{5}$/);
  });
```

with:

```js
  it('returns null when nothing is stored — "no location" must be representable', () => {
    // Previously this asserted a fabricated '78209' default. That default was
    // rendered to users as though confirmed (top bar, aisle context pill) while
    // a separate flag still said the zip was unknown — the root cause of the
    // aisle-mode "asked for a zip I already gave you" bug. The invariant that
    // actually mattered (never send a null zip to a required-zip endpoint) is
    // enforced at the call sites instead — see Deals/Discovery guards.
    expect(renderWith(undefined)).toBe(null);
  });
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/lib/__tests__/useUserZip.test.jsx`
Expected: FAIL — the new test gets `'78209'`, not `null`.

- [ ] **Step 3: Make `loadZip` null-honest and delete `hasStoredZip`**

In `frontend/src/lib/useIsMobile.js`, replace lines 27-37:

```js
// Shared zip persistence — TopBar pill + screens read the last-used zip.
export function loadZip() {
  try { return localStorage.getItem('somm_zip') || '78209'; } catch { return '78209'; }
}
export function hasStoredZip() {
  try { return localStorage.getItem('somm_zip') != null; } catch { return false; }
}

export function saveZip(zip) {
  try { localStorage.setItem('somm_zip', zip); } catch { /* private mode */ }
}
```

with:

```js
// Shared zip persistence — TopBar pill + screens read the last-used zip.
// Returns null when we genuinely don't know where the user is. Callers must
// handle that: screens owning a zip INPUT coerce to '' at the useState
// boundary; screens CONSUMING a zip for a required-zip endpoint guard the
// fetch. Never fabricate a default — the UI showing a zip the app hasn't
// actually been given is what produced the aisle-mode re-ask bug.
export function loadZip() {
  try { return localStorage.getItem('somm_zip') || null; } catch { return null; }
}

export function saveZip(zip) {
  try { localStorage.setItem('somm_zip', zip); } catch { /* private mode */ }
}
```

(`hasStoredZip` is deleted — it was only ever a workaround for the default, and
`loadZip() != null` is now exactly equivalent. Its one consumer is fixed in Task 5.)

- [ ] **Step 4: Fix the `hasStoredZip` unit test**

`frontend/src/lib/__tests__/askMode.test.js` tests the deleted helper directly. Two edits:

Delete this entire block (lines 44-52):
```js
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

And delete its now-unused import on line 3:
```js
import { hasStoredZip } from '../useIsMobile.js';
```

Leave every other test in that file untouched.

- [ ] **Step 5: Run to verify Task 1's own tests pass**

Run: `cd frontend && npx vitest run src/lib/__tests__/useUserZip.test.jsx src/lib/__tests__/askMode.test.js`
Expected: PASS.

Then run the full suite to see the expected damage:
Run: `cd frontend && npx vitest run`
Expected: **RED** — `PreferenceCapture`, `SearchScreen`, `RegionBrowse`, `ModeTabs` suites fail.
This is expected and is repaired in Tasks 2-4. Record the failing suite names in your report.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/useIsMobile.js frontend/src/lib/__tests__/useUserZip.test.jsx frontend/src/lib/__tests__/askMode.test.js
git commit -m "refactor(zip): loadZip returns null instead of a fabricated 78209"
```

---

### Task 2: Zip-INPUT owners coerce null to empty string

**Files:**
- Modify: `frontend/src/screens/PreferenceCapture.jsx:22`
- Modify: `frontend/src/screens/SearchScreen.jsx:77`
- Modify: `frontend/src/screens/RegionBrowse.jsx:48-49`
- Modify: `frontend/src/screens/__tests__/PreferenceCapture.test.jsx`
- Modify: `frontend/src/screens/__tests__/SearchScreen.test.jsx:98`
- Modify: `frontend/src/screens/__tests__/RegionBrowse.test.jsx:69,116`

These three screens call `.length` on the zip during render or on mount. A null is a hard crash,
and `PreferenceCapture` is the app's front door.

- [ ] **Step 1: Write the failing regression tests**

Append to `frontend/src/screens/__tests__/PreferenceCapture.test.jsx` (inside its top-level
`describe`):

```js
  it('renders with an empty zip field when no zip is stored', () => {
    localStorage.clear();
    render(<MemoryRouter><PreferenceCapture /></MemoryRouter>);
    // The input has placeholder="ZIP code" and no aria-label — match on placeholder.
    expect(screen.getByPlaceholderText(/zip code/i)).toHaveValue('');
  });
```

Append to `frontend/src/screens/__tests__/SearchScreen.test.jsx` (inside its top-level
`describe`):

```js
  it('does not search when no zip is stored', async () => {
    localStorage.clear();
    render(<MemoryRouter initialEntries={['/search?q=malbec']}><SearchScreen /></MemoryRouter>);
    await new Promise(r => setTimeout(r, 0));
    expect(searchWines).not.toHaveBeenCalled();
  });
```

Append to `frontend/src/screens/__tests__/RegionBrowse.test.jsx` (inside its top-level
`describe`):

```js
  it('renders without crashing when no zip is stored', () => {
    localStorage.clear();
    render(
      <MemoryRouter initialEntries={['/region/Bordeaux']}>
        <Routes><Route path="/region/:slug" element={<RegionBrowse />} /></Routes>
      </MemoryRouter>
    );
    expect(screen.getByDisplayValue('')).toBeInTheDocument();
  });
```

Before writing each, READ the target test file's existing imports and render helpers — reuse the
file's established pattern for rendering that screen (router wrapper, mocks, `beforeEach`) rather
than the sketch above if it differs. The assertions are what matter, not the scaffolding.

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx vitest run src/screens/__tests__/PreferenceCapture.test.jsx src/screens/__tests__/SearchScreen.test.jsx src/screens/__tests__/RegionBrowse.test.jsx`
Expected: FAIL with `TypeError: Cannot read properties of null (reading 'length')`.

- [ ] **Step 3: Coerce in `PreferenceCapture.jsx`**

Line 22, replace:
```js
  const [zip,      setZip]      = useState(loadZip);
```
with:
```js
  // '' (not null) so the input stays controlled; `valid` already requires 5 digits.
  const [zip,      setZip]      = useState(() => loadZip() ?? '');
```

- [ ] **Step 4: Coerce in `SearchScreen.jsx`**

Line 77, replace:
```js
  const [zip, setZip] = useState(initialZip);
```
with:
```js
  const [zip, setZip] = useState(initialZip ?? '');
```

The existing effect at line 117 (`if (query && zip.length === 5) runSearch(query);`) already
prevents a search without a full zip — no change needed there.

- [ ] **Step 5: Coerce in `RegionBrowse.jsx`**

Lines 48-49, replace:
```js
  const [zip,       setZip]       = useState(initialZip);
  const [zipInput,  setZipInput]  = useState(initialZip);
```
with:
```js
  const [zip,       setZip]       = useState(initialZip ?? '');
  const [zipInput,  setZipInput]  = useState(initialZip ?? '');
```

Then guard the fetch effect — `getRegionWines` requires a zip (`region.py:108`). Replace line 72:
```js
  useEffect(() => { fetchWines(zip); }, [zip]);
```
with:
```js
  useEffect(() => {
    if (!zip) { setLoading(false); return; }   // no location yet — the zip form is shown
    fetchWines(zip);
  }, [zip]);
```

- [ ] **Step 6: Update the tests that used '78209' as an input handle**

`SearchScreen.test.jsx:98` asserts `searchWines` was called with `zip: '78209'` on empty
localStorage. `RegionBrowse.test.jsx:69` asserts `getRegionWines` is called with a default zip;
`:116` uses `getByDisplayValue('78209')` as a handle. `PreferenceCapture.test.jsx:17,24,35,44-45`
likewise rely on the pre-filled default.

For each: add `saveZip('78209')` (import it from `../../lib/useIsMobile.js`) in that suite's
`beforeEach`, so those tests keep testing what they were written to test — the behavior with a
known zip — rather than accidentally testing the default. Do NOT weaken the assertions.

- [ ] **Step 7: Run to verify pass**

Run: `cd frontend && npx vitest run src/screens/__tests__/PreferenceCapture.test.jsx src/screens/__tests__/SearchScreen.test.jsx src/screens/__tests__/RegionBrowse.test.jsx`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/screens/PreferenceCapture.jsx frontend/src/screens/SearchScreen.jsx frontend/src/screens/RegionBrowse.jsx frontend/src/screens/__tests__/PreferenceCapture.test.jsx frontend/src/screens/__tests__/SearchScreen.test.jsx frontend/src/screens/__tests__/RegionBrowse.test.jsx
git commit -m "fix(zip): keep zip inputs controlled when no location is known"
```

---

### Task 3: Zip CONSUMERS guard the fetch

**Files:**
- Modify: `frontend/src/screens/Deals.jsx:29-31`
- Modify: `frontend/src/screens/Discovery.jsx:17-19`
- Modify: `frontend/src/screens/RegionDossier.jsx:305,459` (added by review — see Step 4b)
- Modify: `frontend/src/screens/RegionDetail.jsx:65-68` (added by review — see Step 4b)
- Modify: `frontend/src/screens/__tests__/Deals.test.jsx` (exists)
- Modify: `frontend/src/screens/__tests__/Discovery.test.jsx` (exists)

`GET /api/deals` has a required `zip` param (`deals.py:25`), so a null becomes the literal string
`"null"` in the query.

- [ ] **Step 1: Write the failing test**

`Deals.test.jsx` already exists — read it first and follow its established mock pattern for
`../../lib/api.js` and its render helper. Append:

```js
  it('does not call getDeals when no zip is known', async () => {
    localStorage.clear();
    render(<MemoryRouter><Deals /></MemoryRouter>);
    await new Promise(r => setTimeout(r, 0));
    expect(getDeals).not.toHaveBeenCalled();
    expect(screen.getByText(/set your location/i)).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/screens/__tests__/Deals.test.jsx`
Expected: FAIL — `getDeals` is called with null.

- [ ] **Step 3: Guard `Deals.jsx`**

Replace lines 29-31:
```js
  useEffect(() => {
    getDeals(zip, 40).then(setData).catch(() => setError(true));
  }, [zip]);
```
with:
```js
  useEffect(() => {
    if (!zip) return;                 // required-zip endpoint; ask first, don't send "null"
    getDeals(zip, 40).then(setData).catch(() => setError(true));
  }, [zip]);
```

Then, in the render, show a location prompt instead of an endless loading state. Immediately
after the `const open = deal => {...}` block, add:

```js
  if (!zip) return (
    <div style={{ maxWidth: 640, margin: '0 auto', padding: '48px 24px', textAlign: 'center' }}>
      <div style={{ fontFamily: 'var(--font-serif)', fontSize: 22, color: 'var(--ink)' }}>
        Deals are local by nature.
      </div>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, lineHeight: 1.6, color: 'var(--faded)', marginTop: 8 }}>
        Tell me where you are and I'll show you what dropped near you this week.
      </div>
      <button onClick={() => navigate('/')} style={{ marginTop: 16, cursor: 'pointer', background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 13, padding: '10px 18px' }}>
        Set your location
      </button>
    </div>
  );
```

- [ ] **Step 4: Guard `Discovery.jsx` and fix its dependency array**

Replace lines 17-19:
```js
  useEffect(() => {
    getDeals(zip, 10).then(setData).catch(() => {});
  }, []);
```
with:
```js
  useEffect(() => {
    if (!zip) return;
    getDeals(zip, 10).then(setData).catch(() => {});
  }, [zip]);      // was [] — the rail never refetched after the user set a location
```

The existing `if (!data || data.deals.length === 0) return null;` on the next line already handles
the no-data case, so the rail correctly renders nothing without a zip.

- [ ] **Step 4a: `RegionBrowse`'s no-zip empty state** (added by Task 2 implementer's concern)

Task 2 guarded `RegionBrowse`'s fetch, so with no zip it now renders the header and the zip form
and then nothing — its "No matches" state is gated on `allWines.length > 0` and never fires. Not
misleading (it no longer claims results near a fabricated zip), but it's a dead-end.

In `frontend/src/screens/RegionBrowse.jsx`, find the render branch that handles the empty/loading
states (read the file — it has `loading`, `error`, and a "No wines in {regionName} match your
current filters near {zip}" message around line 221). Add a no-zip branch BEFORE the existing
empty-state check, mirroring the copy voice of the Deals prompt in Step 3:

```jsx
  if (!zip) return (
    <div style={{ padding: '32px 20px', textAlign: 'center', fontFamily: 'var(--font-sans)', fontSize: 13, lineHeight: 1.6, color: 'var(--faded)' }}>
      Tell me where you are — the zip box above — and I'll show you what's on shelves near you.
    </div>
  );
```

Place it so the zip form above it still renders (the user needs the input to recover). If the
file's structure makes that awkward, put the message inside the existing results container rather
than early-returning from the component.

- [ ] **Step 4b: Stop claiming "near you" when we don't know where you are** (added by Task 1 review)

`getWine` and `getSubregionCounts` are Optional-zip endpoints, so these two screens don't crash or
send `"null"` — `api.js:50` and `:68` already guard `zip ? ... : ''`. But omitting the param makes
the API **skip proximity filtering entirely and return nationwide results**, which the dossier
still renders under an "Available near you" heading. That is precisely the prior bug
`useUserZip.js`'s own docstring memorializes ("17 stores nationwide, including a Spec's 252 mi
away") — unreachable while `loadZip` fabricated a default, reachable now. Fixing it is the whole
point of this branch: never assert something we haven't been told.

In `frontend/src/screens/RegionDossier.jsx`, the string `Available near you` appears at **line 305
(desktop layout) and line 459 (mobile layout)** — both must change. In each, replace:
```jsx
<Eyebrow style={{ display: 'block', marginBottom: 10 }}>Available near you</Eyebrow>
```
with:
```jsx
<Eyebrow style={{ display: 'block', marginBottom: 10 }}>{zip ? 'Available near you' : 'Where to find it'}</Eyebrow>
```
(`zip` is already in scope from `useUserZip()` at line 155.)

In `frontend/src/screens/RegionDetail.jsx`, fix the stale-zip dependency — the effect at lines
65-68 lists only `[region]`, so like Discovery it never refetches after the user sets a location.
Replace `}, [region]);` with `}, [region, zip]);`. No label change is needed here (it renders
subregion counts, not a proximity claim).

- [ ] **Step 4c: Test the dossier label**

Append to `frontend/src/screens/__tests__/RegionDossier.test.jsx` (read the file first and reuse
its existing render helper and api mocks):

```js
  it('does not claim "near you" when no zip is known', async () => {
    localStorage.clear();
    renderDossier();                   // reuse this suite's existing helper
    expect(await screen.findByText(/where to find it/i)).toBeInTheDocument();
    expect(screen.queryByText(/available near you/i)).not.toBeInTheDocument();
  });
```

- [ ] **Step 5: Run to verify pass**

Run: `cd frontend && npx vitest run src/screens/__tests__/Deals.test.jsx src/screens/__tests__/Discovery.test.jsx`
Expected: PASS. If `Discovery.test.jsx` relied on the rail fetching with a default zip, seed it
with `saveZip('78209')` in that suite's `beforeEach` rather than weakening its assertions.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/screens/Deals.jsx frontend/src/screens/Discovery.jsx frontend/src/screens/RegionDossier.jsx frontend/src/screens/RegionDetail.jsx frontend/src/screens/__tests__/Deals.test.jsx frontend/src/screens/__tests__/RegionDossier.test.jsx
git commit -m "fix(zip): guard required-zip endpoints and stop claiming 'near you' without a zip"
```

---

### Task 4: Display sites — "Set location" instead of a fabrication

**Files:**
- Modify: `frontend/src/components/MobileChrome.jsx:43,107-109`
- Modify: `frontend/src/screens/Account.jsx:43,84-86`
- Modify: `frontend/src/components/__tests__/ModeTabs.test.jsx:38`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/components/__tests__/ModeTabs.test.jsx`, which renders `TopBar` via its
existing `renderAt(entry)` helper (defined at line 15):

```js
  it('offers to set a location instead of showing a fabricated zip', () => {
    localStorage.clear();
    renderAt('/recommend');
    expect(screen.queryByText(/near null/i)).not.toBeInTheDocument();
    expect(screen.getByText(/set location/i)).toBeInTheDocument();
  });
```

NOTE: `ModeTabs.test.jsx:38` asserts `getByText(/Tonight, near 78209/)` by passing the zip
through router state, so it survives unchanged — do not weaken it.

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/__tests__/ModeTabs.test.jsx`
Expected: FAIL — the bar renders "Tonight, near null".

- [ ] **Step 3: Fix the title in `MobileChrome.jsx`**

Line 43, replace:
```js
    title = `Tonight, near ${zip}`;
```
with:
```js
    title = zip ? `Tonight, near ${zip}` : 'Tonight';
```

- [ ] **Step 4: Make the pill a "Set location" affordance**

Replace lines 107-109:
```js
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10.5, letterSpacing: '0.06em', color: 'var(--faded)', border: '1px solid var(--border)', padding: '5px 10px', flexShrink: 0 }}>
        ◎ {zip}
      </div>
```
with:
```js
      {zip ? (
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10.5, letterSpacing: '0.06em', color: 'var(--faded)', border: '1px solid var(--border)', padding: '5px 10px', flexShrink: 0 }}>
          ◎ {zip}
        </div>
      ) : (
        <button onClick={() => navigate('/')}
          style={{ fontFamily: 'var(--font-sans)', fontSize: 10.5, letterSpacing: '0.06em', color: 'var(--bordeaux)', background: 'none', border: '1px solid var(--bordeaux)', padding: '5px 10px', flexShrink: 0, cursor: 'pointer' }}>
          ◎ Set location
        </button>
      )}
```

(`navigate` is already in scope at `MobileChrome.jsx:32`.)

- [ ] **Step 5: Fix the `Account.jsx` chip**

Line 43 is `const zip = loadZip();`. The chip row at 84-86 renders `{[zip, 'Recent picks'].map(...)}`,
which with a null zip gives `key={null}` and an empty pill.

Replace the array literal `[zip, 'Recent picks']` with:
```js
          {[zip ?? 'Set your location', 'Recent picks'].map(chip => (
```
The existing "edit preferences" button directly below already navigates to `/`, so the chip text
is honest and the fix is available immediately beneath it.

- [ ] **Step 6: Run to verify pass**

Run: `cd frontend && npx vitest run`
Expected: **FULL SUITE GREEN.** Every suite broken by Task 1 is now repaired. If anything is
still red, fix it before committing — do not proceed to Task 5 with a red suite.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/MobileChrome.jsx frontend/src/screens/Account.jsx frontend/src/components/__tests__/ModeTabs.test.jsx
git commit -m "fix(zip): show a Set location affordance instead of a fabricated zip"
```

---

### Task 5: Aisle mode — gate the store picker on a known zip (the reported bug)

**Files:**
- Modify: `frontend/src/screens/ChatRecommend.jsx:183,186,398-403,414-426`
- Modify: `frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx`

This is the reported bug. The fix is structural: the picker becomes unreachable without a zip, so
"store selected but still asked for zip" cannot occur — and the picker can no longer query
`getNearbyStores` against a fabricated location.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx`. NOTE: this suite's
`beforeEach` (line ~41) sets `localStorage.setItem('somm_zip', '78209')` — that seeding is
exactly why this bug shipped. These tests must clear it explicitly.

Read the file's existing render helper and store-picker test (lines ~112-144) and follow its
pattern. The assertions:

```js
  it('asks for a zip BEFORE opening the store picker when none is stored', async () => {
    localStorage.clear();
    renderAsk({ mode: 'ask', openStorePicker: true });   // reuse this file's helper
    expect(await screen.findByText(/roughly where you are/i)).toBeInTheDocument();
    expect(screen.queryByText(/which one are you standing in/i)).not.toBeInTheDocument();
  });

  it('does not re-ask for a zip after a store has been picked', async () => {
    localStorage.clear();
    renderAsk({ mode: 'ask', openStorePicker: true });
    // Answer the zip prompt.
    fireEvent.change(await screen.findByLabelText(/your zip/i), { target: { value: '37210' } });
    fireEvent.click(screen.getByText('Set'));
    // The picker opens next; pick the first store.
    fireEvent.click(await screen.findByText(/Kroger/i));
    // Now ask a question — the zip prompt must NOT come back.
    fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: 'something bold' } });
    fireEvent.click(screen.getByLabelText(/send/i));
    await new Promise(r => setTimeout(r, 0));
    expect(screen.queryByText(/roughly where you are/i)).not.toBeInTheDocument();
  });
```

Adapt selectors to the suite's actual helpers/mocks (`getNearbyStores` must be mocked to return
at least one store named so the `findByText(/Kroger/i)` resolves).

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx vitest run src/screens/__tests__/ChatRecommendAsk.test.jsx`
Expected: FAIL — test 1 finds the picker open with no zip prompt; test 2 sees the zip prompt
return after a store pick.

- [ ] **Step 3: Replace `hasStoredZip` with the null-honest check**

Line 183, replace:
```js
  const [zipConfirmed, setZipConfirmed] = useState(() => Boolean(_restored) || hasStoredZip());
```
with:
```js
  const [zipConfirmed, setZipConfirmed] = useState(() => Boolean(_restored) || loadZip() != null);
```

Then fix the import on line 14, replacing:
```js
import { loadZip, saveZip, hasStoredZip } from '../lib/useIsMobile.js';
```
with:
```js
import { loadZip, saveZip } from '../lib/useIsMobile.js';
```

- [ ] **Step 4: Gate the picker's initial open on a known zip**

Line 186, replace:
```js
  const [pickerOpen, setPickerOpen] = useState(() => Boolean(state?.openStorePicker));
```
with:
```js
  // A store picker without a zip would list stores near a location we don't
  // have. Defer the requested open until a zip exists (see the effect below).
  const [pickerOpen, setPickerOpen] = useState(() =>
    Boolean(state?.openStorePicker) && (Boolean(_restored) || loadZip() != null));
  const [pickerDeferred, setPickerDeferred] = useState(() =>
    Boolean(state?.openStorePicker) && !(Boolean(_restored) || loadZip() != null));
```

- [ ] **Step 5: Prompt for the zip immediately when the picker was deferred**

`handleAskSend`'s zip gate only fires when the user sends a message, but a deferred picker means
we need the zip *now*. `pendingAskText` is what renders `zipRequestBubble` (line 428), so set it
to an empty string to show the prompt without a queued message.

Immediately after the store-picker-data effect (the one ending `}, [pickerOpen]);` around line
229), add:

```js
  // Strip entry ("I'm here, now") with no known zip: ask for it first, then
  // open the picker. Prevents both the wrong-city store list and the re-ask bug.
  useEffect(() => {
    if (pickerDeferred && pendingAskText == null) setPendingAskText('');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickerDeferred]);
```

- [ ] **Step 6: Open the deferred picker once the zip is confirmed**

In `confirmZip` (lines 414-426), replace the whole function:

```js
  const confirmZip = () => {
    if (zipDraft.length !== 5) return;
    saveZip(zipDraft);
    setAskZip(zipDraft);
    setZipConfirmed(true);
    const text = pendingAskText;
    setPendingAskText(null);
    const history = historyFrom(messages.slice(0, -1));
    tasteFor().then(taste => callRecommend(buildAskReq({
      zip: zipDraft, message: text, history: history.length ? history : undefined,
      storeRef, conversational: false, taste,
    })));
  };
```

with:

```js
  const confirmZip = () => {
    if (zipDraft.length !== 5) return;
    saveZip(zipDraft);
    setAskZip(zipDraft);
    setZipConfirmed(true);
    const text = pendingAskText;
    setPendingAskText(null);
    // Deferred strip entry: the zip was asked FOR the picker, not for a
    // question. Open the picker now; there's nothing to send.
    if (pickerDeferred) {
      setPickerDeferred(false);
      setPickerOpen(true);
      return;
    }
    const history = historyFrom(messages.slice(0, -1));
    tasteFor().then(taste => callRecommend(buildAskReq({
      zip: zipDraft, message: text, history: history.length ? history : undefined,
      storeRef, conversational: false, taste,
    })));
  };
```

- [ ] **Step 7: Update the stale comment on the send gate**

Lines 397-398 say the loadZip default doesn't count — that default no longer exists. Replace:
```js
    // Lazy location: the zip request arrives INSIDE the conversation, once,
    // only when no zip is actually stored (the loadZip default doesn't count).
```
with:
```js
    // Lazy location: the zip request arrives INSIDE the conversation, once,
    // only when no zip is stored. loadZip() returns null rather than a default,
    // so "unknown" is a real state and this can't contradict what the UI shows.
```

- [ ] **Step 8: Run to verify pass**

Run: `cd frontend && npx vitest run src/screens/__tests__/ChatRecommendAsk.test.jsx`
Expected: PASS.

Then the full suite:
Run: `cd frontend && npx vitest run`
Expected: FULL SUITE GREEN.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/screens/ChatRecommend.jsx frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx
git commit -m "fix(aisle): ask for a zip before the store picker, never after"
```

---

### Task 6: Manual verification + docs

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Drive the actual bug in a browser**

Run `cd frontend && npm run dev`. In a fresh private window at `localhost:5173`:
1. Open devtools → Application → clear `localStorage` (no `somm_zip`).
2. Confirm the top bar reads **"Tonight"** with a **◎ Set location** button — NOT "near 78209".
3. Tap the aisle strip on `/`.
4. Confirm the **zip prompt appears first**, not the store picker.
5. Enter a zip from a non-San-Antonio market (e.g. `37210` Nashville).
6. Confirm the store picker opens next, listing **Nashville** stores (not San Antonio).
7. Pick a store, then ask a question.
8. **Confirm the zip prompt does NOT reappear** — this is the reported bug.

Report exactly what you observed at each step. If any step misbehaves, STOP and report rather
than patching around it.

- [ ] **Step 2: Update the roadmap**

`CLAUDE.md`'s "What's Next" list currently ends at item 42 (item 34 is `⚙️`). **Pull first**
(`git fetch origin && git status`) — this file is edited from more than one machine and has
caused conflicts before; if the branch is behind, STOP and report.

Append a new item 43 in the style of items 39-42 (dense, concrete, names the root cause and the
fix), covering: the reported symptom (aisle mode re-asked for a zip that was already displayed
with a store already selected); the root cause (`loadZip()` fabricated `'78209'`, which the top
bar and aisle context pill rendered as though confirmed while `zipConfirmed` separately said
unknown); the three linked defects (desync, fabricated display, store picker querying the fake
zip → wrong-city store lists); and the fix (null-honest `loadZip`, `hasStoredZip` deleted, input
owners coerce to `''`, consumers guard required-zip endpoints, "Set location" affordance, picker
gated behind a known zip). Note that the pre-existing `useUserZip` "never returns null" test was
**inverted, not deleted** — the API-safety invariant it protected now lives at the call sites.
Cite `docs/superpowers/specs/2026-08-20-nullable-zip-design.md`.

- [ ] **Step 3: Full suites + commit**

```bash
cd frontend && npx vitest run
cd ../backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q
git add CLAUDE.md
git commit -m "docs: item 43 nullable zip landed"
```

Expected: frontend green, backend green (backend is untouched by this work — it's a regression
check only).

---

## Self-Review Notes

- **Spec coverage:** §1 helper → Task 1; §2 input owners → Task 2; §3 API consumers → Task 3;
  §4 display → Task 4; §5 aisle ordering → Task 5; §6 testing → tests in each task, with the
  inverted invariant test in Task 1 Step 1 and the bug-specific coverage in Task 5 Step 1. Docs
  → Task 6. All covered.
- **Type consistency:** `loadZip()` returns `string | null` everywhere after Task 1;
  `hasStoredZip` is removed in Task 1 and its sole consumer fixed in Task 5 Step 3 (the import
  fix is in the same step, so no task leaves a broken import). `pickerDeferred` is introduced in
  Task 5 Step 4 and consumed in Steps 5-6 of the same task.
- **Known-red window:** Task 1 intentionally leaves the suite red; Tasks 2-4 repair it, and Task
  4 Step 6 is the gate that requires full green before the bug fix lands. This is called out in
  the header so an executor doesn't mistake it for breakage.
- **The riskiest edits are the three `.length` crash sites** (Task 2) — each is a one-line
  `?? ''` coercion with a regression test written first.
