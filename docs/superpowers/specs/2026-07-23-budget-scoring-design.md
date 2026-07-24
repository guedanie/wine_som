# Budget Scoring Rework (Design)

**Date:** 2026-07-23
**Roadmap:** recommender capability follow-on (budget behavior)

## Problem

A user setting "up to $50" got two ~$16–20 bottles and found it unsatisfying. Root
cause in `recommendation/scorer.py` `score_candidates`:

- The frontend slider is a single "up to $X" ceiling; the request sends
  `budget_max = X` and a hardcoded `budget_min = 10` (`frontend/src/lib/regions.js`).
- Budget scoring targets `0.75 * budget_max` ($37.50 for a $50 ceiling) and is a soft
  axis at weight `_W_BUDGET = 1.0` — far below `_W_TYPE = 3.0`, `_W_GRAPE = 2.0`,
  `_W_RATING = 1.5`. So a cheap, high-rated, on-style wine ($16 Juggernaut, 4.1★/71k)
  outscores pricier options; the ~0.6 budget gap can't overcome its rating+type score.

Decision (locked): a stated "up to $X" should pull picks toward the ceiling (people who
set $50 want ~$50 wine), while staying **soft** — a genuinely great-value cheaper wine
can still surface.

## Design

Two coordinated constant changes in `score_candidates`, curve shape unchanged.

### 1. Raise the target toward the ceiling
```python
budget_target = max(budget_min, 0.75 * budget_max)
```
→
```python
budget_target = max(budget_min, 0.85 * budget_max)
```
Sweet spot for "up to $50" moves $37.50 → **$42.50**; picks cluster $40–$50. The existing
symmetric proximity curve then rewards using more of the budget: a $16 wine's budget score
falls (~0.46 → ~0.34), a $42.50 wine peaks (1.0), a $50 wine still scores ~0.81. (No wine
above `budget_max` reaches scoring — the fetch caps price at the ceiling — so the
above-target side is a narrow band.)

### 2. Make the budget axis felt (still soft)
```python
_W_BUDGET = 1.0   →   _W_BUDGET = 1.5
```
At 1.0 the budget difference is too small to change outcomes; at 1.5 it competes, **but
stays below `_W_GRAPE` (2.0) and `_W_TYPE` (3.0)** — so a much-higher-rated, exact-style
cheaper wine can still win. Budget influences; quality/type lead. Update the code comment
to reflect the ceiling-leaning intent.

### Explicitly NOT changing
- The curve shape (symmetric proximity to target).
- `budget_min` (the hardcoded 10 floor) or the frontend slider.
- No separate far-below price floor (the raised target already dis-prefers bargain-bin).
- No price-spread for multi-bottle "recommend two" asks (a different philosophy; possible
  future tweak).

## Validation (part of this work)

These are tuned constants, so acceptance replays the real scenario on live 78209 data:
`scripts/verify_budget_pull.py` — build the "$50, red, bold" intent, fetch + score real
in-stock candidates, and assert:
- (a) the top picks' median/mean price skews into the upper band (materially higher than
  with the old 0.75/1.0 constants — compare both), AND
- (b) a deliberately-seeded standout value wine (a high-rated cheap bottle) still ranks
  among the top, proving softness is preserved.

If the numbers don't land (e.g. picks pinned to the single priciest bottle, or still all
cheap), tune only the two constants (`0.85`, `1.5`) and re-check; curve shape + softness
stay fixed.

## Testing

- Update the two existing budget tests in `tests/test_scorer.py` for the $42.50 target:
  `test_big_budget_pulls_toward_the_top_of_the_window`,
  `test_price_target_clamps_into_narrow_window`.
- Add `test_budget_prefers_near_ceiling_over_cheap_at_equal_quality` (a $45 wine outranks a
  $16 wine when type/grape/rating are equal).
- Add `test_standout_cheap_wine_still_wins` (a much-higher-rated $20 wine outranks a
  mediocre $48 wine — softness preserved).

## Out of scope

- Price-spread across multi-bottle picks.
- Making `budget_min` user-adjustable / a two-handle slider.
- Interpreting phrasing ("under $50" as a hard ceiling vs "around $50") differently.
