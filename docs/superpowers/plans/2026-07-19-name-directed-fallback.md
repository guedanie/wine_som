# Name-Directed Full-Inventory Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a user names a specific bottle, or when the random-500 breadth sample provably missed a concrete constraint, query the full zip-scoped inventory and surface a themed "looking deeper" message while doing it.

**Architecture:** Add a `wine_name` intent field (Haiku parse). Pure helpers in `recommendation/candidate_filters.py` decide when to dig deeper (`deep_fetch_reason`), tokenize/rank names (`significant_name_tokens`, `rank_name_matches`), and pin named matches (`pin_named_matches`). The recommend endpoint runs the deep fetch and the Claude call **inside** the SSE generator, behind a `status` frame, so the fetch stays lazy and the message only shows when we actually dig. The narrative acknowledges the named bottle via two new intent keys read by `_build_user_message`.

**Tech Stack:** FastAPI, supabase-py (PostgREST embedded-resource filters), Anthropic (Haiku parse + Sonnet stream), React (SSE consumer), pytest, vitest.

**Verified PostgREST syntax (probed live 2026-07-19):**
- Name on embedded wines: `q.or_(f"name.ilike.%{tok}%", reference_table="wines")`
- Grape containment (grapes is **jsonb**, case-sensitive Title Case): `q.or_(f'grapes.cs.["{grape}"]', reference_table="wines")`

**Python 3.9** — use `Optional[...]`, never `X | None`. Run backend commands from `backend/`. Run frontend commands from `frontend/`.

---

### Task 1: Add `wine_name` to intent parse + merge

**Files:**
- Modify: `backend/recommendation/intent.py` (tool schema ~19-35, system prompt ~44-48, `intent_from_request` ~62-75, `merge_intent` ~78-101)
- Test: `backend/tests/test_intent.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_intent.py`:

```python
from recommendation.intent import merge_intent, intent_from_request


def test_intent_from_request_sets_wine_name_none():
    out = intent_from_request(wine_type=None, style_preferences=[], avoid=[],
                              budget_min=10.0, budget_max=50.0)
    assert out["wine_name"] is None


def test_merge_takes_parsed_wine_name():
    explicit = intent_from_request(wine_type=None, style_preferences=[], avoid=[],
                                   budget_min=10.0, budget_max=50.0)
    merged = merge_intent({"wine_name": "Opus One", "flavors": [], "grapes": [], "avoid": []}, explicit)
    assert merged["wine_name"] == "Opus One"


def test_merge_no_parsed_leaves_wine_name_none():
    explicit = intent_from_request(wine_type=None, style_preferences=[], avoid=[],
                                   budget_min=10.0, budget_max=50.0)
    assert merge_intent(None, explicit)["wine_name"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_intent.py -k wine_name -v`
Expected: FAIL (`KeyError: 'wine_name'`).

- [ ] **Step 3: Add `wine_name` to the tool schema**

In `backend/recommendation/intent.py`, inside `_TOOL["input_schema"]["properties"]`, add after the `region` line:

```python
            "wine_name": {"type": ["string", "null"]},
```

- [ ] **Step 4: Add the system-prompt guidance**

In `parse_message`, extend the `system=` string. Change the final sentence to:

```python
                "Use null/empty when a field is not implied. Do not invent grapes or regions. "
                "`wine_name`: set ONLY when the user names a specific bottle or producer to look up "
                "(e.g. 'Caymus Special Selection', 'Opus One', 'do you have Silver Oak?'); "
                "leave null for generic style requests."
```

- [ ] **Step 5: Set `wine_name` in `intent_from_request`**

Add to the returned dict in `intent_from_request`:

```python
        "wine_name": None,
```

- [ ] **Step 6: Thread `wine_name` through `merge_intent`**

In `merge_intent`, after the `out["region"] = ...` line, add:

```python
    out["wine_name"] = out.get("wine_name") or parsed.get("wine_name")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_intent.py -v`
Expected: PASS (all, including existing).

- [ ] **Step 8: Commit**

```bash
git add backend/recommendation/intent.py backend/tests/test_intent.py
git commit -m "feat(recommend): parse wine_name intent for named-bottle lookups"
```

---

### Task 2: Shared name tokenizer in candidate_filters (move `_GENERIC_WINE_WORDS`)

`_GENERIC_WINE_WORDS` currently lives in `recommend.py` and is used by `_pick_named_in_narrative`. Move it to `candidate_filters.py` and expose `significant_name_tokens` so the deep fetch and the narrative-reconcile share one definition.

**Files:**
- Modify: `backend/recommendation/candidate_filters.py`
- Modify: `backend/api/routers/recommend.py` (delete local `_GENERIC_WINE_WORDS` ~118-126; import + reuse in `_pick_named_in_narrative` ~128-134)
- Test: `backend/tests/test_candidate_filters.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_candidate_filters.py`:

```python
from recommendation.candidate_filters import significant_name_tokens


def test_tokens_drop_generic_keep_producer():
    assert significant_name_tokens("Caymus Cabernet Sauvignon") == ["caymus"]


def test_tokens_multi_word_producer():
    toks = significant_name_tokens("Opus One 2019")
    assert "opus" in toks and "one" in toks


def test_tokens_all_generic_is_empty():
    assert significant_name_tokens("Red Blend Reserve") == []


def test_tokens_none_safe():
    assert significant_name_tokens(None) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_candidate_filters.py -k tokens -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Add the set + helper to `candidate_filters.py`**

At the top of `backend/recommendation/candidate_filters.py` (after the existing imports), add:

```python
# Generic wine words that don't identify a specific bottle — dropped when
# tokenizing a wine name for name search / narrative reconcile.
_GENERIC_WINE_WORDS = {
    "cabernet", "sauvignon", "merlot", "pinot", "noir", "gris", "grigio", "chardonnay",
    "syrah", "shiraz", "zinfandel", "malbec", "tempranillo", "sangiovese", "nebbiolo",
    "grenache", "mourvedre", "carignan", "riesling", "blanc", "chenin", "viognier",
    "barbera", "tannat", "red", "white", "rose", "wine", "blend", "reserve", "reserva",
    "vineyard", "vineyards", "valley", "county", "napa", "sonoma", "paso", "robles",
    "california", "italian", "the", "and", "estate", "old", "vine", "vines", "cuvee",
}


def significant_name_tokens(name: Optional[str]) -> List[str]:
    """Lowercased 3+ char tokens of a wine name, minus generic varietal/geo words —
    the distinctive producer/bottle tokens to search or reconcile on."""
    return [t for t in re.findall(r"[a-z0-9é]{3,}", (name or "").lower())
            if t not in _GENERIC_WINE_WORDS]
```

(`re` and `Optional`/`List` are already imported in this module.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_candidate_filters.py -k tokens -v`
Expected: PASS.

- [ ] **Step 5: Reuse the shared helper in `recommend.py`**

In `backend/api/routers/recommend.py`:

Delete the local `_GENERIC_WINE_WORDS = {...}` block (~118-126).

Add `significant_name_tokens` to the existing import from `recommendation.candidate_filters`:

```python
from recommendation.candidate_filters import (apply_type_gate, detect_store,
                                              merge_candidates, requested_types_from,
                                              significant_name_tokens)
```

Rewrite `_pick_named_in_narrative` (~128-134) to use it:

```python
def _pick_named_in_narrative(pick: Dict[str, Any], narr_lower: str) -> bool:
    tokens = significant_name_tokens(pick.get("name"))
    return not tokens or any(re.search(r"\b" + re.escape(t) + r"\b", narr_lower) for t in tokens)
```

- [ ] **Step 6: Run the recommend-api + candidate-filters tests**

Run: `cd backend && python3 -m pytest tests/test_candidate_filters.py tests/test_recommend_api.py -v`
Expected: PASS (no regression in `_pick_named_in_narrative` behavior).

- [ ] **Step 7: Commit**

```bash
git add backend/recommendation/candidate_filters.py backend/api/routers/recommend.py backend/tests/test_candidate_filters.py
git commit -m "refactor(recommend): share significant_name_tokens across name search + reconcile"
```

---

### Task 3: `rank_name_matches` — full-token matches first

**Files:**
- Modify: `backend/recommendation/candidate_filters.py`
- Test: `backend/tests/test_candidate_filters.py`

- [ ] **Step 1: Write the failing test**

```python
from recommendation.candidate_filters import rank_name_matches


def test_rank_all_tokens_before_partial():
    cands = [
        {"name": "Caymus Cabernet Sauvignon"},           # matches "caymus" only
        {"name": "Caymus Special Selection Cabernet"},    # matches both
    ]
    ranked = rank_name_matches(cands, ["caymus", "special"])
    assert ranked[0]["name"] == "Caymus Special Selection Cabernet"


def test_rank_drops_zero_match():
    cands = [{"name": "Silver Oak"}, {"name": "Opus One"}]
    assert rank_name_matches(cands, ["caymus"]) == []


def test_rank_empty_tokens_returns_empty():
    assert rank_name_matches([{"name": "Anything"}], []) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_candidate_filters.py -k rank -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement `rank_name_matches`**

Add to `backend/recommendation/candidate_filters.py`:

```python
def rank_name_matches(candidates: List[Dict[str, Any]],
                      tokens: List[str]) -> List[Dict[str, Any]]:
    """Keep candidates whose name contains at least one search token, ordered by
    how many tokens matched (all-token matches first). Empty tokens → []."""
    if not tokens:
        return []
    scored = []
    for c in candidates:
        name = (c.get("name") or "").lower()
        hits = sum(1 for t in tokens if t in name)
        if hits:
            scored.append((hits, c))
    scored.sort(key=lambda hc: hc[0], reverse=True)
    return [c for _, c in scored]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_candidate_filters.py -k rank -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/candidate_filters.py backend/tests/test_candidate_filters.py
git commit -m "feat(recommend): rank_name_matches — full-token name matches first"
```

---

### Task 4: `deep_fetch_reason` — decide when to dig deeper

**Files:**
- Modify: `backend/recommendation/candidate_filters.py`
- Test: `backend/tests/test_candidate_filters.py`

- [ ] **Step 1: Write the failing tests**

```python
from recommendation.candidate_filters import deep_fetch_reason


def _cand(**kw):
    base = {"grapes": [], "region": None, "wine_type": None, "varietal": None}
    base.update(kw)
    return base


def test_reason_named_when_wine_name_present():
    assert deep_fetch_reason({"wine_name": "Opus One"}, [_cand()]) == "named"


def test_reason_weak_when_grape_unmet():
    intent = {"wine_name": None, "grapes": ["Chenin Blanc"], "region": None, "wine_type": None}
    top = [_cand(grapes=["Cabernet Sauvignon"], wine_type="red")]
    assert deep_fetch_reason(intent, top) == "weak"


def test_reason_none_when_grape_met():
    intent = {"wine_name": None, "grapes": ["Chenin Blanc"], "region": None, "wine_type": None}
    top = [_cand(grapes=["Chenin Blanc"], wine_type="white")]
    assert deep_fetch_reason(intent, top) is None


def test_reason_weak_when_region_unmet():
    intent = {"wine_name": None, "grapes": [], "region": "Rioja", "wine_type": None}
    top = [_cand(region="Napa Valley")]
    assert deep_fetch_reason(intent, top) == "weak"


def test_reason_none_when_no_concrete_constraint():
    intent = {"wine_name": None, "grapes": [], "region": None, "wine_type": None, "flavors": ["bold"]}
    assert deep_fetch_reason(intent, [_cand()]) is None


def test_named_beats_weak():
    intent = {"wine_name": "Opus One", "grapes": ["Chenin Blanc"], "region": None, "wine_type": None}
    assert deep_fetch_reason(intent, [_cand()]) == "named"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_candidate_filters.py -k reason -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement `deep_fetch_reason`**

Add to `backend/recommendation/candidate_filters.py` (note: reuses `_norm`-style lowering inline to stay dependency-free):

```python
def _cand_grapes(c: Dict[str, Any]) -> set:
    g = {str(x).lower() for x in (c.get("grapes") or [])}
    if c.get("varietal"):
        g.add(str(c["varietal"]).lower())
    return g


def deep_fetch_reason(intent: Dict[str, Any],
                      top: List[Dict[str, Any]]) -> Optional[str]:
    """Return "named" if the user named a specific bottle, else "weak" if the
    user expressed a concrete constraint (grape/region/wine_type) that NONE of the
    selected top candidates satisfies, else None. Named always wins."""
    if (intent.get("wine_name") or "").strip():
        return "named"

    want_grapes = {str(g).lower() for g in (intent.get("grapes") or [])}
    want_region = (intent.get("region") or "").strip().lower()
    want_type = intent.get("wine_type")
    if not want_grapes and not want_region and not want_type:
        return None

    for c in top:
        if want_grapes and (want_grapes & _cand_grapes(c)):
            return None
        region = (c.get("region") or "").lower()
        if want_region and region and (want_region in region or region in want_region):
            return None
        if want_type and c.get("wine_type") == want_type:
            return None
    return "weak"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_candidate_filters.py -k reason -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/candidate_filters.py backend/tests/test_candidate_filters.py
git commit -m "feat(recommend): deep_fetch_reason — named vs weak-pool trigger"
```

---

### Task 5: `pin_named_matches` — lead with the exact bottle

**Files:**
- Modify: `backend/recommendation/candidate_filters.py`
- Test: `backend/tests/test_candidate_filters.py`

- [ ] **Step 1: Write the failing tests**

```python
from recommendation.candidate_filters import pin_named_matches


def test_pin_named_first_dedup_and_cap():
    top = [{"wine_id": "s1", "name": "Scored A"}, {"wine_id": "s2", "name": "Scored B"}]
    named = [
        {"wine_id": "n1", "name": "Opus One", "price": 400},
        {"wine_id": "n1", "name": "Opus One", "price": 380},   # dup wine, cheaper
        {"wine_id": "n2", "name": "Opus One 2018", "price": 350},
        {"wine_id": "n3", "name": "Opus One 2017", "price": 360},
        {"wine_id": "n4", "name": "Opus One 2016", "price": 370},  # beyond cap
    ]
    out = pin_named_matches(top, named, cap=3)
    ids = [w["wine_id"] for w in out]
    assert ids[:3] == ["n1", "n2", "n3"]              # 3 distinct named, cheapest n1 kept
    assert next(w for w in out if w["wine_id"] == "n1")["price"] == 380
    assert "s1" in ids and "s2" in ids                # scored still present, after
    assert ids.count("n1") == 1                        # deduped


def test_pin_no_named_returns_top_unchanged():
    top = [{"wine_id": "s1", "name": "A"}]
    assert pin_named_matches(top, [], cap=3) == top
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_candidate_filters.py -k pin -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement `pin_named_matches`**

Add to `backend/recommendation/candidate_filters.py`:

```python
def pin_named_matches(top: List[Dict[str, Any]],
                      named: List[Dict[str, Any]],
                      cap: int = 3) -> List[Dict[str, Any]]:
    """Put named-bottle matches at the front of `top`, deduped by wine_id (keeping
    the cheapest row per wine), capped at `cap`. Scored candidates follow, minus any
    now pinned. `named` is assumed already relevance-ordered (rank_name_matches)."""
    if not named:
        return top
    best_by_wine: Dict[Any, Dict[str, Any]] = {}
    order: List[Any] = []
    for c in named:
        wid = c.get("wine_id")
        prev = best_by_wine.get(wid)
        if prev is None:
            best_by_wine[wid] = c
            order.append(wid)
        elif (c.get("price") or float("inf")) < (prev.get("price") or float("inf")):
            best_by_wine[wid] = c
    pinned = [best_by_wine[w] for w in order][:cap]
    pinned_ids = {w.get("wine_id") for w in pinned}
    rest = [w for w in top if w.get("wine_id") not in pinned_ids]
    return pinned + rest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_candidate_filters.py -k pin -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/candidate_filters.py backend/tests/test_candidate_filters.py
git commit -m "feat(recommend): pin_named_matches — lead with the named bottle"
```

---

### Task 6: Deep-fetch DB closures in recommend.py

Implement the two fetch modes. They do DB I/O (covered by the acceptance replay in Task 10); keep them thin so the tested pure helpers carry the logic.

**Files:**
- Modify: `backend/api/routers/recommend.py` (add closures alongside `_targeted_rows`, ~366-392)

- [ ] **Step 1: Add the deep-fetch closures**

In `recommend`, after the `targeted = [...]` / `merge_candidates` block (~388-392) and before `preferred_retailer = _detect_retailer(...)` (~394), add:

```python
    def _named_fetch(wine_name: str) -> list:
        """Full nearby-store inventory whose wine name matches the named bottle —
        budget IGNORED (a direct lookup must not be hidden by the slider)."""
        tokens = significant_name_tokens(wine_name)
        if not tokens:
            return []
        cond = ",".join(f"name.ilike.%{t}%" for t in tokens)

        def _q(since: Optional[str]) -> list:
            q = (supabase.table("retail_inventory").select(INVENTORY_SELECT)
                 .in_("store_ref", nearby_ids).eq("in_stock", True)
                 .or_(cond, reference_table="wines"))
            if since:
                q = q.gte("last_scraped_at", since)
            return q.limit(80).execute().data or []

        rows = _q(stale_cutoff) or _q(None)
        cands = [c for c in (_row_to_candidate(r) for r in rows) if c]
        return rank_name_matches(cands, tokens)

    def _constraint_fetch() -> list:
        """Full nearby-store inventory matching a concrete grape/region the breadth
        sample missed. Budget HONORED (this is still a recommendation)."""
        grapes = resolved.get("grapes") or []
        region = resolved.get("region")
        conds = [f'grapes.cs.["{g.title()}"]' for g in grapes]
        if region:
            conds.append(f"region.ilike.%{region}%")
        if not conds:
            return []

        def _q(since: Optional[str]) -> list:
            q = (supabase.table("retail_inventory").select(INVENTORY_SELECT)
                 .in_("store_ref", nearby_ids).eq("in_stock", True)
                 .gte("price", req.budget_min).lte("price", req.budget_max)
                 .or_(",".join(conds), reference_table="wines"))
            if since:
                q = q.gte("last_scraped_at", since)
            return q.limit(200).execute().data or []

        rows = _q(stale_cutoff) or _q(None)
        return [c for c in (_row_to_candidate(r) for r in rows) if c]
```

Add `rank_name_matches`, `deep_fetch_reason`, and `pin_named_matches` to the `candidate_filters` import at the top of the file:

```python
from recommendation.candidate_filters import (apply_type_gate, deep_fetch_reason,
                                              detect_store, merge_candidates,
                                              pin_named_matches, rank_name_matches,
                                              requested_types_from, significant_name_tokens)
```

- [ ] **Step 2: Verify it imports and the app still starts**

Run: `cd backend && python3 -c "import api.routers.recommend"`
Expected: no error.

- [ ] **Step 3: Run the recommend-api tests**

Run: `cd backend && python3 -m pytest tests/test_recommend_api.py -v`
Expected: PASS (closures are defined but not yet called — no behavior change).

- [ ] **Step 4: Commit**

```bash
git add backend/api/routers/recommend.py
git commit -m "feat(recommend): deep-fetch closures — named (budget-free) + weak-pool grape/region"
```

---

### Task 7: Wire deep fetch + status frame into the SSE generator

Move `stream_recommendations` and the deep fetch inside `event_gen`, emit a themed `status` frame first, then re-score / re-select / pin. Compute the reason before the generator so the fast path is untouched.

**Files:**
- Modify: `backend/api/routers/recommend.py` (~408-488: the scoring block, the pre-stream `stream_recommendations` call, and `event_gen`)

- [ ] **Step 1: Capture the initial scored pool + compute the reason**

The existing block (~408-418) scores, selects `top`, sorts for detected store, and annotates price drops. Refactor it into a reusable helper defined just above `event_gen`, and compute the reason from the first pass. Replace lines ~408-418 with:

```python
    def _score_and_select(pool: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        scored = score_candidates(resolved, pool)
        for w in scored:
            w["_score"] += rng.uniform(-0.4, 0.4)
        scored.sort(key=lambda w: w["_score"], reverse=True)
        sel = _select_diverse_top(scored, _MAX_CANDIDATES, _RETAILER_CAP, _VARIETAL_CAP)
        if detected_store:
            sel.sort(key=lambda w: (w.get("store_ref") == detected_store["id"],
                                    w.get("_score", 0)), reverse=True)
        return sel

    top = _score_and_select(candidates)
    reason = deep_fetch_reason(resolved, top)
```

Note: the `_annotate_price_drops(supabase, top)` call and the `RECOMMEND | ...` log that followed (~418-424) move to AFTER the possible deep fetch — see Step 3. Delete them from here.

- [ ] **Step 2: Build the Claude generator lazily**

The current code (~426-430) calls `stream_recommendations` before `StreamingResponse` to surface init errors early. Since the deep fetch may replace `top`, defer this. Delete the try/except block at ~426-430 and the `by_id = {...}` / `gen = ...` lines. Keep:

```python
    session_id = str(uuid.uuid4())
    _result: dict = {"narrative": [], "picks": []}
```

- [ ] **Step 3: Deep fetch + status frame inside `event_gen`**

Replace the `def event_gen():` body's opening (before the `for event_type, data in gen:` loop) so it becomes:

```python
    def event_gen():
        nonlocal top
        if reason:
            yield "data: " + json.dumps(
                {"type": "status", "text": "Looking deeper into the cellar…"}) + "\n\n"
            if reason == "named":
                named = _named_fetch(resolved["wine_name"])
                pool = merge_candidates(candidates, named)
                resolved["named_bottle"] = resolved.get("wine_name")
                resolved["named_bottle_found"] = bool(named)
                top = _score_and_select(pool)
                top = pin_named_matches(top, named, cap=3)[:_MAX_CANDIDATES]
            else:  # weak
                extra = _constraint_fetch()
                if extra:
                    top = _score_and_select(merge_candidates(candidates, extra))

        _annotate_price_drops(supabase, top)
        logger.info(
            "RECOMMEND | zip=%s budget=%.0f-%.0f message=%r candidates=%d reason=%s",
            req.zip_code, req.budget_min, req.budget_max, req.message[:80],
            len(top), reason,
        )

        by_id = {c["wine_id"]: c for c in top}
        try:
            gen = stream_recommendations(top, resolved, req.conversation_history, req.conversational)
        except Exception:
            yield "data: " + json.dumps(
                {"type": "error", "message": "Recommendation service unavailable"}) + "\n\n"
            yield "data: [DONE]\n\n"
            return

        for event_type, data in gen:
```

The rest of the loop body (`if event_type == "token": ...` through the `[DONE]` + session persistence) stays exactly as-is.

- [ ] **Step 2b (verify import + startup)**

Run: `cd backend && python3 -c "import api.routers.recommend"`
Expected: no error.

- [ ] **Step 4: Run the recommend-api tests**

Run: `cd backend && python3 -m pytest tests/test_recommend_api.py -v`
Expected: PASS. If a test asserted the old pre-stream 500-on-init-failure behavior, update it to assert the SSE `error` frame instead (init failure now yields `{"type":"error"}` then `[DONE]`).

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/recommend.py backend/tests/test_recommend_api.py
git commit -m "feat(recommend): deep fetch + themed status frame inside the SSE stream"
```

---

### Task 8: Narrative honesty — acknowledge the named bottle

`_build_user_message` reads everything from the `intent` dict, so the two keys set in Task 7 (`named_bottle`, `named_bottle_found`) need a directive block. No signature change.

**Files:**
- Modify: `backend/recommendation/claude_client.py` (`_build_user_message` ~254-320; assemble the final message string where the other blocks are concatenated)
- Test: `backend/tests/test_claude_client.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_claude_client.py`:

```python
from recommendation.claude_client import _build_user_message


def _intent(**kw):
    base = {"flavors": [], "avoid": [], "budget_min": 10.0, "budget_max": 50.0, "message": "do you have Opus One?"}
    base.update(kw)
    return base


def test_named_found_directive_present():
    msg = _build_user_message([{"wine_id": "1", "name": "Opus One"}],
                              _intent(named_bottle="Opus One", named_bottle_found=True))
    assert "Opus One" in msg
    assert "specifically asked" in msg.lower()


def test_named_not_found_hedge_directive():
    msg = _build_user_message([{"wine_id": "1", "name": "Silver Oak"}],
                              _intent(named_bottle="Opus One", named_bottle_found=False))
    assert "could not find" in msg.lower() or "couldn't find" in msg.lower()


def test_no_named_bottle_no_directive():
    msg = _build_user_message([{"wine_id": "1", "name": "Silver Oak"}], _intent())
    assert "specifically asked" not in msg.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_claude_client.py -k named -v`
Expected: FAIL.

- [ ] **Step 3: Build the directive + append it**

In `_build_user_message`, after the `similarity_note = (...)` block and before the final message assembly, add:

```python
    named_directive = ""
    named_bottle = intent.get("named_bottle")
    if named_bottle:
        if intent.get("named_bottle_found"):
            named_directive = (
                f"\n\nThe user specifically asked for \"{named_bottle}\". It IS available nearby and "
                "leads the listings — confirm you found it and open with it before any alternatives."
            )
        else:
            named_directive = (
                f"\n\nThe user specifically asked for \"{named_bottle}\", but I could not find it in "
                "nearby inventory. Say so plainly, then offer the closest alternatives from the listings."
            )
```

Then add `named_directive` to the concatenation that forms the returned message string. Locate the `return (...)`/final f-string assembly at the end of `_build_user_message` and append `named_directive` alongside `similarity_note` (same placement pattern). If the function returns via string concatenation of the named blocks, add `+ named_directive` before the listings/closing.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_claude_client.py -k named -v`
Expected: PASS.

- [ ] **Step 5: Run the full claude_client suite**

Run: `cd backend && python3 -m pytest tests/test_claude_client.py -v`
Expected: PASS (no regression).

- [ ] **Step 6: Commit**

```bash
git add backend/recommendation/claude_client.py backend/tests/test_claude_client.py
git commit -m "feat(recommend): narrative confirms/hedges the named bottle"
```

---

### Task 9: Frontend — render the themed status line

`api.js` already yields `JSON.parse(raw)` for every frame, so `{type:'status',text}` passes through untouched — only `ChatRecommend.jsx` changes: store the status text, show it in the loading block, clear it when the first token arrives.

**Files:**
- Modify: `frontend/src/screens/ChatRecommend.jsx` (state ~149-151; `callRecommend` ~177-236; loading render ~349-354)
- Test: `frontend/src/screens/__tests__/ChatRecommend.test.jsx`

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/screens/__tests__/ChatRecommend.test.jsx` (follow the file's existing pattern for mocking `streamRecommend`; the mock yields a sequence of event objects). Add a test where the mocked stream yields a `status` frame before any token:

```jsx
it('shows the themed status line while digging deeper, then clears it on first token', async () => {
  mockStream([
    { type: 'status', text: 'Looking deeper into the cellar…' },
  ]);
  renderChat();
  expect(await screen.findByText('Looking deeper into the cellar…')).toBeInTheDocument();

  mockStream([
    { type: 'status', text: 'Looking deeper into the cellar…' },
    { type: 'token', text: 'Here' },
  ]);
  renderChat();
  await screen.findByText(/Here/);
  expect(screen.queryByText('Looking deeper into the cellar…')).not.toBeInTheDocument();
});
```

(Adapt `mockStream`/`renderChat` to the helpers already in the test file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/screens/__tests__/ChatRecommend.test.jsx -t "themed status"`
Expected: FAIL.

- [ ] **Step 3: Add status state**

In `ChatRecommend.jsx`, near the other `useState` declarations (~149-151), add:

```jsx
  const [statusText, setStatusText] = useState(null);
```

- [ ] **Step 4: Handle the status frame + clear on first token**

In `callRecommend`, at the start of the `try` add nothing new; inside the `for await` loop add a branch and clear on first token. Change the `if (event.type === 'token')` first-token block to also clear status, and add the status branch:

```jsx
        if (event.type === 'token') {
          if (firstToken) {
            firstToken = false;
            setStatusText(null);
            setLoading(false);
            setStreaming(true);
            setMessages(prev => [...prev, { id: uuid(), role: 'sommelier', text: event.text }]);
          } else {
            setMessages(prev => {
              const msgs = [...prev];
              msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], text: msgs[msgs.length - 1].text + event.text };
              return msgs;
            });
          }
        } else if (event.type === 'status') {
          setStatusText(event.text);
        } else if (event.type === 'pick') {
```

Also clear it in the `finally` block so it never lingers on error:

```jsx
    } finally {
      setLoading(false);
      setStreaming(false);
      setStatusText(null);
    }
```

- [ ] **Step 5: Render the status line in the loading block**

Replace the loading block (~349-354) so the themed text shows beside the loader when present:

```jsx
          {loading && (
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 16 }}>
              <Stamp size={32} reversed />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <WineGlassLoader />
                {statusText && (
                  <span className="t-eyebrow" style={{ animation: 'skeleton-pulse 1.4s ease-in-out infinite' }}>
                    {statusText}
                  </span>
                )}
              </div>
            </div>
          )}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/screens/__tests__/ChatRecommend.test.jsx`
Expected: PASS (new + existing).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/screens/ChatRecommend.jsx frontend/src/screens/__tests__/ChatRecommend.test.jsx
git commit -m "feat(chat): render themed 'looking deeper' status line during deep fetch"
```

---

### Task 10: Acceptance replay + docs/roadmap

**Files:**
- Create: `backend/scripts/verify_name_fallback.py` (a throwaway acceptance script, kept for re-runs)
- Modify: `CLAUDE.md` (item 31), `docs/reference/recommendation.md`

- [ ] **Step 1: Write the acceptance script**

Create `backend/scripts/verify_name_fallback.py`:

```python
"""Acceptance replay for item 31 (name-directed full-inventory fallback).
Run from backend/: python3 scripts/verify_name_fallback.py
Uses a live zip with known inventory (78209 San Antonio)."""
from db import get_supabase_client
from recommendation.candidate_filters import significant_name_tokens, rank_name_matches
from utils.geo import find_nearby_store_ids

ZIP = "78209"


def main():
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(ZIP, sb)
    assert nearby, "no nearby stores for 78209"

    # 1. A named bottle known to be stocked surfaces via name search.
    tokens = significant_name_tokens("Caymus Cabernet Sauvignon")
    cond = ",".join(f"name.ilike.%{t}%" for t in tokens)
    rows = (sb.table("retail_inventory")
            .select("price, wine_id, wines!inner(id, name, grapes, region)")
            .in_("store_ref", nearby).eq("in_stock", True)
            .or_(cond, reference_table="wines").limit(80).execute().data or [])
    cands = [{"wine_id": r["wine_id"], "name": r["wines"]["name"], "price": r["price"]} for r in rows]
    ranked = rank_name_matches(cands, tokens)
    print(f"NAMED  | 'Caymus' → {len(ranked)} matches; top={ranked[0]['name'] if ranked else None}")
    assert ranked, "expected Caymus in 78209 inventory"

    # 2. A grape constraint fetch returns rows via jsonb containment.
    grp = (sb.table("retail_inventory")
           .select("wine_id, wines!inner(id, name, grapes)")
           .in_("store_ref", nearby).eq("in_stock", True)
           .or_('grapes.cs.["Chenin Blanc"]', reference_table="wines").limit(50).execute().data or [])
    print(f"WEAK   | Chenin Blanc containment → {len(grp)} rows")
    assert grp, "expected Chenin Blanc rows via jsonb containment"
    print("OK — name search + grape containment both surface inventory")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the acceptance script**

Run: `cd backend && python3 scripts/verify_name_fallback.py`
Expected: prints NAMED/WEAK lines and `OK — ...`, exit 0. (If Caymus/Chenin Blanc aren't in 78209 at run time, swap for a producer/grape confirmed present — the point is that name search + containment surface real rows.)

- [ ] **Step 3: Run the full fast backend + frontend suites**

Run: `cd backend && python3 -m pytest tests/ -m "not integration" -q`
Expected: PASS (prior count + new tests).

Run: `cd frontend && npx vitest run`
Expected: PASS.

- [ ] **Step 4: Update the roadmap + reference doc**

In `CLAUDE.md`, change item 31 from the current stub to:

```markdown
31. ✅ **Name-directed full-inventory fallback** — landed 2026-07-19. `wine_name` added to the Haiku `wine_intent` parse; `deep_fetch_reason` fires a deep fetch when a bottle is named OR when a concrete grape/region/type ask went unmet by the random-500 breadth sample. Named mode searches the full nearby inventory by `wines.name ilike` (budget IGNORED — a lookup shouldn't be hidden by the slider), ranks all-token matches first (`rank_name_matches`), and pins up to 3 to the front (`pin_named_matches`); weak-pool mode re-fetches by grape (jsonb `grapes.cs.[...]`) or region honoring budget. The deep fetch + Claude call moved INSIDE the SSE generator behind a themed `status` frame ("Looking deeper into the cellar…"), so the message only shows when we actually dig and the common request is untouched. Narrative confirms the found bottle or hedges when it's not stocked. Pure helpers in `candidate_filters.py` (tokenize/rank/reason/pin) unit-tested; acceptance `scripts/verify_name_fallback.py`.
```

In `docs/reference/recommendation.md`, add a short "Name-directed fallback" subsection under the candidate-fetch section describing `deep_fetch_reason`, the two fetch modes, the status frame, and the budget-bypass rule.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/verify_name_fallback.py CLAUDE.md docs/reference/recommendation.md
git commit -m "test+docs: item 31 acceptance replay + roadmap/reference update"
```

---

## Self-Review Notes

- **Spec coverage:** §1 intent→T1; §2 deep fetch→T6 (+ tokenizer T2); §3 trigger+status→T4,T7; §4 pin→T5,T7; §5 narrative→T8; §6 frontend→T9; testing→each task + T10. All covered.
- **Type consistency:** `significant_name_tokens`/`rank_name_matches`/`deep_fetch_reason`/`pin_named_matches` names used identically across T2–T7. `named_bottle`/`named_bottle_found` intent keys set in T7, read in T8. `status` SSE type emitted in T7, consumed in T9.
- **Budget rule:** named fetch omits the price filter (T6); weak fetch keeps it (T6) — matches the design decision.
- **Fast path untouched:** `reason is None` skips the status frame and deep fetch; `_score_and_select(candidates)` produces the same `top` as before (same scoring + selection + seeded jitter using the same `rng`).
