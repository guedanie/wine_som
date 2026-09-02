# Multi-Turn Budget State (Design)

**Date:** 2026-09-02
**Source:** `docs/recommendation-architecture-audit.md` item #8 ("Multi-turn intent state").
Found in the field 2026-09-01 while investigating a separate report (the Overture bug,
which turned out to be `detect_store`, not budget — see commit `a075226`).

## Problem

A budget stated in chat is silently discarded after one turn, while the model is
simultaneously instructed to remember it. Backend and model then disagree about the
budget from turn 2 onward.

Three independent facts combine to produce this:

1. **`api/routers/recommend.py:410`** — `parse_message(req.message)` reads **only the
   current message**. Nothing in the parse sees conversation history, so a budget stated
   on turn 1 is invisible on turn 2.
2. **`frontend/src/lib/askMode.js:7`** — the ASK face always sends
   `budget_min: 0, budget_max: 10000`, the wide sentinel. It is never updated by anything
   the user says, so `req.budget_max` is a standing lie on that face.
3. **`recommendation/claude_client.py:121`** — the system prompt says *"Carry context
   across turns. If the user revealed budget, style, or location earlier, apply it — don't
   ask again."* The model obeys; the backend does not.

Everything downstream reads `req.budget_max` faithfully — the SQL fetch, the scorer's
budget axis, `fetch_axis_counts` in the availability oracle, and the prompt's `Budget:`
line via `budget_is_stated()`. All four are therefore correct code operating on a false
input. This is the same shape as items 39/40/44: the machinery is right, the fact it is
given is wrong.

### Verified behavior (live, 2026-09-01)

Reproduced against the local API on prod inventory, zip 78258:

| Turn | Message | `req.budget_max` | Result |
|---|---|---|---|
| 1 | "I'm looking for a bottle of red, my budget is $60" | 10000 | Correct — picks $52–$55, narrative says "your $60 window" |
| 2 | "Do you carry Overture?" | 10000 | **Surfaces Overture at $194.99 and $209.99** — the $60 is gone |

With a *filter*-set budget of $60 the same turn-2 question correctly answers: *"Overture is
available — 6 bottles nearby across H-E-B and Spec's — but all 6 land between $195–$210,
which puts them outside your $60 budget."* The machinery works; it just never learns the
spoken number.

## Scope

**Budget only.** `budget_min` / `budget_max` and nothing else.

Deliberately excluded: `region`, `wine_type`, `grapes`, `avoid`, `flavors`. The audit flags
the risk as *"needs explicit reset semantics or users get stuck in a stale filter"*, and
that risk is concentrated in exactly those fields — a carried region silently narrows every
later turn with no visible signal. `avoid` is worse still: it is a hard exclusion, and a
carried bogus avoid is precisely the invisible-and-catastrophic failure `drop_bogus_avoid`
exists to prevent (item 40).

Budget is the safe one to carry because **a stale budget is visible in the answer's prices**.
The user sees $40 bottles when they wanted $200 and says so. There is no equivalent tell for
a stale region.

Consequence, stated plainly: audit items #2–#6 continue to apply only to turn 1 for the
place/style axes. Carrying those is a separate design.

## Reset semantics

**A budget the user states out loud always wins, in either direction.**

`merge_intent` currently only ever tightens:

```python
if max_price < float(out.get("budget_max", 50.0)):
    out["budget_max"] = float(max_price)
```

That guard exists for the slider path — its docstring notes the inventory fetch already
capped candidates at the slider max, so widening past it would promise wines that were never
retrieved. That reasoning is sound for the slider and wrong for speech.

Carrying a budget forward makes the guard actively harmful: with $60 carried, "actually,
let's splurge — up to $200" evaluates `200 < 60` → false → the budget stays $60, with no
error and no way for the user to tell. A budget the user cannot raise is a trap with no
visible exit, which is the audit's stale-filter outcome arriving by a different road.

So: a spoken `max_price` replaces the carried value up or down.

This also removes the need for a magic reset phrase. The escape hatch is saying a different
number, which users do without being taught.

### The widening fetch-lag, and why it needs a re-fetch

Removing the guard exposes the problem the guard was protecting against. The inventory fetch
runs on `req.budget_max` **before** `merge_intent` resolves the spoken number. So on the turn
where the user says "up to $200" with $60 carried, the candidate pool is already capped at
$60 while the prompt would claim a $200 budget — every listing under the old ceiling, with a
narrative promising the new one. That is a fresh availability mismatch of exactly the kind
items 39/40 exist to eliminate, and shipping the widen without handling it would trade one
bug for another.

**Resolution: a budget-widen triggers a targeted re-fetch**, reusing the established
deep-fetch pattern. `deep_fetch_reason` already returns `"weak"` when a stated constraint
went unmet by the breadth pool, and `_constraint_fetch` already re-queries nearby inventory
honoring budget. A widen is the same situation — a stated constraint the current pool cannot
satisfy — so it gets the same treatment: re-query the nearby pool at the new ceiling, merge
via `merge_candidates`, and re-score. This runs inside the existing SSE `status` frame
("Looking deeper into the cellar…"), so the user sees why the turn takes a beat longer.

Narrowing needs no re-fetch: the pool already contains everything under the new, lower
ceiling, and the scorer plus the budget axis handle the rest.

## Mechanism

The carried budget lives **client-side, echoed back on the next request** — the same shape
item 41 used for prior picks (backend emits → client attaches → backend reads back).

```
turn N    user says "$60"
          parse_message      → max_price = 60
          merge_intent       → resolved budget_max = 60   (spoken wins)
          SSE frame          → {"type": "budget", "min": 0, "max": 60}
          ChatRecommend      → stores into apiReq state

turn N+1  request carries budget_max = 60 as a real value
          fetch / scorer / oracle / prompt all agree
```

**Why not the alternatives.** Re-deriving from `conversation_history` means either a Haiku
re-parse per follow-up (latency and cost on every turn) or a regex over prose, which is the
brittle string-matching this codebase avoids elsewhere. A real server-side session store is
the most "correct" option and would serve future state beyond budget, but
`recommendation_sessions` is currently insert-only with a fresh `uuid4()` per request — it
is a write-only audit log, not a session — so it would mean a schema change, a stable
client-side session id, and a DB round-trip added to the hot path, all to hold state the
client already has.

The chosen mechanism keeps the request self-describing, which matters because the backend is
stateless and the frontend already restores chat state from `sessionStorage` on browser-back
(item 38).

## Changes

### Backend

1. **`recommendation/intent.py` — `merge_intent`.** A spoken `max_price` replaces
   `budget_max` in either direction. `budget_min` follows as today (`min(budget_min,
   max_price)`). No change when the parse yields no `max_price`.

2. **`api/routers/recommend.py`.** Emit an SSE `budget` frame **only when a budget was
   actually spoken this turn** — i.e. when the parse produced a `max_price`. Silence on every
   other turn is load-bearing: it means the client never pins a value the user did not say,
   and an unstated budget keeps the `10000` sentinel so `budget_is_stated()` continues to
   report "no budget given" correctly.

3. **`api/routers/recommend.py` — widen re-fetch.** When the resolved `budget_max` exceeds
   `req.budget_max`, re-query nearby inventory at the new ceiling and `merge_candidates` it
   into the pool before scoring, mirroring `_constraint_fetch`. Without this the turn that
   widens answers from a pool capped at the old budget while claiming the new one.

4. **`api/routers/recommend.py` — the oracle counts against the resolved budget.**
   `fetch_axis_counts` (line 443) and `availability_lines` (line 764) both read
   `req.budget_max` directly. The client echo fixes them from turn 2 onward, but **not on
   the turn the budget is spoken** — there `req.budget_max` is still the wide sentinel while
   `resolved` holds the real number, so the oracle counts everything as in-budget while the
   prompt says `$60`. A shared `effective_budget_max(resolved, req.budget_max)` helper
   prefers the resolved value at both call sites.

   (This was missed in the first draft of this design, which asserted the oracle needed no
   change. It does — the echo is a turn-2 mechanism and the speaking turn needs its own fix.)

5. **Nothing else.** The scorer and the prompt are untouched. They begin behaving correctly
   the moment `req.budget_max` stops lying.

### Frontend

6. **`ChatRecommend.jsx` — `apiReq` becomes React state.** It is currently destructured
   straight from router navigation state (line 167) and is therefore immutable mid-
   conversation. `useState` seeded from navigation state preserves every existing consumer
   (`{...apiReq}` spreads at lines 230 and 409) while allowing updates. It is already
   included in `chatState` and the patched history entry, so item 38's browser-back and
   sessionStorage restore keep working with no further change.

7. **Handle the `budget` frame** alongside the existing `availability` handler (line 324),
   updating the request state.

## Guardrails

- **Never invents a budget.** No frame is emitted on turns where none was spoken, so silence
  cannot be misread as `$0` or as a stated `10000`.
- **PLAN face unaffected.** It already sends a real slider budget; the frame only ever moves
  the value to a number the user said out loud.
- **Not stuck.** Any spoken number wins in both directions, so there is always a visible exit.
- **Wide sentinel preserved.** A conversation where no budget is ever stated keeps
  `budget_max = 10000` end to end, and the prompt keeps saying "No budget was given".

## Testing

TDD throughout; watch each test fail first.

**Unit — `merge_intent`:**
- A spoken budget below the carried one applies (existing behavior, guard against regression).
- A spoken budget **above** the carried one applies (new; fails today).
- No `max_price` in the parse leaves the carried budget untouched.
- `budget_min` tracks below `max_price`.

**Unit — frame emission:**
- A turn with a spoken budget emits the frame with the resolved values.
- A turn with no spoken budget emits no frame.

**Integration — the recorded repro.** Replay `"my budget is $60"` → `"Do you carry
Overture?"` at 78258 and assert Overture is **not** in the picks, and that the narrative
reports it as stocked but out of budget. Note this is a deliberate behavior *reversal*: the
turn-2 answer today surfaces Overture, and after this change it must not. The pre-change
behavior is the bug, not a baseline to preserve.

**Frontend:**
- The `budget` frame updates `apiReq` and the next send carries the new value.
- A restore from `sessionStorage` preserves an updated budget.

## Out of scope

- Carrying `region` / `wine_type` / `grapes` / `avoid` (see Scope).
- Any change to the PLAN-face slider or `PreferenceCapture`.
- A server-side session store, though this design does not preclude one later — the SSE
  frame would remain the delivery mechanism either way.
