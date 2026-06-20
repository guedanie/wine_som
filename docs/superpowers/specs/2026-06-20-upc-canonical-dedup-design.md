# Canonical-UPC Cross-Retailer Deduplication Design

**Date:** 2026-06-20
**Status:** Approved

## Problem

`wines` is deduplicated by exact `upc` string (`on_conflict="upc"`). But the same physical wine is encoded differently by each retailer:

- **HEB** stores the full 12-digit UPC-A (11-digit core **+ check digit**) — 100% valid UPC-A.
- **Spec's** stores the 11-digit core with a **leading zero** (no recomputed check digit) — 89% fail UPC-A validation.

Example — Justin Chardonnay: HEB `733952123144`, Spec's `073395212314`. Shared core: `73395212314`.

Result: the same wine lands as two rows, fragmenting inventory and price across two `wine_id`s. Measured impact: of 1,904 distinct HEB wines, only 14 currently overlap with Spec's by exact UPC; with normalized cores the real overlap is ~810. So ~810 wines are duplicated in the catalog.

## Scope

**In scope:** barcode retailers — HEB, Spec's, and future Central Market (HEB-owned, same GraphQL → HEB UPC format). Both a going-forward dedup fix and a one-time merge of the ~810 existing duplicates.

**Out of scope:** Geraldine's uses synthetic IDs (`shopify-geraldines-{handle}`) — no barcodes. Cross-matching natural-wine shops is a fuzzy name/producer/vintage matching problem (the GrapeMinds matching subsystem's domain), handled separately.

## Field-Merge Policy

When duplicate rows collapse, the survivor takes display fields by **source priority**, per field:
- `name`, `brand`: prefer Spec's > HEB (cleaner names). Geraldine's never appears in barcode groups.
- `description` (on `wine_details`): keep the **longest**.
- `image_url`: first non-null.
- `region` / `sub_region` / `country` / `varietal` / `grapes` / `abv` / `body`: keep survivor's value if present, else fill from loser (Haiku-extracted, source-agnostic).

**Prices are never affected.** They live in `retail_inventory` keyed by *(wine × store)*, not on `wines`. All inventory rows re-point to the survivor and are preserved — this is what enables "cheapest place to buy this wine near you."

## Architecture

Chosen approach: **add a `upc_canonical` column** (keep raw `upc` intact), unique index used for dedup. Preserves each retailer's original barcode for debugging; canonical is the identity. (Rejected: normalizing `upc` in place loses source barcodes; a separate `products` table is over-engineered for two retailers.)

### Component 1: `backend/utils/upc.py`

Pure function, fully unit-testable:

```
canonical_upc(raw: Optional[str]) -> Optional[str]
```

Algorithm:
1. `None` or synthetic (`shopify-…`) → return unchanged (never collides).
2. Strip to digits.
3. 12 digits, **valid UPC-A check digit** → return `[:11]` (HEB-style).
4. 12 digits, invalid check, leading `0` → return `[1:]` (Spec's zero-padded core).
5. 13 digits (EAN-13) with leading `0` → drop it → apply rule 3; else return `[:12]`.
6. Otherwise (10/11-digit oddballs) → return digits unchanged.

UPC-A check validation: `(10 - ((sum(odd positions)*3 + sum(even positions)) % 10)) % 10 == last digit`.

### Component 2: Migration `20260620000002_wine_upc_canonical.sql`

```sql
ALTER TABLE wines ADD COLUMN IF NOT EXISTS upc_canonical TEXT;
```

The **unique index is NOT created here** — it is added by the merge script after backfill, because it would fail against the existing duplicates. This migration alone is intentionally incomplete; it must be followed by the merge script.

### Component 3: Merge/backfill script `backend/scripts/merge_duplicate_wines.py`

Idempotent, re-runnable, per-group error handling. Steps:

1. **Backfill** `upc_canonical = canonical_upc(upc)` for every wine row.
2. **Group** wines by `upc_canonical` where group size > 1.
3. **Survivor** = wine with the most `retail_inventory` rows; tiebreak lowest `id`.
4. **Merge display fields** onto survivor per the field-merge policy above.
5. **Re-point dependents** from each loser → survivor:
   - `retail_inventory.wine_id` → survivor (no `UNIQUE(upc, store_ref)` conflict; raw UPCs differ, so per-retailer prices stay as distinct rows).
   - `wine_details`: `UNIQUE(wine_id)` — keep the longest-description row, delete the loser's.
   - `wine_grapeminds_matches`: re-point; dedupe resulting `(wine_id, grapeminds_id)` collisions, keeping `is_primary` / highest confidence.
   - `user_saved_wines`: re-point (empty today; handled for safety).
6. **Delete** loser wine rows. `recommendation_sessions` keeps wine_ids in a JSONB snapshot (not a live FK), so history is unaffected.
7. **Add unique index** on `upc_canonical` after dupes are gone:
   `CREATE UNIQUE INDEX IF NOT EXISTS idx_wines_upc_canonical ON wines(upc_canonical) WHERE upc_canonical IS NOT NULL;`

Prints a summary: groups merged, wine rows deleted, inventory rows re-pointed.

### Component 4: Scraper integration — `BaseScraper._upsert_wines`

Single change point; all scrapers inherit it.
- Compute `upc_canonical = canonical_upc(item.upc)` per record; include in the upsert payload.
- Change `on_conflict="upc"` → `on_conflict="upc_canonical"`.
- The returned `upc -> wine_id` map must still key on the **raw** `item.upc` (because `retail_inventory.upc` stores the raw barcode). After the canonical upsert, build the map by selecting back on `upc_canonical` and re-associating each item's raw upc to its wine_id.

Geraldine's synthetic IDs pass through `canonical_upc` unchanged and never collide. Central Market (when added) uses HEB's format and dedups automatically.

## Testing

- `tests/test_upc.py` — `canonical_upc` against real examples:
  - HEB `733952123144` → `73395212314`; Spec's `073395212314` → `73395212314` (match)
  - La Marca pair (`085000022436` / `008500002243`) → `08500002243`
  - Daou pair (`890409002398` / `089040900239`) → `89040900239`
  - 13-digit EAN with leading zero; synthetic `shopify-…` unchanged; `None` → `None`
- `tests/test_base_scraper.py` — `_upsert_wines`:
  - HEB+Spec's pair for the same product collapses to one canonical wine row
  - returns both raw-upc → wine_id mappings correctly
  - upsert `on_conflict` target is `upc_canonical`
- Merge script test against a seeded fake DB: 2-row dup group → 1 survivor; inventory re-pointed; longest description wins; grapeminds matches deduped.

## Verification (post live run)

Re-run the exclusivity query. Expected:
- HEB-exclusive: 1,890 → ~1,083
- HEB/Spec's overlap: 14 → ~810
- Total wine count: down ~810

## Implementation Order

1. `canonical_upc` + tests (TDD)
2. Migration (add column)
3. `_upsert_wines` integration + tests (TDD)
4. Merge script + test
5. Apply migration, run merge script live, verify
