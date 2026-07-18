# Recommender Fixes: Country-Aware Matching + Fortified Request Path — Design

**Date:** 2026-07-18 · **Status:** approved design, pre-implementation
**Follow-on to:** item 29 (intent-aware fetch) + item 30 (wine_type backfill). Both fixes surfaced from live beta failures and a capability sweep.

## Problems (both confirmed by a 78209 pipeline sweep)

**1. Fortified is unreachable via a typed request.** Item 30 correctly retyped Port/Sherry/Madeira from `dessert` to `fortified`. But the intent enum (`recommendation/intent.py`) and frontend chips have no `fortified` — only `dessert`. So a "dessert / after-dinner / port" request emits `wine_type="dessert"`, and the type gate excludes the newly-fortified wines. Sweep: a dessert request surfaced **0 of 20** in-stock fortified wines.

**2. Compound country+type queries rely on breadth-sample luck (whole gap class).** The intent parser stuffs a country ("Argentina") into the `region` field, but wines are stored region=Mendoza/Salta/Patagonia with country=Argentina. The item-29 targeted fetch matches `wines.region` only, and the scorer's region boost matches region only — both are country-blind. So a country's wines surface only if they happen to land in the unordered 500-row type-filtered breadth sample. Sweep: `white+Argentina` surfaced **0**; `white+Chile` (5), `white+Germany` (8), `red+Argentina` (5) *looked* ok but are surviving on sample luck, not correctness — any could hit 0 on another turn.

## Decisions (user-approved)

1. **Fortified: fold into dessert at the gate** (not a new enum/chip). One-directional expansion.
2. **Country: make the targeted fetch and the scorer match the intent place against region OR country** (no new intent `country` field — the region-or-country match handles the parser stuffing country into `region`).

## Design

### Fix 1 — Fortified reachable via "dessert" (`recommendation/candidate_filters.py`)

`requested_types_from(chip_types, parsed_type)` gains a one-directional expansion: if the resulting set contains `"dessert"`, also add `"fortified"`. Because this set feeds **both** the type gate (`apply_type_gate`) and the type-aware breadth fetch (`_apply_type_breadth_filter`), a dessert request now fetches fortified-or-null wines and keeps them through the gate. One-directional (dessert → +fortified, never fortified → +dessert), so a `fortified` request — if it ever arises — stays strict. Data is unchanged (Port stays typed `fortified`).

### Fix 2 — Country-aware place matching (two spots)

The intent's `region` field holds a "place" that may be a country. Both fetch and rank must match it against region OR country.

- **`api/routers/recommend.py`** — the targeted fetch's region filter:
  ```python
  # was:  q = q.ilike("wines.region", f"%{region}%")
  # now:  match the place against region OR country
  q = q.or_(f"region.ilike.%{region}%,country.ilike.%{region}%", reference_table="wines")
  ```
  This pulls the Mendoza/Salta whites (country=Argentina) into the candidate pool.
- **`recommendation/scorer.py`** — the region-match boost (`want_region`) also credits `country`, so the place actually *ranks* the wine up (letting it reach the top-12), not just enter the pool:
  ```python
  # region boost also matches the wine's country
  country = _norm(wine.get("country"))
  if want_region and (
        (region and (want_region in region or region in want_region))
        or (country and (want_region in country or country in want_region))):
      score += _W_REGION
  ```
  Additive and safe — a region name won't spuriously match a country string.

## Testing

- **Unit (TDD):**
  - `requested_types_from(["dessert"], None) == {"dessert", "fortified"}`; `(["red"], None) == {"red"}`; `([], "dessert") == {"dessert", "fortified"}` (fold applies to the parsed value too); a `fortified` request stays `{"fortified"}` (no reverse fold).
  - Scorer: an intent `region="Argentina"` gives `_W_REGION` to a wine with `country="Argentina", region="Mendoza"` and does NOT to an unrelated `country="Chile"` wine (loser-first ordering so a stable-sort tie can't fake the pass).
- **Acceptance gate (replay the live failures):**
  - "white wines from Argentina near 78209" → the Mendoza/Salta whites now enter the pool AND rank into the top-12 (the sweep's `white+Argentina` 0→N).
  - "a dessert wine" / "port" near 78209 → a fortified Port/Sherry now surfaces (the sweep's fortified 0→N).
  - Regression: the sweep's healthy axes (type/region/grape/type+region) still surface; existing `test_recommend_api.py` / `test_scorer.py` / `test_candidate_filters.py` green.

## Out of scope / follow-up

- **Second capability sweep — flavor/style, avoid, and body axes** (roadmap item): the first sweep covered structural axes (type/region/country/grape/price/compound) and found only these two gaps. The softer keyword-driven paths — `flavor_tags_for` + the scorer flavor axis, the `avoid` hard-exclusion path, and `body`/`_resolve_body` — were NOT probed and are the likeliest place for the next hidden gaps. A dedicated sweep of those is queued.
- No intent-schema `country` field (region-or-country match handles it); no frontend `fortified` chip (dessert fold handles it).
