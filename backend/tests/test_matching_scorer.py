import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from enrichment.matching.scorer import _normalize, _producer_score, _color_score


def test_normalize_lowercases_and_strips_punctuation():
    assert _normalize("Decoy, Cabernet-Sauvignon!") == "decoy cabernet sauvignon"
    assert _normalize("  Rosé   Wine ") == "rosé wine"


def test_producer_score_exact_match():
    assert _producer_score("Decoy", "Decoy") == 1.0


def test_producer_score_contains():
    # GrapeMinds "Duckhorn Vineyards ... Decoy ..." contains our brand "Decoy"
    assert _producer_score("Decoy", "Duckhorn Vineyards Decoy") == 0.6


def test_producer_score_token_overlap():
    # Neither string contains the other → falls through to Jaccard token overlap
    s = _producer_score("Bodega Catena", "Catena Zapata")
    assert 0.0 < s < 0.6


def test_producer_score_null_brand_is_zero():
    assert _producer_score(None, "Decoy") == 0.0


def test_color_score_match_and_mismatch():
    assert _color_score("red", "red") == 1.0
    assert _color_score("white", "red") == 0.0


def test_color_score_rose_alias():
    assert _color_score("rosé", "rose") == 1.0


def test_color_score_neutral_when_missing_or_unmapped():
    assert _color_score(None, "red") == 0.5
    assert _color_score("red", None) == 0.5
    assert _color_score("sparkling", "sparkling") == 0.5  # 'sparkling' not a GM color
