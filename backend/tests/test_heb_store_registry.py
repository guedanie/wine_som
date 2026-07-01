import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scrapers.heb import STORE_REGISTRY, SA_STORES


def test_active_stores_loaded():
    """All 18 currently-active stores appear in the registry."""
    expected_active = {
        "567", "372", "585", "385", "568", "556",  # SA
        "68", "765", "229", "428", "227", "710",   # Austin
        "780", "754", "768", "91", "465", "425",
    }
    assert expected_active.issubset(set(STORE_REGISTRY.keys()))


def test_inactive_stores_excluded():
    """Stores marked active=false in the CSV are not in STORE_REGISTRY."""
    inactive_ids = {"26", "84", "85", "102", "178", "262"}
    for sid in inactive_ids:
        assert sid not in STORE_REGISTRY, f"store {sid} should be inactive"


def test_store_record_shape():
    """Each registry entry has the expected keys."""
    for sid, info in STORE_REGISTRY.items():
        for key in ("name", "address", "zip", "city", "state"):
            assert key in info, f"store {sid} missing key '{key}'"


def test_sa_stores_alias():
    """SA_STORES contains only San Antonio stores from STORE_REGISTRY."""
    assert len(SA_STORES) >= 6
    for sid, info in SA_STORES.items():
        assert info["city"] == "San Antonio", f"store {sid} city mismatch"
    assert set(SA_STORES.keys()).issubset(set(STORE_REGISTRY.keys()))
