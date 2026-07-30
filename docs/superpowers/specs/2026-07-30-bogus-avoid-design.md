# Bogus-Avoid Guard (Design)

**Date:** 2026-07-30
**Source:** root-cause analysis of the surviving Mendoza FALSE_ABSENCE in
`docs/oracle-verification-round2.md`.

## Problem

`"nothing from Mendoza right?"` — an *availability question* — makes the Haiku intent parser emit
**both**:

```
avoid   = ['Mendoza']
regions = ['Mendoza']
```

`score_candidates` treats `avoid` as a hard exclusion (`continue`), so of 300 fetched
Mendoza/Argentina candidates **275 are deleted (92%)**. The shortlist contains zero Mendoza, and
the narrative then *truthfully* reports *"No Mendoza in sight."*

**We delete exactly what the user asked about, then report it as absent.** Measured: with the
bogus avoid removed those same wines score **2.72–2.86** against a top-12 cut of **1.83** — they
would have dominated the list.

This reframes the round-2 verdict. The red team called it "sycophantic agreement"; the model was
not being sycophantic — it was accurately describing a candidate list we had sabotaged. No amount
of prompt hardening addresses it, and it is **not** audit item #4 (constraint-satisfaction tier):
the wines were fetched and then destroyed, not out-ranked.

Blast radius (15 phrasings): 1 of 10 absence-framed questions produced a bogus avoid. Low
frequency but non-deterministic (LLM variance), invisible when it happens, and it lands precisely
on the phrasing an absence-doubting user reaches for.

## The discriminator (measured)

A term appearing in **both** `avoid` and a positive constraint field (`regions`, `grapes`,
`wine_type`) is a **self-contradiction** — you cannot simultaneously ask for X and ask to exclude X.

| message | avoid | positive fields | contradiction |
|---|---|---|---|
| `nothing from Mendoza right?` | `['Mendoza']` | `regions=['Mendoza']` | **YES** |
| `avoid Chardonnay` | `['Chardonnay']` | — | no |
| `no Merlot for me` | `['Merlot']` | — | no |
| `a red but no oak please` | `['oak']` | — | no |
| `something dry, I don't like sweet wines` | `['sweet']` | — | no |
| `nothing too tannic` | `['tannic']` | — | no |
| `can you avoid Chardonnay?` | `['Chardonnay']` | — | no |

**Zero false positives across six genuine preference avoids** — a real avoid never populates the
positive fields. Note that "is the avoid term a known catalog entity?" does NOT discriminate
(`Chardonnay` and `Merlot` are both), which is why the rule keys on the contradiction rather than
on entity-ness.

## Decision (locked)

**Trust the positive, drop the avoid.** Asymmetric harm: a false exclusion is invisible and
catastrophic (we delete inventory and then claim absence, undetectable by the user); a missed
exclusion is visible and mild (the user sees a wine they didn't want and says so).

## Design

### 1. Contradiction guard in `merge_intent` (primary, deterministic)

After the existing merge, drop any `avoid` term that also appears in a positive field:

```
drop_bogus_avoid(avoid, regions, grapes, wine_type) -> (kept_avoid, dropped)
```

- Comparison is accent-folded, lowercased, and containment-based in both directions
  (`"mendoza"` vs `"Mendoza"`, `"rhone"` vs `"Rhône"`).
- Pure and separately unit-testable; `merge_intent` calls it and logs any drop
  (`INTENT | dropped contradicted avoid term(s): [...]`).

It lives in `merge_intent` so **every** downstream consumer — the breadth/targeted fetches, the
scorer, the availability oracle, and the prompt — sees the corrected intent. Fixing it at one call
site would leave the others inconsistent.

### 2. Parser prompt (secondary)

Teach the distinction directly in `parse_message`: `avoid` means the user wants something
**excluded** ("no oak", "I don't like Chardonnay", "avoid sweet"); an **availability question**
("nothing from Mendoza right?", "is there really no Chablis?", "you probably have zero Nebbiolo")
names the *subject* of the question and belongs in `regions`/`grapes`/`wine_type`, never `avoid`.

This reduces how often the guard fires; the guard is what makes the system safe when the LLM
varies. Both layers, same philosophy as the availability oracle: never let a single fallible
inference silently destroy data.

### 3. Exclusion telemetry ("no silent caps")

`score_candidates` already counts what it excludes implicitly; make it explicit. In
`recommend.py`, after scoring, log:

```
AVOID FILTER | terms=['Mendoza'] removed=275/300 (92%)
```

and when the removed fraction exceeds **50%** with a non-empty avoid list, log a
`SUSPECT_AVOID` warning carrying the terms, the counts, and the message — the same shape the
false-absence tripwire uses. This is the layer that would have surfaced the bug from logs instead
of from a user screenshot.

Implementation: `score_candidates` returns only survivors, so the counts come from comparing the
input pool size to the scored size in `recommend.py` — no scorer signature change.

## Testing

- `tests/test_intent.py`: `drop_bogus_avoid` — contradicted term dropped (Mendoza); **each of the
  six genuine avoids preserved** (the false-positive guard); accent/case-insensitive matching;
  empty avoid, empty positives, and no-contradiction cases; `merge_intent` end-to-end applies it.
- `tests/test_recommend_api.py`: the `SUSPECT_AVOID` threshold helper fires above 50% and is
  silent below / when avoid is empty.
- Acceptance in `scripts/verify_availability_oracle.py`: replay `"nothing from Mendoza right?"` —
  assert Mendoza candidates survive scoring and land in the top-12 (they score 2.72–2.86 vs a 1.83
  cut).

## Out of scope

- Audit items #4 (constraint-satisfaction tier), #5 (unified filter spec), #6 (rank-then-truncate).
  This bug is independent of all three.
- The `avoid` word-boundary false positive noted in the audit (`avoid=["dry"]` excluding *Dry
  Creek* Zinfandel) — real but separate, and not a false-absence mechanism.
