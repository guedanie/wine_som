# Producer-Facts Lookup (Design)

**Date:** 2026-08-08
**Source:** CLAUDE.md roadmap item 42.

## Problem

Asked *"Looking for something from willow creek - close to epoch in style"* (zip 78209), Somm
answered: **"Epoch is a Texas Hill Country producer."** Epoch Estate Wines is **Paso Robles** —
specifically the **Willow Creek District AVA**, which is why the user paired those two terms.

- **Intermittent.** A production probe of the same pairing answered correctly ("Epoch (Paso
  Robles) is a serious, structured Rhône-and-Bordeaux-focused estate"). Model variance, not a
  deterministic path.
- **Likely trigger — context bleed.** At a Texas zip the shortlist is full of `Texas Hill Country`
  wines (Bending Branch, Fall Creek, William Chris, Llano Estacado…). The model appears to absorb
  "Hill Country" from surrounding listings and attach it to the producer the user named.
- **It propagates.** The generated follow-up chip read *"What makes Epoch's style distinctive
  compared to other **Texas Hill Country** producers?"* — one bad fact contaminates the
  suggestions and would carry into the next turn.
- **We had the answer and never looked.** `wines` holds 4 Epoch rows, three labelled
  `region=Paso Robles`.

Structurally this is the same mistake as the false-absence class: **the model inferring what we
can look up deterministically** — but about producer identity rather than availability.

## Why the obvious detectors don't work (measured)

| candidate source | result |
|---|---|
| parser `wine_name` | Unreliable. Returned `None` for *"close to epoch in style"* (the actual failure) and even for *"is the Caymus worth $80…"* on one run, while catching "Whispering Angel" and "Duckhorn". Same LLM variance that motivated the availability fallback. |
| `wines.brand` column | Only **63%** populated (14,605 / 23,002), and **Epoch has no brand at all** — it would miss the exact failing case, the same trap as the curated gazetteer. |

So detection needs a deterministic floor built from `wines.name`, which is 100% populated.

## Design

### 1. Detection — two layers

- **Layer 1:** the parser's `wine_name` when present.
- **Layer 2 (deterministic floor):** `significant_name_tokens(message)` (existing helper; strips
  generic varietal/geo words) → for each token, query `wines.name ilike %token%`.

### 2. Self-validating emission

A token yields a producer fact only when the matched set actually looks like a producer:

- **Bounded:** at most `_PRODUCER_MAX_ROWS` (60) matching wines. A producer has a handful;
  "estate" matches thousands.
- **Region-concentrated:** the top region must hold at least `_PRODUCER_MIN_CONCENTRATION` (0.5)
  of rows that have a region. Epoch: **3 of 4 = 75% Paso Robles**. A generic token scatters
  across unrelated regions and emits nothing.
- At least 2 matching rows with a region (a single row is not evidence of a producer).

This is the same principle as the descriptor guard from item 39/40 work: **validate the thing
before asserting on it.** No maintained vocabulary, and it self-updates with the catalog.

### 3. Majority vote, with counts

Emit the top one or two regions **with counts**, never a single flattened assertion:
- `Epoch → Paso Robles (3 of 4)` — the bad `Ribeira Sacra` row is outvoted (verified).
- `Caymus → Napa Valley (12 of 22)`, `Whispering Angel → Provence (5 of 6)`,
  `Duckhorn → Napa Valley (18 of 29)`.
- Genuinely multi-AVA producers stay honest: `Silver Oak → Napa Valley (9), Alexander Valley (2)`
  lets the narrative say "primarily Napa" instead of asserting one.

The lookup is **catalog-wide and price-blind** — Epoch is Dallas-only at $55–$103 while the user
was in San Antonio, which is exactly the situation where the model reaches for recall.

### 4. Prompt binding

Producer facts render as a `[VERIFIED PRODUCER]` section alongside the existing
`[VERIFIED AVAILABILITY]` block, with one rule added to the availability rules:

> When a producer appears in VERIFIED PRODUCER, use that region — it is drawn from our catalog.
> For a producer that does NOT appear, you may share what you know but must hedge ("I believe
> Epoch is from Paso Robles"), never assert flatly.

Fail-open: no facts → today's behaviour, logged.

### 5. Data defects

- **Fix** the known bad row: `Epoch Estate Wines Block B Paso Robles 2018` →
  `region=Ribeira Sacra, country=Spain` while its own name says Paso Robles.
- **Build a detector** (`scripts/detect_region_contradictions.py`) that finds rows whose NAME
  contains a place contradicting the `region`/`country` fields — e.g. the Block B row, and
  `Walt Blue Jay Pinot Noir Australian Red Wine` (a California wine whose catalog string made
  Somm call it Australian in an earlier probe).
- **Report only — no bulk writes.** Per the standing conservative-enrichment rule
  (`feedback-conservative-enrichment`), wrong-and-permanent is the failure mode to avoid. The
  producer lookup's majority vote already tolerates isolated bad rows, so there is no urgency to
  auto-correct.

## Testing

- `tests/test_producer_facts.py` (pure): concentration threshold (emit at 75%, silent when
  scattered); row cap (a token matching too many wines emits nothing); minimum-rows rule;
  majority vote outvotes a single contradicting row (the Epoch shape); multi-region producer
  renders both with counts; empty input → `[]`.
- `tests/test_claude_client.py`: the `[VERIFIED PRODUCER]` section renders when facts exist and
  is absent when they don't; the hedging rule text is present.
- Acceptance `scripts/verify_producer_facts.py`: live catalog — "epoch" resolves to Paso Robles
  (not Texas Hill Country), Caymus → Napa Valley, and a generic token ("estate") emits nothing.

## Out of scope

- Producers absent from our catalog (handled by the hedging rule, not by data).
- Bulk correction of contradicting rows — detector reports, a human decides.
- Vintage/appellation-level producer facts; region + country is enough to stop this class.
