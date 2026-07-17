# Intent-Aware Candidate Fetch + Wine-Type Guarantee Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the recommender fetch guarantee that intent-relevant wines (named region/store) reach the candidate pool, and make wine_type a hard guarantee (a red request never surfaces a white, while mis-typed NULL reds are kept).

**Architecture:** Pure, unit-tested helpers in a new `recommendation/candidate_filters.py` (type resolution, type gate, fuzzy store detection, candidate merge/dedup) wired into `api/routers/recommend.py`, plus a small targeted DB query that bypasses the unordered 500-row breadth sample. Correctness is guaranteed at *selection* (the type gate) so it never depends on the deferred NULL-wine_type backfill.

**Tech Stack:** Python 3.9 (`Optional[...]`, never `str | None`), pytest, supabase-py/postgrest, `difflib` (stdlib). Commands run from `backend/` with `/usr/bin/python3`.

**Spec:** `docs/superpowers/specs/2026-07-17-intent-aware-fetch-design.md`

---

## Reference: current-code anchors

- `api/routers/recommend.py:26-27` — `_MAX_CANDIDATES = 12`, `_FETCH_PER_RETAILER = 500`.
- `recommend.py:98-104` — `INVENTORY_SELECT` (nested `wines(...)` — a left join).
- `recommend.py:234-253` — `_fetch_rows`/`_query` (the unordered per-retailer 500 fetch).
- `recommend.py:280-314` — candidate-build loop (flattens rows → candidate dicts; `store_name`, `store_ref`, `wine_type` set here).
- `recommend.py:353-365` — existing `_detect_retailer` filter, then the raw `effective_types` type filter (drops NULL-type wines; **this is what Task 3 replaces**).
- `recommend.py:369-373` — `score_candidates(...)` + jitter + `_select_diverse_top`.
- `recommendation/scorer.py:142` — `if want_type and wine.get("wine_type") == want_type: score += _W_TYPE` (unchanged — works once NULL types are resolved-and-written-back in Task 3).
- `utils/__init__.py:24` — `infer_wine_type(text) -> Optional[str]` (resolves "Red Wine"/varietal → red/white/rosé/sparkling/orange/fortified/dessert or None).
- Baselines: fast suite currently **539 passed, 3 deselected**. Run tests: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/<file> -v` (fast suite: `tests/ -m "not integration" -q`).
- Failing query to fix: zip `78209`, red, ≤$45, "Show me one Bordeaux blend at heb lincon heights". The three in-stock Lincoln Heights (store UUID `f557447f-64be-4e7e-b4f1-5b865377bf21`) red Bordeaux blends: Les Allies Médoc ($11.68, `wine_type=red`), Château Lasségue Saint-Émilion ($35.99, `wine_type=red`), Château Saint-Sulpice ($14.38, **`wine_type=None`**).

---

### Task 1: `resolve_wine_type` — infer NULL type from varietal→name→grape

**Files:**
- Create: `backend/recommendation/candidate_filters.py`
- Test: `backend/tests/test_candidate_filters.py` (new)

- [ ] **Step 1: Write the failing test** — create `backend/tests/test_candidate_filters.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.candidate_filters import resolve_wine_type


def test_resolve_uses_existing_type_first():
    assert resolve_wine_type({"wine_type": "red", "name": "White Zin", "varietal": None}) == "red"


def test_resolve_infers_red_from_name_when_type_null():
    # Château Saint-Sulpice: NULL type, name says 'Bordeaux Red Wine'
    w = {"wine_type": None, "varietal": "Red Blend", "name": "Chateau Saint-Sulpice Bordeaux Red Wine",
         "grapes": ["Merlot", "Cabernet Sauvignon"]}
    assert resolve_wine_type(w) == "red"


def test_resolve_infers_white_from_varietal():
    w = {"wine_type": None, "varietal": "Sauvignon Blanc", "name": "Dourthe Bordeaux", "grapes": ["Sauvignon Blanc"]}
    assert resolve_wine_type(w) == "white"


def test_resolve_prefers_varietal_over_name():
    # generic varietal 'Red Blend' -> red even if name has no color word
    w = {"wine_type": None, "varietal": "Merlot", "name": "Chateau Rouget Pomerol", "grapes": []}
    assert resolve_wine_type(w) == "red"


def test_resolve_returns_none_when_unresolvable():
    w = {"wine_type": None, "varietal": None, "name": "Chateau Mystere 2019", "grapes": []}
    assert resolve_wine_type(w) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement** — create `backend/recommendation/candidate_filters.py`:

```python
"""Pure candidate-shaping helpers for the recommend endpoint: NULL wine_type
resolution + hard type gate, fuzzy store detection, and candidate merge/dedup.
Kept free of I/O so they unit-test without a DB (the router wires them)."""
import difflib
import re
from typing import Any, Dict, List, Optional

from utils import infer_wine_type


def resolve_wine_type(wine: Dict[str, Any]) -> Optional[str]:
    """Return the wine's type, inferring from varietal -> name -> first grape
    when the stored wine_type is NULL. None only when nothing resolves."""
    if wine.get("wine_type"):
        return wine["wine_type"]
    for text in (wine.get("varietal"), wine.get("name"),
                 (wine.get("grapes") or [None])[0]):
        if text:
            t = infer_wine_type(text)
            if t:
                return t
    return None
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/candidate_filters.py backend/tests/test_candidate_filters.py
git commit -m "feat: resolve_wine_type — infer NULL wine_type from varietal/name/grape"
```

---

### Task 2: `apply_type_gate` — write back resolved type + hard-exclude conflicts

**Files:**
- Modify: `backend/recommendation/candidate_filters.py`
- Test: `backend/tests/test_candidate_filters.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
from recommendation.candidate_filters import apply_type_gate


def _c(**kw):
    base = {"wine_id": "x", "name": "W", "varietal": None, "grapes": [], "wine_type": None}
    base.update(kw); return base


def test_gate_keeps_resolved_red_drops_resolved_white_for_red_request():
    red = _c(wine_type="red", name="Malbec")
    mistyped_red = _c(wine_type=None, varietal="Red Blend", name="Bordeaux Red Wine")
    white = _c(wine_type="white", varietal="Sauvignon Blanc")
    out = apply_type_gate([red, mistyped_red, white], {"red"})
    ids_types = [c["wine_type"] for c in out]
    assert white not in out
    assert red in out and mistyped_red in out
    # resolved type written back onto the mistyped red so the scorer boost fires
    assert mistyped_red["wine_type"] == "red"


def test_gate_keeps_unresolvable_null_benefit_of_doubt():
    unknown = _c(wine_type=None, name="Chateau Mystere 2019")
    out = apply_type_gate([unknown], {"red"})
    assert unknown in out and unknown["wine_type"] is None


def test_gate_noop_when_no_requested_types():
    white = _c(wine_type="white", varietal="Chardonnay")
    assert apply_type_gate([white], set()) == [white]


def test_gate_fails_open_when_it_would_empty_the_pool():
    # only whites available but user asked red -> return the pool rather than blank
    whites = [_c(wine_type="white", varietal="Chardonnay"), _c(wine_type="white", varietal="Riesling")]
    assert apply_type_gate(whites, {"red"}) == whites
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py -k gate -v`
Expected: FAIL — `apply_type_gate` not defined.

- [ ] **Step 3: Implement** — append to `candidate_filters.py`:

```python
def apply_type_gate(candidates: List[Dict[str, Any]],
                    requested_types: set) -> List[Dict[str, Any]]:
    """Resolve each candidate's NULL wine_type (written back in place), then, when
    the user requested one or more types, drop candidates whose resolved type is
    KNOWN and not requested. Unresolvable (None) types are kept — benefit of the
    doubt. Fails open (returns the input) if the gate would empty the pool."""
    for c in candidates:
        if not c.get("wine_type"):
            c["wine_type"] = resolve_wine_type(c)
    if not requested_types:
        return candidates
    kept = [c for c in candidates
            if c.get("wine_type") is None or c["wine_type"] in requested_types]
    return kept or candidates
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py -v`
Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/candidate_filters.py backend/tests/test_candidate_filters.py
git commit -m "feat: apply_type_gate — resolved-type hard gate, keeps mistyped reds, fails open"
```

---

### Task 3: Wire the type gate into recommend.py (replace the raw type filter)

**Files:**
- Modify: `backend/recommendation/candidate_filters.py` (add `requested_types` helper), `api/routers/recommend.py:360-365`
- Test: `backend/tests/test_candidate_filters.py`

- [ ] **Step 1: Write the failing test** for the requested-types resolver (append)

```python
from recommendation.candidate_filters import requested_types_from


def test_requested_types_union_of_chips_and_parsed_intent():
    assert requested_types_from(["red"], None) == {"red"}
    assert requested_types_from([], "white") == {"white"}
    assert requested_types_from(["red"], "red") == {"red"}
    assert requested_types_from([], None) == set()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py -k requested_types -v`
Expected: FAIL — not defined.

- [ ] **Step 3: Implement**

Append to `candidate_filters.py`:

```python
def requested_types_from(chip_types: Optional[List[str]],
                         parsed_type: Optional[str]) -> set:
    """The set of wine types the user explicitly asked for — UI chips plus the
    parsed message intent."""
    types = set(t for t in (chip_types or []) if t)
    if parsed_type:
        types.add(parsed_type)
    return types
```

In `api/routers/recommend.py`, add to the imports near the other `recommendation` imports:

```python
from recommendation.candidate_filters import (apply_type_gate,
                                              requested_types_from)
```

Replace the raw type filter block (currently at ~lines 360-365):

```python
    effective_types = req.wine_types or ([req.wine_type] if req.wine_type else [])
    if effective_types:
        type_pool = [c for c in candidates if c.get("wine_type") in effective_types]
        if type_pool:
            candidates = type_pool
            logger.info("TYPE FILTER | %s → %d candidates", effective_types, len(candidates))
```

with:

```python
    chip_types = req.wine_types or ([req.wine_type] if req.wine_type else [])
    req_types = requested_types_from(chip_types, resolved.get("wine_type"))
    before = len(candidates)
    candidates = apply_type_gate(candidates, req_types)
    if req_types:
        logger.info("TYPE GATE | %s → %d/%d candidates", sorted(req_types), len(candidates), before)
```

- [ ] **Step 4: Run tests** (the pure helper + existing recommend API suite — the gate now resolves NULL types, so nothing that had a real type regresses)

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py tests/test_recommend_api.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/candidate_filters.py backend/tests/test_candidate_filters.py api/routers/recommend.py
git commit -m "feat: recommend uses resolved-type gate (keeps mistyped reds, never surfaces wrong type)"
```

---

### Task 4: `detect_store` — fuzzy match a named store against nearby stores

**Files:**
- Modify: `backend/recommendation/candidate_filters.py`
- Test: `backend/tests/test_candidate_filters.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
from recommendation.candidate_filters import detect_store

_NEARBY = [
    {"id": "s1", "name": "Lincoln Heights Market H-E-B"},
    {"id": "s2", "name": "Alon Market H-E-B"},
    {"id": "s3", "name": "Geraldine's Natural Wines"},
]


def test_detect_store_tolerates_typo():
    assert detect_store("show me a bordeaux at heb lincon heights", _NEARBY)["id"] == "s1"


def test_detect_store_exact_multiword():
    assert detect_store("anything at Alon Market", _NEARBY)["id"] == "s2"


def test_detect_store_none_when_no_store_named():
    assert detect_store("show me a bold red under $30", _NEARBY) is None


def test_detect_store_ignores_generic_retailer_word_only():
    # 'heb' alone is the retailer, not a store — must not match a specific store
    assert detect_store("something red at heb", _NEARBY) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py -k detect_store -v`
Expected: FAIL — not defined.

- [ ] **Step 3: Implement** — append to `candidate_filters.py`:

```python
# Generic tokens that don't distinguish one store from another.
_STORE_STOPWORDS = {"the", "and", "wine", "wines", "market", "shop", "store",
                    "plus", "natural", "heb", "h-e-b", "heb's", "central"}


def _store_tokens(s: str) -> List[str]:
    words = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split()
    return [w for w in words if len(w) > 2 and w not in _STORE_STOPWORDS]


def detect_store(message: str, nearby_stores: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Fuzzy-match a store named in the message against the nearby stores.
    Tolerates typos ('lincon'); returns None when no distinctive store token
    matches (e.g. only the retailer word 'heb' appears)."""
    msg = _store_tokens(message)
    if not msg:
        return None
    best, best_score = None, 0
    for st in nearby_stores:
        name_toks = _store_tokens(st.get("name", ""))
        score = sum(1 for nt in name_toks
                    if difflib.get_close_matches(nt, msg, n=1, cutoff=0.8))
        if score > best_score:
            best, best_score = st, score
    return best if best_score >= 1 else None
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py -v`
Expected: ALL PASS (17 total).

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/candidate_filters.py backend/tests/test_candidate_filters.py
git commit -m "feat: detect_store — typo-tolerant fuzzy match of a named store to nearby stores"
```

---

### Task 5: `merge_candidates` — dedup breadth + targeted rows

**Files:**
- Modify: `backend/recommendation/candidate_filters.py`
- Test: `backend/tests/test_candidate_filters.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
from recommendation.candidate_filters import merge_candidates


def test_merge_dedups_by_wine_and_store():
    a = {"wine_id": "w1", "store_ref": "s1", "name": "A"}
    b = {"wine_id": "w2", "store_ref": "s1", "name": "B"}
    dup_a = {"wine_id": "w1", "store_ref": "s1", "name": "A"}
    out = merge_candidates([a, b], [dup_a])
    assert len(out) == 2


def test_merge_adds_targeted_rows_absent_from_breadth():
    breadth = [{"wine_id": "w1", "store_ref": "s1"}]
    targeted = [{"wine_id": "w9", "store_ref": "s1"}]   # the Bordeaux that missed the 500 sample
    out = merge_candidates(breadth, targeted)
    assert {c["wine_id"] for c in out} == {"w1", "w9"}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py -k merge -v`
Expected: FAIL — not defined.

- [ ] **Step 3: Implement** — append to `candidate_filters.py`:

```python
def merge_candidates(breadth: List[Dict[str, Any]],
                     targeted: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Union breadth + targeted candidate dicts, deduped by (wine_id, store_ref)."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for c in list(breadth) + list(targeted):
        key = (c.get("wine_id"), c.get("store_ref"))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py -v`
Expected: ALL PASS (19 total).

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/candidate_filters.py backend/tests/test_candidate_filters.py
git commit -m "feat: merge_candidates — dedup breadth + targeted rows by (wine_id, store_ref)"
```

---

### Task 6: Targeted relevance fetch + store boost in recommend.py

**Files:**
- Modify: `api/routers/recommend.py`
- Test: verified by the acceptance gate (Task 8); light mock test optional.

Context: after the breadth pool is built into `by_retailer`/`candidates` (recommend.py ~line 314) and the parsed `resolved` intent + `nearby_ids`/`stores_meta` exist, add a targeted fetch keyed on `resolved["region"]` and any `detect_store` hit, build those rows into candidate dicts with the **same shape** as the breadth loop, and merge.

- [ ] **Step 1: Implement the targeted fetch + store detection + boost**

Add import (with the Task 3 import):

```python
from recommendation.candidate_filters import (apply_type_gate, detect_store,
                                              merge_candidates, requested_types_from)
```

Factor the breadth loop's row→candidate mapping into a local helper so the targeted rows reuse it. Just above the `by_retailer` loop (~line 280), define:

```python
    def _row_to_candidate(row: dict) -> Optional[dict]:
        wine = row.get("wines") or {}
        if not wine:
            return None
        details_raw = wine.get("wine_details") or {}
        details = details_raw[0] if isinstance(details_raw, list) else (details_raw if isinstance(details_raw, dict) else {})
        enriched = bool(details.get("grapeminds_enriched_at"))
        has_extract = bool(wine.get("varietal") or wine.get("region"))
        if not enriched and not has_extract:
            return None
        store = row.get("stores") or {}
        slat, slon = store.get("latitude"), store.get("longitude")
        distance_miles = (
            round(haversine(centroid[0], centroid[1], float(slat), float(slon)), 1)
            if slat is not None and slon is not None else None
        )
        return {
            "wine_id": wine.get("id"), "name": wine.get("name"),
            "varietal": wine.get("varietal"), "region": wine.get("region"),
            "country": wine.get("country"), "wine_type": wine.get("wine_type"),
            "grapes": wine.get("grapes") or [], "body": wine.get("body"),
            "tasting_notes": details.get("tasting_notes"),
            "flavor_profile": details.get("flavor_profile") or [],
            "structure_profile": details.get("structure_profile") or {},
            "price": row.get("price"), "retailer": store.get("retailer_name") or "unknown",
            "store_address": store.get("address") or None,
            "store_name": store.get("name") or None, "store_ref": store.get("id"),
            "distance_miles": distance_miles, "image_url": wine.get("image_url"),
            "vivino_rating": wine.get("vivino_rating"),
            "vivino_ratings_count": wine.get("vivino_ratings_count"),
            "tier": 1 if enriched else 2,
        }
```

Rewrite the existing `by_retailer` build loop to use it (replace the inline dict construction body with):

```python
    by_retailer: dict = {}
    for row in raw_rows:
        cand = _row_to_candidate(row)
        if cand is None:
            continue
        by_retailer.setdefault(cand["retailer"], []).append(cand)
```

After `candidates` is assembled from `by_retailer` and after `resolved` is computed (place this just before the `_detect_retailer` block at ~line 353), add the targeted fetch:

```python
    detected_store = detect_store(req.message, stores_meta.data or [])

    def _targeted_rows() -> list:
        q = (supabase.table("retail_inventory").select(INVENTORY_SELECT)
             .in_("store_ref", nearby_ids).eq("in_stock", True)
             .gte("price", req.budget_min).lte("price", req.budget_max))
        region = resolved.get("region")
        if region:
            q = q.ilike("wines.region", f"%{region}%")
        if detected_store:
            q = q.eq("store_ref", detected_store["id"])
        if not region and not detected_store:
            return []
        return q.limit(300).execute().data or []

    targeted = [c for c in (_row_to_candidate(r) for r in _targeted_rows()) if c]
    if targeted:
        candidates = merge_candidates(candidates, targeted)
        logger.info("TARGETED FETCH | region=%r store=%r → +%d rows",
                    resolved.get("region"), detected_store and detected_store["name"], len(targeted))
```

Note: `INVENTORY_SELECT` becomes `wines!inner(...)` in Task 7, which is what makes `.ilike("wines.region", ...)` filter correctly; until then the ilike on a left-joined embedded column is ignored by postgrest, so **Task 7 must land for the region filter to bite** (the store filter works regardless). Order Task 7 immediately after this task.

After `_select_diverse_top` produces `top` (~line 373), boost the detected store so its wines lead — insert before `_annotate_price_drops(supabase, top)`:

```python
    if detected_store:
        top.sort(key=lambda w: (w.get("store_ref") == detected_store["id"],
                                w.get("_score", 0)), reverse=True)
```

- [ ] **Step 2: Smoke-test the endpoint import + existing suite**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -c "import api.routers.recommend" && /usr/bin/python3 -m pytest tests/test_recommend_api.py -v`
Expected: import OK; recommend API tests PASS (the mock returns a single row; targeted fetch adds nothing new; `_row_to_candidate` refactor is behavior-preserving).

- [ ] **Step 3: Commit**

```bash
git add api/routers/recommend.py
git commit -m "feat: targeted relevance fetch (region/store) + store boost — bypasses the 500-row sample"
```

---

### Task 7: Type-aware breadth fetch (`wines!inner` + type-or-null filter)

**Files:**
- Modify: `api/routers/recommend.py` (`INVENTORY_SELECT`, `_query`)
- Test: `backend/tests/test_recommend_api.py` (assert the query builder is called with the type filter)

- [ ] **Step 1: Write the failing test** — append to `test_recommend_api.py` a test that patches the supabase client and asserts an `or_`/type filter is applied when a wine_type is requested. Add near the other tests:

```python
def test_breadth_fetch_filters_by_requested_type(monkeypatch):
    """When the request carries wine_type=red, the inventory query must constrain
    to red-or-null so the 500-row budget isn't spent on whites."""
    from api.routers import recommend as rec
    calls = {"or_": []}

    class _Q:
        def select(self, *a, **k): return self
        def in_(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def gte(self, *a, **k): return self
        def lte(self, *a, **k): return self
        def ilike(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def or_(self, *a, **k):
            calls["or_"].append((a, k)); return self
        def execute(self):
            from types import SimpleNamespace
            return SimpleNamespace(data=[])

    class _DB:
        def table(self, *a, **k): return _Q()

    # exercise just the query builder path
    rec._apply_type_breadth_filter  # symbol must exist
    q = rec._apply_type_breadth_filter(_Q(), {"red"})
    q.execute()
    assert calls["or_"], "expected an or_() type-or-null filter for a typed request"
    args = calls["or_"][0][0][0]
    assert "wine_type.eq.red" in args and "wine_type.is.null" in args
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_recommend_api.py -k breadth_fetch -v`
Expected: FAIL — `_apply_type_breadth_filter` not defined.

- [ ] **Step 3: Implement**

Change `INVENTORY_SELECT` (recommend.py:98-104): replace `"wines(id, name, ...)"` with `"wines!inner(id, name, ...)"` (inner join — a retail_inventory row with no wine is useless, and the inner join is required to filter on wine columns). Keep all selected columns identical.

Add a module-level helper (near `_query`) and call it from `_query`:

```python
def _apply_type_breadth_filter(q, requested_types: set):
    """Constrain a breadth inventory query to the requested wine types OR NULL
    (NULL kept so mis-typed reds survive; the type gate resolves them later)."""
    if not requested_types:
        return q
    ors = ",".join(f"wine_type.eq.{t}" for t in sorted(requested_types))
    return q.or_(f"{ors},wine_type.is.null", reference_table="wines")
```

Thread `requested_types` into `_fetch_rows`/`_query`. Compute `req_types` (via `requested_types_from(chip_types, resolved.get("wine_type"))`) BEFORE `_fetch_rows` is called, and inside `_query` add `q = _apply_type_breadth_filter(q, req_types)` just before `if since:`. (Move the `chip_types`/`req_types` computation up so it's available to both the fetch and the Task 3 gate; the gate keeps using the same `req_types`.)

- [ ] **Step 4: Run tests**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_recommend_api.py -v`
Expected: ALL PASS. If the supabase-py version rejects `reference_table=`, use `referenced_table=` — verify with `/usr/bin/python3 -c "import inspect,postgrest; print(inspect.signature(postgrest._sync.request_builder.SyncFilterRequestBuilder.or_))"` and match the kwarg name.

- [ ] **Step 5: Commit**

```bash
git add api/routers/recommend.py backend/tests/test_recommend_api.py
git commit -m "feat: type-aware breadth fetch — wines!inner + wine_type-or-null filter"
```

---

### Task 8: Claude absence-hedging prompt

**Files:**
- Modify: `backend/recommendation/claude_client.py` (the system-prompt lines ~131 about no match)

- [ ] **Step 1: Update the prompt**

In `claude_client.py`, find the guidance line (currently ~line 131):

```
- If no perfect match exists, say so directly and offer the closest available alternative.
```

Replace with (scopes absence to what was provided, not the whole store):

```
- The wines listed are what surfaced for this search near the user — not the store's entire shelf. If nothing fits, say what you *can* see doesn't match ("nothing matching that turned up nearby") and offer the closest alternative; never claim a wine or style is absent from a store's full inventory.
```

- [ ] **Step 2: Verify the prompt still builds + suite green**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_claude_client.py tests/test_recommend_api.py -q`
Expected: PASS (prompt is a string; no structural change).

- [ ] **Step 3: Commit**

```bash
git add backend/recommendation/claude_client.py
git commit -m "feat: Somm hedges absence to the surfaced set, never claims whole-inventory absence"
```

---

### Task 9: Acceptance gate — replay the failing query end-to-end (controller runs)

- [ ] **Step 1: Full fast suite**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q`
Expected: ALL PASS (baseline 539 + the new candidate_filters + recommend tests).

- [ ] **Step 2: Verify the targeted fetch surfaces the Bordeaux (DB, no Claude)**

```bash
cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -c "
from db import get_service_client
from utils.geo import find_nearby_store_ids, zip_to_centroid
from recommendation.candidate_filters import detect_store, apply_type_gate, resolve_wine_type
db=get_service_client(); ZIP='78209'
nearby=find_nearby_store_ids(ZIP, db, centroid=zip_to_centroid(ZIP))
meta=db.table('stores').select('id,name').in_('id',nearby).execute().data
st=detect_store('Show me one Bordeaux blend at heb lincon heights', meta)
print('detected store:', st and st['name'])
INV='price,wine_id,stores!inner(id,name),wines!inner(id,name,varietal,region,wine_type,grapes)'
rows=db.table('retail_inventory').select(INV).in_('store_ref',nearby).eq('in_stock',True).gte('price',0).lte('price',45).ilike('wines.region','%Bordeaux%').limit(300).execute().data
cands=[{'wine_id':r['wines']['id'],'name':r['wines']['name'],'varietal':r['wines']['varietal'],'region':r['wines']['region'],'wine_type':r['wines']['wine_type'],'grapes':r['wines']['grapes'] or []} for r in rows]
gated=apply_type_gate(cands, {'red'})
print(f'Bordeaux fetched: {len(cands)} | after red gate: {len(gated)}')
for c in gated: print(f\"  {c['wine_type']:6s} {c['name'][:46]}\")
"
```

Expected: detected store = "Lincoln Heights Market H-E-B"; the red gate keeps Les Allies Médoc, Château Lasségue, **and** Château Saint-Sulpice (NULL→red), and drops any Bordeaux whites/rosé.

- [ ] **Step 3: Live end-to-end** — start the backend and POST the exact query (or drive it from the frontend): zip 78209, `wine_type=red`, `budget_max=45`, message "Show me one Bordeaux blend at heb lincon heights, and another red blend not from Bordeaux". Confirm a **real Bordeaux** (Lasségue / Les Allies / Saint-Sulpice) is returned as the Bordeaux pick, the non-Bordeaux red-blend pick still works, and **no white/rosé** appears. Capture the pick list in the run notes.

---

### Task 10: Docs + roadmap

**Files:**
- Modify: `docs/reference/recommendation.md`, `CLAUDE.md`

- [ ] **Step 1: Update docs**
- `docs/reference/recommendation.md`: document the intent-aware fetch (targeted relevance query bypassing the 500 breadth sample), the resolved-type hard gate (NULL types inferred via `infer_wine_type`, wrong type never surfaces, mis-typed reds kept), fuzzy `detect_store`, and the Claude hedging change.
- `CLAUDE.md` "What's Next": add two roadmap items — (a) **NULL-`wine_type` backfill** (5,443 wines, deterministic `infer_wine_type` pass, same shape as grapes backfill); (b) **name-directed full-inventory fallback** (when a prompt references a specific bottle by name and yields nothing, search the entire zip-scoped, optionally type-filtered inventory instead of the top-500 breadth sample — extension of the targeted fetch).

- [ ] **Step 2: Commit**

```bash
git add docs/reference/recommendation.md CLAUDE.md
git commit -m "docs: intent-aware fetch + type gate; roadmap wine_type backfill + name-directed fallback"
```
