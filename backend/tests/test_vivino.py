import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from enrichment.vivino import (
    build_query,
    clean_wine_name,
    match_score,
    parse_wine_stats,
    search_wine,
)
from unittest.mock import patch


# ── clean_wine_name ──────────────────────────────────────────────

def test_clean_strips_volume():
    assert clean_wine_name("Esprit de Tablas Red Blend 750 ml") == "Esprit de Tablas Red Blend"


def test_clean_strips_punctuation():
    assert clean_wine_name("Kim Crawford Sauvignon Blanc, Marlborough") == \
        "Kim Crawford Sauvignon Blanc Marlborough"


# ── match_score ──────────────────────────────────────────────────

def test_match_score_exact_slug():
    score = match_score(
        "tablas creek esprit de tablas",
        "tablas-creek-vineyard-esprit-de-tablas",
    )
    assert score >= 0.8


def test_match_score_unrelated_wine():
    score = match_score(
        "esprit de tablas",
        "schrader-ccs-beckstoffer-to-kalon-cabernet-sauvignon",
    )
    assert score < 0.3


def test_match_score_junk_tokens_ignored():
    with_junk = match_score(
        "la crema sonoma coast pinot noir 750 ml wine",
        "la-crema-sonoma-coast-pinot-noir",
    )
    assert with_junk >= 0.8


def test_match_score_requires_two_shared_tokens():
    assert match_score("pinot", "pinot-noir-estate") == 0.0


def test_match_score_varietal_only_overlap_rejected():
    # different producer, same varietal — must not match
    assert match_score("beringer pinot grigio", "frecciarossa-pinot-grigio") == 0.0


def test_match_score_brand_plus_varietal_accepted():
    score = match_score("kim crawford sauvignon blanc", "kim-crawford-sauvignon-blanc")
    assert score >= 0.8


def test_strip_query_noise():
    from enrichment.vivino import strip_query_noise
    assert strip_query_noise("Beringer Pinot Grigio California White Wine") == \
        "Beringer Pinot Grigio"


# ── build_query ──────────────────────────────────────────────────

def test_build_query_prepends_missing_brand():
    assert build_query("Esprit de Tablas 750ml", "Tablas Creek") == \
        "Tablas Creek Esprit de Tablas"


def test_build_query_skips_brand_already_in_name():
    assert build_query("Tablas Creek Esprit de Tablas", "Tablas Creek") == \
        "Tablas Creek Esprit de Tablas"


# ── search_wine (fixture HTML, no network) ───────────────────────

_SEARCH_HTML = (
    '<a href="/en/tablas-creek-vineyard-esprit-de-tablas/w/2758387?year=2021&amp;price_id=1">x</a>'
    '<a href="/en/some-other-wine/w/999">y</a>'
)


def test_search_wine_returns_top_hit():
    with patch("enrichment.vivino._get", return_value=_SEARCH_HTML):
        m = search_wine("tablas creek esprit de tablas")
    assert m["wine_id"] == 2758387
    assert m["slug"] == "tablas-creek-vineyard-esprit-de-tablas"
    assert m["year"] == 2021
    assert m["score"] >= 0.8
    assert "&amp;" not in m["href"]


def test_search_wine_empty_page_returns_none():
    with patch("enrichment.vivino._get", return_value=""):
        assert search_wine("anything") is None


# ── parse_wine_stats (fixture JSON, no network) ──────────────────

_WINE_PAGE = (
    '{"vintage":{"id":176907205,"statistics":{"ratings_count":74,"ratings_average":4.2},'
    '"wine":{"id":2758387,"name":"Esprit de Tablas",'
    '"statistics":{"ratings_count":26908,"ratings_average":4.0}}},'
    '"recommended":[{"wine":{"id":555,"statistics":{"ratings_count":9,"ratings_average":4.9}}}]}'
)


def test_parse_wine_stats_anchors_on_wine_id():
    stats = parse_wine_stats(_WINE_PAGE, 2758387)
    assert stats == {"ratings_count": 26908, "ratings_average": 4.0}


def test_parse_wine_stats_ignores_other_wines():
    stats = parse_wine_stats(_WINE_PAGE, 555)
    assert stats == {"ratings_count": 9, "ratings_average": 4.9}


def test_parse_wine_stats_missing_id_returns_none():
    assert parse_wine_stats(_WINE_PAGE, 123456) is None


def test_parse_wine_stats_zero_ratings_skipped():
    page = '{"wine":{"id":7,"statistics":{"ratings_count":0,"ratings_average":0}}}'
    assert parse_wine_stats(page, 7) is None
