# Bottle Identify — frontend v1 (tappable screen for testers) — design

**Date:** 2026-10-26
**Status:** approved, not yet implemented

## Problem

The backend (`POST /api/identify`, merged to `main` in `backend/api/routers/identify.py`) is live but has no UI — testers can't reach it without hitting the raw API directly. The owner wants a small group of real users to try bottle identification through the actual app this week. A full design handoff already exists (`frontend/design-system/handoffs/bottle-scan/`) specifying camera FAB entry, barcode scanning, a five-state bottom sheet, save/cellar hooks, and a sign-in-nudge integration — but that is a multi-day build. This spec scopes a deliberately smaller v1: the core loop only (photo in, identification out), fast enough to ship this week, with everything else named as a deferred seam rather than silently dropped.

## Scope

**In scope (v1):**
- A new screen + route reachable from real navigation (not a hidden/shared-link-only route).
- Native camera capture via file input (the design brief's own recommended approach for iOS PWA reliability).
- Calling `/api/identify` and rendering all six real outcomes the backend can return (`exact`, `candidates`, `vintage_mismatch`, `unstocked`, `unreadable`, `not_wine`).
- A photo-retake affordance from every state.
- On a found wine, a link into the existing, already-built wine dossier (`/wine/:id`) for anything deeper (price, availability, save, cellar) — reusing a proven screen rather than rebuilding that logic here.

**Explicitly deferred (named, not silently dropped):**
- Barcode scanning (Tier 1 of the full design).
- The raised camera-FAB visual treatment (v1 uses a plain 6th tab icon).
- Save/cellar action buttons directly on the identify result (v1 hands off to the dossier for that).
- The anonymous sign-in-nudge integration (not needed since v1 has no save action of its own).
- Desktop drag-and-drop modal variant — v1's desktop entry navigates to the same `/identify` route (not a modal); the `<input type="file" accept="image/*">` on desktop browsers simply opens the OS file picker instead of the camera (the `capture="environment"` attribute is ignored on desktop, which is standard, expected behavior — no separate code path needed).
- "Recently scanned" history.
- Pixel-fidelity to the hi-fi mockup (`Somm - Bottle Scan.html`) — v1 follows the design tokens and general shape, not an exact recreation.

## Design

### Entry point

A 6th tab added to `BottomTabs` (`src/components/MobileChrome.jsx`) — camera icon, label "Scan", `to: '/identify'`, inserted into the existing `TABS` array following the same `{id, label, to, match, icon}` shape as the other five. A matching link added to the desktop `NavBar` (`src/components/NavBar.jsx`), following its existing mapped-list pattern.

Risk accepted knowingly: this changes a live, working 5-tab bar before the feature itself is validated. Decided deliberately (over a hidden route) because discoverability for real testers matters more here than nav stability, and the change itself is additive and small (one more icon, same pattern as the existing five).

### Screen: `src/screens/Identify.jsx`, route `/identify`

State machine, four states:
1. **`idle`** — a camera/upload prompt (somm-voice copy, e.g. "Show me the bottle"), a single button opening `<input type="file" accept="image/*" capture="environment">`.
2. **`identifying`** — shown immediately on file selection, before the fetch resolves. Somm-voice loading copy ("Let me get a look at it…"), consistent with the existing streamed "Looking deeper into the cellar…" pattern elsewhere in the app. No fake progress bar — this is a single request, not a stream.
3. **`result`** — renders based on the response's `status` field (see below).
4. **`error`** — network failure or a non-2xx from the endpoint (400/502/429) with a retry button. Distinct from `not_wine`/`unreadable`, which are successful 200 responses with an informational status, not errors.

### Result rendering by `status`

| status | Rendering |
|---|---|
| `exact` | Wine name (serif), producer + vintage + region (Archivo small), a button "See where to buy" → `navigate('/wine/' + wine.id)`. |
| `vintage_mismatch` | Same layout as `exact`, plus one somm-voice line using `read_vintage` and the matched wine's vintage (e.g. "I see the 2021 nearby — yours looks like the 2019."). |
| `candidates` | A short list (name + vintage + region per row) from the `candidates` array, each tappable → same dossier handoff using that candidate's id. |
| `unstocked` | Somm-voice line naming the read producer/wine name if available (e.g. "Nobody near you stocks that one — hang tight, this list grows every week."), no card. No dead end. |
| `unreadable` | Somm-voice line + one concrete retake tip ("Try getting the whole front label in frame"), plus the retake button. |
| `not_wine` | Somm-voice line acknowledging it's not a wine, plus the retake button. |

All copy follows `frontend/CLAUDE.md`'s voice section (knowledgeable friend, specific, never "no results found").

### API client addition

`src/lib/api.js` gains `identifyBottle(photoFile)`:

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

Follows the same `BASE`/error-handling convention as every other function in that file (`getWine`, `getDeals`, etc.) — multipart `FormData` instead of JSON body is the only structural difference, since this endpoint takes a file upload.

### What this does NOT touch

- `backend/api/routers/identify.py` — unmodified. The `_debug` block in its response is simply ignored by the frontend (not rendered, not stripped — out of scope for this spec to touch backend response shape).
- `RegionDossier.jsx` / `/wine/:id` — unmodified, just linked to.
- Any auth/sign-in flow — v1 has no action that requires being signed in.

## Testing

- Component tests for `Identify.jsx` (new file, following the existing `src/screens/__tests__/` convention) covering: idle → file selected → identifying state shown, each of the six `status` renderings, the error state on a fetch rejection, and the retake button resetting to `idle` from every terminal state.
- A test for `identifyBottle()` in `src/lib/api.js`'s test file, mocking `fetch` to confirm `FormData` is sent and errors surface the `detail` message — following the existing pattern for other `api.js` functions' tests.
- No test exercises real vision accuracy (same caveat as the backend spec) — that remains the owner's manual job with real testers.

## Workflow

Built on its own feature branch/worktree (same pattern as the backend endpoint) since it touches live navigation before the underlying feature is validated. Owner (and the small tester group) validates by using the real app; iterate on the branch; merge to `main` once satisfied.
