# NULL wine_type Backfill (+ infer_wine_type hardening) — Design

**Date:** 2026-07-17 · **Status:** approved design, pre-implementation
**Roadmap:** CLAUDE.md item 30 · **Sibling:** the 2026-07-14 grapes backfill (same shape)

## Problem

5,443 wines (27.5% of the catalog) have `wine_type = NULL`. NULL is invisible to
DB-level type surfaces — the search screen's type filter, `/deals`, `/discover`,
and the type/varietal-null stats. (The recommender itself already resolves NULL
types at query time via the shipped `resolve_wine_type`/`infer_wine_type`, so
this pass targets the DB-level surfaces, not the recommender.)

Measured 2026-07-17 over the 5,443:
- `infer_wine_type` as-is resolves **3,135 (58%)** — 2,085 red, 877 white, 91
  sparkling, plus small rosé/dessert/orange/fortified.
- Of the 2,308 it misses, **~331 are real grapes** (Arneis, Furmint, Nero
  d'Avola, Corvina, Gamay, Grüner Veltliner, Cinsault, Aligoté, Pinot Meunier,
  Schioppettino…) that `reference.py`'s `CORE_GRAPES` knows but `infer_wine_type`'s
  smaller vocab doesn't; **~517 are name-only wines with a definitionally
  single-color appellation** (Chablis→white, Champagne→sparkling, Brunello→red,
  Sauternes→dessert, Jerez/Fino→fortified); **~462 are non-wine grocery junk**
  (fruit cocktail, pancake mix, sake, peach slices — correctly left NULL); and
  **~500 are signal-less producer-only listings** (Vivino/LLM territory).

## Governing rule

The conservative rule applies (`feedback-conservative-enrichment`): never write a
wrong value. This is sharpened by the type gate shipped 2026-07-17 — **a NULL
type is kept for any request, but a *wrong* type excludes the wine from its
correct-type search.** So a wrong type is worse than NULL. `wine_type` is
fill-only and Vivino cannot overwrite it, so writes are permanent. Hence:
deterministic, law-backed inference only; verify before writing.

## Decisions (user-approved)

1. Write all inferable rows (target ~73%), after hardening `infer_wine_type` and
   a dry-run precision audit.
2. Expand determinism in two law-backed ways: **sync the grape vocab with
   `CORE_GRAPES`** and **add appellation→type inference**.
3. Target is DB-level surfaces + stats (the recommender already handles NULLs).

## Design

### 1. Harden `infer_wine_type` (`utils/__init__.py`) — shared by every caller

- **1a. Sparkling method/style terms.** Add `pet nat`, `pet-nat`, `pétillant`,
  `pétillant naturel`, `col fondo`, `méthode ancestrale`, `ancestral` to
  `SPARKLING_TERMS` (already checked *before* the red/white varietal lists), so
  "Zinfandel Pet Nat" resolves sparkling, not red. Fixes the runtime gate too.
- **1b. Grape-vocab parity with `CORE_GRAPES`.** Extend `RED_VARIETALS` /
  `WHITE_VARIETALS` / `ROSE_TERMS` with the grapes present in
  `reference.CORE_GRAPES` but missing from `infer_wine_type` (Arneis, Furmint,
  Corvina, Nero d'Avola, Gamay, Grüner Veltliner, Cinsault, Aligoté, Pinot
  Meunier, Schioppettino, Melon de Bourgogne, Monastrell, Garnacha, and the rest).
  Add a **parity test** (`test_infer_covers_core_grapes`) asserting every
  `CORE_GRAPES` entry resolves via `infer_wine_type`, so the two vocabularies
  can't silently drift. (No cross-module import — the modules are independent and
  stay that way; the test enforces coverage.)

### 2. `wine_type_for_appellation(region, sub_region)` (new, `reference.py`)

A curated `APPELLATION_WINE_TYPE` map of **definitionally single-color/style**
appellations → type. Only appellations that are one type by law/definition:
- **white:** Chablis, Sancerre, Pouilly-Fumé, Muscadet, Savennières, Gavi, Soave,
  Vinho Verde, Rueda, Albariño/Rías Baixas, Chablis-family, Entre-Deux-Mers…
- **red:** Brunello di Montalcino, Rosso di Montalcino, Barolo, Barbaresco,
  Chianti (Classico), Vino Nobile, Morellino, Bandol-red-only? (no — Bandol does
  rosé; EXCLUDE multi-color)…
- **sparkling:** Champagne, Cava, Prosecco, Franciacorta, Crémant (all), Lambrusco.
- **dessert:** Sauternes, Barsac, Tokaji (Aszú), Recioto, Vin Santo, Ice Wine.
- **fortified:** Port/Porto, Sherry/Jerez/Fino/Manzanilla/Amontillado, Madeira,
  Marsala, Banyuls.
Multi-color appellations (Burgundy villages, Bordeaux communes, Rhône, Alsace,
generic regions like Tuscany/Piedmont/Napa) are **excluded** — they can't be
typed from place alone. `wine_type_for_appellation` checks `sub_region` then
`region` against the map, returns None on no single-color match.

### 3. Backfill script `scripts/backfill_wine_type.py` (mirrors `backfill_grapes.py`)

- Pure `plan_change(row)`: resolve via
  `infer_wine_type(varietal)` → `infer_wine_type(name)` →
  `infer_wine_type(first grape)` → `wine_type_for_appellation(region, sub_region)`.
  Return `{"wine_type": resolved}` only when the row's `wine_type` is NULL and
  something resolves; else `{}`. Fill-only.
- Runner: paged fetch of `wine_type IS NULL` wines, `--dry-run`/`--limit`,
  per-type counts + per-signal counts (varietal/name/grape/appellation), Slack
  summary, run from the mini with `/usr/bin/python3`.

### 4. Dry-run precision audit (conservative-rule teeth)

Before the live run: full dry-run to a log; hand-sample the name-fallback tier
(watch for brand-color false positives — a "Red Car" Chardonnay) and the new
appellation-inferred tier; confirm non-wine junk (sake/cocktail/fruit/pancake)
resolves to None and stays NULL. If a systematic error class appears, patch
`infer_wine_type` / the appellation map and re-run before writing.

### 5. Live run + verification

Expected fill ≈ **3,985 of 5,443** (~73%): the 3,135 baseline + ~331 vocab-sync
+ ~500 appellation-typed. Verify: per-type distribution, catalog `wine_type`-null
rate drop (~27.5% → ~10%), and spot-check that a formerly-NULL wine (e.g. a
Chablis, an Arneis) now appears in the search screen's type filter. ~1,460 stay
NULL (grocery junk + signal-less producers → Vivino/LLM).

## Testing

- **TDD `infer_wine_type`:** Pet Nat/Col Fondo → sparkling (not red); each newly
  added grape → correct color; the `CORE_GRAPES` parity test; regression on
  existing behavior (no false-positive on brand color words already handled).
- **TDD `wine_type_for_appellation`:** Chablis→white, Champagne→sparkling,
  Brunello→red, Sauternes→dessert, Jerez→fortified; multi-color appellation
  (Meursault's Burgundy / a Bordeaux commune / "Tuscany") → None; None inputs → None.
- **TDD `plan_change`:** each resolve tier fires in precedence order; fill-only
  (never overwrites a set type); non-wine name → no-op; appellation fallback
  fires only when varietal/name/grape all miss.
- **Acceptance gate:** dry-run counts reconcile to the estimate; a hand-audit of
  ~30 name-fallback + appellation rows shows no mislabels before the live run.

## Out of scope

- The ~462 non-wine grocery items (should arguably be filtered out of the wine
  catalog entirely — separate concern) and ~500 signal-less producers (Vivino/LLM).
- Changing the runtime `resolve_wine_type` — the backfill writes `wine_type` to
  the DB, so those rows no longer need runtime inference; new wines inherit the
  hardened `infer_wine_type` automatically via extraction.
- Any `wine_type` provenance/source column (fill-only + audit makes it moot).
