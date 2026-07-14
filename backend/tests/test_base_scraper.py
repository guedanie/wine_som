import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from unittest.mock import MagicMock
from scrapers.base import RetailInventoryItem
from scrapers.heb import HebScraper
from utils.upc import canonical_upc


class FakeWinesDB:
    """
    Simulates Supabase/PostgREST for the wines table, including the 1000-row
    default cap on an unfiltered select. A filtered select via .in_(col, ...)
    returns exactly the matching rows (no cap), matching on the named column.
    """
    def __init__(self, all_wines):
        self.all = all_wines           # list of {"id","upc","upc_canonical"}
        self._op = None
        self._filter = None            # (col, set(vals)) or None

    def table(self, name):
        return self

    def upsert(self, records, on_conflict=None):
        self._op = "upsert"
        return self

    def select(self, cols):
        self._op = "select"
        self._filter = None
        return self

    def in_(self, col, vals):
        self._filter = (col, set(vals))
        return self

    def execute(self):
        if self._op == "upsert":
            return MagicMock(data=[])
        # select
        if self._filter is not None:
            col, vals = self._filter
            data = [w for w in self.all if w.get(col) in vals]
        else:
            data = self.all[:1000]     # PostgREST default cap
        return MagicMock(data=data)


def test_upsert_wines_links_batch_upcs_beyond_1000_cap():
    # 1200 pre-existing wines; the batch's wines live BEYOND index 1000, so an
    # unfiltered select (capped at 1000) cannot see them — reproducing the orphan bug.
    existing = [
        {"id": f"id-{i}", "upc": f"upc-{i}", "upc_canonical": canonical_upc(f"upc-{i}")}
        for i in range(1200)
    ]
    batch_upcs = ["upc-1100", "upc-1101", "upc-1102"]

    scraper = HebScraper.__new__(HebScraper)  # skip __init__ (no real Supabase)
    scraper.supabase = FakeWinesDB(existing)

    items = [
        RetailInventoryItem(
            wine_name=f"Cabernet Sauvignon {u}",
            retailer_name="H-E-B",
            zip_code="78208",
            upc=u,
        )
        for u in batch_upcs
    ]

    upc_to_id = scraper._upsert_wines(items)

    for u in batch_upcs:
        assert u in upc_to_id, f"{u} orphaned — upc->id map missing a batch UPC"
    assert upc_to_id["upc-1100"] == "id-1100"


def test_upsert_wines_empty_batch_returns_empty_map():
    scraper = HebScraper.__new__(HebScraper)
    scraper.supabase = FakeWinesDB([])
    assert scraper._upsert_wines([]) == {}


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


def test_upsert_stores_populates_lat_lon():
    """Stores upserted with a valid zip should have latitude/longitude populated."""
    upserted = {}

    class FakeStoresDB:
        def table(self, name):
            return self
        def upsert(self, records, on_conflict=None):
            for r in records:
                upserted[r["store_id"]] = r
            return self
        def select(self, cols):
            return self
        def in_(self, col, vals):
            return self
        def execute(self):
            return MagicMock(data=[
                {"id": "uuid-1", "retailer_name": "H-E-B", "store_id": "567"}
            ])

    scraper = HebScraper.__new__(HebScraper)
    scraper.supabase = FakeStoresDB()

    items = [RetailInventoryItem(
        wine_name="Test Wine",
        retailer_name="H-E-B",
        store_id="567",
        store_name="H-E-B",
        zip_code="78208",
        price=15.0,
        in_stock=True,
    )]
    scraper._upsert_stores(items)

    assert "567" in upserted
    assert upserted["567"]["latitude"] is not None
    assert upserted["567"]["longitude"] is not None
    # Should be San Antonio coordinates
    assert 29.0 < upserted["567"]["latitude"] < 30.0


class FakeCapturingWinesDB:
    """Captures the records passed to wines.upsert for assertion."""
    def __init__(self):
        self.captured = None
    def table(self, name):
        return self
    def upsert(self, records, on_conflict=None):
        self.captured = records
        return self
    def select(self, cols):
        return self
    def in_(self, col, vals):
        return self
    def execute(self):
        return MagicMock(data=[])


def test_upsert_wines_includes_image_url():
    db = FakeCapturingWinesDB()
    scraper = HebScraper.__new__(HebScraper)
    scraper.supabase = db
    items = [RetailInventoryItem(
        wine_name="Decoy Cabernet", retailer_name="Spec's", zip_code="78209",
        upc="u1", image_url="https://cdn.example.com/decoy.jpg")]
    scraper._upsert_wines(items)
    assert db.captured[0]["image_url"] == "https://cdn.example.com/decoy.jpg"


def test_upsert_wines_dedups_by_canonical_when_two_raws_collide():
    """Two distinct raw UPCs that canonicalize to the same value must collapse
    to ONE upsert record — else Postgres raises
    'ON CONFLICT DO UPDATE command cannot affect row a second time'.
    Keep-last semantics: the last occurrence's fields win."""
    db = FakeCapturingWinesDB()
    scraper = HebScraper.__new__(HebScraper)
    scraper.supabase = db
    # 12-digit UPC and its 13-digit "0"-prefixed twin canonicalize identically
    items = [
        RetailInventoryItem(wine_name="Justin Chardonnay (raw a)", retailer_name="H-E-B",
                            zip_code="78209", upc="733952123144", price=19.99),
        RetailInventoryItem(wine_name="Justin Chardonnay (raw b)", retailer_name="Spec's",
                            zip_code="78209", upc="0733952123144", price=21.99),
    ]
    scraper._upsert_wines(items)
    assert len(db.captured) == 1, (
        f"expected 1 upsert record after canonical dedup, got {len(db.captured)}: {db.captured}"
    )
    # keep-last: raw b wins
    assert db.captured[0]["name"] == "Justin Chardonnay (raw b)"
    assert db.captured[0]["avg_price"] == 21.99


def test_upsert_inventory_dedups_by_upc_and_store_ref():
    """Two inventory rows with the same (upc, store_ref) must collapse to one
    upsert record. Keep-last: the last occurrence's price wins."""
    db = FakeStoresDB([{"id": "store-uuid-1", "retailer_name": "H-E-B", "store_id": "567"}])
    scraper = HebScraper.__new__(HebScraper)
    scraper.supabase = db
    items = [
        RetailInventoryItem(wine_name="Dup", retailer_name="H-E-B", zip_code="78208",
                            store_id="567", upc="u1", price=19.99),
        RetailInventoryItem(wine_name="Dup", retailer_name="H-E-B", zip_code="78208",
                            store_id="567", upc="u1", price=22.50),
    ]
    scraper._upsert_inventory(items, {"u1": "wine-1"})
    recs = db.captured["upsert"]["retail_inventory"]
    assert len(recs) == 1, f"expected 1 inventory record after dedup, got {len(recs)}: {recs}"
    assert recs[0]["price"] == 22.50   # last wins


def test_upsert_wines_omits_image_url_when_absent():
    db = FakeCapturingWinesDB()
    scraper = HebScraper.__new__(HebScraper)
    scraper.supabase = db
    items = [RetailInventoryItem(
        wine_name="No Image Wine", retailer_name="H-E-B", zip_code="78208", upc="u2")]
    scraper._upsert_wines(items)
    assert "image_url" not in db.captured[0]


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
