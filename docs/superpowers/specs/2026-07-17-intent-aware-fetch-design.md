# Intent-Aware Candidate Fetch + Wine-Type Guarantee — Design

**Date:** 2026-07-17 · **Status:** approved design, pre-implementation
**Triggered by:** a live beta failure — "red · ≤$45 · Show me one Bordeaux blend at heb lincon heights" returned "No true Bordeaux blend shows up at Lincoln Heights H-E-B in the inventory," when three red Bordeaux blends were in fact in stock there.

## Root cause (confirmed by replication)

`api/routers/recommend.py` fetches candidates with `_FETCH_PER_RETAILER = 500` per retailer, over that retailer's stores within a 10-mile radius (`find_nearby_store_ids(..., radius_miles=10.0)`). The query filters `in_stock`, budget, and freshness, but is **unordered and intent-blind**. For zip 78209 the nearby H-E-B pool is 5,511 in-budget/in-stock/fresh rows; the fetch samples an arbitrary **500 (9%)**. All three Lincoln Heights Bordeaux blends fell outside that sample, so they were never scored — the correctly-parsed `region: Bordeaux` intent boost never applied, because scoring only runs on fetched rows. Claude received 12 candidates (none Bordeaux) and asserted absence.

Two contributing issues:
- **Wine_type is only a soft scorer boost, never a gate** — a red request can surface a white if it out-scores on other axes. (Users are more sensitive to type than region.)
- **5,443 wines (27.5%) have NULL `wine_type`** (403 with "red" in the name, incl. Château Saint-Sulpice — a real Merlot/Cab/Malbec blend). A naive `wine_type=red` fetch filter would *drop* all of these.

## Decisions (user-approved)

1. **Split scope:** this spec fixes the recommender fetch/selection end-to-end. The 5,443 NULL-`wine_type` backfill is a separate later data pass (not blocking — handled at query time here).
2. **Region hard where safe, wine_type lenient-in-fetch but hard-gated-at-selection.**
3. **Store-scoping: soft-prefer + fuzzy** (tolerate the "lincon" typo; never return blank on a near-miss).
4. **Wine-type is a guarantee:** a request for a type must never surface a conflicting type.

## Design

### 1. Targeted relevance fetch (core fix)
Keep the 500-row breadth fetch. Additionally, when the parsed intent carries a `region`, a detected store, and/or specific grapes, run a **small supplementary query** for those exact matches within the 10-mile radius and merge into the pool (dedup by `wine_id`+`store_ref`). "region=Bordeaux, nearby" returns ~16 rows — all guaranteed into the pool. This avoids hard-filtering the main query on region (no "Napa" vs "Napa Valley" brittleness) while guaranteeing the named thing is present. Region match in the targeted query is flexible (`ilike`/canonical), mirroring the scorer's substring region logic.

### 2. Type-aware breadth fetch
When intent specifies `wine_type`, filter the 500-row query to `wine_type IN (type, NULL)` so the budget buys plausibly-right-type wines while keeping mis-typed reds. Requires switching the nested `wines(...)` select to `wines!inner(...)` to enable the embedded-column filter. Whites are still excluded at selection (§3), so this is an efficiency gain, not the correctness guarantee.

### 3. Type resolution + hard gate (the guarantee)
At candidate build, resolve every NULL `wine_type` deterministically with the existing `utils.infer_wine_type` applied in order: `varietal → name → first grape`. Then, **when the user explicitly requested a `wine_type`, hard-exclude any candidate whose resolved type is known AND conflicts.**
- Saint-Sulpice: NULL → name "Bordeaux Red Wine" → red → **kept** for a red request.
- A NULL Sauvignon Blanc → white → **excluded** for a red request.
- A truly unresolvable NULL → kept (benefit of the doubt; rare).

This closes the "red request surfaced a white" gap, using reliable deterministic inference rather than trusting the NULL column.

### 4. Store-awareness (fuzzy, soft)
Add `_detect_store(message, nearby_stores)` beside the existing `_detect_retailer()`. Fuzzy-match the message against the *nearby* store names (token/substring + small edit distance) so "lincon heights" resolves to "Lincoln Heights Market H-E-B". A detected store:
- guarantees its in-radius matches into the pool (via §1), and
- gives those candidates a scoring boost,
- but **never hard-filters** — a typo or thin-stock store still yields nearby alternatives, never a blank result.

### 5. Claude hedging (trust safety net)
Adjust the `claude_client` prompt so an absence is phrased relative to what was provided ("nothing matching in what's available near you") rather than an absolute inventory claim. Largely moot once the pool contains the matches, but prevents a confident-wrong absence assertion when a genuine gap exists.

## Testing

- **Unit (TDD):** type resolver (`varietal→name→grape` precedence; "Bordeaux Red Wine" → red; "Sauvignon Blanc" → white; unresolvable → None); type gate (red request keeps resolved-red + unresolvable, drops resolved-white and vice-versa); store fuzzy-match (tolerates "lincon", rejects unrelated names, scoped to nearby only); targeted-fetch merge/dedup (no duplicate wine_id+store_ref; targeted rows present even when absent from the breadth sample).
- **Acceptance gate:** replay the exact failing query (`red · ≤$45 · "Bordeaux blend at heb lincon heights"`, zip 78209). Confirm the three Lincoln Heights Bordeaux blends enter the candidate pool, a real Bordeaux is picked, the non-Bordeaux red-blend pick still works, and **no white surfaces**.
- Regression: existing `test_recommend_api.py` / `test_scorer.py` green.

## Out of scope / future (add to roadmap)

- **NULL-`wine_type` backfill** (5,443 wines) — a separate deterministic data pass (name/varietal/grape → type via `infer_wine_type`), same shape as the grapes backfill. Deferred; §2/§3 handle mis-typed wines at query time meanwhile.
- **FUTURE TODO — name-directed full-inventory fallback:** when a prompt yields no results *and* the intent references a specific bottle by name, let Somm search the **entire zip-scoped inventory** (optionally type-filtered) rather than the top-500 breadth sample — an extension of §1's targeted fetch, triggered by a bottle-name reference, with its own fuzzy-bottle-match + ranking design. Capture as a new CLAUDE.md roadmap item during implementation docs.
