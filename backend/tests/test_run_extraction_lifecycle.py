"""
run_extraction should book a scraper_runs row so verify_scrape_runs.py can see it.

Retailer name: "Extraction (local qwen)". Lifecycle: insert running → update
success/failed on exit. Without this, a dead extraction Sunday is invisible
until varietal/region NULL coverage drifts up.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1]))

from enrichment.extraction import run_extraction


EXTRACTION_RETAILER = "Extraction (local qwen)"


class FakeRunsDB:
    """Captures scraper_runs insert + update calls with just enough chainability."""

    def __init__(self):
        self.inserts = []            # list of records
        self.updates = []            # list of (record, eq_id)
        self._table = None
        self._pending_update = None
        self._pending_eq = None
        # wines table calls just return an empty page so fetch_wines short-circuits.
        self._empty_data = MagicMock(data=[])

    def table(self, name):
        self._table = name
        return self

    def insert(self, record):
        self.inserts.append((self._table, record))
        return self

    def update(self, record):
        if self._table == "scraper_runs":
            self._pending_update = record
        return self

    def eq(self, col, val):
        if self._table == "scraper_runs" and self._pending_update is not None:
            self._pending_eq = (col, val)
        return self

    def select(self, *a, **k):
        return self

    def is_(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def range(self, *a, **k):
        return self

    def execute(self):
        if self._table == "scraper_runs" and self._pending_update is not None:
            self.updates.append((self._pending_update, self._pending_eq))
            self._pending_update = None
            self._pending_eq = None
            return MagicMock(data=[])
        return self._empty_data


def _run_main(db, extractor=None):
    """Invoke run_extraction.main with a fake db + a stub extractor."""
    with patch("enrichment.extraction.run_extraction.get_service_client", return_value=db), \
         patch("enrichment.extraction.run_extraction.get_extractor",
               return_value=extractor or (lambda batch, batch_size=15: [])), \
         patch("sys.argv", ["run_extraction"]):
        run_extraction.main()


def test_success_writes_running_then_success_row():
    db = FakeRunsDB()
    _run_main(db)

    # exactly one insert with status=running, correct retailer name
    runs_inserts = [r for t, r in db.inserts if t == "scraper_runs"]
    assert len(runs_inserts) == 1
    assert runs_inserts[0]["retailer_name"] == EXTRACTION_RETAILER
    assert runs_inserts[0]["status"] == "running"
    assert "id" in runs_inserts[0]

    # exactly one update, status=success, records_updated present
    assert len(db.updates) == 1
    update_rec, eq = db.updates[0]
    assert update_rec["status"] == "success"
    assert "records_updated" in update_rec
    assert update_rec.get("completed_at")
    assert eq == ("id", runs_inserts[0]["id"])


def test_records_updated_reflects_written_wines():
    """records_updated should equal the wines actually written, not the input count."""
    # fetch_wines returns [] with the fake db, so we simulate by patching fetch_wines
    db = FakeRunsDB()
    fake_wines = [{"id": f"w-{i}", "name": "Test", "wine_type": "red",
                   "description": "", "description_long": ""} for i in range(7)]

    def fake_extractor(batch, batch_size=15):
        return [{"wine_id": w["id"], "region": "Napa"} for w in batch]

    with patch("enrichment.extraction.run_extraction.get_service_client", return_value=db), \
         patch("enrichment.extraction.run_extraction.get_extractor", return_value=fake_extractor), \
         patch("enrichment.extraction.run_extraction.fetch_wines", return_value=fake_wines), \
         patch("enrichment.extraction.run_extraction.write_batch"), \
         patch("sys.argv", ["run_extraction"]):
        run_extraction.main()

    update_rec, _ = db.updates[0]
    assert update_rec["records_updated"] == 7


def test_failure_writes_failed_row_and_reraises():
    db = FakeRunsDB()

    def boom(batch, batch_size=15):
        raise RuntimeError("Ollama unreachable")

    fake_wines = [{"id": "w-1", "name": "X", "wine_type": "red",
                   "description": "", "description_long": ""}]

    raised = False
    try:
        with patch("enrichment.extraction.run_extraction.get_service_client", return_value=db), \
             patch("enrichment.extraction.run_extraction.get_extractor", return_value=boom), \
             patch("enrichment.extraction.run_extraction.fetch_wines", return_value=fake_wines), \
             patch("sys.argv", ["run_extraction"]):
            run_extraction.main()
    except RuntimeError:
        raised = True

    assert raised, "main should re-raise so launchd/shell surfaces a nonzero exit"
    assert len(db.updates) == 1
    update_rec, _ = db.updates[0]
    assert update_rec["status"] == "failed"
    assert "Ollama unreachable" in (update_rec.get("error_message") or "")
    assert update_rec.get("completed_at")
