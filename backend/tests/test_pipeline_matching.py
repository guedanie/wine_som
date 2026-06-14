import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import patch, MagicMock
from enrichment.pipeline import persist_candidates


def _capture_table():
    """A fake Supabase table that records delete/insert calls."""
    calls = {"deleted": False, "inserted": None}

    class FakeTable:
        def delete(self):
            calls["deleted"] = True
            return self
        def eq(self, *a, **k):
            return self
        def insert(self, records):
            calls["inserted"] = records
            return self
        def execute(self):
            return MagicMock(data=[])

    client = MagicMock()
    client.table.return_value = FakeTable()
    return client, calls


def test_persist_candidates_deletes_then_inserts_top3():
    client, calls = _capture_table()
    candidates = [
        {"grapeminds_id": "136214", "display_name": "Decoy, Cabernet Sauvignon",
         "producer_name": "Decoy", "color": "red", "confidence": 0.97, "rank": 1, "is_primary": True},
        {"grapeminds_id": "235600", "display_name": "Decoy, Cab, Sonoma",
         "producer_name": "Decoy", "color": "red", "confidence": 0.93, "rank": 2, "is_primary": False},
    ]
    with patch("enrichment.pipeline.get_service_client", return_value=client):
        persist_candidates("wine-1", candidates)

    assert calls["deleted"] is True
    assert calls["inserted"] is not None
    assert len(calls["inserted"]) == 2
    first = calls["inserted"][0]
    assert first["wine_id"] == "wine-1"
    assert first["grapeminds_id"] == "136214"
    assert first["is_primary"] is True


def test_persist_candidates_empty_is_noop():
    client, calls = _capture_table()
    with patch("enrichment.pipeline.get_service_client", return_value=client):
        persist_candidates("wine-1", [])
    assert calls["inserted"] is None
