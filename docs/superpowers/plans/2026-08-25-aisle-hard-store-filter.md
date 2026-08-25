# Aisle-Mode Hard Store Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In aisle mode, when the user has picked a store, recommend ONLY wines on that store's shelves — never a wine exclusive to a different store — and when the store has no strong fit, say so honestly and offer to check nearby stores, which the user accepts through the chat (never auto-cross-store). Fixes CLAUDE.md item 44.

**Architecture:** The picked store already reaches the backend as the structured `store_ref` (item 37b), resolved to `detected_store`, but is only used to *sort* rows — never to *filter*, and the prompt is never told which store the user is in. This adds a hard filter at the single scoring choke point (`_score_and_select`, which sees the breadth pool AND every deep-fetch merge), passes the standing store into the prompt as a stated fact with an in-store directive, and — because "widen to nearby" is just the frontend re-sending the same question WITHOUT `store_ref` — needs no backend widen flag. The frontend adds a "Check nearby stores" affordance (modeled on the existing no-card-closer offer) that re-sends the last question widened for one turn; the store scope persists in state for the next turn.

**Tech Stack:** Python 3.9 (`Optional[str]`, never `str | None`) + FastAPI + pytest (run from `backend/`); React 19 + vitest/@testing-library (run from `frontend/`).

## Global Constraints

- **Python 3.9** — `Optional[str]` from `typing`, not `str | None`.
- **Run backend tests from `backend/`**: `python3 -m pytest tests/ -m "not integration" -q`. **Run frontend tests from `frontend/`**: `npx vitest run`.
- **Hard filter is a HARD exclusion** — like `avoid`, it must be visible: log how many rows it drops, and it must **fail open only in a controlled way** (see Task 1 — an empty store pool is the honest "store has nothing" signal, NOT a reason to widen silently).
- **Frontend: no hardcoded hexes** — CSS variables only; conversational surfaces keep soft radius; the affordance mirrors the existing `offerButtons` styling.
- **Voice:** the in-store directive text and any copy is knowledgeable-friend, addresses the user as "you", app speaks as "I"; never "error"/"no results found".
- TDD every unit; commit after each task; `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` on commits.

**Out of scope / deferred:** a persistent always-visible "check nearby" link (the affordance is shown on store-scoped answers only); a structured `store_scoped` SSE flag (the frontend already knows it sent `storeRef`, so no backend schema change); desktop aisle layout.

---

### Task 1: Backend — hard-filter the candidate pool to the picked store

**Files:**
- Modify: `backend/recommendation/candidate_filters.py` (add `filter_to_store`)
- Modify: `backend/api/routers/recommend.py` (call it inside `_score_and_select`; drop the now-redundant post-sort)
- Test: `backend/tests/test_candidate_filters.py` (append)

**Interfaces:**
- Consumes: candidate dicts carry `store_ref` (the store UUID) — set in `_row_to_candidate` (`recommend.py`).
- Produces: `filter_to_store(candidates, store_id) -> List[dict]` — keeps only rows whose `store_ref == store_id`. Pure, no I/O.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_candidate_filters.py`:

```python
# ---- item 44: hard store filter (aisle mode) ----

from recommendation.candidate_filters import filter_to_store


def test_filter_to_store_keeps_only_that_store():
    cands = [
        {"wine_id": "w1", "store_ref": "s1", "name": "In-store red"},
        {"wine_id": "w2", "store_ref": "s2", "name": "Other-store red"},
        {"wine_id": "w1", "store_ref": "s1", "name": "In-store red (dup row)"},
    ]
    out = filter_to_store(cands, "s1")
    assert [c["store_ref"] for c in out] == ["s1", "s1"]
    assert all(c["store_ref"] == "s1" for c in out)


def test_filter_to_store_empty_when_store_absent():
    # An empty result is the honest "store has nothing" signal — do NOT fail open here.
    cands = [{"wine_id": "w2", "store_ref": "s2"}]
    assert filter_to_store(cands, "s1") == []


def test_filter_to_store_noop_on_falsy_store():
    cands = [{"wine_id": "w1", "store_ref": "s1"}]
    assert filter_to_store(cands, None) == cands
```

- [ ] **Step 2: Run it, watch it fail**

Run: `cd backend && python3 -m pytest tests/test_candidate_filters.py -k filter_to_store -q`
Expected: ImportError / fail — `filter_to_store` does not exist.

- [ ] **Step 3: Implement the helper**

Add to `backend/recommendation/candidate_filters.py` (near `merge_candidates`):

```python
def filter_to_store(candidates: List[Dict[str, Any]],
                    store_id: Optional[str]) -> List[Dict[str, Any]]:
    """Keep only rows on the given store's shelves — the aisle-mode HARD filter
    (item 44). A wine exclusive to another store must never surface to someone
    standing in this one. No-op on a falsy store_id. An empty result is the
    honest 'this store has nothing' signal — the caller must NOT silently widen."""
    if not store_id:
        return candidates
    return [c for c in candidates if c.get("store_ref") == store_id]
```

- [ ] **Step 4: Wire it into the scoring choke point**

In `backend/api/routers/recommend.py`, inside `_score_and_select(pool)`, at the very top of the function body (before `score_candidates`), add the hard filter so it catches the breadth pool AND every deep-fetch merge:

```python
    def _score_and_select(pool: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Aisle-mode hard filter (item 44): a picked store means the user is
        # standing there — only its shelves are eligible. Applied here (the one
        # scoring choke point) so breadth + every deep-fetch path is covered.
        if detected_store:
            before = len(pool)
            pool = filter_to_store(pool, detected_store["id"])
            logger.info("STORE FILTER | %s → %d/%d candidates",
                        detected_store.get("name"), len(pool), before)
        scored = score_candidates(resolved, pool)
        ...
```

Then DELETE the now-redundant post-sort block (every survivor is already in-store):

```python
        if detected_store:
            sel.sort(key=lambda w: (w.get("store_ref") == detected_store["id"],
                                    w.get("_score", 0)), reverse=True)
```

Add the import: in the `from recommendation.candidate_filters import (...)` block, add `filter_to_store`.

- [ ] **Step 5: Run the helper tests + full fast suite**

Run: `cd backend && python3 -m pytest tests/test_candidate_filters.py -k filter_to_store -q` → pass.
Run: `python3 -m pytest tests/ -m "not integration" -q` → all green (the removed post-sort has no dedicated test; `test_recommend_api` must stay green).

- [ ] **Step 6: Commit**

```bash
git add backend/recommendation/candidate_filters.py backend/api/routers/recommend.py backend/tests/test_candidate_filters.py
git commit -m "feat(aisle): hard-filter the shortlist to the picked store (item 44)"
```

---

### Task 2: Backend — tell the prompt the standing store + in-store directive

**Files:**
- Modify: `backend/api/routers/recommend.py` (set `resolved["standing_store"]`)
- Modify: `backend/recommendation/claude_client.py` (`_build_user_message`: render the in-store directive)
- Test: `backend/tests/test_claude_client.py` (append)

**Interfaces:**
- Consumes: `intent["standing_store"]` — the picked store's display name (str) or None.
- Produces: when set, `_build_user_message` emits an in-store directive naming the store, stating every listing is on its shelves, and requiring an honest "no strong fit → offer to check nearby" instead of a weak pad.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_claude_client.py`:

```python
# ---- item 44: in-store directive ----

def test_standing_store_directive_present_and_named():
    from recommendation.claude_client import _build_user_message
    intent = {"flavors": [], "avoid": [], "grapes": [],
              "budget_min": 10.0, "budget_max": 50.0,
              "message": "a red for pizza",
              "standing_store": "Geraldine's Natural Wines"}
    msg = _build_user_message([], intent)
    assert "Geraldine's Natural Wines" in msg
    assert "on their shelves" in msg.lower() or "on its shelves" in msg.lower()
    assert "nearby" in msg.lower()          # the honest thin-store offer


def test_no_standing_store_directive_when_absent():
    from recommendation.claude_client import _build_user_message
    intent = {"flavors": [], "avoid": [], "grapes": [],
              "budget_min": 10.0, "budget_max": 50.0, "message": "a red for pizza"}
    msg = _build_user_message([], intent)
    assert "standing in" not in msg.lower()
```

- [ ] **Step 2: Run it, watch it fail**

Run: `cd backend && python3 -m pytest tests/test_claude_client.py -k standing_store -q`
Expected: fail — no such directive.

- [ ] **Step 3: Set the fact in the router**

In `backend/api/routers/recommend.py`, right after `detected_store` is resolved (just after the `if req.store_ref and detected_store ...` log line, ~line 425):

```python
    resolved["standing_store"] = detected_store["name"] if detected_store else None
```

- [ ] **Step 4: Render the directive**

In `backend/recommendation/claude_client.py` `_build_user_message`, near the other directive blocks (e.g. after `comparison_directive`), add:

```python
    store_directive = ""
    standing = intent.get("standing_store")
    if standing:
        store_directive = (
            f"\n\nThe user is standing in {standing} and wants to buy right now. "
            f"EVERY wine listed below is on {standing}'s shelves — recommend only from "
            f"this list, and never suggest a bottle that isn't here. If none is a strong "
            f"match for what they asked, say so plainly (name the closest thing on the "
            f"shelf if there is one) and offer to check nearby stores — e.g. \"{standing} "
            f"doesn't have a great match for that; want me to check nearby stores?\" — "
            f"rather than padding with a weak pick. Do not leave {standing} unless the user "
            f"asks you to."
        )
```

Then interpolate `{store_directive}` into the returned message string (alongside `{comparison_directive}` / `{fact_block}`).

- [ ] **Step 5: Run tests**

Run: `cd backend && python3 -m pytest tests/test_claude_client.py -q` → pass. Then full fast suite green.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/recommend.py backend/recommendation/claude_client.py backend/tests/test_claude_client.py
git commit -m "feat(aisle): pass the standing store into the prompt + honest thin-store offer (item 44)"
```

---

### Task 3: Frontend — "Check nearby stores" affordance + widened re-send

**Files:**
- Modify: `frontend/src/screens/ChatRecommend.jsx`
- Test: `frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx` (append)

**Interfaces:**
- Consumes: `buildAskReq({..., storeRef})` — omitting `storeRef` produces a request with no `store_ref`, which the backend reads as "no store scope" (widen).
- Produces: on a store-scoped answer (an ask-mode sommelier turn while `storeRef` is set), a "Check nearby stores" action; tapping it re-sends the **last user question** with `storeRef` omitted for that one turn (the `storeRef` state stays set for subsequent turns).

Mechanics (in ChatRecommend.jsx):
- Track the last real question: `handleAskSend(text)` already appends the user message. Add a ref `lastAskTextRef` set to `text` in `handleAskSend` (and in `confirmZip`'s send).
- Mark store-scoped sommelier turns: when `storeRef` is set at send time, the answer that comes back should carry the affordance. Simplest: tag the sommelier message. In `callRecommend`, the sommelier message is created on first token; capture whether this run was store-scoped via a closure boolean `const scoped = askMode && !!storeRef;` set at call time, and after the run attach `storeScoped: scoped` to the last sommelier message in the `finally` (only when it produced picks). To keep it simple and robust, gate the affordance in render on `askMode && storeRef && m.role === 'sommelier' && m.picks?.length`.
- The affordance (render under a store-scoped sommelier message, modeled on `offerButtons`):

```jsx
  const checkNearby = (m) => askMode && storeRef && m.role === 'sommelier' && m.picks?.length ? (
    <button onClick={() => {
      const q = lastAskTextRef.current;
      if (!q) return;
      const history = historyFrom(messages);
      setMessages(prev => [...prev, { id: uuid(), role: 'user', text: 'Check nearby stores' }]);
      tasteFor().then(taste => callRecommend(buildAskReq({
        zip: askZip, message: q, history, conversational: naturalChatMode(), taste,
        // storeRef intentionally omitted → backend widens for this one turn
      })));
    }}
      style={{ marginTop: 8, cursor: 'pointer', background: 'none', color: 'var(--bordeaux)',
        border: '1.5px solid var(--bordeaux)', fontFamily: 'var(--font-sans)', fontSize: 12,
        padding: '7px 13px' }}>
      Check nearby stores
    </button>
  ) : null;
```

- Render `{checkNearby(m)}` in both the mobile and desktop message maps, right after `{offerButtons(m)}` (same spots).

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx`:

```jsx
describe('hard store filter — check nearby (item 44)', () => {
  it('offers Check nearby stores on a store-scoped answer and widens on tap', async () => {
    const { getNearbyStores } = await import('../../lib/api.js');
    getNearbyStores.mockResolvedValue({ zip: '78209', stores: [
      { id: 's1', retailer_name: "Geraldine's", name: "Geraldine's Natural Wines", address: 'x', distance_miles: 0 },
    ] });
    streamRecommend
      .mockImplementationOnce(async function* () {
        yield { type: 'token', text: "Here's the best on Geraldine's shelves." };
        yield { type: 'picks', picks: [{ wine_id: 'w1', name: 'COS Cerasuolo', price: 30, retailer: "Geraldine's", why: 'In store.' }], session_id: 's' };
      })
      .mockImplementationOnce(async function* () {
        yield { type: 'token', text: 'Looking wider.' };
        yield { type: 'picks', picks: [{ wine_id: 'w2', name: 'Torbreck Shiraz', price: 40, retailer: 'Twin Liquors', why: 'Nearby.' }], session_id: 's2' };
      });
    renderAsk({ mode: 'ask', openStorePicker: true });
    await screen.findByText("Geraldine's Natural Wines");
    await userEvent.click(screen.getByText("Geraldine's Natural Wines"));   // pick the store
    await userEvent.type(screen.getAllByRole('textbox')[0], 'a red for pizza{Enter}');
    await screen.findByText('COS Cerasuolo');
    // first request carried the store scope
    expect(streamRecommend.mock.calls[0][0].store_ref).toBe('s1');
    // the affordance appears; tapping it re-sends the question WITHOUT store_ref
    await userEvent.click(screen.getByText('Check nearby stores'));
    await screen.findByText('Torbreck Shiraz');
    const widened = streamRecommend.mock.calls[1][0];
    expect(widened.store_ref).toBeUndefined();
    expect(widened.message).toBe('a red for pizza');
  });

  it('does not show Check nearby stores when no store is picked', async () => {
    streamRecommend.mockImplementation(async function* () {
      yield { type: 'token', text: 'Ok.' };
      yield { type: 'picks', picks: [{ wine_id: 'w1', name: 'Some Red', price: 20, retailer: 'H-E-B', why: 'x' }], session_id: 's' };
    });
    renderAsk();
    await userEvent.type(screen.getAllByRole('textbox')[0], 'a red for pizza{Enter}');
    await screen.findByText('Some Red');
    expect(screen.queryByText('Check nearby stores')).toBeNull();
  });
});
```

- [ ] **Step 2: Run, watch fail**

Run: `cd frontend && npx vitest run src/screens/__tests__/ChatRecommendAsk.test.jsx -t "Check nearby"`
Expected: fail — no affordance; widened call not made.

- [ ] **Step 3: Implement** the `lastAskTextRef`, the `checkNearby` render helper, and wire `{checkNearby(m)}` into both message maps per the mechanics above. (`historyFrom`, `buildAskReq`, `naturalChatMode`, `tasteFor`, `askZip`, `storeRef` are all already in scope.)

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run src/screens/__tests__/ChatRecommendAsk.test.jsx` → pass. Then full `npx vitest run` → green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/screens/ChatRecommend.jsx frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx
git commit -m "feat(aisle): Check nearby stores affordance widens one turn on accept (item 44)"
```

---

### Task 4: Fix the store-picker copy + docs

**Files:**
- Modify: `frontend/src/screens/ChatRecommend.jsx` (store-picker bubble copy)
- Modify: `CLAUDE.md` (flip item 44 to ✅), `docs/reference/recommendation.md` (short note)
- Test: `frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx` — the existing store-picker test asserts the footnote text; update it.

**Interfaces:** none (copy + docs).

- [ ] **Step 1: Find and update the failing assertion**

The store-picker test asserts the old footnote. Grep it:
`cd frontend && grep -rn "soft filter, not a cage" src/`
Update the assertion in `ChatRecommendAsk.test.jsx` (store picker describe block) from the old copy to the new copy string below, then run it to watch it fail against the unchanged component.

- [ ] **Step 2: Rewrite the copy**

In `ChatRecommend.jsx` store-picker bubble, replace:

```
Store is a soft filter, not a cage — I'll still name a better bottle down the road if there is one.
```

with:

```
I'll keep to what's on their shelves. If they don't have a great match, I'll say so and you can send me to check nearby.
```

- [ ] **Step 3: Run the frontend suite** → green.

- [ ] **Step 4: Flip the docs**

In `CLAUDE.md`, change item 44 from `⬜` to `✅` and append a landed-note: hard filter at `_score_and_select` via `filter_to_store`, `standing_store` prompt fact + honest thin-store offer, frontend "Check nearby stores" one-turn widen (re-send without `store_ref`), corrected picker copy. Add a one-paragraph note to `docs/reference/recommendation.md` under the aisle-mode section.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/screens/ChatRecommend.jsx frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx CLAUDE.md docs/reference/recommendation.md
git commit -m "docs+copy(aisle): item 44 hard store filter — corrected picker copy + docs"
```

---

### Task 5: End-to-end verification

- [ ] **Step 1:** `cd backend && python3 -m pytest tests/ -m "not integration" -q` → green. `cd frontend && npx vitest run` → green.
- [ ] **Step 2 (live, optional but recommended):** boot backend (`RATE_LIMITS_OFF=1 uvicorn api.main:app`), reproduce the item-44 case against live 78209 data with a script mirroring `verify_comparison_fetch.py`: resolve Geraldine's store_ref, confirm a store-scoped fetch → `_score_and_select` yields ONLY Geraldine's rows (assert no other `store_ref` survives), and that omitting the store widens the pool. Save as `backend/scripts/verify_store_filter.py`.
- [ ] **Step 3: Commit** the acceptance script; push the branch and open a PR.

---

## Self-Review Notes

- **Spec coverage:** hard filter (T1) → the core bug; prompt fact + thin-store honesty (T2); accept-through-chat widen without auto-cross-store (T3 — widen only fires on explicit tap, re-sending without `store_ref`); corrected copy + docs (T4). The user's rule "no cross-store without explicitly asking" is structurally enforced: cross-store is only reachable by omitting `store_ref`, which only the affordance does.
- **Type consistency:** `filter_to_store(candidates, store_id)` signature matches its one call site; `standing_store` (str|None) set in router, read in prompt; `storeRef` omitted (not nulled) on widen so `buildAskReq`'s `if (storeRef)` guard drops the field.
- **One-turn widen, not permanent:** the `storeRef` React state is untouched by the affordance, so the next typed question re-applies the store scope — matches "you're still in the store."
- **Failure mode:** if the picked store genuinely has zero candidates, `_score_and_select` returns `[]` → the existing no-pick/closer path + the prompt's honest-offer directive handle it; we never silently widen.
