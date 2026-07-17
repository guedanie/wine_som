import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.candidate_filters import resolve_wine_type


def test_resolve_uses_existing_type_first():
    assert resolve_wine_type({"wine_type": "red", "name": "White Zin", "varietal": None}) == "red"


def test_resolve_infers_red_from_name_when_type_null():
    w = {"wine_type": None, "varietal": "Red Blend", "name": "Chateau Saint-Sulpice Bordeaux Red Wine",
         "grapes": ["Merlot", "Cabernet Sauvignon"]}
    assert resolve_wine_type(w) == "red"


def test_resolve_infers_white_from_varietal():
    w = {"wine_type": None, "varietal": "Sauvignon Blanc", "name": "Dourthe Bordeaux", "grapes": ["Sauvignon Blanc"]}
    assert resolve_wine_type(w) == "white"


def test_resolve_prefers_varietal_over_name():
    w = {"wine_type": None, "varietal": "Merlot", "name": "Chateau Rouget Pomerol", "grapes": []}
    assert resolve_wine_type(w) == "red"


def test_resolve_returns_none_when_unresolvable():
    w = {"wine_type": None, "varietal": None, "name": "Chateau Mystere 2019", "grapes": []}
    assert resolve_wine_type(w) is None


from recommendation.candidate_filters import apply_type_gate


def _c(**kw):
    base = {"wine_id": "x", "name": "W", "varietal": None, "grapes": [], "wine_type": None}
    base.update(kw); return base


def test_gate_keeps_resolved_red_drops_resolved_white_for_red_request():
    red = _c(wine_type="red", name="Malbec")
    mistyped_red = _c(wine_type=None, varietal="Red Blend", name="Bordeaux Red Wine")
    white = _c(wine_type="white", varietal="Sauvignon Blanc")
    out = apply_type_gate([red, mistyped_red, white], {"red"})
    assert white not in out
    assert red in out and mistyped_red in out
    assert mistyped_red["wine_type"] == "red"


def test_gate_keeps_unresolvable_null_benefit_of_doubt():
    unknown = _c(wine_type=None, name="Chateau Mystere 2019")
    out = apply_type_gate([unknown], {"red"})
    assert unknown in out and unknown["wine_type"] is None


def test_gate_noop_when_no_requested_types():
    white = _c(wine_type="white", varietal="Chardonnay")
    assert apply_type_gate([white], set()) == [white]


def test_gate_fails_open_when_it_would_empty_the_pool():
    whites = [_c(wine_type="white", varietal="Chardonnay"), _c(wine_type="white", varietal="Riesling")]
    assert apply_type_gate(whites, {"red"}) == whites


from recommendation.candidate_filters import requested_types_from


def test_requested_types_union_of_chips_and_parsed_intent():
    assert requested_types_from(["red"], None) == {"red"}
    assert requested_types_from([], "white") == {"white"}
    assert requested_types_from(["red"], "red") == {"red"}
    assert requested_types_from([], None) == set()


from recommendation.candidate_filters import detect_store

_NEARBY = [
    {"id": "s1", "name": "Lincoln Heights Market H-E-B"},
    {"id": "s2", "name": "Alon Market H-E-B"},
    {"id": "s3", "name": "Geraldine's Natural Wines"},
]


def test_detect_store_tolerates_typo():
    assert detect_store("show me a bordeaux at heb lincon heights", _NEARBY)["id"] == "s1"


def test_detect_store_exact_multiword():
    assert detect_store("anything at Alon Market", _NEARBY)["id"] == "s2"


def test_detect_store_none_when_no_store_named():
    assert detect_store("show me a bold red under $30", _NEARBY) is None


def test_detect_store_ignores_generic_retailer_word_only():
    assert detect_store("something red at heb", _NEARBY) is None
