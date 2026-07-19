# Recommender Country + Fortified Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make fortified wines reachable via a "dessert" request, and make compound country+type queries ("white from Argentina") deterministically surface by matching the intent's place against region OR country in both the fetch and the scorer.

**Architecture:** Three small edits — one to a pure helper (`requested_types_from`), one to the scorer's region boost, one to the recommender's targeted-fetch filter — plus an acceptance gate replaying the two live failures. No schema or frontend change.

**Tech Stack:** Python 3.9 (`Optional[...]`, never `str | None`), pytest, supabase-py. Commands from `backend/` with `/usr/bin/python3`.

**Spec:** `docs/superpowers/specs/2026-07-18-recommender-country-fortified-fixes-design.md`

---

## Reference: current-code anchors

- `recommendation/candidate_filters.py` — `requested_types_from(chip_types, parsed_type)`:
  ```python
  types = set(t for t in (chip_types or []) if t)
  if parsed_type:
      types.add(parsed_type)
  return types
  ```
- `recommendation/scorer.py:133` — `region = _norm(wine.get("region"))` (inside the candidate loop; `_norm` already imported). `:155-156`:
  ```python
          if want_region and region and (want_region in region or region in want_region):
              score += _W_REGION
  ```
- `api/routers/recommend.py:376` — `q = q.ilike("wines.region", f"%{region}%")` (inside `_targeted_rows`; `region = resolved.get("region")`; `INVENTORY_SELECT` uses `wines!inner(...)` so embedded-column filters apply; the postgrest `or_` kwarg is `reference_table`, confirmed).
- Baseline fast suite: **582 passed, 3 deselected.**

---

### Task 1: Fold `fortified` into `dessert` requests

**Files:**
- Modify: `backend/recommendation/candidate_filters.py`
- Test: `backend/tests/test_candidate_filters.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_dessert_request_also_accepts_fortified():
    """The intent enum can't express 'fortified' (only 'dessert'), so a
    dessert/after-dinner request must also surface Port/Sherry (item 30 typed
    them fortified). One-directional: fortified requests stay strict."""
    assert requested_types_from(["dessert"], None) == {"dessert", "fortified"}
    assert requested_types_from([], "dessert") == {"dessert", "fortified"}
    assert requested_types_from(["red"], None) == {"red"}
    assert requested_types_from(["fortified"], None) == {"fortified"}   # no reverse fold
    assert requested_types_from([], None) == set()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py -k dessert_request_also -v`
Expected: FAIL — `{"dessert"}` != `{"dessert","fortified"}`.

- [ ] **Step 3: Implement** — in `requested_types_from`, add the fold just before `return`:

```python
def requested_types_from(chip_types: Optional[List[str]],
                         parsed_type: Optional[str]) -> set:
    """The set of wine types the user explicitly asked for — UI chips plus the
    parsed message intent. 'dessert' also accepts 'fortified' (the intent enum
    has no fortified value, so Port/Sherry — typed fortified — surface under a
    dessert/after-dinner ask). One-directional."""
    types = set(t for t in (chip_types or []) if t)
    if parsed_type:
        types.add(parsed_type)
    if "dessert" in types:
        types.add("fortified")
    return types
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py -v`
Expected: ALL PASS (the fold is additive; existing type-gate tests unaffected since none request dessert).

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/candidate_filters.py backend/tests/test_candidate_filters.py
git commit -m "feat: dessert requests also surface fortified (Port/Sherry) — enum has no fortified value"
```

---

### Task 2: Scorer region boost credits country

**Files:**
- Modify: `backend/recommendation/scorer.py`
- Test: `backend/tests/test_scorer.py`

- [ ] **Step 1: Write the failing test** (append; loser-first so a stable-sort tie can't fake the pass)

```python
def test_region_intent_boosts_a_wine_matched_by_country():
    """The intent parser puts a country ('Argentina') in the region field, but
    wines are stored region=Mendoza / country=Argentina. The region boost must
    credit a country match so 'from Argentina' ranks Argentine wines up."""
    other = _wine("Chilean White", wine_type="white", varietal="Sauvignon Blanc",
                  region="Casablanca Valley", country="Chile")
    argentine = _wine("Mendoza White", wine_type="white", varietal="Torrontés",
                      region="Mendoza", country="Argentina")
    result = score_candidates(_intent(wine_type="white", region="Argentina"),
                              [other, argentine])
    assert result[0]["name"] == "Mendoza White"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_scorer.py -k region_intent_boosts_a_wine_matched_by_country -v`
Expected: FAIL — the Argentine wine gets no region boost (region "mendoza" ∌ "argentina"), so it doesn't lead.

- [ ] **Step 3: Implement** — in `scorer.py`, right after `region = _norm(wine.get("region"))` (line 133) add:

```python
        country = _norm(wine.get("country"))
```

and change the region-boost condition (lines 155-156) to also match country:

```python
        if want_region and (
                (region and (want_region in region or region in want_region))
                or (country and (want_region in country or country in want_region))):
            score += _W_REGION
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_scorer.py -v`
Expected: ALL PASS. (Additive — a region intent that used to match only region now also matches country; no existing test asserts a country intent is *ignored*.)

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/scorer.py backend/tests/test_scorer.py
git commit -m "feat: scorer region boost also credits a country match (region intent holds a country)"
```

---

### Task 3: Targeted fetch matches region OR country

**Files:**
- Modify: `backend/api/routers/recommend.py`
- Test: verified by the acceptance gate (Task 4); the endpoint is exercised by the mocked `test_recommend_api.py`.

- [ ] **Step 1: Implement** — in `_targeted_rows` (recommend.py), replace the region filter line:

```python
                q = q.ilike("wines.region", f"%{region}%")
```

with a region-OR-country match:

```python
                q = q.or_(f"region.ilike.%{region}%,country.ilike.%{region}%",
                          reference_table="wines")
```

(The intent's `region` value may be a country — "Argentina" — so match it against both columns. `reference_table` is the confirmed postgrest kwarg; `wines!inner` in `INVENTORY_SELECT` makes the embedded filter apply.)

- [ ] **Step 2: Verify import + recommend API suite**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -c "import api.routers.recommend" && /usr/bin/python3 -m pytest tests/test_recommend_api.py -v`
Expected: import clean; ALL PASS. (The mock's chained `.or_` returns self — already stubbed for the breadth filter — so the targeted `.or_` works against the mock; the single mocked row's behavior is unchanged.)

- [ ] **Step 3: Commit**

```bash
git add backend/api/routers/recommend.py
git commit -m "feat: targeted fetch matches intent place against region OR country (fixes country queries)"
```

---

### Task 4: Acceptance gate — replay both live failures (controller runs)

- [ ] **Step 1: Full fast suite**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q`
Expected: ALL PASS (582 + the new tests).

- [ ] **Step 2: DB-level acceptance — country query (white from Argentina)**

```bash
cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -c "
from db import get_service_client
from utils.geo import find_nearby_store_ids, zip_to_centroid
from recommendation.scorer import score_candidates
from recommendation.candidate_filters import apply_type_gate, requested_types_from
db=get_service_client(); ZIP='78209'
nearby=find_nearby_store_ids(ZIP, db, centroid=zip_to_centroid(ZIP))
INV='price,wine_id,stores!inner(id),wines!inner(id,name,wine_type,varietal,region,country,grapes)'
# targeted region-OR-country fetch for Argentina
rows=db.table('retail_inventory').select(INV).in_('store_ref',nearby).eq('in_stock',True).gte('price',0).lte('price',60).or_('region.ilike.%Argentina%,country.ilike.%Argentina%', reference_table='wines').limit(300).execute().data
cands=[{'wine_id':r['wines']['id'],'name':r['wines']['name'],'varietal':r['wines']['varietal'],'region':r['wines']['region'],'country':r['wines']['country'],'wine_type':r['wines']['wine_type'],'grapes':r['wines']['grapes'] or [],'price':r['price'],'tier':2,'flavor_profile':[]} for r in rows]
gated=apply_type_gate(cands, {'white'})
intent={'wine_type':'white','body':None,'flavors':[],'grapes':[],'region':'Argentina','avoid':[],'budget_min':0.0,'budget_max':60.0}
scored=score_candidates(intent, gated)
print(f'targeted region-OR-country Argentina: {len(cands)} rows | white after gate: {len(gated)}')
for c in scored[:6]: print(f\"  {c['wine_type']:6} {c['country']:10} {c['name'][:40]}\")
"
```

Expected: the targeted fetch now returns the Mendoza/Salta whites (country=Argentina), the gate keeps the whites, and the scorer ranks them — the sweep's `white+Argentina` 0 → several.

- [ ] **Step 3: DB-level acceptance — dessert request surfaces fortified**

```bash
cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -c "
from recommendation.candidate_filters import requested_types_from, apply_type_gate
req = requested_types_from(['dessert'], 'dessert')
print('dessert request resolves to types:', sorted(req))
port = {'wine_id':'p','name':'Grahams Six Grapes Port','wine_type':'fortified','varietal':'Touriga Nacional','grapes':['Touriga Nacional']}
kept = apply_type_gate([port], req)
print('Port kept under dessert request:', bool(kept))
"
```

Expected: `['dessert', 'fortified']`; Port kept True (the sweep's fortified 0 → surfaces).

- [ ] **Step 4: Regression spot-check** — re-run the sweep harness (`<scratchpad>/somm_sweep.py`) if present, or a quick check that `white+Bordeaux` / `red+Napa` still surface (region-based targeting unaffected). Record results.

---

### Task 5: Docs

**Files:**
- Modify: `CLAUDE.md` (item 33), `docs/reference/recommendation.md`

- [ ] **Step 1: Update docs**
- `CLAUDE.md` item 33: flip `✅→⚙️` to `✅`, note DONE — dessert requests fold in fortified; targeted fetch + scorer match place against region OR country; verified the sweep's `white+Argentina` and dessert→Port failures resolve. Keep the "second sweep (flavor/avoid/body)" as the REMAINING follow-up.
- `docs/reference/recommendation.md`: document the country-OR-region matching (targeted fetch + scorer) and the dessert→fortified request fold.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md docs/reference/recommendation.md
git commit -m "docs: recommender country-aware matching + fortified-via-dessert landed"
```
