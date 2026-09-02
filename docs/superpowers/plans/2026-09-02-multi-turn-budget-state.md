# Multi-Turn Budget State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A budget stated in chat persists across turns, so the SQL fetch, scorer, availability oracle, and prompt all act on the number the user actually said.

**Architecture:** The backend emits a `budget` SSE frame whenever a budget is spoken; `ChatRecommend` stores it into `apiReq` state and echoes it on the next request, so `req.budget_max` becomes truthful. `merge_intent` lets a spoken number win in either direction, and a widening budget triggers a targeted re-fetch because the breadth query already ran at the old ceiling.

**Tech Stack:** Python 3.9 (`Optional[str]`, never `str | None`), FastAPI + SSE, supabase-py, pytest. React 19 + Vite, vitest.

**Spec:** `docs/superpowers/specs/2026-09-02-multi-turn-budget-state-design.md`

**Run commands from the right directory** — `pytest` from `backend/`, `vitest` from `frontend/`. Running from the repo root is a known failure mode in this codebase.

---

### Task 1: A spoken budget wins in either direction

`merge_intent` only ever tightens. Once a budget is carried forward, that guard silently swallows "actually, up to $200".

**Files:**
- Modify: `backend/recommendation/intent.py:192-196`
- Test: `backend/tests/test_intent.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_intent.py`:

```python
def test_spoken_budget_widens_a_carried_one():
    """Once a budget is carried across turns, tighten-only becomes a trap:
    'up to $200' against a carried $60 evaluates 200 < 60 and is ignored, with
    no error and no way for the user to tell."""
    out = merge_intent({"max_price": 200}, {"budget_min": 0, "budget_max": 60})
    assert out["budget_max"] == 200.0


def test_spoken_budget_still_narrows():
    out = merge_intent({"max_price": 20}, {"budget_min": 0, "budget_max": 60})
    assert out["budget_max"] == 20.0


def test_budget_min_follows_below_a_narrowed_max():
    out = merge_intent({"max_price": 15}, {"budget_min": 30, "budget_max": 60})
    assert out["budget_min"] == 15.0


def test_no_spoken_price_leaves_the_carried_budget_alone():
    out = merge_intent({"max_price": None}, {"budget_min": 0, "budget_max": 60})
    assert out["budget_max"] == 60
```

- [ ] **Step 2: Run the tests to verify they fail**

Run from `backend/`: `python3 -m pytest tests/test_intent.py -k budget -v`
Expected: `test_spoken_budget_widens_a_carried_one` FAILS with `assert 60 == 200.0`. The other three pass (they pin existing behavior).

- [ ] **Step 3: Remove the tighten-only guard**

In `backend/recommendation/intent.py`, replace lines 192-196:

```python
    max_price = parsed.get("max_price")
    if isinstance(max_price, (int, float)) and max_price > 0:
        if max_price < float(out.get("budget_max", 50.0)):
            out["budget_max"] = float(max_price)
            out["budget_min"] = min(float(out.get("budget_min", 10.0)), float(max_price))
    return out
```

with:

```python
    # A budget the user SAYS wins over whatever the request carried, in either
    # direction. The old `max_price < budget_max` guard existed because the
    # inventory fetch had already capped candidates at the slider max — but once
    # a budget is carried across turns that guard becomes a trap: "up to $200"
    # against a carried $60 is silently ignored, and a budget the user cannot
    # raise has no visible exit. The fetch-lag the guard protected against is
    # handled by the widen re-fetch in recommend.py instead.
    max_price = parsed.get("max_price")
    if isinstance(max_price, (int, float)) and max_price > 0:
        out["budget_max"] = float(max_price)
        out["budget_min"] = min(float(out.get("budget_min", 10.0)), float(max_price))
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run from `backend/`: `python3 -m pytest tests/test_intent.py -v`
Expected: PASS.

Then the full suite, because this changes a shared helper:
Run from `backend/`: `python3 -m pytest tests/ -m "not integration" -q`
Expected: all pass. If a test fails asserting the old tighten-only behavior, read it carefully — if it pins the guard itself, update it to the new contract and say so in the commit; if it pins something else, the change broke something real.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/intent.py backend/tests/test_intent.py
git commit -m "fix(intent): a spoken budget wins in either direction"
```

---

### Task 2: The oracle and availability strip use the resolved budget

`fetch_axis_counts` and `availability_lines` both read `req.budget_max`. On the turn a budget is spoken that value is still the wide sentinel, so the oracle counts everything as in-budget while the prompt says `$60` — the two disagree on the one turn it matters most.

**Files:**
- Modify: `backend/api/routers/recommend.py:443`, `backend/api/routers/recommend.py:763-764`
- Test: `backend/tests/test_availability.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_availability.py`:

```python
def test_effective_budget_prefers_the_resolved_value():
    """On the turn a budget is spoken, req.budget_max is still the wide
    sentinel. Counting 'in budget' against 10000 while the prompt says $60
    makes the oracle and the narrative disagree."""
    from api.routers.recommend import effective_budget_max
    assert effective_budget_max({"budget_max": 60.0}, 10000.0) == 60.0


def test_effective_budget_falls_back_to_the_request():
    from api.routers.recommend import effective_budget_max
    assert effective_budget_max({}, 50.0) == 50.0
    assert effective_budget_max({"budget_max": None}, 50.0) == 50.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run from `backend/`: `python3 -m pytest tests/test_availability.py -k effective_budget -v`
Expected: FAIL with `ImportError: cannot import name 'effective_budget_max'`.

- [ ] **Step 3: Add the helper and use it at both call sites**

In `backend/api/routers/recommend.py`, add near the other module-level helpers (just above `def _varietal_key`, around line 118):

```python
def effective_budget_max(resolved: Dict[str, Any], request_max: float) -> float:
    """The budget to count and render against.

    A budget spoken THIS turn lives only in `resolved` — `req.budget_max` is
    still whatever the client sent (the wide sentinel, in ASK mode). Counting
    against the request value would tell the user "12 in budget" while the
    narrative says $60.
    """
    value = resolved.get("budget_max")
    return float(value) if isinstance(value, (int, float)) else float(request_max)
```

Then at line 443, replace:

```python
    _axis_counts = fetch_axis_counts(supabase, _axes, nearby_ids, req.budget_max) if _axes else {}
```

with:

```python
    _axis_counts = fetch_axis_counts(
        supabase, _axes, nearby_ids, effective_budget_max(resolved, req.budget_max)) if _axes else {}
```

And at lines 763-764, replace:

```python
                        _lines = availability_lines(
                            resolved.get("availability_facts") or [], top, req.budget_max)
```

with:

```python
                        _lines = availability_lines(
                            resolved.get("availability_facts") or [], top,
                            effective_budget_max(resolved, req.budget_max))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run from `backend/`: `python3 -m pytest tests/test_availability.py -v && python3 -m pytest tests/ -m "not integration" -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/recommend.py backend/tests/test_availability.py
git commit -m "fix(recommend): count availability against the resolved budget"
```

---

### Task 3: Re-fetch when the budget widens

The breadth query at line 307 already ran with `req.budget_max`. When the user widens, the pool is capped at the old ceiling while the prompt claims the new one — a fresh availability mismatch of the items 39/40 kind.

**Files:**
- Modify: `backend/api/routers/recommend.py` (add `_widen_fetch` after `_constraint_fetch`, ends line ~565; wire into `event_gen` near line 660)
- Test: `backend/tests/test_candidate_filters.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_candidate_filters.py`:

```python
def test_budget_widened_detects_only_upward_moves():
    """Narrowing needs no re-fetch — the pool already holds everything under
    the lower ceiling. Only widening exposes wines the breadth query never
    retrieved."""
    from api.routers.recommend import budget_widened
    assert budget_widened({"budget_max": 200.0}, 60.0) is True
    assert budget_widened({"budget_max": 20.0}, 60.0) is False
    assert budget_widened({"budget_max": 60.0}, 60.0) is False
    assert budget_widened({}, 60.0) is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run from `backend/`: `python3 -m pytest tests/test_candidate_filters.py -k budget_widened -v`
Expected: FAIL with `ImportError: cannot import name 'budget_widened'`.

- [ ] **Step 3: Add the predicate**

In `backend/api/routers/recommend.py`, directly below `effective_budget_max` from Task 2:

```python
def budget_widened(resolved: Dict[str, Any], request_max: float) -> bool:
    """True when the user spoke a budget HIGHER than the one the fetch ran on.

    Only widening matters: the breadth query already retrieved everything at or
    below `request_max`, so narrowing is a scoring problem, while widening means
    the newly-affordable wines are simply absent from the pool.
    """
    value = resolved.get("budget_max")
    if not isinstance(value, (int, float)):
        return False
    return float(value) > float(request_max)
```

- [ ] **Step 4: Run the test to verify it passes**

Run from `backend/`: `python3 -m pytest tests/test_candidate_filters.py -k budget_widened -v`
Expected: PASS.

- [ ] **Step 5: Add the fetch helper**

In `backend/api/routers/recommend.py`, immediately after the `_constraint_fetch` function (it ends with `return [c for c in (_row_to_candidate(r) for r in rows) if c]` around line 565), add:

```python
    def _widen_fetch() -> list:
        """Nearby inventory in the band the breadth query never asked for.

        Breadth already fetched everything <= req.budget_max, so this asks only
        for the newly-affordable slice above it — cheaper than re-running the
        whole breadth query, and it merges cleanly."""
        def _q(since: Optional[str]) -> list:
            q = (supabase.table("retail_inventory").select(INVENTORY_SELECT)
                 .in_("store_ref", nearby_ids).eq("in_stock", True)
                 .gt("price", req.budget_max)
                 .lte("price", effective_budget_max(resolved, req.budget_max)))
            q = _apply_type_breadth_filter(q, breadth_types)
            if since:
                q = q.gte("last_scraped_at", since)
            return q.limit(200).execute().data or []

        rows = _q(stale_cutoff) or _q(None)
        return [c for c in (_row_to_candidate(r) for r in rows) if c]
```

- [ ] **Step 6: Wire it into the deep-fetch block**

In `backend/api/routers/recommend.py`, find:

```python
    top = _score_and_select(candidates)
    reason = deep_fetch_reason(resolved, top)
```

and replace with:

```python
    top = _score_and_select(candidates)
    reason = deep_fetch_reason(resolved, top)
    # A widened budget means the pool is capped at the OLD ceiling while the
    # prompt will claim the new one. Re-fetch before anything reads `top`.
    widened = budget_widened(resolved, req.budget_max)
```

Then inside `event_gen`, find:

```python
        if reason:
            yield "data: " + json.dumps(
                {"type": "status", "text": "Looking deeper into the cellar…"}) + "\n\n"
            try:
                if reason == "named":
```

and replace the first three lines so the status frame also covers a widen, and the widen runs first:

```python
        if reason or widened:
            yield "data: " + json.dumps(
                {"type": "status", "text": "Looking deeper into the cellar…"}) + "\n\n"
            try:
                if widened:
                    _wide = _widen_fetch()
                    if _wide:
                        candidates = merge_candidates(candidates, _wide)
                        top = _score_and_select(candidates)
                        logger.info("WIDEN FETCH | %.0f → %.0f | +%d rows",
                                    req.budget_max,
                                    effective_budget_max(resolved, req.budget_max),
                                    len(_wide))
                if reason == "named":
```

Add `nonlocal candidates` to the existing `nonlocal top` declaration at the top of `event_gen` so the reassignment sticks:

```python
    def event_gen():
        nonlocal top, candidates
```

- [ ] **Step 7: Run the full suite**

Run from `backend/`: `python3 -m pytest tests/ -m "not integration" -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/api/routers/recommend.py backend/tests/test_candidate_filters.py
git commit -m "fix(recommend): re-fetch when a spoken budget widens the ceiling"
```

---

### Task 4: Emit the budget SSE frame

**Files:**
- Modify: `backend/api/routers/recommend.py` (in `event_gen`, after the availability frame around line 768)
- Test: `backend/tests/test_recommend_api.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_recommend_api.py`:

```python
def test_budget_frame_payload_shape():
    """Emitted only when a budget was SPOKEN this turn. Silence is
    load-bearing: it stops the client pinning a value the user never said,
    which would make budget_is_stated() report a phantom budget."""
    from api.routers.recommend import budget_frame
    assert budget_frame({"max_price": 60}, {"budget_min": 0.0, "budget_max": 60.0}) == \
        {"type": "budget", "min": 0.0, "max": 60.0}


def test_no_budget_frame_when_none_was_spoken():
    from api.routers.recommend import budget_frame
    assert budget_frame({}, {"budget_min": 0.0, "budget_max": 10000.0}) is None
    assert budget_frame(None, {"budget_min": 0.0, "budget_max": 10000.0}) is None
    assert budget_frame({"max_price": None}, {"budget_min": 0.0, "budget_max": 50.0}) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run from `backend/`: `python3 -m pytest tests/test_recommend_api.py -k budget_frame -v`
Expected: FAIL with `ImportError: cannot import name 'budget_frame'`.

- [ ] **Step 3: Add the builder**

In `backend/api/routers/recommend.py`, directly below `budget_widened`:

```python
def budget_frame(parsed: Optional[Dict[str, Any]],
                 resolved: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The SSE frame telling the client what budget to carry forward.

    Returns None unless the user SPOKE a budget this turn. A turn that says
    nothing about money must leave the client's budget exactly as it was —
    emitting the resolved value unconditionally would pin the wide sentinel as
    a real budget and break `budget_is_stated()`.
    """
    max_price = (parsed or {}).get("max_price")
    if not isinstance(max_price, (int, float)) or max_price <= 0:
        return None
    return {"type": "budget",
            "min": float(resolved.get("budget_min") or 0.0),
            "max": float(resolved.get("budget_max") or max_price)}
```

- [ ] **Step 4: Emit it in the stream**

In `event_gen`, immediately after the availability-frame `try/except` block (which ends with a bare `except Exception: pass` around line 770) and before `yield "data: [DONE]\n\n"`, add:

```python
                # Carry the spoken budget to the client so the NEXT request
                # sends it as a real budget_max (item #8 / multi-turn state).
                _bframe = budget_frame(parsed, resolved)
                if _bframe:
                    yield "data: " + json.dumps(_bframe) + "\n\n"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run from `backend/`: `python3 -m pytest tests/ -m "not integration" -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/recommend.py backend/tests/test_recommend_api.py
git commit -m "feat(recommend): emit a budget frame when one is spoken"
```

---

### Task 5: `apiReq` becomes React state

It is currently destructured straight from router navigation state, so nothing can update it mid-conversation.

**Files:**
- Modify: `frontend/src/screens/ChatRecommend.jsx:167` and the two `{...apiReq}` spreads (lines ~230, ~409), plus the two `chatState`/`navigate` sites (lines ~552, ~559)

- [ ] **Step 1: Convert to state**

At line 167, replace:

```jsx
  const { prefs, apiReq, reqId, _restored: _restoredNav } = state ?? {};
```

with:

```jsx
  const { prefs, apiReq: apiReqNav, reqId, _restored: _restoredNav } = state ?? {};
  // A budget spoken mid-conversation has to update the request, so this can no
  // longer be a plain read of navigation state. Seeded from nav state, then
  // owned here; it already rides chatState + the patched history entry, so
  // item-38 browser-back and the sessionStorage restore keep working.
  const [apiReq, setApiReq] = useState(apiReqNav);
```

- [ ] **Step 2: Verify no other consumer broke**

Run from `frontend/`: `grep -n "apiReq" src/screens/ChatRecommend.jsx`
Expected: every remaining use is either `{...apiReq}` (unchanged — still reads the current value) or `apiReq` inside `chatState` / `navigate` state. If any line still reads `apiReqNav`, that is a bug — only the `useState` seed should.

- [ ] **Step 3: Run the frontend suite**

Run from `frontend/`: `npx vitest run`
Expected: all pass. No behavior has changed yet — this task only makes the value mutable.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/screens/ChatRecommend.jsx
git commit -m "refactor(chat): make apiReq stateful so a spoken budget can update it"
```

---

### Task 6: Handle the budget frame in the client

**Files:**
- Modify: `frontend/src/screens/ChatRecommend.jsx` (SSE handler, beside the `availability` branch around line 324)
- Test: `frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx`:

```jsx
import { applyBudgetFrame } from '../ChatRecommend';

describe('budget frame', () => {
  it('replaces the carried budget in either direction', () => {
    expect(applyBudgetFrame({ budget_min: 0, budget_max: 10000 },
                            { type: 'budget', min: 0, max: 60 }))
      .toEqual({ budget_min: 0, budget_max: 60 });
    expect(applyBudgetFrame({ budget_min: 0, budget_max: 60 },
                            { type: 'budget', min: 0, max: 200 }))
      .toEqual({ budget_min: 0, budget_max: 200 });
  });

  it('leaves the request untouched on a malformed frame', () => {
    const req = { budget_min: 0, budget_max: 60 };
    expect(applyBudgetFrame(req, { type: 'budget' })).toBe(req);
    expect(applyBudgetFrame(req, { type: 'budget', max: null })).toBe(req);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run from `frontend/`: `npx vitest run src/screens/__tests__/ChatRecommendAsk.test.jsx`
Expected: FAIL — `applyBudgetFrame` is not exported.

- [ ] **Step 3: Add the pure helper and export it**

In `frontend/src/screens/ChatRecommend.jsx`, near the other module-level helpers at the top of the file (above the component), add:

```jsx
// Pure so it can be tested without mounting the screen. Returns the SAME object
// when the frame is unusable, so a malformed frame can never blank a budget the
// user actually set.
export function applyBudgetFrame(req, frame) {
  const max = frame?.max;
  if (typeof max !== 'number' || !(max > 0)) return req;
  const min = typeof frame.min === 'number' ? frame.min : (req.budget_min ?? 0);
  return { ...req, budget_min: min, budget_max: max };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run from `frontend/`: `npx vitest run src/screens/__tests__/ChatRecommendAsk.test.jsx`
Expected: PASS.

- [ ] **Step 5: Wire it into the SSE handler**

In the event handler, directly after the closing brace of the `else if (event.type === 'availability') { ... }` branch (around line 336), add:

```jsx
        } else if (event.type === 'budget') {
          // The user said a number out loud. Carry it so the NEXT request sends
          // a real budget_max instead of the wide sentinel — that is what makes
          // the fetch, scorer, oracle and prompt agree from turn 2 on.
          setApiReq(prev => applyBudgetFrame(prev, event));
```

- [ ] **Step 6: Run the frontend suite**

Run from `frontend/`: `npx vitest run`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/screens/ChatRecommend.jsx frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx
git commit -m "feat(chat): carry a spoken budget into the next request"
```

---

### Task 7: End-to-end acceptance

The codebase's convention is a `scripts/verify_*.py` replay per landed behavior (see `verify_referent_carry.py`, `verify_store_filter.py`).

**Files:**
- Create: `backend/scripts/verify_budget_carry.py`

- [ ] **Step 1: Write the script**

Create `backend/scripts/verify_budget_carry.py`:

```python
"""Acceptance replay for multi-turn budget state (audit item #8).

Run a local server first:
    cd backend && python3 -m uvicorn api.main:app --port 8077
Then, from backend/:
    python3 scripts/verify_budget_carry.py

Uses zip 78258, where Overture is stocked at $169.99-$225 (verified 2026-09-01).
"""
import json
import sys
import urllib.request

URL = "http://127.0.0.1:8077/api/recommend"
ZIP = "78258"


def ask(message, history=None, budget_max=10000):
    req = {"zip_code": ZIP, "budget_min": 0, "budget_max": budget_max,
           "style_preferences": [], "avoid": [], "message": message,
           "conversational": False, "taste": None}
    if history:
        req["conversation_history"] = history
    r = urllib.request.Request(URL, data=json.dumps(req).encode(),
                               headers={"Content-Type": "application/json"})
    narrative, picks, budget = "", [], None
    with urllib.request.urlopen(r, timeout=180) as resp:
        for raw in resp:
            line = raw.decode().strip()
            if not line.startswith("data: ") or line[6:] == "[DONE]":
                continue
            ev = json.loads(line[6:])
            if ev.get("type") == "token":
                narrative += ev.get("text", "")
            elif ev.get("type") == "pick":
                picks.append(ev.get("pick") or {})
            elif ev.get("type") == "budget":
                budget = ev
    return narrative, picks, budget


def main() -> int:
    t1 = "I'm looking for a bottle of red, my budget is $60"
    n1, p1, b1 = ask(t1)
    print(f"TURN 1 | budget frame: {b1}")
    assert b1 and b1["max"] == 60.0, f"expected a $60 budget frame, got {b1}"
    assert all((x.get("price") or 0) <= 60 for x in p1), \
        f"picks exceeded the stated budget: {[x.get('price') for x in p1]}"

    hist = [{"role": "user", "content": t1},
            {"role": "assistant", "content": n1,
             "picks": [{"wine_id": x.get("wine_id"), "name": x.get("name")} for x in p1]}]

    # The client would have stored the frame; replay that by sending it back.
    n2, p2, _ = ask("Do you carry Overture?", hist, budget_max=b1["max"])
    has_overture = any("overture" in (x.get("name") or "").lower() for x in p2)
    print(f"TURN 2 | overture in picks: {has_overture}")
    print(f"TURN 2 | narrative: {n2.strip()[:200]}")
    assert not has_overture, \
        "Overture ($195-$210) surfaced against a carried $60 budget — the budget did not carry"

    n3, p3, b3 = ask("actually, let's splurge — up to $250", hist, budget_max=60)
    print(f"TURN 3 | budget frame: {b3}")
    assert b3 and b3["max"] == 250.0, f"a widened budget was not applied: {b3}"
    assert any((x.get("price") or 0) > 60 for x in p3), \
        f"widening returned only sub-$60 wines — the re-fetch did not run: " \
        f"{[x.get('price') for x in p3]}"

    print("OK — budget carries, constrains turn 2, and widens with a re-fetch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it against a local server**

In one shell, from `backend/`: `python3 -m uvicorn api.main:app --port 8077`
In another, from `backend/`: `python3 scripts/verify_budget_carry.py`
Expected: `OK — budget carries, constrains turn 2, and widens with a re-fetch`

If turn 2 still shows Overture, the client echo is not reaching `req.budget_max` — check Task 4's frame is emitted and Task 6 wires it. If turn 3 returns only sub-$60 wines, the widen re-fetch in Task 3 did not run — check `budget_widened` and the `nonlocal candidates`.

- [ ] **Step 3: Stop the server and commit**

```bash
pkill -f "uvicorn api.main:app --port 8077"
git add backend/scripts/verify_budget_carry.py
git commit -m "test: acceptance replay for multi-turn budget state"
```

---

### Task 8: Update the roadmap

**Files:**
- Modify: `CLAUDE.md` (What's Next), `docs/recommendation-architecture-audit.md:183`

- [ ] **Step 1: Mark audit item #8 done**

In `docs/recommendation-architecture-audit.md`, line 183, prefix the row's description with `✅ DONE 2026-09-02 (budget only) — ` and add a trailing sentence: `region/wine_type/grapes/avoid deliberately not carried; see docs/superpowers/specs/2026-09-02-multi-turn-budget-state-design.md.`

- [ ] **Step 2: Add a roadmap entry**

In `CLAUDE.md`, add to the "What's Next" list, following the existing numbered style:

```markdown
50. ✅ **Multi-turn budget state** — a budget stated in chat survives the turn (audit item #8). ASK mode always sent the `budget_max: 10000` sentinel and `parse_message` reads only the current message, so a spoken "$60" vanished on turn 2 while the system prompt told the model to carry it — backend and model disagreed from turn 2 on. Backend now emits a `budget` SSE frame when a budget is spoken; `ChatRecommend` stores it into `apiReq` and echoes it, so `req.budget_max` becomes truthful and fetch/scorer/oracle/prompt agree. A spoken number wins in EITHER direction (the tighten-only guard became a trap once budgets carried: "up to $200" against a carried $60 evaluated `200 < 60` and was silently ignored), and a widen triggers a targeted re-fetch because the breadth query already ran at the old ceiling. Also fixed: the oracle counted "in budget" against `req.budget_max`, so on the speaking turn it counted against 10000 while the prompt said $60. Scope is budget ONLY — region/grape/type/avoid stay per-turn, because that is where the audit's "stuck in a stale filter" risk lives and a stale budget is at least visible in the answer's prices. Acceptance: `scripts/verify_budget_carry.py`.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/recommendation-architecture-audit.md
git commit -m "docs: multi-turn budget state landed (audit item #8)"
```

---

## Verification checklist

- [ ] `cd backend && python3 -m pytest tests/ -m "not integration" -q` — all pass
- [ ] `cd frontend && npx vitest run` — all pass
- [ ] `cd backend && python3 scripts/verify_budget_carry.py` (with a local server) — OK
- [ ] Turn 2 of the replay does **not** surface Overture. This is a deliberate reversal: today it does, and that is the bug.
