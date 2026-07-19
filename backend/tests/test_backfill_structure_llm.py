import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.backfill_structure_llm import (
    needs_sweetness, needs_full_profile, merge_sweetness, full_profile_from,
    clamp_1_10, validate_batch)


def test_needs_sweetness():
    assert needs_sweetness({"body": 8, "tannins": 7, "acidity": 5}) is True
    assert needs_sweetness({"body": 8, "sweetness": 1}) is False
    assert needs_sweetness({"body": 8, "sweetness": None}) is True
    assert needs_sweetness(None) is False


def test_needs_full_profile():
    assert needs_full_profile({"varietal": "Xinomavro-Moschofilero field blend",
                               "grapes": ["Xinomavro", "Moschofilero"], "region": None},
                              has_profile=False) is True
    assert needs_full_profile({"varietal": "Merlot", "grapes": ["Merlot"], "region": None},
                              has_profile=False) is False
    assert needs_full_profile({"varietal": "X", "grapes": ["Y"], "region": None},
                              has_profile=True) is False
    assert needs_full_profile({"varietal": None, "grapes": [], "region": "Tuscany"},
                              has_profile=False) is False


def test_clamp_1_10():
    assert clamp_1_10(7) == 7
    assert clamp_1_10("5") == 5
    assert clamp_1_10(0) is None
    assert clamp_1_10(11) is None
    assert clamp_1_10(None) is None
    assert clamp_1_10("x") is None


def test_merge_sweetness_only_touches_sweetness():
    prof = {"body": 8, "tannins": 7, "acidity": 5, "source": "table"}
    out = merge_sweetness(prof, 2)
    assert out == {"body": 8, "tannins": 7, "acidity": 5, "source": "table",
                   "sweetness": 2, "sweetness_source": "llm"}
    assert "sweetness" not in prof


def test_merge_sweetness_marks_source_unless_profile_is_llm():
    llm_prof = {"body": 5, "tannins": 4, "acidity": 6, "source": "llm"}
    out = merge_sweetness(llm_prof, 8)
    assert out["sweetness"] == 8 and "sweetness_source" not in out


def test_full_profile_from_maps_tannin_and_clamps():
    out = full_profile_from({"body": 9, "tannin": 8, "acidity": 6, "sweetness": 1})
    assert out == {"body": 9, "tannins": 8, "acidity": 6, "sweetness": 1, "source": "llm"}
    assert full_profile_from({"body": 9, "tannin": 99, "acidity": 6, "sweetness": 1}) is None


def test_non_wine_names_are_skipped_from_eligibility():
    from scripts.backfill_structure_llm import is_non_wine_row
    assert is_non_wine_row({"name": "Slamzees Cookies and Cream"}) is True
    assert is_non_wine_row({"name": "Hiro Sake Red Junmai"}) is True
    assert is_non_wine_row({"name": "Domaine X Chablis 2022"}) is False
    assert is_non_wine_row({"name": None}) is False


def test_validate_batch_drops_foreign_and_malformed_ids():
    batch_ids = {"a", "b"}
    resp = {"wines": [
        {"wine_id": "a", "body": 5, "tannin": 4, "acidity": 6, "sweetness": 1},
        {"wine_id": "zzz", "body": 5, "tannin": 4, "acidity": 6, "sweetness": 1},
        {"wine_id": "b", "body": 5, "tannin": 4, "acidity": 6, "sweetness": 99},
    ]}
    clean, bad_id, bad_val = validate_batch(resp, batch_ids)
    assert set(clean.keys()) == {"a"}
    assert bad_id == 1 and bad_val == 1
