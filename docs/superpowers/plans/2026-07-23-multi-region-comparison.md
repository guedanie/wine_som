# Multi-Region Comparison Queries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support prompts naming 2+ places ("California vs Mendoza") — capture all, fetch each, score each, and guarantee the picks represent each named region.

**Architecture:** Add `regions: List[str]` to the intent (scalar `region` kept in sync for back-compat). The scorer credits any named place; the targeted fetch pulls each place separately; a new `ensure_region_representation` helper pins each named region's best candidate into the top-12; a narrative directive tells Claude to pick one from each.

**Tech Stack:** Python 3.9 (`Optional[...]`, never `X | None`), pytest.

**Env:** Backend commands from `/Users/danielguerrero/dev/wine_app/backend`. Bare `python3` is a BROKEN Homebrew stub — use `/usr/bin/python3`. Never stage `.claude/settings.local.json`.

**Reference:** spec `docs/superpowers/specs/2026-07-23-multi-region-comparison-design.md`.

---

### Task 1: Intent — capture `regions` list

**Files:**
- Modify: `backend/recommendation/intent.py` (tool schema, system prompt, `intent_from_request`, `merge_intent`)
- Test: `backend/tests/test_intent.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_merge_captures_regions_list():
    explicit = intent_from_request(wine_type=None, style_preferences=[], avoid=[],
                                   budget_min=10.0, budget_max=50.0)
    merged = merge_intent({"regions": ["California", "Mendoza"], "region": "California",
                           "flavors": [], "grapes": [], "avoid": []}, explicit)
    assert merged["regions"] == ["California", "Mendoza"]
    assert merged["region"] == "California"           # scalar back-compat


def test_merge_regions_backfills_from_scalar_region():
    explicit = intent_from_request(wine_type=None, style_preferences=[], avoid=[],
                                   budget_min=10.0, budget_max=50.0)
    merged = merge_intent({"region": "Rioja", "flavors": [], "grapes": [], "avoid": []}, explicit)
    assert merged["regions"] == ["Rioja"]             # single region → 1-element list
    assert merged["region"] == "Rioja"


def test_intent_from_request_regions_empty():
    out = intent_from_request(wine_type=None, style_preferences=[], avoid=[],
                              budget_min=10.0, budget_max=50.0)
    assert out["regions"] == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_intent.py -k regions -v`
Expected: FAIL (`KeyError: 'regions'`).

- [ ] **Step 3: Add `regions` to the tool schema**

In `_TOOL["input_schema"]["properties"]`, after the `region` line add:
```python
            "regions": {"type": "array", "items": {"type": "string"}},
```

- [ ] **Step 4: System-prompt guidance**

In `parse_message`, extend the system string (after the wine_name sentence) with:
```python
                " `regions`: list EVERY wine region or country the user names, in the "
                "order mentioned (e.g. 'California vs Mendoza' -> ['California','Mendoza']); "
                "keep `region` as the single primary place."
```

- [ ] **Step 5: `intent_from_request` sets `regions: []`**

Add `"regions": [],` to the returned dict.

- [ ] **Step 6: `merge_intent` — populate regions + keep scalar in sync**

After the existing `out["region"] = out.get("region") or parsed.get("region")` line, add:
```python
    out["regions"] = list(parsed.get("regions") or [])
    if not out["regions"] and out.get("region"):
        out["regions"] = [out["region"]]
    if not out.get("region") and out["regions"]:
        out["region"] = out["regions"][0]
```

- [ ] **Step 7: Run to verify pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_intent.py -v`
Expected: PASS (all).

- [ ] **Step 8: Commit**

```bash
git add backend/recommendation/intent.py backend/tests/test_intent.py
git commit -m "feat(intent): capture regions list for multi-place queries"
```

---

### Task 2: Scorer — credit any named place

**Files:**
- Modify: `backend/recommendation/scorer.py` (`score_candidates`: `want_region` → `want_regions`, the `_W_REGION` block)
- Test: `backend/tests/test_scorer.py`

- [ ] **Step 1: Write the failing test**

```python
def test_region_boost_credits_any_named_place():
    # two places named; a wine from the SECOND must still get the region boost
    mendoza = _wine("Malbec", wine_type="red", varietal="Malbec", region="Mendoza", country="Argentina")
    napa = _wine("Cab", wine_type="red", varietal="Cabernet Sauvignon", region="Napa Valley", country="USA")
    intent = _intent(wine_type="red")
    intent["regions"] = ["California", "Mendoza"]
    result = score_candidates(intent, [mendoza, napa])
    scores = {w["name"]: w["_score"] for w in result}
    # both should be boosted for their region (California~Napa via containment? no —
    # 'california' not in 'napa valley'); assert Mendoza (2nd place) got the boost
    assert scores["Malbec"] > 0
    # a wine from neither place gets no region boost
    other = _wine("Rioja Red", wine_type="red", varietal="Tempranillo", region="Rioja", country="Spain")
    r2 = score_candidates(intent, [mendoza, other])
    s2 = {w["name"]: w["_score"] for w in r2}
    assert s2["Malbec"] > s2["Rioja Red"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_scorer.py -k region_boost_credits -v`
Expected: FAIL (region ignored — `want_regions` not read yet; Malbec gets no region boost).

- [ ] **Step 3: Replace `want_region` with `want_regions`**

Change line ~158:
```python
    want_region = _norm(intent.get("region")) if intent.get("region") else None
```
to:
```python
    want_regions = [_norm(r) for r in (intent.get("regions")
                    or ([intent["region"]] if intent.get("region") else [])) if r]
```

- [ ] **Step 4: Update the `_W_REGION` block**

Replace lines ~199-202:
```python
        if want_region and (
                (region and (want_region in region or region in want_region))
                or (country and (want_region in country or country in want_region))):
            score += _W_REGION
```
with:
```python
        if want_regions and any(
                (region and (wr in region or region in wr))
                or (country and (wr in country or country in wr))
                for wr in want_regions):
            score += _W_REGION
```

- [ ] **Step 5: Run to verify pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_scorer.py -v`
Expected: PASS (new + existing region tests `test_region_match_is_accent_insensitive`, `test_region_match_uses_containment` — those use the scalar `region`, still covered because `want_regions` falls back to `[region]`).

- [ ] **Step 6: Commit**

```bash
git add backend/recommendation/scorer.py backend/tests/test_scorer.py
git commit -m "feat(scorer): region boost credits any named place (want_regions)"
```

---

### Task 3: `ensure_region_representation` helper

**Files:**
- Modify: `backend/recommendation/candidate_filters.py`
- Test: `backend/tests/test_candidate_filters.py`

- [ ] **Step 1: Write the failing tests**

```python
from recommendation.candidate_filters import ensure_region_representation


def _c(wid, region, country="USA", score=1.0):
    return {"wine_id": wid, "store_ref": "s", "region": region, "country": country, "_score": score}


def test_representation_pins_missing_region():
    top = [_c("1", "Napa Valley", score=5), _c("2", "Sonoma", score=4)]
    scored = top + [_c("9", "Mendoza", "Argentina", score=1)]
    out = ensure_region_representation(top, scored, ["California", "Mendoza"], 12)
    assert any(c["wine_id"] == "9" for c in out)       # Mendoza pinned in


def test_representation_noop_when_both_present():
    top = [_c("1", "Napa Valley", score=5), _c("9", "Mendoza", "Argentina", score=4)]
    out = ensure_region_representation(top, top, ["Napa", "Mendoza"], 12)
    assert {c["wine_id"] for c in out} == {"1", "9"}


def test_representation_noop_single_region():
    top = [_c("1", "Napa Valley", score=5)]
    assert ensure_region_representation(top, top, ["California"], 12) == top


def test_representation_respects_cap_keeps_pinned():
    top = [_c(str(i), "Napa Valley", score=10 - i) for i in range(12)]   # full, all California
    scored = top + [_c("M", "Mendoza", "Argentina", score=0.5)]
    out = ensure_region_representation(top, scored, ["California", "Mendoza"], 12)
    assert len(out) == 12
    assert any(c["wine_id"] == "M" for c in out)        # Mendoza survives the cap
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py -k representation -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement the helper**

Add to `backend/recommendation/candidate_filters.py` (add `import unicodedata` at top if not present):

```python
def _norm_place(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


def _cand_in_place(cand: Dict[str, Any], nr: str) -> bool:
    reg = _norm_place(cand.get("region"))
    ctry = _norm_place(cand.get("country"))
    return bool((reg and (nr in reg or reg in nr)) or (ctry and (nr in ctry or ctry in nr)))


def ensure_region_representation(top: List[Dict[str, Any]], scored: List[Dict[str, Any]],
                                 regions: List[str], max_candidates: int) -> List[Dict[str, Any]]:
    """For a 2+ place comparison, guarantee `top` contains ≥1 candidate per named place.
    Pins each missing place's best-scoring candidate from `scored` (which is score-sorted
    desc); pinned candidates survive the `max_candidates` cap, the rest fill by score.
    No-op for <2 regions."""
    norm_regions = [_norm_place(r) for r in regions if r]
    if len(norm_regions) < 2:
        return top

    def key(c):
        return (c.get("wine_id"), c.get("store_ref"))

    present_ids = {key(c) for c in top}
    pinned = []
    for nr in norm_regions:
        if any(_cand_in_place(c, nr) for c in top) or any(_cand_in_place(p, nr) for p in pinned):
            continue
        best = next((c for c in scored if _cand_in_place(c, nr) and key(c) not in present_ids), None)
        if best is not None:
            pinned.append(best)
            present_ids.add(key(best))
    if not pinned:
        return top

    pinned_ids = {key(p) for p in pinned}
    others = [c for c in top if key(c) not in pinned_ids]
    others.sort(key=lambda c: c.get("_score", 0), reverse=True)
    return (pinned + others)[:max_candidates]
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py -k representation -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/candidate_filters.py backend/tests/test_candidate_filters.py
git commit -m "feat(recommend): ensure_region_representation for comparison queries"
```

---

### Task 4: Narrative — comparison directive

**Files:**
- Modify: `backend/recommendation/claude_client.py` (`_build_user_message`)
- Test: `backend/tests/test_claude_client.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_comparison_directive_present():
    msg = _build_user_message([{"wine_id": "1", "name": "X"}],
                              _intent(comparison_regions=["California", "Mendoza"]))
    assert "California" in msg and "Mendoza" in msg
    assert "one from each" in msg.lower()


def test_no_comparison_directive_when_absent():
    msg = _build_user_message([{"wine_id": "1", "name": "X"}], _intent())
    assert "one from each" not in msg.lower()
```

(`_intent` helper in this test file already accepts **kwargs into the intent dict; if not, pass `{**_intent(), "comparison_regions": [...]}`.)

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py -k comparison -v`
Expected: FAIL.

- [ ] **Step 3: Build + insert the directive**

In `_build_user_message`, after the `named_directive` block (~line 345) add:
```python
    comparison_directive = ""
    cmp_regions = intent.get("comparison_regions")
    if cmp_regions and len(cmp_regions) >= 2:
        joined = " vs ".join(cmp_regions)
        comparison_directive = (
            f"\n\nThe user is comparing wines from {joined} — recommend one from each so "
            "they can taste the difference side by side, drawing from the listings."
        )
```
Then add `f"{comparison_directive}"` into the `return (...)` assembly, right after `f"{named_directive}"`.

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/claude_client.py backend/tests/test_claude_client.py
git commit -m "feat(recommend): narrative directive for region comparison queries"
```

---

### Task 5: Wire into `recommend.py`

**Files:**
- Modify: `backend/api/routers/recommend.py` (`_targeted_rows`, `_score_and_select`, import, `comparison_regions` hint)

- [ ] **Step 1: Import the helper**

Add `ensure_region_representation` to the existing `recommendation.candidate_filters` import.

- [ ] **Step 2: `_targeted_rows` fetches each place separately**

Replace the current `_targeted_rows` body so it iterates `regions`:
```python
    def _targeted_rows() -> list:
        regions = resolved.get("regions") or (
            [resolved["region"]] if resolved.get("region") else [])
        if not regions and not detected_store:
            return []

        def _q(place: Optional[str], since: Optional[str]) -> list:
            q = (supabase.table("retail_inventory").select(INVENTORY_SELECT)
                 .in_("store_ref", nearby_ids).eq("in_stock", True)
                 .gte("price", req.budget_min).lte("price", req.budget_max))
            if place:
                q = q.or_(f"region.ilike.%{place}%,country.ilike.%{place}%",
                          reference_table="wines")
            if detected_store:
                q = q.eq("store_ref", detected_store["id"])
            if since:
                q = q.gte("last_scraped_at", since)
            return q.limit(300).execute().data or []

        rows: list = []
        for place in (regions or [None]):   # [None] → store-only fetch when no region
            rows.extend(_q(place, stale_cutoff) or _q(place, None))
        return rows
```

- [ ] **Step 3: Apply representation inside `_score_and_select`**

In `_score_and_select`, after `sel = _select_diverse_top(...)` and BEFORE the `if detected_store:` sort, add:
```python
        sel = ensure_region_representation(
            sel, scored, resolved.get("regions") or [], _MAX_CANDIDATES)
```

- [ ] **Step 4: Set the `comparison_regions` hint**

After `resolved = merge_intent(...)` and the other `resolved[...]` assignments (near where `resolved["message"]` is set), add:
```python
    _cmp = resolved.get("regions") or []
    resolved["comparison_regions"] = _cmp if len(_cmp) >= 2 else None
```

- [ ] **Step 5: Verify import + run the recommend-api + full fast suite**

Run:
```bash
cd backend && /usr/bin/python3 -c "import api.routers.recommend"
/usr/bin/python3 -m pytest tests/test_recommend_api.py tests/ -m "not integration" -q
```
Expected: import clean; suite passes.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/recommend.py
git commit -m "feat(recommend): per-place targeted fetch + region representation + comparison hint"
```

---

### Task 6: Acceptance replay + docs

**Files:**
- Create: `backend/scripts/verify_multi_region.py`
- Modify: `CLAUDE.md` (item 33 or a new note), `docs/reference/recommendation.md`

- [ ] **Step 1: Write the acceptance script**

Create `backend/scripts/verify_multi_region.py`:
```python
"""Acceptance: a California-vs-Mendoza comparison surfaces BOTH regions.
Run from backend/: /usr/bin/python3 -m scripts.verify_multi_region"""
from db import get_supabase_client
from recommendation.intent import parse_message, merge_intent, intent_from_request
from recommendation.scorer import score_candidates
from recommendation.candidate_filters import ensure_region_representation, _cand_in_place
from utils.geo import find_nearby_store_ids

ZIP = "78209"
SEL = ("price, wine_id, wines!inner(id, name, varietal, region, country, wine_type, "
       "grapes, image_url, vivino_rating, vivino_ratings_count)")


def main():
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(ZIP, sb)
    parsed = parse_message("a cab from California vs a Mendoza one, recommend two to try")
    intent = merge_intent(parsed, intent_from_request(
        wine_type="red", style_preferences=[], avoid=[], budget_min=10.0, budget_max=50.0))
    print("regions parsed:", intent.get("regions"))
    assert len(intent.get("regions") or []) >= 2, "expected 2 regions parsed"

    cands = []
    for place in intent["regions"]:
        rows = (sb.table("retail_inventory").select(SEL).in_("store_ref", nearby)
                .eq("in_stock", True).gte("price", 10).lte("price", 50)
                .or_(f"region.ilike.%{place}%,country.ilike.%{place}%", reference_table="wines")
                .limit(300).execute().data or [])
        for r in rows:
            w = r["wines"]
            cands.append({"wine_id": w["id"], "store_ref": "s", "name": w["name"],
                          "varietal": w.get("varietal"), "region": w.get("region"),
                          "country": w.get("country"), "wine_type": w.get("wine_type"),
                          "grapes": w.get("grapes") or [], "price": r["price"]})
    scored = score_candidates(intent, cands)
    top = ensure_region_representation(scored[:12], scored, intent["regions"], 12)
    for nr in [r.lower() for r in intent["regions"]]:
        n = sum(1 for c in top if _cand_in_place(c, nr))
        print(f"  top-12 candidates matching {nr!r}: {n}")
        assert n >= 1, f"no representation for {nr}"
    print("OK — both regions represented in the top-12")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `cd backend && /usr/bin/python3 -m scripts.verify_multi_region 2>&1 | grep -vE "NotOpenSSL|warnings.warn"`
Expected: prints `regions parsed: ['California', 'Mendoza']`, ≥1 for each, `OK — both regions represented`.

- [ ] **Step 3: Update docs**

- `docs/reference/recommendation.md`: add a "Multi-region comparison" subsection (regions list in intent, per-place targeted fetch, scorer credits any, `ensure_region_representation`, comparison narrative directive).
- `CLAUDE.md`: add a one-line note under the recommender items that comparison/multi-region queries are handled (2026-07-23).

- [ ] **Step 4: Run the full fast suite once more**

Run: `cd backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/verify_multi_region.py CLAUDE.md docs/reference/recommendation.md
git commit -m "test+docs: multi-region comparison acceptance + reference"
```

---

## Self-Review Notes

- **Spec coverage:** §1 intent→T1; §2 fetch→T5; §3 scorer→T2; §4 selection→T3+T5; §5 narrative→T4; §6 testing→each + T6. All covered.
- **Type consistency:** `regions` list + `region` scalar kept in sync (T1). `want_regions` (T2). `ensure_region_representation(top, scored, regions, max)` identical in T3 def, T5 call, T6 acceptance. `comparison_regions` set in T5, read in T4.
- **Back-compat:** scalar `region` still populated (T1) so `deep_fetch_reason`/logging unaffected; scorer falls back to `[region]` when `regions` empty, so existing single-region tests pass.
- **Representation ordering:** `_score_and_select` applies representation BEFORE the `detected_store` sort, so a named-store query still surfaces that store first while keeping both regions present.
