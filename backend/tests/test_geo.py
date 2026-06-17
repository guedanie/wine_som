import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from utils.geo import zip_to_centroid, haversine


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
