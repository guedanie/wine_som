# Multi-Region Comparison Queries (Design)

**Date:** 2026-07-23
**Roadmap:** recommender capability follow-on (comparison queries)

## Problem

A prompt naming two places — "a cab from **California** vs a **Mendoza** one, recommend
two to try" — parses to a single `region` field. Live repro of the exact prompt:

```
wine_type: 'red'   region: 'California'   grapes: ['Cabernet Sauvignon']
```

`Mendoza` is dropped. Consequences:
- The targeted fetch (`_targeted_rows`, item 29) pulls only California cabs; Mendoza gets
  no targeted fetch and reaches the pool only via the arbitrary breadth-500 sample.
- The scorer credits only `California` for the `_W_REGION` boost.
- Result: Somm truthfully says "nothing from Mendoza surfaced" though **397 Mendoza wines
  are in stock near 78209**. The comparison the user asked for is impossible.

Not a data or deploy issue (verified: live prod returns Mendoza for a single-region
"Malbec from Mendoza" query). The recommender simply handles **one place per query**.

## Goal

Support queries naming 2+ places: capture all of them, fetch each, score each, and
**guarantee the picks represent each named region** so a comparison actually returns one
of each.

## Design

### 1. Intent — capture every named place

`recommendation/intent.py`:
- Add `regions: {"type": "array", "items": {"type": "string"}}` to the `wine_intent`
  tool schema. System-prompt line: "`regions`: list EVERY wine region or country the user
  names, in order (e.g. 'California vs Mendoza' → ['California','Mendoza']); use the
  existing `region` for the single primary place."
- `intent_from_request`: set `regions: []`.
- `merge_intent`: `out["regions"] = list(parsed.get("regions") or ([] if not
  out.get("region") else [out["region"]]))`; then keep the scalar in sync —
  `out["region"] = out.get("region") or (out["regions"][0] if out["regions"] else None)`.
  The scalar `region` stays populated so existing readers (`deep_fetch_reason`,
  logging) keep working; new code reads `regions`.

### 2. Targeted fetch — fetch each place separately

`api/routers/recommend.py` `_targeted_rows`:
- Today: one `region.ilike OR country.ilike` clause for the single region.
- New: iterate `resolved.get("regions")`; for EACH place run a fetch keyed on
  `region.ilike.%P% OR country.ilike.%P%` (reference_table="wines") with its own row
  budget, and merge the results. Per-place fetching (vs one combined OR sharing a 300-row
  cap) guarantees each named region contributes candidates — a single unordered OR could
  return mostly one region. Store detection (`detected_store`) still composes as today.
- Empty `regions` → same behavior as today (no targeted region fetch).

### 3. Scorer — credit any named place

`recommendation/scorer.py`:
- Replace `want_region = _norm(intent.get("region"))` with
  `want_regions = [_norm(r) for r in (intent.get("regions") or ([intent["region"]] if
  intent.get("region") else []))]`.
- The `_W_REGION` block credits the wine when it matches **any** place in `want_regions`
  (region-contains OR country-contains, per item 33). One `_W_REGION` credit per wine
  (not summed across places).
- Taste-profile `p_regions` logic is unchanged (separate).

### 4. Selection — guarantee representation

New pure helper in `recommendation/candidate_filters.py` (next to `pin_named_matches`):

```
ensure_region_representation(top, scored, regions, max_candidates) -> List
```

When `len(regions) >= 2`: for each named place with NO candidate in `top` matching it
(region/country contains), find the best-scoring matching candidate in the full `scored`
pool and pin it into `top`; if `top` is at `max_candidates`, drop the lowest-scoring
non-pinned entry to make room. At most one guaranteed pin per named place. When fewer
than 2 regions, returns `top` unchanged. Matching uses the same normalized containment as
the scorer.

Wired in `recommend.py` after `_select_diverse_top` (and after any `detected_store` sort),
using the full scored pool.

### 5. Narrative nudge

When `len(regions) >= 2`, set `resolved["comparison_regions"] = regions`. In
`claude_client.py` `_build_user_message`, render a directive when present: "The user is
comparing wines from {A} vs {B} — recommend one from each so they can taste the
difference side by side." Renders nothing when absent (single-region unchanged).

### 6. Testing

- `test_intent.py`: `merge_intent` captures `regions` list + keeps `region` scalar in
  sync; parsed-only; empty case.
- `test_scorer.py`: a wine matching the 2nd named region gets the `_W_REGION` boost (not
  just the 1st).
- `test_candidate_filters.py`: `ensure_region_representation` pins a missing region's best
  candidate, respects `max_candidates` (drops lowest non-pinned), no-op for <2 regions,
  no-op when both already represented.
- `test_claude_client.py`: comparison directive present when `comparison_regions` set,
  absent otherwise.
- Acceptance replay: "cab from California vs Mendoza under $50" at 78209 → the selected
  top includes ≥1 California AND ≥1 Mendoza candidate.

## Out of scope

- Budget-tuning (per-bottle target firmness / "$50 should pull toward $50") — separate
  item the user deferred.
- Comparisons across a non-place axis (grape vs grape, "old world vs new world") — only
  named regions/countries here.
