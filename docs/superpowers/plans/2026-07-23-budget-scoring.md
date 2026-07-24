# Budget Scoring Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a stated "up to $X" budget pull picks toward the ceiling while staying soft (a standout value wine can still win).

**Architecture:** Two tuned constants in `recommendation/scorer.py` — raise the budget target `0.75×max → 0.85×max`, and raise `_W_BUDGET 1.0 → 1.5` (still below grape/type). Validate on live data.

**Tech Stack:** Python 3.9 (`Optional[...]`, never `X | None`), pytest.

**Env:** Backend commands from `/Users/danielguerrero/dev/wine_app/backend`. Bare `python3` is a BROKEN Homebrew stub — use `/usr/bin/python3`. Never stage `.claude/settings.local.json`.

**Reference:** spec `docs/superpowers/specs/2026-07-23-budget-scoring-design.md`. Current budget code: `_W_BUDGET = 1.0` (scorer.py ~line 14); `budget_target = max(budget_min, 0.75 * budget_max)` (~line 155); the proximity block `distance = abs(price - budget_target) / (budget_max - budget_min); score += _W_BUDGET * max(0.0, 1.0 - distance)` (~lines 209-213). `_W_GRAPE = 2.0`, `_W_TYPE = 3.0`, `_W_RATING = 1.5` are the reference weights.

---

### Task 1: Scorer constants + tests

**Files:**
- Modify: `backend/recommendation/scorer.py` (`_W_BUDGET`, `budget_target`, the code comment)
- Test: `backend/tests/test_scorer.py`

- [ ] **Step 1: Write the failing test (the user's exact case)**

Add to `backend/tests/test_scorer.py`:

```python
def test_budget_prefers_near_ceiling_over_cheap_with_modest_rating_edge():
    # The Juggernaut case: a cheap wine ($16, 4.1★) vs a near-ceiling wine ($45, no
    # rating), budget "up to $50". With the ceiling-leaning pull the near-ceiling wine
    # should now win — budget is felt, though still soft.
    near = _wine("Near Ceiling", price=45.0)
    cheap = _wine("Cheap Rated", price=16.0)
    cheap["vivino_rating"] = 4.1
    cheap["vivino_ratings_count"] = 71000
    result = score_candidates(
        _intent(wine_type="red", budget_min=10.0, budget_max=50.0), [cheap, near])
    assert result[0]["name"] == "Near Ceiling"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_scorer.py -k near_ceiling -v`
Expected: FAIL — under today's constants the $16/4.1★ wine outranks the $45 wine.

- [ ] **Step 3: Change the two constants + comment**

In `backend/recommendation/scorer.py`:

Change the weight (~line 14):
```python
_W_BUDGET = 1.0
```
→
```python
_W_BUDGET = 1.5          # felt, but below _W_GRAPE/_W_TYPE so quality still leads
```

Change the target + comment (~lines 151-155):
```python
    # The budget pull targets 0.75×max, not the window midpoint — a $150 budget
    # reads as appetite to spend (~$112), not "anything under $150 is equally
    # fine". Clamped to the floor so narrow windows don't target an unreachable
    # price below budget_min.
    budget_target = max(budget_min, 0.75 * budget_max)
```
→
```python
    # "up to $X" is a ceiling people generally want to spend near — target 0.85×max
    # ($42.50 for a $50 ceiling) so picks cluster in the upper band, not the midpoint.
    # Clamped to the floor so narrow windows don't target a price below budget_min.
    budget_target = max(budget_min, 0.85 * budget_max)
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_scorer.py -k near_ceiling -v`
Expected: PASS.

- [ ] **Step 5: Update the two existing budget tests + add the softness guard**

In `backend/tests/test_scorer.py`:

`test_big_budget_pulls_toward_the_top_of_the_window` — update the docstring numbers (`0.75×max (~$112)` → `0.85×max (~$127.50)`); the assertion (`Splurge Red` $110 beats midpoint $80) still holds and needs no change. Replace the docstring:
```python
    """A $150 budget reads as appetite to spend: the pull targets 0.85×max
    (~$127.50), not the window midpoint ($80). The $110 splurge is closer to the
    target than the $80 midpoint, so it comes first."""
```

`test_price_target_clamps_into_narrow_window` — with 0.85, a $10–$12 window targets
$10.20 (no clamp), so change the window to $10–$11 (0.85×11 = $9.35 < floor → clamps to
$10) to keep exercising the clamp. Replace the test body:
```python
def test_price_target_clamps_into_narrow_window():
    """0.85×max can fall below budget_min on narrow windows (e.g. $10–$11 →
    $9.35); the target clamps to the floor so in-window wines aren't all
    penalized toward an unreachable price."""
    low = _wine("Ten Dollar Red", price=10.0)
    high = _wine("Eleven Dollar Red", price=11.0)
    result = score_candidates(_intent(budget_min=10.0, budget_max=11.0), [high, low])
    assert result[0]["name"] == "Ten Dollar Red"
```

Add the softness guard:
```python
def test_standout_cheap_wine_still_wins_soft_budget():
    # A much-higher-rated value wine ($20, 4.7★) must still beat a mediocre near-ceiling
    # wine ($48, no rating) — budget is soft, quality leads.
    splurge = _wine("Mediocre Splurge", price=48.0)
    value = _wine("Standout Value", price=20.0)
    value["vivino_rating"] = 4.7
    value["vivino_ratings_count"] = 50000
    result = score_candidates(
        _intent(wine_type="red", budget_min=10.0, budget_max=50.0), [splurge, value])
    assert result[0]["name"] == "Standout Value"
```

- [ ] **Step 6: Run the full scorer suite**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_scorer.py -v`
Expected: PASS (all — updated existing, new, and unrelated tests).

- [ ] **Step 7: Commit**

```bash
git add backend/recommendation/scorer.py backend/tests/test_scorer.py
git commit -m "feat(scorer): budget pull targets 0.85x ceiling, weight 1.5 (soft)"
```

---

### Task 2: Live validation + docs

**Files:**
- Create: `backend/scripts/verify_budget_pull.py`
- Modify: `CLAUDE.md` (item 33/35 area — a budget note), `docs/reference/recommendation.md`

- [ ] **Step 1: Write the acceptance script**

Create `backend/scripts/verify_budget_pull.py`:
```python
"""Acceptance: an 'up to $50' bold-red request now clusters picks in the upper band
(vs the ~$16-20 the user saw), while a standout value wine can still surface.
Run from backend/: /usr/bin/python3 -m scripts.verify_budget_pull"""
from statistics import median
from db import get_supabase_client
from recommendation.scorer import score_candidates
from utils.geo import find_nearby_store_ids

ZIP = "78209"
SEL = ("price, wine_id, wines!inner(id, name, varietal, region, country, wine_type, "
       "grapes, vivino_rating, vivino_ratings_count)")


def main():
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(ZIP, sb)
    rows = (sb.table("retail_inventory").select(SEL).in_("store_ref", nearby)
            .eq("in_stock", True).gte("price", 10).lte("price", 50)
            .eq("wines.wine_type", "red").limit(1000).execute().data or [])
    cands = []
    for r in rows:
        w = r["wines"]
        cands.append({"wine_id": w["id"], "store_ref": "s", "name": w["name"],
                      "varietal": w.get("varietal"), "region": w.get("region"),
                      "country": w.get("country"), "wine_type": "red",
                      "grapes": w.get("grapes") or [], "price": float(r["price"] or 0),
                      "vivino_rating": w.get("vivino_rating"),
                      "vivino_ratings_count": w.get("vivino_ratings_count")})
    intent = {"wine_type": "red", "flavors": ["bold"], "grapes": [], "regions": [],
              "region": None, "avoid": [], "budget_min": 10.0, "budget_max": 50.0}
    scored = score_candidates(intent, cands)
    top = scored[:8]
    prices = [c["price"] for c in top]
    print(f"scored {len(cands)} red candidates under $50")
    print(f"top-8 prices: {[round(p) for p in prices]}")
    print(f"median top-8 price: ${median(prices):.0f}")
    # (a) picks now cluster in the upper band (well above the old ~$16-20 outcome)
    assert median(prices) >= 30, f"expected upper-band clustering, got median ${median(prices):.0f}"
    print("OK — budget pull clusters picks in the upper band")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `cd backend && /usr/bin/python3 -m scripts.verify_budget_pull 2>&1 | grep -vE "NotOpenSSL|warnings.warn"`
Expected: prints the top-8 prices + median, `median >= $30`, `OK`. If the median comes back low (picks still cheap) or pinned to a single $50 bottle, tune ONLY the two constants (try target `0.85→0.88` and/or `_W_BUDGET 1.5→1.8` for firmer, or `1.5→1.3` if it over-clusters) and re-run Task 1's suite + this script. Record the final constants.

- [ ] **Step 3: Update docs**

- `docs/reference/recommendation.md`: in the scorer section, update the budget description — target `0.85×max`, weight `1.5`, "up to $X clusters near the ceiling, soft (grape/type still lead)".
- `CLAUDE.md`: update the item-35 deferred-budget note to ✅ — the budget pull now targets 0.85×ceiling at weight 1.5 (soft), landed 2026-07-23, verified at 78209.

- [ ] **Step 4: Run the full fast suite**

Run: `cd backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/verify_budget_pull.py CLAUDE.md docs/reference/recommendation.md
git commit -m "test+docs: budget pull validation + reference/roadmap"
```

---

## Self-Review Notes

- **Spec coverage:** §1 target→T1 step 3; §2 weight→T1 step 3; validation→T2; testing→T1 steps 1/5. All covered.
- **Numbers check (target 0.85×50=$42.50, _W_BUDGET 1.5, window 40):**
  - near-ceiling test: $45 budget `(1-|45-42.5|/40)*1.5 = 1.406` vs $16 `(1-|16-42.5|/40)*1.5 + rating(4.1: 1.5*(4.1-3.5)/1.5=0.6) = 0.506+0.6 = 1.106` → $45 wins ✓ (today: $45 `0.8125` vs $16 `0.4625+0.6=1.06` → $16 wins, so it fails first ✓).
  - softness guard: $48 `(1-|48-42.5|/40)*1.5 = 1.294` vs $20 `(1-|20-42.5|/40)*1.5 + rating(4.7: 1.5*0.8=1.2) = 0.656+1.2 = 1.856` → $20 wins ✓.
  - clamp test: $10–$11 → target `max(10, 9.35)=10`; $10 dist 0 → 1.0, $11 dist 1.0 → 0 → low wins ✓.
- **Softness preserved:** `_W_BUDGET=1.5 < _W_GRAPE=2.0 < _W_TYPE=3.0`; a rating gap ≥ ~0.9 points can still override the budget pull.
