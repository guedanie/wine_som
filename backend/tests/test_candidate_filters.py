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


from recommendation.candidate_filters import deep_fetch_reason


def _cand(**kw):
    base = {"grapes": [], "region": None, "wine_type": None, "varietal": None}
    base.update(kw)
    return base


def test_reason_named_when_wine_name_present():
    assert deep_fetch_reason({"wine_name": "Opus One"}, [_cand()]) == "named"


def test_reason_none_when_wine_name_all_generic():
    # "Red Blend" has no significant tokens — must not fire the named deep-fetch
    # (no false "I couldn't find Red Blend nearby"); with no other constraint → None.
    intent = {"wine_name": "Red Blend", "grapes": [], "region": None, "wine_type": None}
    assert deep_fetch_reason(intent, [_cand()]) is None


def test_reason_weak_when_grape_unmet():
    intent = {"wine_name": None, "grapes": ["Chenin Blanc"], "region": None, "wine_type": None}
    top = [_cand(grapes=["Cabernet Sauvignon"], wine_type="red")]
    assert deep_fetch_reason(intent, top) == "weak"


def test_reason_none_when_grape_met():
    intent = {"wine_name": None, "grapes": ["Chenin Blanc"], "region": None, "wine_type": None}
    top = [_cand(grapes=["Chenin Blanc"], wine_type="white")]
    assert deep_fetch_reason(intent, top) is None


def test_reason_weak_when_region_unmet():
    intent = {"wine_name": None, "grapes": [], "region": "Rioja", "wine_type": None}
    top = [_cand(region="Napa Valley")]
    assert deep_fetch_reason(intent, top) == "weak"


def test_reason_none_when_no_concrete_constraint():
    intent = {"wine_name": None, "grapes": [], "region": None, "wine_type": None, "flavors": ["bold"]}
    assert deep_fetch_reason(intent, [_cand()]) is None


def test_named_beats_weak():
    intent = {"wine_name": "Opus One", "grapes": ["Chenin Blanc"], "region": None, "wine_type": None}
    assert deep_fetch_reason(intent, [_cand()]) == "named"


from recommendation.candidate_filters import pin_named_matches


def test_pin_named_first_dedup_and_cap():
    top = [{"wine_id": "s1", "name": "Scored A"}, {"wine_id": "s2", "name": "Scored B"}]
    named = [
        {"wine_id": "n1", "name": "Opus One", "price": 400},
        {"wine_id": "n1", "name": "Opus One", "price": 380},   # dup wine, cheaper
        {"wine_id": "n2", "name": "Opus One 2018", "price": 350},
        {"wine_id": "n3", "name": "Opus One 2017", "price": 360},
        {"wine_id": "n4", "name": "Opus One 2016", "price": 370},  # beyond cap
    ]
    out = pin_named_matches(top, named, cap=3)
    ids = [w["wine_id"] for w in out]
    assert ids[:3] == ["n1", "n2", "n3"]              # 3 distinct named, cheapest n1 kept
    assert next(w for w in out if w["wine_id"] == "n1")["price"] == 380
    assert "s1" in ids and "s2" in ids                # scored still present, after
    assert ids.count("n1") == 1                        # deduped


def test_pin_no_named_returns_top_unchanged():
    top = [{"wine_id": "s1", "name": "A"}]
    assert pin_named_matches(top, [], cap=3) == top


from recommendation.candidate_filters import ensure_region_representation


def _rc(wid, region, country="USA", score=1.0):
    return {"wine_id": wid, "store_ref": "s", "region": region, "country": country, "_score": score}


def test_representation_pins_missing_region():
    top = [_rc("1", "Napa Valley", score=5), _rc("2", "Sonoma", score=4)]
    scored = top + [_rc("9", "Mendoza", "Argentina", score=1)]
    out = ensure_region_representation(top, scored, ["California", "Mendoza"], 12)
    assert any(c["wine_id"] == "9" for c in out)


def test_representation_noop_when_both_present():
    top = [_rc("1", "Napa Valley", score=5), _rc("9", "Mendoza", "Argentina", score=4)]
    out = ensure_region_representation(top, top, ["Napa", "Mendoza"], 12)
    assert {c["wine_id"] for c in out} == {"1", "9"}


def test_representation_noop_single_region():
    top = [_rc("1", "Napa Valley", score=5)]
    assert ensure_region_representation(top, top, ["California"], 12) == top


def test_representation_respects_cap_keeps_pinned():
    top = [_rc(str(i), "Napa Valley", score=10 - i) for i in range(12)]
    scored = top + [_rc("M", "Mendoza", "Argentina", score=0.5)]
    out = ensure_region_representation(top, scored, ["California", "Mendoza"], 12)
    assert len(out) == 12
    assert any(c["wine_id"] == "M" for c in out)


from recommendation.candidate_filters import detect_retailer

_NEARBY_RETAILERS = ["H-E-B", "Central Market", "Twin Liquors", "Spec's", "Geraldine's Natural Wines"]


def test_detect_retailer_heb_all_variants():
    for m in ["anything from heb?", "what about HEB", "got any h-e-b picks",
              "show me h.e.b", "HEB please"]:
        assert detect_retailer(m, _NEARBY_RETAILERS) == "H-E-B", m


def test_detect_retailer_multiword_and_shorthand():
    assert detect_retailer("anything at central market?", _NEARBY_RETAILERS) == "Central Market"
    assert detect_retailer("cm options?", _NEARBY_RETAILERS) == "Central Market"
    assert detect_retailer("twin liquors?", _NEARBY_RETAILERS) == "Twin Liquors"
    assert detect_retailer("from twin", _NEARBY_RETAILERS) == "Twin Liquors"


def test_detect_retailer_typo_tolerant():
    assert detect_retailer("anything at centrl market?", _NEARBY_RETAILERS) == "Central Market"


def test_detect_retailer_none_when_unnamed():
    assert detect_retailer("something light and elegant under $40", _NEARBY_RETAILERS) is None


def test_detect_retailer_only_returns_nearby():
    assert detect_retailer("anything from kroger?", _NEARBY_RETAILERS) is None


# ---- multi-bottle comparison pinning (aisle-mode delta 3) ----

from recommendation.candidate_filters import pin_comparison_matches

def test_deep_fetch_reason_named_via_wine_names_list():
    intent = {"wine_name": None, "wine_names": ["Caymus Cabernet", "Bonanza Cabernet"],
              "grapes": [], "region": None, "wine_type": None}
    assert deep_fetch_reason(intent, []) == "named"


def test_pin_comparison_matches_pins_each_bottle_in_named_order():
    top = [{"wine_id": "x", "name": "Filler Red", "price": 12.0}]
    caymus = [{"wine_id": "c1", "name": "Caymus Cabernet Sauvignon", "price": 89.0}]
    bonanza = [{"wine_id": "b1", "name": "Bonanza Cabernet Sauvignon", "price": 21.0}]
    out = pin_comparison_matches(top, [caymus, bonanza], cap_per_name=2)
    ids = [w["wine_id"] for w in out]
    assert ids[:2] == ["c1", "b1"]      # both bottles pinned, first-named first
    assert "x" in ids                    # scored candidates survive behind them


def test_pin_comparison_matches_caps_per_name():
    top = []
    a = [{"wine_id": f"a{i}", "name": f"Caymus Bottling {i}", "price": 50.0} for i in range(4)]
    b = [{"wine_id": "b1", "name": "Bonanza Cabernet", "price": 21.0}]
    out = pin_comparison_matches(top, [a, b], cap_per_name=2)
    ids = [w["wine_id"] for w in out]
    assert ids == ["a0", "a1", "b1"]     # first name capped at 2, second still present


# ---- structured store_ref (aisle-mode delta 1) ----

from recommendation.candidate_filters import resolve_store_scope

_STORES = [
    {"id": "s1", "retailer_name": "H-E-B", "name": "H-E-B Lincoln Heights"},
    {"id": "s2", "retailer_name": "Spec's", "name": "Spec's Broadway"},
]


def test_resolve_requested_store_by_ref_wins_over_message():
    """The picker's store is where the user is standing; a store named in the
    same breath doesn't override it (and isn't reported as mentioned)."""
    standing, mentioned = resolve_store_scope("s2", _STORES, "anything at lincoln heights?")
    assert standing["id"] == "s2"
    assert mentioned is None


def test_resolve_requested_store_unknown_ref_falls_back_to_detection():
    """A stale ref from another zip yields no STANDING store — the text match is
    only a mention, so it must not inherit the hard filter."""
    standing, mentioned = resolve_store_scope(
        "stale-ref-from-old-zip", _STORES, "anything at lincoln heights?")
    assert standing is None
    assert mentioned is not None and mentioned["id"] == "s1"


def test_resolve_requested_store_none_when_no_ref_and_no_mention():
    assert resolve_store_scope(None, _STORES, "a bold red for tonight") == (None, None)


# ---- item 41: referent carry across turns ----

from recommendation.candidate_filters import (is_referential, pin_prior_picks,
                                              prior_picks_from_history)


def test_prior_picks_from_history_ordered_deduped():
    history = [
        {"role": "user", "content": "a sauvignon blanc from sancerre?"},
        {"role": "sommelier", "content": "Two I like.",
         "picks": [{"wine_id": "w1", "name": "Avaline SB"},
                   {"wine_id": "w2", "name": "Starborough SB"}]},
        {"role": "user", "content": "anything cheaper?"},
        {"role": "sommelier", "content": "One more.",
         "picks": [{"wine_id": "w2", "name": "Starborough SB"},   # repeat
                   {"wine_id": "w3", "name": "Kim Crawford SB"}]},
    ]
    out = prior_picks_from_history(history)
    assert [p["wine_id"] for p in out] == ["w1", "w2", "w3"]
    assert out[0]["name"] == "Avaline SB"


def test_prior_picks_from_history_empty_and_prose_only():
    assert prior_picks_from_history(None) == []
    assert prior_picks_from_history([{"role": "sommelier", "content": "hi"}]) == []


def test_is_referential_positives():
    for msg in ["Can we compare these two? Which do you recommend?",
                "which one is better?", "I'll take the first one",
                "are both of those dry?", "what about that one instead",
                "which of the two should I grab?"]:
        assert is_referential(msg), msg


def test_is_referential_negatives():
    for msg in ["a bold red for tonight", "anything from HEB?",
                "is nebbiolo like pinot noir?", "caymus or bonanza cabernet?",
                "which malbec pairs with brisket?"]:
        assert not is_referential(msg), msg


def test_pin_prior_picks_pins_in_history_order_cheapest_row():
    top = [{"wine_id": "x", "name": "Filler", "price": 15.0}]
    prior = [
        {"wine_id": "w2", "name": "Starborough SB", "price": 13.0},
        {"wine_id": "w1", "name": "Avaline SB", "price": 24.0},
        {"wine_id": "w1", "name": "Avaline SB", "price": 22.0},   # cheaper row same wine
    ]
    out = pin_prior_picks(top, prior, ["w1", "w2"], cap=4)
    assert [w["wine_id"] for w in out[:2]] == ["w1", "w2"]   # history order, not input order
    assert out[0]["price"] == 22.0                            # cheapest row per wine
    assert "x" in [w["wine_id"] for w in out]


# ---- item 44: hard store filter (aisle mode) ----

from recommendation.candidate_filters import filter_to_store


def test_filter_to_store_keeps_only_that_store():
    cands = [
        {"wine_id": "w1", "store_ref": "s1", "name": "In-store red"},
        {"wine_id": "w2", "store_ref": "s2", "name": "Other-store red"},
        {"wine_id": "w1", "store_ref": "s1", "name": "In-store red (dup row)"},
    ]
    out = filter_to_store(cands, "s1")
    assert [c["store_ref"] for c in out] == ["s1", "s1"]
    assert all(c["store_ref"] == "s1" for c in out)


def test_filter_to_store_empty_when_store_absent():
    cands = [{"wine_id": "w2", "store_ref": "s2"}]
    assert filter_to_store(cands, "s1") == []


def test_filter_to_store_noop_on_falsy_store():
    cands = [{"wine_id": "w1", "store_ref": "s1"}]
    assert filter_to_store(cands, None) == cands


# ---------------------------------------------------------------------------
# Ordinary chat words must not lock a store (2026-09-01 Overture incident)
# ---------------------------------------------------------------------------

def test_detect_store_ignores_ordinary_english_words():
    """'Do you have Overture?' scoped the whole request to 'Blanco and West Ave
    H-E-B' because difflib rates 'ave' vs 'have' at 0.857. Item 44 then hard-
    filtered the pool to that store and deleted the six Overture bottles the
    named fetch had just gone and found."""
    nearby = [
        {"id": "s1", "name": "Blanco and West Ave H-E-B"},
        {"id": "s2", "name": "San Antonio - De Zavala"},
        {"id": "s3", "name": "Twin Liquors - Four Points"},
        {"id": "s4", "name": "Central Market Lovers Lane"},
    ]
    assert detect_store("Do you have Overture?", nearby) is None
    assert detect_store("do you carry an italian red", nearby) is None
    assert detect_store("looking for something under $40", nearby) is None
    assert detect_store("tell me more about this one", nearby) is None
    assert detect_store("is it any good, and what goes with it", nearby) is None


def test_detect_store_still_matches_a_genuinely_named_store():
    """The precision fix must not cost recall — a real store name, including a
    typo, still has to resolve."""
    nearby = [
        {"id": "s1", "name": "Blanco and West Ave H-E-B"},
        {"id": "s2", "name": "San Antonio - De Zavala"},
    ]
    assert detect_store("anything at the Blanco store?", nearby)["id"] == "s1"
    assert detect_store("what's at de zavala", nearby)["id"] == "s2"
    # The documented typo tolerance (a dropped letter) survives the stricter
    # cutoff: 'lincon'/'lincoln' scores .923.
    assert detect_store("bordeaux at heb lincon heights",
                        [{"id": "s9", "name": "Lincoln Heights Market H-E-B"}])["id"] == "s9"


def test_detect_store_gives_up_short_word_substitutions():
    """Deliberate limit, not an oversight. A one-letter SUBSTITUTION in a short
    word ('blanko'/'blanco') scores .833 and no longer resolves, because that is
    the same range ordinary words score in — .857 for 'have'/'ave'. Precision is
    worth more than this: a missed detection now only costs a ranking boost
    (detection is soft — see resolve_store_scope), while a false one used to
    delete the entire catalog."""
    nearby = [{"id": "s1", "name": "Blanco and West Ave H-E-B"}]
    assert detect_store("bordeaux at blanko", nearby) is None


# ---------------------------------------------------------------------------
# Standing (picked) store vs mentioned (guessed) store
# ---------------------------------------------------------------------------

def test_picked_store_is_standing_not_merely_mentioned():
    """A structured store_ref comes from the aisle store picker — the user
    really is in that building, which is what licenses item 44's hard filter."""
    from recommendation.candidate_filters import resolve_store_scope
    nearby = [{"id": "s1", "name": "Geraldine's Natural Wines"},
              {"id": "s2", "name": "Blanco and West Ave H-E-B"}]
    standing, mentioned = resolve_store_scope("s1", nearby, "something for pizza")
    assert standing["id"] == "s1"
    assert mentioned is None


def test_text_named_store_is_mentioned_not_standing():
    """Free text is a GUESS. It may scope a fetch and boost ranking, but it must
    not license deleting the rest of the catalog — that is what turned a fuzzy
    'have'/'Ave' hit into a false 'we don't carry Overture'."""
    from recommendation.candidate_filters import resolve_store_scope
    nearby = [{"id": "s1", "name": "Geraldine's Natural Wines"},
              {"id": "s2", "name": "Blanco and West Ave H-E-B"}]
    standing, mentioned = resolve_store_scope(None, nearby, "what's at geraldine's?")
    assert standing is None
    assert mentioned["id"] == "s1"


def test_stale_store_ref_from_another_zip_is_ignored():
    from recommendation.candidate_filters import resolve_store_scope
    nearby = [{"id": "s1", "name": "Geraldine's Natural Wines"}]
    standing, mentioned = resolve_store_scope("gone", nearby, "a bold red")
    assert standing is None and mentioned is None


def test_no_store_anywhere():
    from recommendation.candidate_filters import resolve_store_scope
    nearby = [{"id": "s1", "name": "Geraldine's Natural Wines"}]
    assert resolve_store_scope(None, nearby, "a bold red under $40") == (None, None)
