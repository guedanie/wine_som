# Stores Registry Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize per-store metadata out of `retail_inventory` into a `stores` registry (UUID PK, unique per retailer+store_id), and cut over scrapers + the recommender to use it.

**Architecture:** A new `stores` table holds store metadata once; `retail_inventory` references a store by UUID and keeps only volatile data (price, curbside_price, in_stock). One atomic migration backfills `stores` from existing inventory and slims the table. `BaseScraper` gains `_upsert_stores`; the HEB writer and the recommender retrieval are updated to use `store_ref` / join `stores`.

**Tech Stack:** Python 3.9 (`Optional[...]`, not `X | None`), supabase-py, Supabase/PostgREST, pytest. Migration applied via `supabase db push`.

**Spec:** `docs/superpowers/specs/2026-06-14-stores-table-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `supabase/migrations/20260614000002_stores_table.sql` | Create | `stores` table + backfill + slim `retail_inventory` |
| `backend/scrapers/base.py` | Modify | `_upsert_stores` + `_upsert_inventory` (store_ref) |
| `backend/scrapers/heb.py` | Modify | `_upsert_inventory_with_curbside` uses `store_ref` |
| `backend/api/routers/recommend.py` | Modify | Retrieval joins `stores`, retailer/zip from store |
| `backend/tests/test_base_scraper.py` | Modify | Store resolution + slim inventory tests |
| `backend/tests/test_heb.py` | Modify | HEB inventory `store_ref` test |
| `backend/tests/test_recommend_api.py` | Modify | Nest `stores` in fixture |

All commands run from `backend/` unless noted.

---

### Task 1: Migration — stores table + backfill + slim retail_inventory

**Files:**
- Create: `supabase/migrations/20260614000002_stores_table.sql`

- [ ] **Step 1: Write the migration**

Create `supabase/migrations/20260614000002_stores_table.sql`:

```sql
-- One row per physical store; metadata lives here once instead of on every inventory row.
CREATE TABLE stores (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  retailer_name TEXT NOT NULL,
  store_id      TEXT NOT NULL,
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

-- FK column on inventory (nullable during backfill)
ALTER TABLE retail_inventory ADD COLUMN store_ref UUID REFERENCES stores(id) ON DELETE CASCADE;

-- Seed stores from existing inventory (one row per retailer+store_id)
INSERT INTO stores (retailer_name, store_id, name, address, city, state, zip_code, latitude, longitude)
SELECT DISTINCT ON (retailer_name, store_id)
       retailer_name, store_id, store_name, address, city, state, zip_code, latitude, longitude
FROM retail_inventory
WHERE store_id IS NOT NULL
ORDER BY retailer_name, store_id;

-- Link every inventory row to its store
UPDATE retail_inventory ri SET store_ref = s.id
FROM stores s
WHERE ri.retailer_name = s.retailer_name AND ri.store_id = s.store_id;

-- GUARD: fails (and rolls back the whole migration) if any row failed to link
ALTER TABLE retail_inventory ALTER COLUMN store_ref SET NOT NULL;

-- Drop denormalized columns (also drops the old UNIQUE(upc, store_id))
ALTER TABLE retail_inventory
  DROP COLUMN retailer_name, DROP COLUMN store_id, DROP COLUMN store_name,
  DROP COLUMN address, DROP COLUMN city, DROP COLUMN state, DROP COLUMN zip_code,
  DROP COLUMN latitude, DROP COLUMN longitude;

-- New uniqueness: one inventory row per wine per store
ALTER TABLE retail_inventory ADD CONSTRAINT uq_inv_upc_store UNIQUE (upc, store_ref);
```

- [ ] **Step 2: Apply to the cloud DB**

```bash
cd /Users/danielguerrero/Documents/ai_dev/wine_app
supabase db push --dry-run < /dev/null 2>&1 | grep -iE "would push|stores_table"
```
Expected: lists only `20260614000002_stores_table.sql`. Then:
```bash
supabase db push --yes < /dev/null 2>&1 | grep -iE "Applying|Finished"
```
Expected: `Applying migration 20260614000002_stores_table.sql...` then `Finished supabase db push.`

- [ ] **Step 3: Verify backfill**

```bash
cd backend && python3 -c "
from db import get_service_client
c = get_service_client()
s = c.table('stores').select('id,retailer_name,store_id,zip_code', count='exact').execute()
print('stores:', s.count)
for r in s.data: print('  ', r['retailer_name'], r['store_id'], r['zip_code'])
orphan = c.table('retail_inventory').select('id', count='exact').is_('store_ref','null').limit(1).execute()
print('inventory rows without store_ref:', orphan.count)
"
```
Expected: 2 stores (H-E-B 567, Geraldine's), and `inventory rows without store_ref: 0`.

- [ ] **Step 4: Commit**

```bash
cd /Users/danielguerrero/Documents/ai_dev/wine_app
git add supabase/migrations/20260614000002_stores_table.sql
git commit -m "feat: stores registry table + slim retail_inventory (migration)"
```

---

### Task 2: BaseScraper — `_upsert_stores` + slim `_upsert_inventory` (TDD)

**Files:**
- Modify: `backend/scrapers/base.py`
- Modify: `backend/tests/test_base_scraper.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_base_scraper.py`:

```python
class FakeStoresDB:
    """Routes by table name; returns seeded stores for the lookup, captures upserts."""
    def __init__(self, store_rows):
        self.store_rows = store_rows           # [{"id","retailer_name","store_id"}]
        self.captured = {}
        self._table = None
        self._op = None
        self._filter = None

    def table(self, name):
        self._table = name
        self._op = None
        self._filter = None
        return self

    def upsert(self, records, on_conflict=None):
        self.captured.setdefault("upsert", {})[self._table] = records
        self._op = "upsert"
        return self

    def select(self, cols):
        self._op = "select"
        return self

    def in_(self, col, vals):
        self._filter = set(vals)
        return self

    def eq(self, *a, **k):
        return self

    def execute(self):
        if self._op == "select" and self._table == "stores":
            data = [s for s in self.store_rows
                    if self._filter is None or s["store_id"] in self._filter]
            return MagicMock(data=data)
        return MagicMock(data=[])


def test_upsert_stores_returns_keyed_map():
    db = FakeStoresDB([{"id": "store-uuid-1", "retailer_name": "H-E-B", "store_id": "567"}])
    scraper = HebScraper.__new__(HebScraper)
    scraper.supabase = db
    items = [RetailInventoryItem(
        wine_name="X", retailer_name="H-E-B", zip_code="78208",
        store_id="567", store_name="Lincoln Heights", upc="u1")]
    m = scraper._upsert_stores(items)
    assert m[("H-E-B", "567")] == "store-uuid-1"
    assert db.captured["upsert"]["stores"][0]["retailer_name"] == "H-E-B"
    assert db.captured["upsert"]["stores"][0]["name"] == "Lincoln Heights"


def test_upsert_inventory_writes_store_ref_no_denorm():
    db = FakeStoresDB([{"id": "store-uuid-1", "retailer_name": "H-E-B", "store_id": "567"}])
    scraper = HebScraper.__new__(HebScraper)
    scraper.supabase = db
    items = [RetailInventoryItem(
        wine_name="X", retailer_name="H-E-B", zip_code="78208",
        store_id="567", upc="u1", price=20.0)]
    scraper._upsert_inventory(items, {"u1": "wine-1"})
    rec = db.captured["upsert"]["retail_inventory"][0]
    assert rec["store_ref"] == "store-uuid-1"
    assert rec["wine_id"] == "wine-1"
    assert "retailer_name" not in rec and "zip_code" not in rec and "store_id" not in rec
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python3 -m pytest tests/test_base_scraper.py -v
```
Expected: failures — `_upsert_stores` does not exist; `_upsert_inventory` still writes denormalized fields.

- [ ] **Step 3: Implement in `backend/scrapers/base.py`**

Add `_upsert_stores` (place it right before `_upsert_inventory`):

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

Replace the entire `_upsert_inventory` method with:

```python
    def _upsert_inventory(self, items: List[RetailInventoryItem], upc_to_id: dict):
        """Upsert slim retail inventory rows referencing a store_ref."""
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

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && python3 -m pytest tests/test_base_scraper.py -v
```
Expected: all pass (the 2 prior `_upsert_wines` tests + 2 new).

- [ ] **Step 5: Commit**

```bash
git add backend/scrapers/base.py backend/tests/test_base_scraper.py
git commit -m "feat: BaseScraper _upsert_stores + slim store_ref inventory (TDD)"
```

---

### Task 3: HEB writer — `store_ref` cutover (TDD)

**Files:**
- Modify: `backend/scrapers/heb.py`
- Modify: `backend/tests/test_heb.py`

- [ ] **Step 1: Append a failing test**

Append to `backend/tests/test_heb.py`:

```python
def test_upsert_inventory_with_curbside_uses_store_ref():
    scraper = HebScraper.__new__(HebScraper)
    captured = {}

    class FakeTable:
        def upsert(self, records, on_conflict=None):
            captured["records"] = records
            captured["on_conflict"] = on_conflict
            return self
        def execute(self):
            return MagicMock(data=[])

    scraper.supabase = MagicMock()
    scraper.supabase.table.return_value = FakeTable()
    scraper._upsert_wines = lambda items: {"669576019191": "wine-1"}
    scraper._upsert_stores = lambda items: {("H-E-B", "567"): "store-1"}

    p = _parse_record(_raw_record())  # Decoy, upc 669576019191, curbside 19.92
    scraper._upsert_inventory_with_curbside([p])

    rec = captured["records"][0]
    assert captured["on_conflict"] == "upc,store_ref"
    assert rec["store_ref"] == "store-1"
    assert rec["wine_id"] == "wine-1"
    assert rec["curbside_price"] == 19.92
    assert "retailer_name" not in rec and "zip_code" not in rec and "store_id" not in rec
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd backend && python3 -m pytest tests/test_heb.py::test_upsert_inventory_with_curbside_uses_store_ref -v
```
Expected: fail — current method writes denormalized fields, no `store_ref`, `on_conflict="upc,store_id"`.

- [ ] **Step 3: Update `_upsert_inventory_with_curbside` in `backend/scrapers/heb.py`**

Replace the method body with:

```python
    def _upsert_inventory_with_curbside(self, products: List[HEBProduct]):
        """Like base._upsert_inventory but includes curbside_price; references store_ref."""
        from datetime import datetime, timezone
        items = self._products_to_inventory_items(products)
        upc_to_id = self._upsert_wines(items)
        store_map = self._upsert_stores(items)
        now = datetime.now(timezone.utc).isoformat()
        curbside_by_upc = {p.upc: p.curbside_price for p in products if p.upc}
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
                "curbside_price": curbside_by_upc.get(item.upc),
                "in_stock": item.in_stock,
                "last_scraped_at": now,
            }.items() if v is not None})
        if records:
            self.supabase.table("retail_inventory").upsert(
                records, on_conflict="upc,store_ref"
            ).execute()
        return upc_to_id
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python3 -m pytest tests/test_heb.py -v
```
Expected: all pass (existing 11 + 1 new).

- [ ] **Step 5: Commit**

```bash
git add backend/scrapers/heb.py backend/tests/test_heb.py
git commit -m "feat: HEB inventory writer uses store_ref (TDD)"
```

---

### Task 4: Recommender — join `stores` (TDD)

**Files:**
- Modify: `backend/api/routers/recommend.py`
- Modify: `backend/tests/test_recommend_api.py`

- [ ] **Step 1: Update the test fixture to nest `stores`**

In `backend/tests/test_recommend_api.py`, replace the `WINE_ROW` dict (the one with top-level `price`, `retailer_name`, `wine_id`, `wines`) with:

```python
WINE_ROW = {
    "price": 22.0,
    "curbside_price": None,
    "wine_id": "abc-123",
    "stores": {"retailer_name": "Geraldine's", "store_name": "Geraldine's", "zip_code": "78209"},
    "wines": {
        "id": "abc-123",
        "name": "Test Malbec",
        "varietal": "Malbec",
        "region": "Mendoza",
        "country": "Argentina",
        "wine_type": "red",
        "wine_details": [{
            "tasting_notes": "dark fruit, plum, chocolate",
            "flavor_profile": ["dark fruit", "plum"],
            "structure_profile": {"body": 8, "tannins": 7, "acidity": 5},
            "grapeminds_enriched_at": "2026-06-03T00:00:00Z",
        }],
    },
}
```

- [ ] **Step 2: Run the recommend tests to confirm the retailer assertion path still needs the code change**

```bash
cd backend && python3 -m pytest tests/test_recommend_api.py -v
```
Expected: `test_recommend_returns_200` and `test_recommend_picks_have_required_fields` still pass on shape, but the candidate's `retailer` now comes back `None` (old code reads top-level `retailer_name`, which no longer exists in the fixture). This confirms the code must change. (If they pass anyway, the code change in Step 3 is still required for production correctness.)

- [ ] **Step 3: Update the retrieval + flattening in `backend/api/routers/recommend.py`**

Replace the `result = (...)` query block and the candidate-append block. Change the `.select(...)` and `.eq("zip_code", ...)` call from:

```python
    result = (
        supabase.table("retail_inventory")
        .select(
            "price, retailer_name, wine_id,"
            "wines(id, name, varietal, region, country, wine_type,"
            "wine_details(tasting_notes, flavor_profile, structure_profile, grapeminds_enriched_at))"
        )
        .eq("zip_code", req.zip_code)
        .eq("in_stock", True)
        .gte("price", req.budget_min)
        .lte("price", req.budget_max)
        .execute()
    )
```

to:

```python
    result = (
        supabase.table("retail_inventory")
        .select(
            "price, curbside_price, wine_id,"
            "stores!inner(retailer_name, store_name, zip_code),"
            "wines(id, name, varietal, region, country, wine_type,"
            "wine_details(tasting_notes, flavor_profile, structure_profile, grapeminds_enriched_at))"
        )
        .eq("stores.zip_code", req.zip_code)
        .eq("in_stock", True)
        .gte("price", req.budget_min)
        .lte("price", req.budget_max)
        .execute()
    )
```

And change the candidate append's `"retailer"` line from:

```python
            "retailer": row.get("retailer_name"),
```

to:

```python
            "retailer": (row.get("stores") or {}).get("retailer_name"),
```

- [ ] **Step 4: Run the recommend tests**

```bash
cd backend && python3 -m pytest tests/test_recommend_api.py -v
```
Expected: all 5 pass; the happy-path picks now carry `retailer = "Geraldine's"` from the joined store.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/recommend.py backend/tests/test_recommend_api.py
git commit -m "feat: recommender joins stores for retailer + zip (TDD)"
```

---

### Task 5: Full suite verification + live smoke check

- [ ] **Step 1: Run the whole suite**

```bash
cd backend && python3 -m pytest tests/ -q
```
Expected: all tests pass — the prior suite plus **3 new** tests (2 in `test_base_scraper.py`, 1 in `test_heb.py`). If the network-dependent `test_search_wines_returns_list` fails, confirm the Supabase project is awake — it's environmental, not a regression.

- [ ] **Step 2: Live smoke check — inventory still joins to stores**

```bash
cd backend && python3 -c "
from db import get_service_client
c = get_service_client()
r = c.table('retail_inventory').select('price, stores(retailer_name, zip_code), wines(name)').not_.is_('store_ref','null').limit(3).execute()
for row in r.data:
    print(row['price'], (row.get('stores') or {}).get('retailer_name'), (row.get('wines') or {}).get('name'))
"
```
Expected: 3 rows printing price, retailer, and wine name via the `stores` join.

- [ ] **Step 3: Report** the pass count and confirm `git status` is clean.
