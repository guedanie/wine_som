# Availability Oracle (Design)

**Date:** 2026-07-30
**Source:** `docs/recommendation-architecture-audit.md` — prioritized plan item #2 (+ the #3 tripwire)

## Problem

Somm has no availability oracle. **Absence is never computed — it is inferred by an LLM from a
12-row shortlist.** One artifact (the candidate shortlist) answers two incompatible questions:
*"what should I recommend?"* (correctly a bounded, ranked, diversity-capped top-12) and
*"what exists nearby?"* (a closed-world question a bounded sample structurally cannot answer).

Every stage that legitimately narrows the recommendation — the unordered `LIMIT 500`/retailer,
`_MAX_CANDIDATES=12`, `_VARIETAL_CAP`, the enrichment gate, the staleness cutoff, the budget clamp,
personalization weights — therefore also silently narrows the evidence base for absence. And
`_SYSTEM_PROMPT` hands the model a ready-made denial phrase ("nothing matching that turned up
nearby") with no rule that ever forbids denial and no computed fact to check it against.

Six false-absence incidents have been patched one at a time. Only two availability facts are ever
computed (`named_bottle_found`, `retailer_has_fit`), both added reactively. Live evidence of the
class: "no Barolos at Geraldine's" — measured today, Geraldine's has **3 Barolos, $59–$110**, i.e.
present but above the $50 cap.

## Goal

Make a false absence claim **structurally impossible**: absence becomes a deterministic computed
fact, and the prompt layer is forbidden from asserting absence except under that fact.

## Decisions (locked)

- **Axis scope v1:** each named region/appellation/country, each grape, `wine_type`, `wine_name`,
  plus the ×retailer/×store compound when one is detected.
- **Tripwire included now** (the post-stream false-absence detector).
- **Retire `named_bottle_found` and `retailer_has_fit`** — facts replace both; one code path.
- **Latency accepted:** ~500ms added on constraint-naming requests (parallel, overlapped).

## Design

### 1. `backend/recommendation/availability.py`

Pure logic separated from I/O so the logic unit-tests without a DB.

**Pure:**
- `axes_from_intent(resolved, detected_retailer, detected_store) -> List[Dict]` — the constraints the
  user actually named. Each axis: `{"kind": "place"|"grape"|"type"|"name", "value": str,
  "scope": Optional[str]}` where `scope` is a retailer/store label for the compound case.
  Empty list when the user named nothing concrete (no facts, no queries, no added latency).
- `derive_state(total, in_budget, shortlisted_n, stale) -> str` — precedence order:
  1. `UNMEASURED` — `stale` is True (the retailer's freshest row is beyond the staleness cutoff, or
     the axis has no queryable column). Distinguishes "has nothing" from "wasn't measured".
  2. `NOT_IN_CATALOG` — `total == 0`. **The only state that licenses an absence sentence.**
  3. `PRESENT_OUT_OF_BUDGET` — `total > 0` and `in_budget == 0`.
  4. `PRESENT_SHORTLISTED` — `shortlisted_n > 0`.
  5. `PRESENT_NOT_SHORTLISTED` — otherwise.
- `count_shortlisted(axis, top) -> int` — in-memory match of an axis against the final candidates
  (normalized/accent-folded containment over region, sub_region, country, varietal, grapes, name).
- `format_fact_block(facts) -> str` — the prompt text; `""` when there are no facts.

**I/O:** `fetch_axis_counts(supabase, axes, store_ids, budget_max) -> Dict[axis_key, Dict]`
- One `count='exact'` query per axis with `.limit(1)` (the count is exact regardless of rows
  returned, so the payload stays tiny), plus one budget-filtered count.
- Predicate is the **union**: `region OR sub_region OR country OR varietal OR grapes OR name`,
  matched case/accent-insensitively. `sub_region` is deliberately included — the audit found it is
  never selected, queried, or scored anywhere in the recommender today (6,264 wines carry an
  appellation there; `sub_region ilike '%Pauillac%'` = 159 wines vs `region ilike` = 11).
- **No LIMIT, no budget clamp on the total, no staleness filter, no enrichment gate, no type gate.**
  Bypassing every narrowing stage is the entire point — those stages caused the bugs.
- Price range (`min`/`max`) fetched only when `in_budget == 0 and total > 0`, for the
  `PRESENT_OUT_OF_BUDGET` script.
- Fan-out via `concurrent.futures.ThreadPoolExecutor` (supabase-py is sync), bounded worker count,
  so total latency ≈ one query (~500ms) regardless of axis count.
- Any exception → return `{}` (fail open to current behavior) and log.

### 2. Wiring (`api/routers/recommend.py`)

- **Counts fire early** — right after intent resolution / retailer+store detection, before scoring, so
  the latency overlaps existing work.
- **States are finalized at prompt-build time** inside `event_gen`, once `top` is final: combine the
  cached counts with `count_shortlisted(axis, top)` via `derive_state`, and set
  `resolved["availability_facts"]`.
- Fails open: no facts on error → today's behavior, logged.

### 3. Prompt binding (`recommendation/claude_client.py`)

- **Delete** the denial phrase from `_SYSTEM_PROMPT` ("If nothing fits, say what you *can* see doesn't
  match ('nothing matching that turned up nearby')…"). It is a ready-made false statement.
- **Render the fact block** before the listings when `availability_facts` is non-empty, e.g.
  `Barolo × Geraldine's: 3 nearby, $59–$110, none within your $50 budget [PRESENT_OUT_OF_BUDGET]`.
- **Three licence rules** in the directive:
  1. Absence may be asserted **only** for a `NOT_IN_CATALOG` fact. For every other state use the
     sanctioned script (out-of-budget → name the count and price range; not-shortlisted → "there are
     N nearby; here's the closest I surfaced"; unmeasured → "I can't filter on that" / stale-data
     note). "I judged this a poor fit" and "this doesn't exist nearby" are different sentences with
     different licences.
  2. Any listing satisfying the user's literal constraint **must** appear in `picks` ("never pad"
     applies to unrequested filler, never to a constraint match).
  3. Never contradict a fact.
- **Retire** `named_bottle_found` / `retailer_has_fit` and the "doesn't stock" directive; a `name`
  axis and a `×retailer` axis produce those facts natively.

### 4. Tripwire (post-stream)

In `event_gen`, after `[DONE]` (so it never delays the stream): regex the assembled narrative for the
absence family ("no ", "none", "nothing", "doesn't stock", "not available", "couldn't find"…); if it
fires while any fact is `PRESENT_*`, log `FALSE_ABSENCE_SUSPECT` with the narrative excerpt + the
contradicting fact and Slack-alert via the existing webhook. Wrapped in try/except — never breaks a
response. Rationale: of 12 absence assertions across 290 persisted sessions, **8 occurred on turns
that returned picks**, so a zero-pick metric alone would catch only a third.

## Testing

- `tests/test_availability.py` (pure): `derive_state` truth table including precedence
  (stale beats zero-count; zero beats out-of-budget); `axes_from_intent` (each kind, the compound,
  empty when nothing named); `count_shortlisted` (accent/containment, sub_region match);
  `format_fact_block` (each state's rendering, empty input → "").
- `tests/test_claude_client.py`: fact block present/absent; licence rules present; the denial phrase
  is **gone**; `named_bottle_found`/`retailer_has_fit` directives removed (rewrite those tests).
- Tripwire unit test: fires on absence-language + `PRESENT_*`; silent on `NOT_IN_CATALOG`; silent
  when no absence language.
- Acceptance `scripts/verify_availability_oracle.py`: the live Barolo × Geraldine's case →
  `PRESENT_OUT_OF_BUDGET` with `$59–$110`; an H-E-B axis → `PRESENT_*`, never absence; a genuinely
  absent axis → `NOT_IN_CATALOG`.

## Out of scope (later plan items)

- #4 constraint-satisfaction tier (`ensure_constraint_representation`, gating personalization) —
  fixes the measured 12/12 → 0/12 shortlist collapse.
- #5 unified `filter_spec` (one predicate: sub_region everywhere, accent folding, grape aliases,
  canonical type, per-retailer staleness) — this spec adds `sub_region`/accent handling **only inside
  the oracle's own predicate**, not to the fetch paths.
- #6 rank-then-truncate replacing the unordered `LIMIT 500`.
- #1 CI + the full capability suite; #7 vocabulary contract tests.
