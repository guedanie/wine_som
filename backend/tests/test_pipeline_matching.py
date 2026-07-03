import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import patch, MagicMock
from enrichment.pipeline import persist_candidates


def _capture_table():
    """A fake Supabase table that records upsert calls."""
    calls = {"upserted": None}

    class FakeTable:
        def upsert(self, records, on_conflict=None):
            calls["upserted"] = records
            return self
        def execute(self):
            return MagicMock(data=[])

    client = MagicMock()
    client.table.return_value = FakeTable()
    return client, calls


def test_persist_candidates_upserts_records():
    client, calls = _capture_table()
    candidates = [
        {"grapeminds_id": "136214", "display_name": "Decoy, Cabernet Sauvignon",
         "producer_name": "Decoy", "color": "red", "confidence": 0.97, "rank": 1, "is_primary": True},
        {"grapeminds_id": "235600", "display_name": "Decoy, Cab, Sonoma",
         "producer_name": "Decoy", "color": "red", "confidence": 0.93, "rank": 2, "is_primary": False},
    ]
    with patch("enrichment.pipeline.get_service_client", return_value=client):
        persist_candidates("wine-1", candidates)

    assert calls["upserted"] is not None
    assert len(calls["upserted"]) == 2
    first = calls["upserted"][0]
    assert first["wine_id"] == "wine-1"
    assert first["grapeminds_id"] == "136214"
    assert first["is_primary"] is True


def test_persist_candidates_empty_is_noop():
    client, calls = _capture_table()
    with patch("enrichment.pipeline.get_service_client", return_value=client):
        persist_candidates("wine-1", [])
    assert calls["upserted"] is None
