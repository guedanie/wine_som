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


def test_detect_store_no_false_positive_on_geographic_words():
    """Common geo/descriptor words shared with wine vocabulary must not lock a
    store: 'oaky'/'valley'/'heights' appear in both store names and wine talk."""
    nearby = [
        {"id": "s1", "name": "Lincoln Heights Market H-E-B"},
        {"id": "s4", "name": "Oak Park Market H-E-B"},
        {"id": "s5", "name": "Valley View Market H-E-B"},
    ]
    assert detect_store("an oaky red under $30", nearby) is None
    assert detect_store("a napa valley cabernet", nearby) is None
    assert detect_store("something from the heights", nearby) is None
    # but the distinctive name token still resolves Lincoln Heights (typo-tolerant)
    assert detect_store("bordeaux at lincon heights", nearby)["id"] == "s1"


from recommendation.candidate_filters import merge_candidates


def test_merge_dedups_by_wine_and_store():
    a = {"wine_id": "w1", "store_ref": "s1", "name": "A"}
    b = {"wine_id": "w2", "store_ref": "s1", "name": "B"}
    dup_a = {"wine_id": "w1", "store_ref": "s1", "name": "A"}
    out = merge_candidates([a, b], [dup_a])
    assert len(out) == 2


def test_merge_adds_targeted_rows_absent_from_breadth():
    breadth = [{"wine_id": "w1", "store_ref": "s1"}]
    targeted = [{"wine_id": "w9", "store_ref": "s1"}]
    out = merge_candidates(breadth, targeted)
    assert {c["wine_id"] for c in out} == {"w1", "w9"}


def test_dessert_request_also_accepts_fortified():
    """The intent enum can't express 'fortified' (only 'dessert'), so a
    dessert/after-dinner request must also surface Port/Sherry (item 30 typed
    them fortified). One-directional: fortified requests stay strict."""
    assert requested_types_from(["dessert"], None) == {"dessert", "fortified"}
    assert requested_types_from([], "dessert") == {"dessert", "fortified"}
    assert requested_types_from(["red"], None) == {"red"}
    assert requested_types_from(["fortified"], None) == {"fortified"}
    assert requested_types_from([], None) == set()


from recommendation.candidate_filters import significant_name_tokens


def test_tokens_drop_generic_keep_producer():
    assert significant_name_tokens("Caymus Cabernet Sauvignon") == ["caymus"]


def test_tokens_multi_word_producer():
    toks = significant_name_tokens("Opus One 2019")
    assert "opus" in toks and "one" in toks


def test_tokens_all_generic_is_empty():
    assert significant_name_tokens("Red Blend Reserve") == []


def test_tokens_none_safe():
    assert significant_name_tokens(None) == []


from recommendation.candidate_filters import rank_name_matches


def test_rank_all_tokens_before_partial():
    cands = [
        {"name": "Caymus Cabernet Sauvignon"},           # matches "caymus" only
        {"name": "Caymus Special Selection Cabernet"},    # matches both
    ]
    ranked = rank_name_matches(cands, ["caymus", "special"])
    assert ranked[0]["name"] == "Caymus Special Selection Cabernet"


def test_rank_drops_zero_match():
    cands = [{"name": "Silver Oak"}, {"name": "Opus One"}]
    assert rank_name_matches(cands, ["caymus"]) == []


def test_rank_empty_tokens_returns_empty():
    assert rank_name_matches([{"name": "Anything"}], []) == []
