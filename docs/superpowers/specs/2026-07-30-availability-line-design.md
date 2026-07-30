# Deterministic Availability Line (Design)

**Date:** 2026-07-30
**Source:** `docs/oracle-verification-round2.md` — the two surviving FALSE_ABSENCE mechanisms.

## Problem

The availability oracle computes the truth deterministically, but the **model states it**. Two
rounds of prompt hardening moved the red-team PASS rate 50% → 85% and eliminated the
`UNUSED_FACT` class (6 → 0), yet 2 of 13 probes still produced a false absence — via two
different adherence failures:

1. **Axis substitution** — `"any Brunello di Montalcino under $50?"`. The fact said
   `Brunello di Montalcino: PRESENT_NOT_SHORTLISTED, 24 total, 4 in budget, from $26.99`. The
   narrative ran the count script on the *broader* axis instead: it cited Montalcino (12 in
   budget) and scoped its claim to *"the closest genuine fits **from this area**"* — turning a
   legal shortlist hedge into an availability claim, while the axis the user actually named got
   no count at all.
2. **Sycophantic agreement** — `"nothing from Mendoza right?"`. Fact:
   `Mendoza: PRESENT_NOT_SHORTLISTED, 401 total, 394 in budget, $4.18–$72.62`. Narrative:
   *"**No Mendoza here** — everything on this list is from somewhere else entirely, so you've got
   a clean slate."* It agreed with the user's false premise despite the fact. Inconsistent
   rather than systematic — it *refused* the identical framing for H-E-B and Twin Liquors.

A third prompt round would be pleading with the model about a number we already have. The
structural answer is the same move that made the oracle work, applied one layer out: **stop
asking the model to state the fact and render it ourselves.**

A related arithmetic defect appeared across four PASS probes: the model emits `in_budget` while
labelling it as the *remainder* ("6,227 **more** bottles … beyond what's shortlisted" when 6,227
is the total). Always user-favorable, so no false-absence risk, but wrong.

## Decisions (locked)

- **Placement:** an eyebrow-styled strip beneath the sommelier paragraph, above the cards —
  clearly *system voice*, not the somm's, so a hedging narrative and the true count can coexist.
- **Trigger:** only when it adds information (never on a plain "recommend me a red").

## Design

### 1. `availability_lines(facts, top) -> List[str]` (pure, `recommendation/availability.py`)

Renders informative facts as short factual strings. Silent otherwise.

| state | condition | line shape |
|---|---|---|
| `PRESENT_NOT_SHORTLISTED` | `in_budget > shown_matches` | `394 Mendoza in budget nearby ($4–$73) · none in this list` / `… · 3 shown` |
| `PRESENT_OUT_OF_BUDGET` | always | `3 Barolo at Geraldine's ($59–$110) · above your $50` |
| `NOT_IN_CATALOG` | always | `No Brunello di Montalcino nearby` (the one licensed absence) |
| `UNMEASURED` | always | `Couldn't confirm availability` |
| `PRESENT_SHORTLISTED` | — | silent (the picks already answer it) |

Two guards, each derived from a measured failure:

- **Exact axis only (narrow beats broad).** Lines are keyed to the axis the user named. When two
  axes overlap and one is a superstring of the other (`Brunello di Montalcino` vs `Brunello`;
  `Montalcino`), the **narrowest** is rendered and the broader is suppressed. This makes the
  Brunello substitution structurally impossible in the line.
- **Correct arithmetic.** `shown_matches` comes from `count_shortlisted(axis, top)`, so
  "none in this list" / "N more" is computed, never the model's mislabelled `in_budget`.

Scoped axes render their scope (`at Geraldine's`); unscoped render `nearby`. Cap at 3 lines.
Budget is passed in for the "above your $X" phrasing.

### 2. Transport — SSE `availability` event

`recommend.py` emits `{"type": "availability", "lines": [...]}` after the `picks` event (a
footnote; never delays first text). Emitted only when `lines` is non-empty. Wrapped so a failure
here can never break the stream. The frontend already ignores unknown event types, so an older
client degrades safely.

### 3. Frontend — eyebrow strip

`api.js` passes the event through unchanged (it already yields every parsed frame).
`ChatRecommend.jsx` stores `availabilityLines` per sommelier message and renders them beneath the
paragraph, above the cards, using the existing `t-eyebrow` class (uppercase, tracked,
`--text-muted`) with a `·` separator. No emoji, no new colors, no box — per `frontend/CLAUDE.md`.
Rendered in both the mobile and desktop layouts. Cleared on a new query.

### 4. What stays unchanged

- The prompt rules (they produced the 50%→85% gain and eliminated `UNUSED_FACT`).
- The post-stream tripwire as **detection**. This spec adds **prevention**: the truth reaches the
  user even when the prose is wrong.

## Testing

- `tests/test_availability.py`: one case per state (including `PRESENT_SHORTLISTED` silence and
  the `in_budget <= shown` silence); narrow-beats-broad suppression (Brunello vs Montalcino);
  arithmetic ("none in this list" when 0 shown, "N more" otherwise); scoped vs unscoped phrasing;
  empty input → `[]`; cap at 3.
- `tests/test_recommend_api.py`: the `availability` SSE frame is emitted when lines exist and
  omitted when they don't.
- Frontend `ChatRecommend.test.jsx`: strip renders on an `availability` event; absent without one.
- Acceptance: extend `scripts/verify_availability_oracle.py` to replay both red-team failures and
  assert a correct line for each (Mendoza → "394 … in budget"; Brunello → the narrow axis, not
  Montalcino).

## Honest limitation

This guarantees the user *sees* the truth; it does not stop the narrative from contradicting it.
A disagreement is now visible to the user and alerted by the tripwire. The deeper fix is the
constraint-satisfaction tier (audit plan item #4) so the shortlist stops missing wines the user
explicitly named — the retrieval failure that pushes the narrative into hedging. In all three
false-absence-adjacent probes this round, **0 picks satisfied the named axis** despite in-budget
stock existing.

## Out of scope

- Audit items #4 (constraint tier), #5 (unified filter spec), #6 (rank-then-truncate).
- Exempting the probe harness from the app rate limiter (15/hr/IP cost 12 of 25 probes this
  round) — worth doing, but separate.
