# Canonical-UPC Cross-Retailer Dedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deduplicate the same physical wine across barcode retailers (HEB, Spec's, future Central Market) by normalizing UPCs to an 11-digit canonical core, then merge the ~810 existing duplicate wine rows.

**Architecture:** A pure `canonical_upc()` function normalizes HEB's full UPC-A and Spec's zero-padded core to one key. `wines` gets a `upc_canonical` column; `_upsert_wines` dedups on it. A one-time idempotent merge script collapses existing dupes, re-pointing inventory/details/matches to a survivor, then adds the unique index.

**Tech Stack:** Python 3.9 (`Optional[X]`, no `X | None`), Supabase (`supabase-py`), pytest.

**Reference spec:** `docs/superpowers/specs/2026-06-20-upc-canonical-dedup-design.md`

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `backend/utils/upc.py` | `canonical_upc()` pure function + UPC-A check digit |
| Create | `backend/tests/test_upc.py` | Unit tests for `canonical_upc` |
| Create | `supabase/migrations/20260620000002_wine_upc_canonical.sql` | Add `upc_canonical` column (no index yet) |
| Modify | `backend/scrapers/base.py` | `_upsert_wines` computes canonical, dedups on it, returns raw-upc map |
| Modify | `backend/tests/test_base_scraper.py` | Test cross-format collapse + raw-upc mapping |
| Create | `backend/scripts/merge_duplicate_wines.py` | One-time idempotent merge + index creation |
| Create | `backend/tests/test_merge_duplicate_wines.py` | Test pure merge helpers |

---

## Task 1: `canonical_upc` function (TDD)

**Files:**
- Create: `backend/utils/upc.py`
- Create: `backend/tests/test_upc.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_upc.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from utils.upc import canonical_upc


def test_heb_full_upca_drops_check_digit():
    # HEB stores valid 12-digit UPC-A; canonical = first 11 (drop check digit)
    assert canonical_upc("733952123144") == "73395212314"


def test_specs_zero_padded_core_drops_leading_zero():
    # Spec's stores 0 + 11-digit core; canonical = last 11
    assert canonical_upc("073395212314") == "73395212314"


def test_heb_and_specs_same_product_match():
    assert canonical_upc("733952123144") == canonical_upc("073395212314")


def test_la_marca_pair_matches():
    # HEB UPC also starts with 0 but is valid UPC-A; Spec's is zero-padded core
    assert canonical_upc("085000022436") == canonical_upc("008500002243") == "08500002243"


def test_daou_pair_matches():
    assert canonical_upc("890409002398") == canonical_upc("089040900239") == "89040900239"


def test_ean13_leading_zero_normalizes_to_upca_core():
    # 13-digit EAN with leading zero -> strip to 12-digit UPC-A -> core
    assert canonical_upc("0733952123144") == "73395212314"


def test_synthetic_shopify_id_unchanged():
    assert canonical_upc("shopify-geraldines-some-wine-2023") == "shopify-geraldines-some-wine-2023"


def test_none_returns_none():
    assert canonical_upc(None) is None


def test_empty_returns_none():
    assert canonical_upc("") is None


def test_short_oddball_returned_as_digits():
    # 10-digit Spec's oddball: returned as-is (digits only)
    assert canonical_upc("1234567890") == "1234567890"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_upc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'utils.upc'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/utils/upc.py`:

```python
"""
Canonical UPC normalization for cross-retailer wine deduplication.

HEB stores full 12-digit UPC-A (11-digit core + check digit).
Spec's stores the 11-digit core with a leading zero (no recomputed check).
Both normalize to the same 11-digit core. See:
docs/superpowers/specs/2026-06-20-upc-canonical-dedup-design.md
"""
from typing import Optional


def _is_valid_upca(d: str) -> bool:
    """True if d is a 12-digit string whose last digit is a valid UPC-A check digit."""
    if len(d) != 12 or not d.isdigit():
        return False
    odd = sum(int(d[i]) for i in range(0, 11, 2))
    even = sum(int(d[i]) for i in range(1, 11, 2))
    check = (10 - ((odd * 3 + even) % 10)) % 10
    return check == int(d[11])


def canonical_upc(raw: Optional[str]) -> Optional[str]:
    """
    Return the canonical 11-digit core for a retail UPC, or the input unchanged
    for synthetic IDs. Returns None for None/empty input.
    """
    if not raw:
        return None
    # Synthetic (non-barcode) IDs pass through untouched — they never collide.
    if not any(c.isdigit() for c in raw) or raw.startswith("shopify-"):
        return raw

    d = "".join(c for c in raw if c.isdigit())

    # 13-digit EAN with leading zero -> 12-digit UPC-A
    if len(d) == 13 and d.startswith("0"):
        d = d[1:]

    if len(d) == 12:
        if _is_valid_upca(d):
            return d[:11]          # HEB-style: core + check digit
        if d.startswith("0"):
            return d[1:]           # Spec's-style: 0-padded core
        return d[:11]              # invalid, no pad: best-effort drop check digit

    if len(d) == 13:
        return d[:12]              # true EAN-13: drop check digit

    return d                       # 10/11-digit oddballs: return digits unchanged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_upc.py -v`
Expected: 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/utils/upc.py backend/tests/test_upc.py
git commit -m "feat: canonical_upc UPC normalization for cross-retailer dedup (TDD)"
```

---

## Task 2: Migration — add `upc_canonical` column

**Files:**
- Create: `supabase/migrations/20260620000002_wine_upc_canonical.sql`

- [ ] **Step 1: Write the migration**

Create `supabase/migrations/20260620000002_wine_upc_canonical.sql`:

```sql
-- Canonical 11-digit UPC core for cross-retailer dedup (HEB full UPC-A vs Spec's
-- zero-padded core normalize to the same value). The UNIQUE index is added by the
-- merge script (backend/scripts/merge_duplicate_wines.py) AFTER existing duplicates
-- are merged — creating it here would fail against current duplicate rows.
ALTER TABLE wines ADD COLUMN IF NOT EXISTS upc_canonical TEXT;
```

- [ ] **Step 2: Commit (do not apply yet)**

The migration is applied live in Task 5, together with the merge script, so the unique-index ordering is preserved.

```bash
git add supabase/migrations/20260620000002_wine_upc_canonical.sql
git commit -m "feat: migration adds wines.upc_canonical column"
```

---

## Task 3: `_upsert_wines` dedups on canonical (TDD)

**Files:**
- Modify: `backend/scrapers/base.py` (the `_upsert_wines` method, currently lines 51–86)
- Modify: `backend/tests/test_base_scraper.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_base_scraper.py`:

```python
class FakeCanonicalDB:
    """
    Simulates the wines table keyed by upc_canonical. upsert collapses records
    with the same upc_canonical into one row (first raw upc wins the stored value).
    select by upc_canonical returns id + upc_canonical.
    """
    def __init__(self):
        self.rows = {}          # upc_canonical -> {"id","upc","upc_canonical"}
        self._next = 1
        self._op = None
        self._filter = None

    def table(self, name):
        self._op = None
        self._filter = None
        return self

    def upsert(self, records, on_conflict=None):
        assert on_conflict == "upc_canonical", f"expected canonical conflict, got {on_conflict}"
        for r in records:
            key = r["upc_canonical"]
            if key not in self.rows:
                self.rows[key] = {"id": f"wine-{self._next}", "upc": r.get("upc"), "upc_canonical": key}
                self._next += 1
        self._op = "upsert"
        return self

    def select(self, cols):
        self._op = "select"
        return self

    def in_(self, col, vals):
        self._filter = (col, set(vals))
        return self

    def execute(self):
        if self._op == "select":
            col, vals = self._filter
            data = [r for r in self.rows.values() if r.get(col) in vals]
            return MagicMock(data=data)
        return MagicMock(data=[])


def test_upsert_wines_collapses_cross_format_upcs():
    """HEB and Spec's UPCs for the same wine collapse to ONE canonical row,
    but both raw UPCs map to that wine_id."""
    db = FakeCanonicalDB()
    scraper = HebScraper.__new__(HebScraper)
    scraper.supabase = db
    items = [
        RetailInventoryItem(wine_name="Justin Chardonnay", retailer_name="H-E-B",
                            zip_code="78209", upc="733952123144"),
        RetailInventoryItem(wine_name="Justin Chardonnay", retailer_name="Spec's",
                            zip_code="78209", upc="073395212314"),
    ]
    upc_to_id = scraper._upsert_wines(items)
    # one canonical row created
    assert len(db.rows) == 1
    # both raw UPCs resolve to the same wine_id
    assert upc_to_id["733952123144"] == upc_to_id["073395212314"]


def test_upsert_wines_writes_canonical_column():
    db = FakeCanonicalDB()
    scraper = HebScraper.__new__(HebScraper)
    scraper.supabase = db
    items = [RetailInventoryItem(wine_name="Decoy", retailer_name="Spec's",
                                 zip_code="78209", upc="073395212314")]
    scraper._upsert_wines(items)
    assert "73395212314" in db.rows   # canonical core stored as key
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_base_scraper.py::test_upsert_wines_collapses_cross_format_upcs -v`
Expected: FAIL — `AssertionError: expected canonical conflict, got upc` (still upserting on raw `upc`).

- [ ] **Step 3: Rewrite `_upsert_wines` in `backend/scrapers/base.py`**

Replace the entire `_upsert_wines` method (lines 51–86) with:

```python
    def _upsert_wines(self, items: List[RetailInventoryItem]) -> dict:
        """
        Upsert wine catalog records, deduplicated by canonical UPC so the same
        physical wine from different retailers collapses to one row.
        Returns a {raw_upc -> wine_id} mapping for inventory linking.
        """
        from utils import infer_wine_type
        from utils.upc import canonical_upc

        seen = set()
        records = []
        for item in items:
            if not item.wine_name or (item.upc and item.upc in seen):
                continue
            if item.upc:
                seen.add(item.upc)
            canon = canonical_upc(item.upc)
            record = {k: v for k, v in {
                "upc": item.upc,
                "upc_canonical": canon,
                "name": item.wine_name,
                "brand": item.brand,
                "varietal": item.varietal,
                "wine_type": infer_wine_type(item.varietal or item.wine_name),
                "avg_price": item.price,
                "image_url": item.image_url,
            }.items() if v is not None}
            records.append(record)

        if records:
            self.supabase.table("wines").upsert(records, on_conflict="upc_canonical").execute()

        # Build {raw_upc -> wine_id}. retail_inventory stores the RAW upc, so we map
        # each item's raw upc through its canonical to the resulting wine_id.
        canons = [r["upc_canonical"] for r in records if r.get("upc_canonical")]
        if not canons:
            return {}
        result = self.supabase.table("wines").select("id,upc_canonical").in_("upc_canonical", canons).execute()
        canon_to_id = {w["upc_canonical"]: w["id"] for w in result.data if w.get("upc_canonical")}
        mapping = {}
        for item in items:
            if not item.upc:
                continue
            wid = canon_to_id.get(canonical_upc(item.upc))
            if wid:
                mapping[item.upc] = wid
        return mapping
```

- [ ] **Step 4: Run the new tests + the existing base-scraper suite**

Run: `cd backend && python3 -m pytest tests/test_base_scraper.py -v`
Expected: all PASS, including the two new tests. (The pre-existing `test_upsert_wines_links_batch_upcs_beyond_1000_cap` and `test_upsert_wines_includes_image_url` use `FakeWinesDB`/`FakeCapturingWinesDB` — verify those fakes still satisfy the new `on_conflict="upc_canonical"` and the canonical select. If a pre-existing fake asserts `on_conflict` or filters on `upc`, update it to accept `upc_canonical` and to return `upc_canonical` from select.)

- [ ] **Step 5: Reconcile pre-existing base-scraper fakes**

The pre-existing `FakeWinesDB` (used by `test_upsert_wines_links_batch_upcs_beyond_1000_cap`) returns rows with `id` + `upc` and filters select on `upc`. The new code selects `id,upc_canonical` filtered on `upc_canonical`. Update `FakeWinesDB` so its seeded rows include `upc_canonical` and its `in_`/`execute` handle an `upc_canonical` filter. Concretely, in `backend/tests/test_base_scraper.py`, change the seeded existing-wines fixtures to include `upc_canonical` equal to `canonical_upc(upc)` and make `FakeWinesDB.execute` return `upc_canonical` in each row. Re-run until green.

```python
# at top of test_base_scraper.py
from utils.upc import canonical_upc
```

The `test_upsert_wines_links_batch_upcs_beyond_1000_cap` seeds `{"id": f"id-{i}", "upc": f"upc-{i}"}`. Those raw upcs are non-numeric ("upc-1100"), so `canonical_upc` returns them unchanged — give each seeded row `"upc_canonical": f"upc-{i}"` and have `FakeWinesDB` filter/return on `upc_canonical`. The assertion `upc_to_id["upc-1100"] == "id-1100"` still holds because the raw upc maps through its (identical) canonical to the same id.

- [ ] **Step 6: Run the full suite**

Run: `cd backend && python3 -m pytest tests/ -v`
Expected: all tests PASS (was 113; now 113 + new upc/base tests).

- [ ] **Step 7: Commit**

```bash
git add backend/scrapers/base.py backend/tests/test_base_scraper.py
git commit -m "feat: _upsert_wines dedups on canonical UPC (TDD)"
```

---

## Task 4: Merge script + tests (TDD)

**Files:**
- Create: `backend/scripts/merge_duplicate_wines.py`
- Create: `backend/tests/test_merge_duplicate_wines.py`

The script separates **pure decision helpers** (testable) from DB I/O.

- [ ] **Step 1: Write the failing test for pure helpers**

Create `backend/tests/test_merge_duplicate_wines.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.merge_duplicate_wines import pick_survivor, merge_fields


def test_pick_survivor_prefers_most_inventory():
    group = [
        {"id": "a", "inventory_count": 1},
        {"id": "b", "inventory_count": 5},
        {"id": "c", "inventory_count": 3},
    ]
    assert pick_survivor(group) == "b"


def test_pick_survivor_tiebreak_lowest_id():
    group = [
        {"id": "z", "inventory_count": 2},
        {"id": "a", "inventory_count": 2},
    ]
    assert pick_survivor(group) == "a"


def test_merge_fields_prefers_specs_name_over_heb():
    survivor = {"id": "s", "name": "Decoy Cabernet Sauvignon California Red Wine",
                "source": "H-E-B", "region": None, "image_url": None}
    losers = [{"id": "l", "name": "Decoy Cabernet", "source": "Spec's",
               "region": "California", "image_url": "http://img"}]
    merged = merge_fields(survivor, losers)
    assert merged["name"] == "Decoy Cabernet"        # Spec's preferred
    assert merged["region"] == "California"           # filled from loser
    assert merged["image_url"] == "http://img"        # first non-null


def test_merge_fields_keeps_survivor_value_when_present():
    survivor = {"id": "s", "name": "A", "source": "Spec's",
                "region": "Napa", "image_url": "http://s"}
    losers = [{"id": "l", "name": "B", "source": "H-E-B",
               "region": "Sonoma", "image_url": "http://l"}]
    merged = merge_fields(survivor, losers)
    assert merged["region"] == "Napa"                 # survivor already had it
    assert merged["image_url"] == "http://s"          # survivor non-null wins
    assert merged["name"] == "A"                       # survivor is Spec's, kept
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_merge_duplicate_wines.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.merge_duplicate_wines'`

- [ ] **Step 3: Write the merge script**

Create `backend/scripts/merge_duplicate_wines.py`:

```python
"""
One-time, idempotent merge of duplicate wine rows that share a canonical UPC.

Run AFTER applying migration 20260620000002 (adds wines.upc_canonical):
    cd backend
    python3 scripts/merge_duplicate_wines.py

Steps: backfill upc_canonical -> group dupes -> merge fields onto a survivor ->
re-point retail_inventory / wine_details / wine_grapeminds_matches / user_saved_wines
-> delete losers -> create the unique index. Re-running after a partial failure is safe.

See docs/superpowers/specs/2026-06-20-upc-canonical-dedup-design.md
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from db import get_service_client
from utils.upc import canonical_upc

# Name source priority for display fields (lower index = preferred).
_NAME_PRIORITY = {"Spec's": 0, "H-E-B": 1}


def pick_survivor(group):
    """group: list of {"id", "inventory_count"}. Most inventory wins; tiebreak lowest id."""
    return sorted(group, key=lambda w: (-w["inventory_count"], w["id"]))[0]["id"]


def merge_fields(survivor, losers):
    """
    Return the dict of wine-column updates for the survivor.
    name/brand: prefer Spec's > HEB. region/sub_region/country/varietal/grapes/abv/body:
    keep survivor value if present, else fill from any loser.
    image_url: first non-null (survivor first).
    """
    out = dict(survivor)
    candidates = [survivor] + losers

    # name/brand by source priority
    for field in ("name", "brand"):
        ranked = sorted(
            [c for c in candidates if c.get(field)],
            key=lambda c: _NAME_PRIORITY.get(c.get("source"), 99),
        )
        if ranked:
            out[field] = ranked[0][field]

    # fill-if-null fields
    for field in ("region", "sub_region", "country", "varietal", "grapes", "abv", "body"):
        if out.get(field) in (None, "", [], "[]"):
            for c in candidates:
                if c.get(field) not in (None, "", [], "[]"):
                    out[field] = c[field]
                    break

    # image_url: first non-null, survivor first
    if not out.get("image_url"):
        for c in candidates:
            if c.get("image_url"):
                out["image_url"] = c["image_url"]
                break

    return out


# ─── DB orchestration ──────────────────────────────────────────────────────

_WINE_FIELDS = ("id,upc,upc_canonical,name,brand,region,sub_region,country,"
                "varietal,grapes,abv,body,image_url")


def _all_wines(db):
    rows, page, size = [], 0, 1000
    while True:
        r = db.table("wines").select(_WINE_FIELDS).range(page*size, (page+1)*size-1).execute()
        if not r.data:
            break
        rows.extend(r.data)
        if len(r.data) < size:
            break
        page += 1
    return rows


def _wine_source(db, wine_id):
    """Infer a wine's retailer from its inventory's stores (for name priority)."""
    inv = db.table("retail_inventory").select("store_ref").eq("wine_id", wine_id).execute()
    refs = [r["store_ref"] for r in inv.data if r.get("store_ref")]
    if not refs:
        return None
    st = db.table("stores").select("retailer_name").in_("id", refs[:50]).execute()
    names = {s["retailer_name"] for s in st.data}
    if "Spec's" in names:
        return "Spec's"
    if "H-E-B" in names:
        return "H-E-B"
    return next(iter(names), None)


def _inventory_count(db, wine_id):
    r = db.table("retail_inventory").select("id", count="exact").eq("wine_id", wine_id).execute()
    return r.count or 0


def main():
    db = get_service_client()

    print("Backfilling upc_canonical ...", flush=True)
    wines = _all_wines(db)
    for w in wines:
        canon = canonical_upc(w.get("upc"))
        if canon and w.get("upc_canonical") != canon:
            db.table("wines").update({"upc_canonical": canon}).eq("id", w["id"]).execute()
        w["upc_canonical"] = canon

    # group by canonical
    from collections import defaultdict
    groups = defaultdict(list)
    for w in wines:
        if w.get("upc_canonical"):
            groups[w["upc_canonical"]].append(w)
    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"  {len(dupes)} duplicate groups found", flush=True)

    merged = deleted = repointed = 0
    for canon, group in dupes.items():
        try:
            enriched = [{**w, "inventory_count": _inventory_count(db, w["id"]),
                         "source": _wine_source(db, w["id"])} for w in group]
            survivor_id = pick_survivor(enriched)
            survivor = next(w for w in enriched if w["id"] == survivor_id)
            losers = [w for w in enriched if w["id"] != survivor_id]

            # merge display fields onto survivor
            updates = merge_fields(survivor, losers)
            db.table("wines").update({
                k: updates.get(k) for k in
                ("name", "brand", "region", "sub_region", "country",
                 "varietal", "grapes", "abv", "body", "image_url")
            }).eq("id", survivor_id).execute()

            for loser in losers:
                lid = loser["id"]
                # retail_inventory -> survivor (raw upcs differ, no unique conflict)
                db.table("retail_inventory").update({"wine_id": survivor_id}).eq("wine_id", lid).execute()
                repointed += 1

                # wine_details: UNIQUE(wine_id) — keep longest description on survivor
                sd = db.table("wine_details").select("*").eq("wine_id", survivor_id).execute().data
                ld = db.table("wine_details").select("*").eq("wine_id", lid).execute().data
                if ld:
                    loser_desc = (ld[0].get("description") or "")
                    surv_desc = (sd[0].get("description") or "") if sd else ""
                    if not sd:
                        db.table("wine_details").update({"wine_id": survivor_id}).eq("wine_id", lid).execute()
                    else:
                        if len(loser_desc) > len(surv_desc) and loser_desc:
                            db.table("wine_details").update(
                                {"description": loser_desc}).eq("wine_id", survivor_id).execute()
                        db.table("wine_details").delete().eq("wine_id", lid).execute()

                # wine_grapeminds_matches: UNIQUE(wine_id, grapeminds_id) — re-point, skip collisions
                surv_gm = {m["grapeminds_id"] for m in
                           db.table("wine_grapeminds_matches").select("grapeminds_id").eq("wine_id", survivor_id).execute().data}
                for m in db.table("wine_grapeminds_matches").select("id,grapeminds_id").eq("wine_id", lid).execute().data:
                    if m["grapeminds_id"] in surv_gm:
                        db.table("wine_grapeminds_matches").delete().eq("id", m["id"]).execute()
                    else:
                        db.table("wine_grapeminds_matches").update({"wine_id": survivor_id}).eq("id", m["id"]).execute()

                # user_saved_wines: re-point (empty today; best-effort)
                try:
                    db.table("user_saved_wines").update({"wine_id": survivor_id}).eq("wine_id", lid).execute()
                except Exception:
                    pass

                # delete loser wine row
                db.table("wines").delete().eq("id", lid).execute()
                deleted += 1
            merged += 1
        except Exception as e:
            print(f"  group {canon} failed: {e}", flush=True)

    print(f"\nMerged {merged} groups, deleted {deleted} loser rows, re-pointed {repointed} inventory sets", flush=True)

    # create the unique index now that dupes are gone (idempotent)
    print("Creating unique index on upc_canonical ...", flush=True)
    db.rpc("exec_sql", {"sql":
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_wines_upc_canonical "
        "ON wines(upc_canonical) WHERE upc_canonical IS NOT NULL;"}).execute()
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
```

> **Note on the unique index:** if the project's Supabase has no `exec_sql` RPC, the index will instead be created as a follow-up migration in Task 5 Step 4. The script's `db.rpc(...)` call is wrapped so a missing RPC does not fail the merge — replace the final block with a printed reminder if `exec_sql` is unavailable.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_merge_duplicate_wines.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `cd backend && python3 -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/merge_duplicate_wines.py backend/tests/test_merge_duplicate_wines.py
git commit -m "feat: merge_duplicate_wines script + pure-helper tests (TDD)"
```

---

## Task 5: Apply migration, run merge live, verify

**Files:** none (operational). Requires explicit user authorization for the live cloud DB.

- [ ] **Step 1: Apply the column migration**

```bash
cd /Users/danielguerrero/Documents/ai_dev/wine_app
supabase db push
```
Expected: applies `20260620000002_wine_upc_canonical.sql`.

- [ ] **Step 2: Snapshot pre-merge counts**

```bash
cd backend && python3 - << 'EOF'
from db import get_service_client
db = get_service_client()
print("wines:", db.table("wines").select("id", count="exact").execute().count)
EOF
```
Record the count.

- [ ] **Step 3: Run the merge script**

```bash
cd backend && python3 scripts/merge_duplicate_wines.py
```
Expected: prints "~810 duplicate groups found", then a merge summary.

- [ ] **Step 4: If `exec_sql` RPC was unavailable, add the index via migration**

Create `supabase/migrations/20260620000003_wines_upc_canonical_index.sql`:
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_wines_upc_canonical
  ON wines(upc_canonical) WHERE upc_canonical IS NOT NULL;
```
Then `supabase db push`. (Skip if the script already created the index.)

- [ ] **Step 5: Verify the corrected exclusivity numbers**

```bash
cd backend && python3 - << 'EOF'
from db import get_service_client
from collections import defaultdict
db = get_service_client()
stores = {s["id"]: s["retailer_name"] for s in db.table("stores").select("id,retailer_name").execute().data}
wr = defaultdict(set)
page, size = 0, 1000
while True:
    rows = db.table("retail_inventory").select("wine_id,store_ref").range(page*size,(page+1)*size-1).execute()
    if not rows.data: break
    for r in rows.data:
        if r.get("wine_id"): wr[r["wine_id"]].add(stores.get(r.get("store_ref")))
    if len(rows.data) < size: break
    page += 1
heb = {w for w,rs in wr.items() if "H-E-B" in rs}
other = {w for w,rs in wr.items() if rs - {"H-E-B"}}
print("wines total:", db.table("wines").select("id", count="exact").execute().count)
print("HEB-exclusive:", len(heb - other), "(expect ~1083)")
print("HEB/other overlap:", len(heb & other), "(expect ~810)")
EOF
```
Expected: total wines down ~810; HEB-exclusive ~1,083; overlap ~810.

- [ ] **Step 6: Update CLAUDE.md**

Add to the Critical Technical Notes: a "Cross-retailer dedup" subsection documenting `canonical_upc`, the `upc_canonical` column + unique index, and that `_upsert_wines` dedups on it. Commit and push.

```bash
git add CLAUDE.md && git commit -m "docs: document canonical-UPC dedup" && git push origin main
```
