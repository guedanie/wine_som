import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from unittest.mock import MagicMock
from utils.geo import zip_to_centroid, haversine, find_nearby_store_ids


def test_zip_to_centroid_known_sa_zip():
    result = zip_to_centroid("78209")
    assert result is not None
    lat, lon = result
    # San Antonio centroid should be roughly 29.4, -98.4
    assert 29.0 < lat < 30.0
    assert -99.0 < lon < -98.0


def test_zip_to_centroid_unknown_returns_none():
    result = zip_to_centroid("00000")
    assert result is None


def test_zip_to_centroid_garbage_returns_none():
    result = zip_to_centroid("notazip")
    assert result is None


def test_haversine_same_point_is_zero():
    assert haversine(29.47, -98.46, 29.47, -98.46) == 0.0


def test_haversine_known_distance():
    # 78209 centroid to 78208 centroid — both SA, should be under 5 miles
    c1 = zip_to_centroid("78209")
    c2 = zip_to_centroid("78208")
    assert c1 is not None and c2 is not None
    dist = haversine(c1[0], c1[1], c2[0], c2[1])
    assert dist < 5.0


def test_haversine_sa_to_austin_is_roughly_80_miles():
    sa = zip_to_centroid("78209")    # San Antonio
    atx = zip_to_centroid("78701")   # Austin
    assert sa is not None and atx is not None
    dist = haversine(sa[0], sa[1], atx[0], atx[1])
    # Centroid-to-centroid great-circle distance is ~69 miles; road distance is ~80 miles
    assert 65.0 < dist < 90.0


def _make_db(stores):
    """Return a mock DB client whose stores table returns the given list."""
    db = MagicMock()
    db.table.return_value.select.return_value.execute.return_value = MagicMock(data=stores)
    return db


def test_find_nearby_store_ids_sa_zip_returns_nearby_store():
    # A store at HEB 78208 centroid should be within 10 miles of 78209
    heb_centroid = zip_to_centroid("78208")
    assert heb_centroid is not None
    stores = [{"id": "store-1", "latitude": heb_centroid[0], "longitude": heb_centroid[1]}]
    db = _make_db(stores)
    result = find_nearby_store_ids("78209", db, radius_miles=10.0)
    assert "store-1" in result


def test_find_nearby_store_ids_distant_zip_returns_empty():
    # Austin store is ~80 miles from SA zip — should be excluded at 10-mile radius
    atx_centroid = zip_to_centroid("78701")
    assert atx_centroid is not None
    stores = [{"id": "store-atx", "latitude": atx_centroid[0], "longitude": atx_centroid[1]}]
    db = _make_db(stores)
    result = find_nearby_store_ids("78209", db, radius_miles=10.0)
    assert result == []


def test_find_nearby_store_ids_unknown_zip_returns_empty():
    db = _make_db([{"id": "store-1", "latitude": 29.47, "longitude": -98.46}])
    result = find_nearby_store_ids("00000", db)
    assert result == []


def test_find_nearby_store_ids_store_missing_coords_is_skipped():
    stores = [{"id": "no-coords", "latitude": None, "longitude": None}]
    db = _make_db(stores)
    result = find_nearby_store_ids("78209", db)
    assert result == []
