# Grapes Backfill + Vivino Queue Prioritization — Design

**Date:** 2026-07-14 · **CLAUDE.md items:** 27 (grapes backfill, Vivino queue), 13 (both-null priority), + one scorer rule
**Status:** approved design, pre-implementation

## Problem

Old-World rows extracted before the appellation-law blend defaults shipped have
`grapes = []` (empty JSON array, not NULL) — so the weekly `--null-only`
extraction never revisits them and the scorer's grape matching can't see them.

Measured 2026-07-14:

| Region | Total | grapes-empty | covered by current defaults | uncovered |
|---|---|---|---|---|
| Bordeaux | 1,093 | 361 (33%) | 284 | 77 (47 no sub_region, 30 missing appellations) |
| Rhône | 360 | 130 (36%) | 84 | 46 (21 no sub_region, 25 missing appellations) |

Related defects found during design:

- **White-wine landmine:** `default_grapes_for()` has no wine_type gate — the
  extractor (extractor.py step 3b) would stamp a red blend on a white
  Pessac-Léognan. ~14 known white rows sit in "covered" appellations.
- **"Red blend" requests boost almost nothing:** candidate grape matching
  (scorer.py:118) reads only the `grapes` column; literal "Red Blend" appears
  in `grapes` on 7 wines but as `varietal` on 819. The liked-wines path
  already unions varietal into the grape set (scorer.py:38-40); the candidate
  path doesn't.
- **Vivino can't correct defaults:** `write_facts` is fill-only, so once
  defaults land, a later high-confidence Vivino match can't write the real
  blend.

## Decisions (user-approved)

1. Expand `APPELLATION_DEFAULT_GRAPES` + add a wine_type gate.
2. Region-level defaults for **reds only** (Bordeaux → Merlot-led, Rhône → GSM).
3. Varietal: NULL → blend's first grape (matches extraction); a specific-grape
   varietal is trusted (`grapes = [varietal]`, no appellation blend); generic
   varietals ("Red Blend", "Red Wine", …) keep their value and get the blend.
4. Blend-aware scorer rule included in this work.
5. Vivino queue tiers: both-null → un-enriched Bordeaux/Rhône → rest.
6. Vivino may replace grapes that exactly equal a known default blend.

## Design

### 1. `enrichment/extraction/reference.py`

**Defaults become color-aware.** Internal table maps
`_norm(appellation) → (grapes, color, requires_type)`:

- `color`: `"red" | "white" | "rose"` — the blend's color.
- `requires_type`: True for appellations that legally allow multiple colors
  (Graves, Pessac-Léognan, Côtes de Bordeaux, region-level entries) — the
  default fires only when the caller's wine_type matches. Single-color AOCs
  (Pauillac, Hermitage, Sauternes…) fire when wine_type is unknown (None) but
  never when it conflicts.

**`default_grapes_for(appellation, wine_type=None)`** — second arg added,
default None keeps the signature backward-compatible. Returns None on color
conflict or when `requires_type` and wine_type is None.

**New entries** (grapes → first is the varietal):

- Right-bank additions: Saint-Émilion Grand Cru; Lussac-/Montagne-/
  Puisseguin-Saint-Émilion; Castillon + Castillon Côtes de Bordeaux +
  Côtes de Castillon; Côtes de Bordeaux; Bordeaux Supérieur — all
  `[Merlot, Cabernet Franc, Cabernet Sauvignon]` (red).
- Whites: Entre-Deux-Mers → `[Sauvignon Blanc, Sémillon]` (white).
- Northern Rhône: Hermitage, Cornas, Crozes-Hermitage, Côte-Rôtie,
  Saint-Joseph → `[Syrah]` (red); Condrieu → `[Viognier]` (white).
- Rosé: Tavel → `[Grenache]` (rose).
- Southern-Rhône satellites: Ventoux, Cairanne, Rasteau, Vinsobres →
  GSM (red).
- Existing entries keep their blends; Graves + Pessac-Léognan additionally
  get white variants `[Sauvignon Blanc, Sémillon]` selected by wine_type.

**`_norm` folds hyphens to spaces** — fixes "Lalande de Pomerol" vs
"Lalande-de-Pomerol" and "Côte-Rôtie" vs "Cote-Rotie" classes everywhere
`_norm` is used (appellation index + defaults). Guard with tests that current
lookups still resolve.

**`REGION_DEFAULT_GRAPES`** (new, red-gated — wine_type must be exactly
"red"): `Bordeaux → [Merlot, Cabernet Sauvignon, Cabernet Franc]`,
`Rhône → [Grenache, Syrah, Mourvèdre]`. Exposed via
`default_grapes_for_region(region, wine_type)`.

**`ALL_DEFAULT_BLENDS`** (new): frozenset of tuples of every default blend
(appellation + region level) — consumed by Vivino's replace rule.

### 2. `enrichment/extraction/extractor.py`

- `_post_process(rec, source_text, wine_type=None)` — new optional kwarg,
  threaded from the wine row by the extraction runner (`extract_facts` and
  `run_extraction.py` pass the row's `wine_type`).
- Step 3b becomes: try `default_grapes_for(sub_region, wine_type)`, else
  `default_grapes_for_region(region, wine_type)`. Still never overwrites
  model-supplied grapes. Step 8 (varietal = first grape) unchanged.

### 3. `scripts/backfill_grapes.py` (new; `revalidate_regions.py` pattern)

Pure planning core + thin runner:

```
plan_change(row) -> dict   # {} when no-op; else {"grapes": [...]} (+ "varietal")
```

Order of precedence per row (row has `id, name, region, sub_region, varietal,
wine_type, grapes`):

1. Skip unless `region ∈ {Bordeaux, Rhône}` and `not (grapes or [])`.
2. `varietal` is a specific canonical grape (i.e. `canonical_grape(varietal)`
   maps into the known grape vocabulary, not a generic like "Red Blend",
   "White Blend", "Red Wine", "White Wine", "Other", "Sauternes") →
   `grapes = [canonical varietal]`. Varietal untouched.
3. Else `default_grapes_for(sub_region, wine_type)` →
   `grapes = blend`.
4. Else `default_grapes_for_region(region, wine_type)` (reds only) →
   `grapes = blend`.
5. Else no-op (left for Vivino).
6. Whenever grapes were set and `varietal` is NULL → `varietal = grapes[0]`.

Runner: paged fetch (1000/page, `.order("id")`), `--dry-run`, `--limit N`,
per-row change line, summary counts by rule (specific-varietal / appellation /
region-level / skipped), Slack notification on live runs. Writes only the
changed fields. Run from `backend/` on the mini with `/usr/bin/python3`.

Expected fill: ~430–460 of the 491 empty rows (284+84 currently covered,
+~55 from expanded appellations, + red subset of the 68 region-only rows,
+~25 specific-varietal rows; whites in dual-color appellations without a
wine_type and non-red region-only rows remain for Vivino).

### 4. `recommendation/scorer.py` — blend-aware grape matching

- Candidate grape set gains `varietal`:
  `grapes = {_norm(g) for g in (wine.get("grapes") or [])}` ∪
  `{_norm(varietal)}` when set — mirrors `_norm_liked`.
- Blend rule: if `want_grapes` contains `"red blend"` (resp. `"white blend"`),
  a wine also earns `_W_GRAPE` when it has **≥2 entries in its `grapes`
  column** and `wine_type == "red"` (resp. `"white"`). Wines with
  `varietal="Red Blend"` already match via the union above. Conservative:
  unknown wine_type does not match the blend rule.
- No weight changes; the boost fires at most once per wine (existing
  `want_grapes & grapes` OR blend rule).

### 5. `scripts/run_vivino_sample.py` — queue tiers + default replacement

- `fetch_sample` (default path only; `--missing-images` behavior unchanged)
  fills the limit from three tiers, all with `vivino_enriched_at IS NULL` +
  the existing junk-name filters, deduped by id, in order:
  1. both-null: `varietal IS NULL AND region IS NULL` (item 13 — invisible
     to the recommender),
  2. `region IN ('Bordeaux','Rhône')` (item 27 — unrated Old World),
  3. the rest (current query).
- `write_facts`: grapes may be **replaced** (not just filled) when the
  current value, as a tuple, is in `ALL_DEFAULT_BLENDS` and the Vivino match
  supplies grapes — real per-wine data beats law-book approximations. All
  other fields stay fill-only. Existing FACTS_THRESHOLD gate unchanged.

## Testing (TDD, `backend/tests/`)

- `test_extraction_reference.py` (extend): gate conflicts (white wine ×
  left-bank appellation → None), requires_type (Graves + None → None,
  Graves + red → Cab-led, Graves + white → Sauv Blanc-led), new appellations,
  hyphen/accent variants via `_norm`, region defaults red-only,
  `ALL_DEFAULT_BLENDS` contents.
- `test_backfill_grapes.py` (new): each precedence rule, generic-varietal
  handling, white-in-red-appellation skip, varietal set only when NULL,
  no-op rows, non-Bordeaux/Rhône rows untouched.
- `test_scorer.py` (extend): "red blend" ask boosts a 3-grape red and a
  varietal="Red Blend" wine, does not boost a single-grape red or a 2-grape
  white; candidate varietal-union matches a varietal-only wine. Reorder
  inputs so stable-sort ties can't mask the change (CLAUDE.md TDD note).
- `test_vivino_runner.py` (extend): tier ordering + dedup + limit trim;
  write_facts replaces a default blend, does not replace scraped/extracted
  grapes, still fills empty.
- Extractor: `_post_process` passes wine_type through; default None preserves
  current single-color behavior.

## Rollout (from the mini, `backend/`)

1. Land code + tests (`python3 -m pytest tests/ -m "not integration"`).
2. `python3 -m scripts.backfill_grapes --dry-run` — reconcile counts against
   the table above before writing.
3. Live run; verify Slack summary; spot-check a Pauillac (Cab-led), a
   Saint-Émilion (Merlot-led), a Tavel (Grenache/rosé), a white Entre-Deux-Mers.
4. Update CLAUDE.md item 27 (grapes backfill done; Vivino queue done) +
   item 13 (queue priority live), `docs/reference/enrichment.md`,
   `docs/mini-agent-tasks.md`.

## Out of scope

- Bulk NULLing of unevidenced regions (still deferred — Task 3 policy).
- Re-queueing already-attempted (stamped) Vivino failures.
- Scorer region-fallback for still-empty rows (item 27's optional follow-on).
- The extraction prompt itself (defaults are post-process only).
