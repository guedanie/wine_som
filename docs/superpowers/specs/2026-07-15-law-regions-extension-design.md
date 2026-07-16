# Law-Regions Defaults Extension — Design

**Date:** 2026-07-15 · **Follow-on to:** `2026-07-14-grapes-backfill-design.md` (all machinery from that spec is live)
**Status:** approved design, pre-implementation

## Problem

After the 2026-07-14 backfill, 1,726 wines still carry a *generic* varietal
("Red Blend", "Sparkling Wine", "Port"…) with an empty grapes array — invisible
to specific-grape matching, flavor tags, structure inference, and the
shared-grape personalization component. A sweep showed a large slice sits in
regions whose grapes are fixed by law or overwhelming convention. Measured
2026-07-15 (grapes-empty rows):

| Region | Rows | Shape |
|---|---|---|
| Champagne | 157 | 145 sparkling, 146 no sub_region |
| Douro | 119 | 93 dessert (Port), 20 unknown-type, subs Port/Porto/Douro |
| Tuscany | 102 | 78 unknown-type; subs incl. Chianti (Classico) 10, Montalcino 3, Bolgheri 6 |
| Penedès | 37 | 26 sparkling, no sub_region |
| Other Spain | 24 | 8 under sub_region 'Cava' |
| Provence | 74 | 65 rosé; subs Côtes de Provence 19, Bandol 6, Cassis 2 |

## Governing rule (user directive, 2026-07-15)

**Lean conservative — never populate wrong information.** Hard-law entries
ship freely. Convention-grade entries are admitted only because (a) they are
multi-grape, so the Vivino replace rule can correct outliers, and (b) the user
explicitly approved each one. Single-grape values are permanent (excluded from
Vivino replacement), so they are used only where the law guarantees them.
This rule is standing policy for future enrichment work
(memory: `feedback-conservative-enrichment`).

## Decisions (user-approved)

- **Tier A (hard law) + Tier B (approved conventions) both ship.**
- Champagne lead grape: **Pinot Noir** first.
- Tuscany: **appellation-level only** — no region default (Super Tuscans +
  permanent single-grape risk).
- **Dropped**: Bolgheri (permissive DOC — a style, not a law; reverses an
  earlier provisional call), Madeira (named-varietal wines make any default
  uncertain), Cassis (blend varies; 2 rows), Toscana IGT (definitionally open).
- The one `sub_region='Madeira'` row currently filed under region 'Douro' is
  **hand-retyped to region 'Madeira'** before the run (data correction in the
  residue-sweep tradition) so the Douro region rule cannot reach it.

## Design

### 1. `reference.py` — region rules become color-aware

`REGION_DEFAULT_GRAPES` (flat dict, red-only) is replaced by
`_REGION_DEFAULT_RULES`: a list of `(regions, grapes, colors)` tuples, indexed
by `_norm(region)`. **Region-level rules always require an explicit wine_type**
(never fire on None/"") — this preserves the existing Bordeaux/Rhône behavior
and is the conservative default for region-granularity inference. The public
API `default_grapes_for_region(region, wine_type)` is unchanged in signature.

Entries:

| Regions | Blend (first = varietal) | Colors | Tier |
|---|---|---|---|
| Bordeaux | Merlot, Cabernet Sauvignon, Cabernet Franc | red | (existing) |
| Rhône | Grenache, Syrah, Mourvèdre | red | (existing) |
| Champagne | **Pinot Noir, Chardonnay, Pinot Meunier** | sparkling, rose | A (7 legal grapes; these three = 99.7% of plantings; rosé Champagne uses the same grapes) |
| Douro | Touriga Nacional, Touriga Franca, Tinta Roriz | red, dessert | B (Port law permits 80+ varieties; modern big three) |
| Penedès | Macabeo, Xarel·lo, Parellada | sparkling | B (Penedès sparkling ≈ Cava; trio ≈ 85–90% of production) |
| Provence | Grenache, Cinsault, Syrah | rose | B (near-universal template; proportions free) |

`ALL_DEFAULT_BLENDS` picks the new blends up automatically from the rebuilt
index (Vivino replace eligibility, multi-grape only, unchanged).

### 2. `reference.py` — new appellation entries in `_DEFAULT_RULES`

| Appellations | Blend | Colors | requires_type | Tier |
|---|---|---|---|---|
| Chianti, Chianti Classico, Brunello di Montalcino, Rosso di Montalcino, Montalcino, Vino Nobile di Montepulciano, Morellino di Scansano | Sangiovese | red | False (red-only DOCGs) | A (Brunello/Rosso 100% by law; others ≥70–85% — "contains Sangiovese" is guaranteed, single-grape permanence is safe) |
| Carmignano | Sangiovese, Cabernet Sauvignon | red | False | A (Cabernet legally required, 10–20%) |
| Cava | Macabeo, Xarel·lo, Parellada | sparkling | False (sparkling-only DO) | B |
| Bandol | Mourvèdre, Grenache, Cinsault | red, rose | **True** (Bandol also bottles white — unknown type must not guess) | A for red (≥50% Mourvèdre by law), B for rosé |
| Blanc de Blancs | Chardonnay | sparkling | False (100% Chardonnay by definition) | A |

Notes: "Montalcino" and "Blanc de Blancs" are added ONLY to the defaults index,
NOT to `APPELLATIONS` (no evidence-gate / parent-region side effects — scope
discipline). All other named appellations already exist in `APPELLATIONS`.

### 3. Backfill re-run

`scripts/backfill_grapes.py`: `TARGET_REGIONS` extends to
`("Bordeaux", "Rhône", "Champagne", "Douro", "Tuscany", "Penedès",
"Other Spain", "Provence")`. No logic changes — the precedence chain
(trusted varietal → appellation → region) and the generic-varietal handling
already do the right thing ("Port", "Champagne", "Rosé Blend" are all
non-specific per `is_specific_grape`, so they keep their varietal and gain the
blend). 'Other Spain' has no region rule, so only its Cava sub-rows fill.

Pre-step: retype the single Madeira row (region 'Douro' → 'Madeira').
Run order: dry-run → reconcile against the table below → live → verify → docs.

**Expected fill ≈ 355**: Champagne ~147 (8 unknown-type left), Douro ~96
(20 unknown-type left), Tuscany ~13 (78 unknown-type + Bolgheri 6 left),
Penedès ~26, Cava ~8, Provence ~65 (unknown/white left). Everything left
flows to the Vivino queue as before.

### 4. Extractor

Zero code changes — step 3b already calls
`default_grapes_for(sub, wine_type) or default_grapes_for_region(region,
wine_type)`, so the weekly extraction inherits the new entries the moment
`reference.py` lands.

## Testing (TDD, extending existing files)

- `test_extraction_reference.py`: region rules — Champagne sparkling + rosé
  fire, Champagne unknown/red → None; Douro dessert + red fire; Penedès
  sparkling; Provence rose-only; Bordeaux/Rhône red behavior unchanged;
  region rules NEVER fire on None/empty wine_type. Appellations — Chianti
  family → Sangiovese (fires on unknown type, red-only DOCG), Carmignano
  two-grape, Cava on unknown type, Bandol requires explicit type,
  Blanc de Blancs → Chardonnay. `ALL_DEFAULT_BLENDS` contains the Champagne,
  Port, and Cava trios.
- `test_backfill_grapes.py`: Champagne sparkling row fills PN-led + varietal
  set when NULL; Port dessert row fills; generic varietal 'Port' keeps its
  label; Tuscany unknown-type no-sub row is a no-op; Chianti Classico
  unknown-type row fills Sangiovese; Provence white row is a no-op.
- Extractor: existing tests cover the mechanism; no new extractor tests needed.

## Out of scope

- California/anything-goes generic blends (item 12 / Vivino).
- `APPELLATIONS` / evidence-gate changes.
- Scorer changes (yesterday's blend rule already covers these wines once
  grapes are filled).
