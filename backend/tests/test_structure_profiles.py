import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.structure_profiles import structure_for


# ── base grape profiles ──────────────────────────────────────────

def test_cabernet_base_is_full_and_tannic():
    s = structure_for("Cabernet Sauvignon", None, None)
    assert s["body"] == 8
    assert s["tannins"] == 8
    assert s["acidity"] == 6
    assert s["source"] == "table"


def test_pinot_noir_is_light_low_tannin_high_acid():
    s = structure_for("Pinot Noir", None, None)
    assert s["body"] == 4
    assert s["tannins"] == 4
    assert s["acidity"] == 7


def test_white_has_no_tannin():
    s = structure_for("Sauvignon Blanc", None, None)
    assert s["tannins"] == 1
    assert s["body"] == 3
    assert s["acidity"] == 8


def test_unknown_grape_returns_none():
    assert structure_for("Frankenwine", None, None) is None
    assert structure_for(None, [], None) is None


def test_falls_back_to_grapes_list_when_no_varietal():
    s = structure_for(None, ["Malbec"], None)
    assert s is not None
    assert s["body"] == 8


def test_grape_spelling_is_accent_insensitive():
    a = structure_for("Mourvèdre", None, None)
    b = structure_for("mourvedre", None, None)
    assert a == b


# ── region modifiers (the key insight: Napa Cab is bolder) ───────

def test_napa_cabernet_is_bolder_than_base_cabernet():
    base = structure_for("Cabernet Sauvignon", None, None)
    napa = structure_for("Cabernet Sauvignon", None, "Napa Valley")
    assert napa["body"] > base["body"]
    assert napa["tannins"] >= base["tannins"]
    assert napa["acidity"] <= base["acidity"]   # warmer = softer acid


def test_cool_climate_raises_acidity_lowers_body():
    base = structure_for("Pinot Noir", None, None)
    cool = structure_for("Pinot Noir", None, "Willamette Valley")
    assert cool["acidity"] > base["acidity"]
    assert cool["body"] < base["body"]


def test_region_modifier_clamps_to_1_10():
    # Tannat base tannins = 10; a +tannin region must not exceed 10
    s = structure_for("Tannat", None, "Bordeaux")
    assert s["tannins"] == 10
    # nothing ever goes below 1
    for v in s.values():
        if isinstance(v, int):
            assert 1 <= v <= 10


def test_unknown_region_uses_base_profile():
    base = structure_for("Merlot", None, None)
    unk = structure_for("Merlot", None, "Neverland")
    assert base == unk


def test_region_alone_without_known_grape_is_none():
    # region can't produce a profile without a grape to anchor on
    assert structure_for("Frankenwine", None, "Napa Valley") is None
