# Purge Non-Wine Inventory (Design)

**Date:** 2026-07-21
**Roadmap item:** 32

## Problem

Grocery scrapers (H-E-B / Central Market) pull non-wine catalog noise into the `wines`
table: fruit cocktail, pancake mix, sake, cough syrup, peach slices, cookies & cream,
beer, glassware. Catalog scan (20,759 wines) found ~703 name-matched non-wine rows, of
which **149 still carry a `wine_type`** and thus reach the recommender; the rest are
mostly filtered today only incidentally (the recommend fetch drops rows with no
`varietal`/`region` and no GrapeMinds enrichment). Non-wine also pollutes catalog stats,
Discover, `/deals`, and search.

The recommender is for **still/sparkling table wine**. Non-wine should be excluded
everywhere it surfaces — without ever dropping a real wine.

## Key constraint: false positives are the failure mode

A wine that vanishes from recommendations is worse than a stray non-wine slipping
through. The catalog scan surfaced concrete traps a naive token match would misfire on:

- **Barrel-aged wines**: "Bota Box **Bourbon Barrel** Cabernet", "Mondavi Merlot **Rum
  Barrel** Aged", "Cooper & Thief **Brandy Barrel** Pinot" — real wines.
- **Producer / place collisions**: "**Stout** Family Sauvignon Blanc" (winery), "**MARTINI**
  & Rossi Asti" (real sparkling), "Hampton **Water** / Summer **Water**" (famous rosés),
  "Silver Oak **Soda** Canyon Napa" (a place), 'Iruai "Road **Opener**"' (a wine name).
- **Real wine in gift packaging**: "Chateau Calon-Ségur Bordeaux **Gift Set**".

Design is therefore deny-list + guards, and errs toward keeping.

## Decisions (locked)

- **Wine-adjacent products are KEPT**: vermouth (~118), sangria (~60), and RTD
  wine-cocktails (margarita/spritz/chocolate "wine" ~60) are wine-based and may be
  stocked intentionally — the purge targets only clearly non-wine products.
- **Soft-delete** via a new column (reversible, auditable), not hard delete.
- **Conservative trade-off accepted**: a genuinely non-wine item that carries a
  hallucinated `varietal`/`grape` will survive the purge (the wine-signal guard protects
  it). Acceptable — err toward keeping.
- **Weekly-pipeline wiring is a follow-up**, not core scope.

## Design

### 1. Canonical detection module — `backend/enrichment/non_wine.py`

Consolidates non-wine detection (the existing `_NON_WINE_MARKERS` / `_is_non_wine` in
`scripts/backfill_wine_type.py` move here; `backfill_wine_type.py` imports the shared
name check — DRY, and it makes that pass skip the new markers too, which is correct).

- **`NON_WINE_MARKERS`** — the current tuple plus the *clean* additions from the scan:
  - beer family: `beer, ale, lager, ipa, pilsner`
  - merchandise: `gift set, gift basket, glassware, corkscrew, decanter, tumbler, wine opener`
  - `cough syrup`
  - **NOT added** (collide with real wines): `bourbon, rum, brandy, water, soda, martini,
    opener, stout, punch`.
- **`is_non_wine_name(name: Optional[str]) -> bool`** — whole-word match
  `re.search(rf"\b{re.escape(m)}\b", name.lower())` over `NON_WINE_MARKERS`. (Same logic
  as today's `_is_non_wine`.)
- **`_ALLOWLIST`** — a small hardcoded set of normalized name fragments that must never
  be excluded even if flagged and un-enriched: `hampton water`, `summer water`,
  `road opener`. Extensible.
- **`should_exclude(wine: Dict) -> bool`** — the purge gate. True only when ALL hold:
  1. `is_non_wine_name(wine["name"])` is true;
  2. **barrel guard**: `"barrel"` not in `name.lower()` (protects barrel-aged wines);
  3. **wine-signal guard**: `wine.get("varietal")` is falsy AND `not (wine.get("grapes"))`
     (a real wine almost always carries a varietal/grape; beer/sake/fruit-cocktail don't);
  4. **allowlist guard**: no `_ALLOWLIST` fragment appears in `name.lower()`.

### 2. Migration — soft-delete column

`supabase/migrations/<ts>_wines_excluded.sql`: add `excluded_at timestamptz` (nullable,
default null) and `exclusion_reason text` to `wines`. Add-only; null = active. Grants
follow the existing pattern so anon reads see the column.

### 3. Purge script — `backend/scripts/purge_non_wine.py`

- **Dry-run by default**: scans all `wines` (paginated `.order("id")`), computes
  `should_exclude`, prints the total count, a sample, and the marker that fired per row.
  No writes.
- **`--apply`**: sets `excluded_at = now()` and `exclusion_reason = <matched marker>` for
  each `should_exclude` row. Idempotent — only touches rows where `excluded_at IS NULL`.
- Uses the service client (write). Reversal is a one-line SQL `UPDATE … SET excluded_at =
  NULL` — documented in the script header.

### 4. Read-path filtering — exclude everywhere wine surfaces

Every read path that surfaces wines filters `excluded_at IS NULL`:
- **Recommend** (`api/routers/recommend.py`): add `excluded_at` to `INVENTORY_SELECT`; in
  `_row_to_candidate`, return `None` when `wine.get("excluded_at")` is set (belt). Add the
  DB-level filter to the breadth + targeted + deep fetches where it composes cleanly.
- **`/deals`**, **Discover rail**, **search** endpoints: add the same `excluded_at IS NULL`
  filter to their wine queries.

### 5. Testing

- `backend/tests/test_non_wine.py`:
  - clean flags: "Del Monte Fruit Cocktail", "Pacifico Mexican Lager", "Gekkeikan Sake
    Nigori", "Stemless Champagne Glassware Set" → `should_exclude` True.
  - traps kept (`should_exclude` False): "Bota Box Bourbon Barrel Cabernet" (varietal
    Cabernet + barrel), "MARTINI & Rossi Asti" (grape Moscato), "Stout Family Sauvignon
    Blanc" (varietal), "Hampton Water Rosé" (allowlist), "Calon-Ségur Bordeaux Gift Set"
    (region/varietal).
  - `is_non_wine_name` whole-word: "Barbera"/"Barolo"/"Alentejo"/"Beerenauslese" NOT flagged.
- `backfill_wine_type` tests still pass after the import refactor.
- Purge dry-run sanity against live data (acceptance, not committed as a test).

## Out of scope (follow-up)

- Wiring `purge_non_wine.py --apply` into the weekly scrape/enrichment pipeline so
  re-scraped grocery noise is swept continuously.
- Re-flagging on `wine_type`/varietal change (a purge row that later gains a real varietal
  is simply left excluded until a manual/weekly re-run clears it — acceptable).
