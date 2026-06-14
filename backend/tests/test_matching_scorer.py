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


from enrichment.matching.scorer import _name_score, score_candidates


def test_name_score_strips_retailer_noise():
    # Only "decoy" + "cabernet" + "sauvignon" survive stopword/size stripping → strong overlap
    s = _name_score(
        "Decoy Cabernet Sauvignon California Red Wine 750 ml",
        "Decoy, Cabernet Sauvignon",
    )
    assert s == 1.0


def test_name_score_strips_vintage_for_geraldines_style():
    s = _name_score("Les Lunes Rouge 2021", "Les Lunes, Pinot Noir, Carneros")
    # "les" + "lunes" overlap; "rouge"/"pinot"/"noir"/"carneros" differ → partial
    assert 0.0 < s < 1.0


def _hit(gm_id, display_name, producer_name, color):
    return {"id": gm_id, "display_name": display_name,
            "producer_name": producer_name, "color": color}


def test_score_candidates_ranks_and_marks_primary():
    hits = [
        _hit(240170, "Duckhorn Vineyards, Decoy Cabernet Sauvignon, Sonoma County", "Duckhorn Vineyards", "red"),
        _hit(136214, "Decoy, Cabernet Sauvignon", "Decoy", "red"),
        _hit(235600, "Decoy, Cabernet Sauvignon, Sonoma County", "Decoy", "red"),
    ]
    out = score_candidates(
        hits,
        brand="Decoy",
        wine_type="red",
        name="Decoy Cabernet Sauvignon California Red Wine",
    )
    assert [c["grapeminds_id"] for c in out][0] == "136214"   # best is exact Decoy Cab
    assert out[0]["rank"] == 1 and out[0]["is_primary"] is True
    assert out[1]["is_primary"] is False
    assert all(0.0 <= c["confidence"] <= 1.0 for c in out)
    # confidence descending
    assert out[0]["confidence"] >= out[1]["confidence"] >= out[2]["confidence"]


def test_score_candidates_keeps_top_3():
    hits = [_hit(i, f"Wine {i}", f"Producer {i}", "red") for i in range(6)]
    out = score_candidates(hits, brand="Producer 0", wine_type="red", name="Wine 0")
    assert len(out) == 3


def test_score_candidates_dedupes_grapeminds_id():
    hits = [_hit(111, "Decoy, Cabernet Sauvignon", "Decoy", "red"),
            _hit(111, "Decoy, Cabernet Sauvignon", "Decoy", "red")]
    out = score_candidates(hits, brand="Decoy", wine_type="red", name="Decoy Cabernet Sauvignon")
    assert len(out) == 1


def test_score_candidates_empty_hits():
    assert score_candidates([], brand="Decoy", wine_type="red", name="Decoy") == []
