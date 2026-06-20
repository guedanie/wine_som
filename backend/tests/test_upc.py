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
