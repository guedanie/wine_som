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
