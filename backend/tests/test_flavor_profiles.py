import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.flavor_profiles import flavor_tags_for, infer_body


def test_gsm_blend_is_earthy_and_savory():
    tags = flavor_tags_for(
        varietal="Grenache",
        grapes=["Grenache", "Syrah", "Mourvèdre"],
        region="Rhône",
    )
    assert "earthy" in tags
    assert "savory" in tags


def test_cabernet_is_bold():
    tags = flavor_tags_for(varietal="Cabernet Sauvignon", grapes=["Cabernet Sauvignon"], region="Napa Valley")
    assert "bold" in tags


def test_region_contributes_tags_even_without_grape_match():
    tags = flavor_tags_for(varietal=None, grapes=[], region="Tuscany")
    assert "earthy" in tags


def test_accent_insensitive_grape_lookup():
    # "Mourvedre" without accent should still match "Mourvèdre"
    tags = flavor_tags_for(varietal="Mourvedre", grapes=["Mourvedre"], region=None)
    assert "earthy" in tags


def test_unknown_grape_and_region_returns_empty():
    assert flavor_tags_for(varietal="Nonexistent", grapes=["Nonexistent"], region="Nowhere") == set()


def test_infer_body_full_from_bold_tags():
    assert infer_body({"bold", "structured"}) == "full"


def test_infer_body_light_from_light_tag():
    assert infer_body({"light", "red-fruit"}) == "light"


def test_infer_body_none_when_ambiguous():
    assert infer_body({"savory", "spice"}) is None


def test_new_vocab_words_present():
    from recommendation.flavor_profiles import FLAVOR_VOCAB
    assert {"floral", "citrus", "mineral"} <= FLAVOR_VOCAB


def test_intent_flavor_vocab_stays_in_sync_with_flavor_profiles():
    """intent.py's _FLAVOR_VOCAB is a hand-written prompt string — this guards against
    it silently drifting from the real vocabulary set, the way CORE_GRAPES is guarded
    elsewhere in the codebase."""
    from recommendation.flavor_profiles import FLAVOR_VOCAB
    from recommendation.intent import _FLAVOR_VOCAB
    words = {w.strip() for w in _FLAVOR_VOCAB.split(",")}
    assert words == FLAVOR_VOCAB
