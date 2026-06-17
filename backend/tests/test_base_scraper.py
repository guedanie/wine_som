import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from unittest.mock import MagicMock
from scrapers.base import RetailInventoryItem
from scrapers.heb import HebScraper


class FakeWinesDB:
    """
    Simulates Supabase/PostgREST for the wines table, including the 1000-row
    default cap on an unfiltered select. A filtered select via .in_("upc", ...)
    returns exactly the matching rows (no cap).
    """
    def __init__(self, all_wines):
        self.all = all_wines           # list of {"id","upc"}
        self._op = None
        self._filter_upcs = None

    def table(self, name):
        return self

    def upsert(self, records, on_conflict=None):
        self._op = "upsert"
        return self

    def select(self, cols):
        self._op = "select"
        self._filter_upcs = None
        return self

    def in_(self, col, vals):
        self._filter_upcs = set(vals)
        return self

    def execute(self):
        if self._op == "upsert":
            return MagicMock(data=[])
        # select
        if self._filter_upcs is not None:
            data = [w for w in self.all if w["upc"] in self._filter_upcs]
        else:
            data = self.all[:1000]     # PostgREST default cap
        return MagicMock(data=data)


def test_upsert_wines_links_batch_upcs_beyond_1000_cap():
    # 1200 pre-existing wines; the batch's wines live BEYOND index 1000, so an
    # unfiltered select (capped at 1000) cannot see them — reproducing the orphan bug.
    existing = [{"id": f"id-{i}", "upc": f"upc-{i}"} for i in range(1200)]
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
