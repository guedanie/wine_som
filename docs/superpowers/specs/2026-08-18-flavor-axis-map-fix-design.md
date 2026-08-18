# Flavor-Axis Map-Fixable Slice (Design)

**Date:** 2026-08-18
**Source:** CLAUDE.md roadmap item 34(c).

## Problem

`flavor_tags_for` (`recommendation/flavor_profiles.py`) derives a wine's flavor tags from a
curated grape+region map. A capability sweep found 28% of a 6k sample get zero tags
(flavor-invisible to the scorer). That 28% has three distinct causes, and only a slice is
map-fixable:

- **~7% — pure data gap** (no grape + no varietal + no region). Not a map problem; belongs to
  Vivino/LLM enrichment.
- **~19% — junk category labels** dumped into the grape/varietal field ("Other", "Red Wine",
  "Sparkling Wine", "Sake", etc.). Not real grapes; belongs to the item-32 purge + item-30
  wine_type work. Map expansion is meaningless for these.
- **~8–10% — the genuinely map-fixable slice**: real, specific, unmapped grapes and regions —
  Moscato (~118 rows), Glera/Prosecco (~69), Nero d'Avola (~24), California catch-all (~109),
  Veneto (~78), Sicily, Champagne, Loire, Alsace, Penedès.

Compounding gap: the parser clamps `flavors` to a 15-word `FLAVOR_VOCAB` with no word for
floral/aromatic character — so even a correctly-mapped Moscato can't be *asked for* by name,
since "floral" isn't in the vocabulary the Haiku parser is told to draw from. Adding a grape to
the map without adding the matching vocab word is a no-op.

This design covers only the map-fixable slice.

## Verified against the live catalog

Exact-match lookup (`_norm`'d) means a map key only fires when it equals the wine's `varietal`
string or an element of its `grapes` jsonb array — not a substring of a longer comma-joined
string. Checked the actual catalog before choosing keys:

- `Moscato`, `Glera`, `Prosecco`, `Nero d'Avola` all appear as clean standalone values in
  `grapes`/`varietal` for real rows (not only buried inside joined strings like "Frappato, Nero
  D'avola" — those already fail to match today for the *existing* map too, a pre-existing
  limitation this design doesn't attempt to fix).
- `California`, `Champagne`, `Alsace` all appear as exact `region` values.

## Design

### 1. Vocab — add `floral`, `citrus`, `mineral`

Added to `FLAVOR_VOCAB` (`flavor_profiles.py`) and the parser's `_FLAVOR_VOCAB` prompt string
(`intent.py`), which must stay textually in sync (today enforced only by a code comment — this
design adds a drift-guard test, mirroring the pattern already used for `CORE_GRAPES`).

Rejected: a broader vocab add (buttery, oaky, smoky, jammy, tropical) — those aren't defensible
for anything in this batch (buttery/oaky are oak-treatment-driven, not grape/region-driven; no
table entry below would use them) and would sit unused. Scope the vocab to what this batch's
data can actually back up.

### 2. `GRAPE_FLAVORS` additions

```python
"Moscato": {"floral", "light", "ripe"},
"Glera": {"floral", "citrus", "light"},
"Prosecco": {"floral", "citrus", "light"},   # alias — catalog stores both as standalone values
"Nero d'Avola": {"bold", "dark-fruit", "savory"},
```

### 3. `REGION_FLAVORS` additions

```python
"California": {"ripe"},      # conservative single tag, matches the existing
                              # Napa Valley / Sonoma / Central Coast pattern
"Champagne": {"mineral", "light"},
"Alsace": {"floral", "spice"},
```

**Deliberately excluded:** Veneto, Sicily, Loire, Penedès. Each spans stylistically incompatible
wines under one region label (Veneto = light Soave whites AND big Amarone reds AND Prosecco;
Sicily = Nero d'Avola reds AND Grillo/Catarratto whites AND Marsala; similarly Loire, Penedès) —
a single region-level tag set would overclaim for whichever style doesn't match. Per the
project's standing conservative-enrichment rule, an asserted flavor tag must be defensible, not
guessed at region-wide breadth. Veneto and Sicily still gain *partial* coverage indirectly
through the new Glera/Nero d'Avola grape entries; Loire and Penedès get nothing in this pass.

### 4. Testing

`tests/test_flavor_profiles.py`, matching its existing pure-function style:
- One test per new grape (Moscato floral, Glera/Prosecco alias parity, Nero d'Avola
  bold+savory).
- One test per new region (California ripe, Champagne mineral+light, Alsace floral+spice).
- One test confirming Veneto/Sicily/Loire/Penedès *alone* (no grape, region only) still return
  an empty set — documents the deliberate skip so a future editor doesn't "fix" it as an
  oversight.
- One drift-guard test asserting `intent._FLAVOR_VOCAB`'s word list exactly equals
  `flavor_profiles.FLAVOR_VOCAB`.

## Out of scope

- The ~7% pure data gap and ~19% junk-category-label slice (items 32/30/Vivino territory).
- Fixing comma-joined multi-grape varietal strings failing exact-match (pre-existing limitation,
  not introduced or worsened here).
- Region-level tags for Veneto/Sicily/Loire/Penedès (see above).
- Any change to how the scorer weights flavor-tag overlap (`_W_FLAVOR_TAG`) — this design only
  expands what tags exist, not how they're scored.
