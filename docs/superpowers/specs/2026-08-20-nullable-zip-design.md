# Nullable Zip — "We Don't Know Where You Are" as an Honest State (Design)

**Date:** 2026-08-20
**Source:** Bug report — in aisle/ask mode, a user with a zip already showing and a store already
selected was still asked for their zip.

## Problem

The reported symptom is one visible face of a deeper defect: **the app cannot represent "no
location known," so it invents one.**

`loadZip()` (`frontend/src/lib/useIsMobile.js:28-30`) returns a hardcoded `'78209'` when
`localStorage['somm_zip']` is unset. That fabricated value then propagates into:

- the persistent mobile top bar — `` `Tonight, near ${zip}` `` (`MobileChrome.jsx:43`) and the
  `◎ {zip}` pill (`:108`),
- the aisle-mode context pill — `◎ {askZip}` (`ChatRecommend.jsx:483`),
- the store-picker query — `getNearbyStores(askZip)` (`ChatRecommend.jsx:225`).

So the UI tells the user it knows their zip, and simultaneously a separate flag says it doesn't.

### The three linked defects

1. **State desync (the reported bug).** `zipConfirmed` (`ChatRecommend.jsx:183`) is the sole gate
   for the zip prompt (`:399`) and is set in exactly one place — `confirmZip()` (`:414-426`).
   The store-picker handlers (`:453`, `:470`) set `storeRef`/`storeLabel` and never touch it. A
   user entering via `AisleStrip` (`AisleStrip.jsx:11` passes `openStorePicker: true`) lands
   straight in the picker before any zip was asked, picks a store, and their first message still
   trips the zip gate.
2. **The UI displays a zip it does not have.** The `'78209'` default renders as though confirmed
   in the top bar and context pill — the likely reason the reporter believed they had already
   specified it.
3. **The store picker queries against the fabricated zip.** With no stored zip,
   `getNearbyStores('78209')` returns *San Antonio* stores to a user who may be anywhere. Any
   store they pick is wrong.

Defect 3 is why the obvious fix is wrong in isolation: making a store pick simply set
`zipConfirmed = true` would lock a non-San-Antonio user into a wrong-city store list and stop
asking — strictly worse than today's annoying re-ask.

## Prior art in this codebase (why null-honest is the intended direction)

- The dossier path already treats zip as nullable and degrades cleanly: `api.js:50` and `:68`
  guard `zip ? ... : ''`; backends `wines.py:30` and `region.py:57` take `Optional[str]`;
  `DossierRateButton:30` does `zip: zip ?? null`.
- `hasStoredZip()` (`useIsMobile.js:31-33`) exists *only* to work around `loadZip()`'s default —
  its call site is commented *"only when no zip is actually stored (the loadZip default doesn't
  count)"* (`ChatRecommend.jsx:398`). The helper is an apology for the lie.

### The one piece of contrary evidence, and how this design honors it

`src/lib/__tests__/useUserZip.test.jsx:47-49` asserts the hook **"never returns null/undefined —
inventory filters depend on it."** That test is a deliberate decision, not an oversight, and it
is not simply deleted here.

It conflates two invariants:

- *"never send a null zip to a required-zip endpoint"* — **real, and preserved** (see §3 below),
- *"always show the user a zip, even a fabricated one"* — **the bug itself.**

The test is therefore **inverted rather than removed**: it keeps guarding API safety and stops
guarding the display lie.

## Design

### 1. Helper — make null representable

`loadZip()` returns `localStorage['somm_zip'] || null`. `hasStoredZip()` is **removed**; it
becomes exactly `loadZip() != null`. `useUserZip()` becomes nullable (its `?? loadZip()` tail
already propagates null naturally).

Unifying on `getItem() || null` also fixes a latent inconsistency: a stored empty string
currently makes `hasStoredZip()` true while `loadZip()` returns `'78209'`.

### 2. Screens owning a zip INPUT — coerce at the state boundary

`PreferenceCapture.jsx:22`, `SearchScreen.jsx:76`, `RegionBrowse.jsx:47` each do
`useState(initialZip)` and then call `.length` during render or on mount — a null would be a hard
crash on three screens including the app's front door.

Fix: `useState(initialZip ?? '')`. Inputs stay controlled, and the existing `.length === 5`
validation already means "not submittable yet," which is now simply true rather than papered over.

### 3. Screens consuming a zip for API CALLS — guard, never send null

`Deals.jsx:30` and `Discovery.jsx:19` call `getDeals(zip, …)` against `GET /api/deals`, whose
`zip` is a required query param (`deals.py:25`) — a null becomes the literal string `"null"`.

Fix: `if (!zip) return;` before the fetch. `Deals` (a whole screen keyed on location) shows a
"set your location to see deals near you" prompt linking to `/`; `Discovery`'s deals rail simply
does not render, matching its existing behavior when a week has no drops. Also fix `Discovery`'s
dependency array from `[]` to `[zip]` — today it fires once with the initial value and never
refetches after the user sets a location.

This is the invariant the old `useUserZip` test was really protecting, now enforced where it
belongs: at the call sites, not by fabricating data.

### 4. Display sites — an affordance, not a fabrication

`MobileChrome.jsx:43/:108` and `Account.jsx:85` render the zip directly.

Fix: when zip is null, the `◎ {zip}` pill becomes a tappable **`◎ Set location`** button
navigating to `/` (PreferenceCapture, which already owns the primary zip input — no new screen),
and the title drops the clause to plain `Tonight` rather than "Tonight, near null". `Account`'s
chip gets the same treatment instead of rendering an empty bordered pill.

### 5. Aisle mode — fix the ordering, not the symptom

Gate the store picker on a known zip: if `openStorePicker` is requested while no zip is
confirmed, show the zip prompt **first**, then open the picker once confirmed.

This eliminates the reported bug **structurally** — the picker becomes unreachable without a zip,
so "store selected but still asked for zip" cannot occur — and simultaneously fixes defect 3,
since the picker can no longer query against a fabricated location. No `zipConfirmed`-setting
side effect is added to the store handlers; with the ordering enforced it would be dead code.

The "Somewhere else — just use my zip" branch (`:470`) is correct as-is and stays unchanged: it
explicitly defers to the zip, which by then is known.

### 6. Testing

- **Invert** `useUserZip.test.jsx:47-49` per the reasoning above: assert null is returned when
  nothing is stored, and that null-zip screens never call a required-zip endpoint.
- Update the ~5 suites using `getByDisplayValue('78209')` as an input handle
  (`PreferenceCapture.test.jsx:17,24,35,44-45`, `SearchScreen.test.jsx:98`,
  `RegionBrowse.test.jsx:69,116`, `ModeTabs.test.jsx:38`).
- **New coverage for the reported bug**: entering aisle mode via the strip with an empty
  `localStorage` must prompt for zip before the store picker, and must not re-prompt after a
  store is picked. `ChatRecommendAsk.test.jsx` currently seeds `somm_zip` in `beforeEach`
  (`:41`), which is exactly why this shipped — the no-zip path was never exercised for the
  picker.
- Regression guards for the three crash sites: each input-owning screen renders with empty
  `localStorage` without throwing.

## Out of scope

- Adding a `zip` field to the `GET /api/stores/nearby` response (unnecessary once ordering is
  fixed — a zip is always known before the picker opens).
- Geolocation / auto-detecting the user's zip.
- Any change to the recommend/search/region endpoints' required-zip contracts.
- The desktop (non-`MobileChrome`) header, which does not render a zip pill.
