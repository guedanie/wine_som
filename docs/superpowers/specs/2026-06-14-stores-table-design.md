# Stores Registry Table — Design

**Date:** 2026-06-14
**Status:** Approved (design)
**Scope:** Normalize per-store metadata out of `retail_inventory` into a `stores` registry; full cutover of writers and readers. Foundation for multi-store H-E-B + Central Market and zip→nearest-store.

---

## 1. Overview

Today `retail_inventory` is store-specific (keyed by `UNIQUE(upc, store_id)`) but **duplicates store metadata** (name, address, city, state, zip, lat/lng) on every row. Fine for 3 stores; an update-anomaly liability once we scale to hundreds of H-E-B stores plus Central Market.

This introduces a **`stores` registry** (one row per physical store) and slims `retail_inventory` to per-store *volatile* data (price, curbside price, stock) referencing a store by UUID. It is a **full cutover**: schema migration + data backfill + updated scraper writes + updated recommender read + dropping the denormalized columns — no lingering dual source of truth.

---

## 2. Scope

**In scope:**
- New `stores` table; `retail_inventory.store_ref` FK; drop denormalized columns.
- One atomic migration that backfills `stores` and links inventory before dropping anything.
- Cutover of `BaseScraper`, `HebScraper`, and `recommend.py`.
- Tests for the new store resolution and the updated recommender retrieval.

**Out of scope (future):**
- **zip→nearest-store by distance** — the schema carries `lat/lng`, but current scrapers don't capture coordinates, so zip filtering stays exact-match for now.
- **Central Market scraper** — same Apollo backend as H-E-B (client name `central-market`); a separate scraper task. This stores table is the prerequisite that lets CM stores coexist cleanly.
- **Warm-up (B) / refresh (C)** specs — to be written next, on top of this.

---

## 3. Schema

### New table: `stores`

```sql
CREATE TABLE stores (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  retailer_name TEXT NOT NULL,          -- chain: "H-E-B", "Central Market", "Geraldine's Natural Wines"
  store_id      TEXT NOT NULL,          -- chain's own id: H-E-B "567", CM store #, Geraldine slug
  name          TEXT,
  address       TEXT,
  city          TEXT,
  state         TEXT,
  zip_code      TEXT,
  latitude      NUMERIC(9,6),
  longitude     NUMERIC(9,6),
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (retailer_name, store_id)
);
CREATE INDEX idx_stores_zip ON stores(zip_code);

ALTER TABLE stores ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read stores" ON stores FOR SELECT USING (TRUE);
GRANT SELECT ON stores TO anon, authenticated;
GRANT ALL    ON stores TO service_role;
```

Synthetic UUID PK with `UNIQUE(retailer_name, store_id)` — collision-proof across chains (H-E-B "567" can't clash with a Central Market "567").

### `retail_inventory` after cutover

Keeps only: `id, wine_id, upc, store_ref, price, curbside_price, in_stock, last_scraped_at`.
- `store_ref UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE`
- `UNIQUE (upc, store_ref)` (replaces `UNIQUE(upc, store_id)`)

---

## 4. Migration & Backfill

One atomic migration (`supabase/migrations/20260614000002_stores_table.sql`). Ordered so no column is dropped before its data is moved; Postgres runs DDL transactionally, so a failure rolls the whole thing back.

```sql
-- 1. stores table (Section 3) ...

-- 2. nullable FK column on inventory
ALTER TABLE retail_inventory ADD COLUMN store_ref UUID REFERENCES stores(id) ON DELETE CASCADE;

-- 3. seed stores: one row per (retailer, store_id) with its metadata
INSERT INTO stores (retailer_name, store_id, name, address, city, state, zip_code, latitude, longitude)
SELECT DISTINCT ON (retailer_name, store_id)
       retailer_name, store_id, store_name, address, city, state, zip_code, latitude, longitude
FROM retail_inventory
WHERE store_id IS NOT NULL
ORDER BY retailer_name, store_id;

-- 4. link every inventory row to its store
UPDATE retail_inventory ri SET store_ref = s.id
FROM stores s
WHERE ri.retailer_name = s.retailer_name AND ri.store_id = s.store_id;

-- 5. GUARD: aborts the whole migration if any row failed to link (before any column is dropped)
ALTER TABLE retail_inventory ALTER COLUMN store_ref SET NOT NULL;

-- 6. drop denormalized columns (also drops the old UNIQUE(upc, store_id))
ALTER TABLE retail_inventory
  DROP COLUMN retailer_name, DROP COLUMN store_id, DROP COLUMN store_name,
  DROP COLUMN address, DROP COLUMN city, DROP COLUMN state, DROP COLUMN zip_code,
  DROP COLUMN latitude, DROP COLUMN longitude;

-- 7. new uniqueness
ALTER TABLE retail_inventory ADD CONSTRAINT uq_inv_upc_store UNIQUE (upc, store_ref);
```

**Step 5 is the backstop:** if backfill missed any row, `SET NOT NULL` errors and rolls back before columns are dropped — data can't be silently lost.

Applied via `supabase db push --yes` (history is clean). Post-apply verification: `stores` has 2 rows (H-E-B 567 + Geraldine's), and `retail_inventory` has 0 rows with null `store_ref`.

---

## 5. Code Cutover

### `backend/scrapers/base.py`

New `_upsert_stores` (parallels `_upsert_wines`' bounded-lookup pattern):

```python
def _upsert_stores(self, items: List[RetailInventoryItem]) -> dict:
    """Upsert the distinct stores in this batch; return {(retailer_name, store_id): store_uuid}."""
    seen = {}
    for item in items:
        key = (item.retailer_name, item.store_id)
        if item.retailer_name and item.store_id and key not in seen:
            seen[key] = {k: v for k, v in {
                "retailer_name": item.retailer_name,
                "store_id": item.store_id,
                "name": item.store_name,
                "address": item.address,
                "city": item.city,
                "state": item.state,
                "zip_code": item.zip_code,
            }.items() if v is not None}
    if not seen:
        return {}
    self.supabase.table("stores").upsert(
        list(seen.values()), on_conflict="retailer_name,store_id"
    ).execute()
    store_ids = [k[1] for k in seen]
    result = (
        self.supabase.table("stores")
        .select("id,retailer_name,store_id")
        .in_("store_id", store_ids)
        .execute()
    )
    return {(s["retailer_name"], s["store_id"]): s["id"] for s in result.data}
```

`_upsert_inventory` writes slim rows referencing `store_ref`:

```python
def _upsert_inventory(self, items: List[RetailInventoryItem], upc_to_id: dict):
    store_map = self._upsert_stores(items)
    now = datetime.now(timezone.utc).isoformat()
    records = []
    for item in items:
        store_ref = store_map.get((item.retailer_name, item.store_id))
        if not store_ref:
            continue
        records.append({k: v for k, v in {
            "wine_id": upc_to_id.get(item.upc) if item.upc else None,
            "upc": item.upc,
            "store_ref": store_ref,
            "price": item.price,
            "in_stock": item.in_stock,
            "last_scraped_at": now,
        }.items() if v is not None})
    if records:
        self.supabase.table("retail_inventory").upsert(
            records, on_conflict="upc,store_ref"
        ).execute()
```

`RetailInventoryItem` is unchanged — it still carries the store metadata as *input*; the scraper maps it to a store upsert + a slim inventory row.

### `backend/scrapers/heb.py`

`_upsert_inventory_with_curbside` resolves `store_ref` via the inherited `_upsert_stores` and writes `curbside_price` + `store_ref` (no denormalized fields), `on_conflict="upc,store_ref"`.

### `backend/scrapers/geraldines.py`

Inherits the updated `base._upsert_inventory` — no change beyond what base provides.

### `backend/api/routers/recommend.py` (the inventory reader)

- Retrieval query joins the store and filters on its zip:
  ```python
  .select("price, curbside_price, wine_id, "
          "stores!inner(retailer_name, store_name, zip_code), "
          "wines(id, name, varietal, region, country, wine_type, "
          "wine_details(tasting_notes, flavor_profile, structure_profile, grapeminds_enriched_at))")
  .eq("stores.zip_code", req.zip_code)
  .eq("in_stock", True)
  .gte("price", req.budget_min)
  .lte("price", req.budget_max)
  ```
- Candidate flattening reads retailer from the joined store: `store = row.get("stores") or {}; retailer = store.get("retailer_name")`.

Zip filtering behaves exactly as today, now sourced from `stores.zip_code`.

---

## 6. Testing

1. **`backend/tests/test_base_scraper.py`** (extend):
   - `test_upsert_stores_dedupes_and_maps` — given items across one store, `_upsert_stores` upserts once and returns a `{(retailer, store_id): uuid}` map (fake Supabase capturing upsert payload + returning a seeded `stores` select).
   - `test_upsert_inventory_writes_store_ref` — `_upsert_inventory` writes rows with `store_ref` and no denormalized columns; `on_conflict="upc,store_ref"`.
2. **`backend/tests/test_heb.py`** (extend): `test_upsert_inventory_with_curbside_uses_store_ref` — verifies the HEB inventory write carries `store_ref` + `curbside_price` and omits denormalized fields (fake Supabase).
   - Existing `test_scraper_maps_to_inventory_items` is unaffected (`RetailInventoryItem` unchanged).
3. **`backend/tests/test_recommend_api.py`** (update): the `WINE_ROW` fixture nests `stores` (`{"retailer_name","store_name","zip_code"}`) instead of a top-level `retailer_name`; assertions read retailer from the nested store. The mocked DB is fluent, so only the data shape changes.

All existing suites must still pass.

---

## 7. Error Handling & Edge Cases

| Case | Behavior |
|---|---|
| Item missing `retailer_name` or `store_id` | Excluded from `_upsert_stores`; its inventory row is skipped (can't link to a store). |
| Store metadata differs across rows for same `(retailer, store_id)` | `DISTINCT ON` (migration) / first-seen (scraper) wins; later scrapes upsert-overwrite the store row. |
| Inventory upsert conflict | `on_conflict="upc,store_ref"` updates price/curbside/stock/last_scraped_at in place (idempotent re-scrape). |
| Backfill leaves a null `store_ref` | Migration step 5 (`SET NOT NULL`) aborts the entire migration before any column is dropped. |
| `stores` select for the map | Filtered by the batch's `store_id`s — bounded, never hits the 1,000-row cap. |

---

## 8. File Map

| File | Action | Responsibility |
|---|---|---|
| `supabase/migrations/20260614000002_stores_table.sql` | Create | `stores` table + backfill + slim `retail_inventory` |
| `backend/scrapers/base.py` | Modify | `_upsert_stores` + `_upsert_inventory` (store_ref) |
| `backend/scrapers/heb.py` | Modify | `_upsert_inventory_with_curbside` uses `store_ref` |
| `backend/api/routers/recommend.py` | Modify | Retrieval joins `stores`, filters by `stores.zip_code` |
| `backend/tests/test_base_scraper.py` | Modify | Store resolution + slim inventory tests |
| `backend/tests/test_heb.py` | Modify | HEB inventory `store_ref` test |
| `backend/tests/test_recommend_api.py` | Modify | Nest `stores` in fixture; retailer from store |

`geraldines.py` needs no change (inherits base).

---

## 9. Out of Scope / Future

- **zip→nearest-store by distance** — populate `stores.lat/lng` (geocode or capture during scrape), then rank stores by haversine distance to the user's zip in `recommend.py`.
- **Central Market scraper** — reuse the HEB GraphQL scraper with `Apollographql-Client-Name: central-market` + CM store ids; writes `retailer_name = "Central Market"` rows that slot into this `stores` model cleanly.
- **Warm-up (B) & refresh (C)** — the GrapeMinds enrichment scaling specs, written next, with cross-store/retailer prioritization built on this registry.
