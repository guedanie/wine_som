import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import asyncio
import inspect
from enrichment.vivino import (
    VivinoFetchError,
    build_query,
    clean_wine_name,
    match_score,
    parse_wine_attributes,
    parse_wine_stats,
    search_wine,
    structure_to_profile,
    fetch_ratings,
)
from unittest.mock import patch, AsyncMock, MagicMock

import pytest


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


# ── search_wine / fetch_ratings (fixture HTML, no network) ──────

_SEARCH_HTML = (
    '<a href="/en/tablas-creek-vineyard-esprit-de-tablas/w/2758387?year=2021&amp;price_id=1">x</a>'
    '<a href="/en/some-other-wine/w/999">y</a>'
)


def test_search_wine_is_async():
    """search_wine must be a coroutine function so it can be awaited. (parallelisation)"""
    assert inspect.iscoroutinefunction(search_wine)


def test_fetch_ratings_is_async():
    """fetch_ratings must be a coroutine function so it can be awaited. (parallelisation)"""
    assert inspect.iscoroutinefunction(fetch_ratings)


def test_search_wine_returns_top_hit():
    mock_client = AsyncMock()
    with patch("enrichment.vivino._get", new=AsyncMock(return_value=_SEARCH_HTML)):
        m = asyncio.run(search_wine("tablas creek esprit de tablas", mock_client, delay=0))
    assert m["wine_id"] == 2758387
    assert m["slug"] == "tablas-creek-vineyard-esprit-de-tablas"
    assert m["year"] == 2021
    assert m["score"] >= 0.8
    assert "&amp;" not in m["href"]


def test_search_wine_empty_page_returns_none():
    """A fetched page with no wine links is a genuine no-result — returns None."""
    mock_client = AsyncMock()
    with patch("enrichment.vivino._get", new=AsyncMock(return_value="")):
        assert asyncio.run(search_wine("anything", mock_client, delay=0)) is None


# ── rate-limit / fetch-failure handling ──────────────────────────

def test_get_returns_none_on_429():
    """_get must return None on a non-200 status so callers can tell a block
    from a genuine empty result. (429 pages contain no wine links and were
    being misread as 'no search hits'.)"""
    from enrichment.vivino import _get
    resp = MagicMock()
    resp.status_code = 429
    resp.text = "<html>too many requests</html>"
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    assert asyncio.run(_get("https://x", client)) is None


def test_get_returns_text_on_200():
    from enrichment.vivino import _get
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "<html>ok</html>"
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    assert asyncio.run(_get("https://x", client)) == "<html>ok</html>"


def test_search_wine_raises_on_fetch_failure():
    """When the fetch itself fails (block/network), search_wine must raise
    VivinoFetchError — NOT return None — so the runner can skip stamping."""
    mock_client = AsyncMock()
    with patch("enrichment.vivino._get", new=AsyncMock(return_value=None)):
        with pytest.raises(VivinoFetchError):
            asyncio.run(search_wine("anything", mock_client, delay=0))


def test_fetch_ratings_raises_on_fetch_failure():
    mock_client = AsyncMock()
    with patch("enrichment.vivino._get", new=AsyncMock(return_value=None)):
        with pytest.raises(VivinoFetchError):
            asyncio.run(fetch_ratings(
                {"wine_id": 1, "href": "/en/x/w/1"}, mock_client, delay=0,
            ))


def test_fetch_ratings_returns_stats():
    mock_client = AsyncMock()
    with patch("enrichment.vivino._get", new=AsyncMock(return_value=_WINE_PAGE)):
        stats = asyncio.run(fetch_ratings(
            {"wine_id": 2758387, "href": "/en/tablas-creek/w/2758387"},
            mock_client,
            delay=0,
        ))
    assert stats["ratings_count"] == 26908
    assert stats["ratings_average"] == 4.0


# ── parse_wine_stats (fixture JSON, no network) ──────────────────

_WINE_PAGE = (
    '{"vintage":{"id":176907205,"statistics":{"ratings_count":74,"ratings_average":4.2},'
    '"wine":{"id":2758387,"name":"Esprit de Tablas",'
    '"statistics":{"ratings_count":26908,"ratings_average":4.0}}},'
    '"recommended":[{"wine":{"id":555,"statistics":{"ratings_count":9,"ratings_average":4.9}}}]}'
)

_WINE_PAGE_WITH_IMAGE = (
    '{"vintage":{"id":176907205,'
    '"image":{"variations":{"bottle_medium":"//images.vivino.com/thumbs/test_pb_x600.png"}},'
    '"statistics":{"ratings_count":74,"ratings_average":4.2},'
    '"wine":{"id":2758387,"name":"Esprit de Tablas",'
    '"statistics":{"ratings_count":26908,"ratings_average":4.0}}},'
    '"recommended":[{"wine":{"id":555,"statistics":{"ratings_count":9,"ratings_average":4.9}}}]}'
)


def test_parse_wine_stats_anchors_on_wine_id():
    stats = parse_wine_stats(_WINE_PAGE, 2758387)
    assert stats["ratings_count"] == 26908
    assert stats["ratings_average"] == 4.0


def test_parse_wine_stats_ignores_other_wines():
    stats = parse_wine_stats(_WINE_PAGE, 555)
    assert stats["ratings_count"] == 9
    assert stats["ratings_average"] == 4.9


def test_parse_wine_stats_missing_id_returns_none():
    assert parse_wine_stats(_WINE_PAGE, 123456) is None


def test_parse_wine_stats_zero_ratings_skipped():
    page = '{"wine":{"id":7,"statistics":{"ratings_count":0,"ratings_average":0}}}'
    assert parse_wine_stats(page, 7) is None


def test_parse_wine_stats_extracts_bottle_image_url():
    """bottle_medium URL must be returned as image_url with https: prefix. (vivino images)"""
    stats = parse_wine_stats(_WINE_PAGE_WITH_IMAGE, 2758387)
    assert stats["image_url"] == "https://images.vivino.com/thumbs/test_pb_x600.png"


def test_parse_wine_stats_image_url_none_when_missing():
    """image_url must be None (not absent) when page has no bottle_medium."""
    stats = parse_wine_stats(_WINE_PAGE, 2758387)
    assert "image_url" in stats
    assert stats["image_url"] is None


def test_fetch_ratings_includes_image_url():
    """fetch_ratings must surface the image_url from the page. (vivino images)"""
    mock_client = AsyncMock()
    with patch("enrichment.vivino._get", new=AsyncMock(return_value=_WINE_PAGE_WITH_IMAGE)):
        stats = asyncio.run(fetch_ratings(
            {"wine_id": 2758387, "href": "/en/tablas-creek/w/2758387"},
            mock_client,
            delay=0,
        ))
    assert stats["image_url"] == "https://images.vivino.com/thumbs/test_pb_x600.png"


# ── parse_wine_attributes (real page shapes from Yellow Tail Shiraz w/2547) ──

# Localization junk that appears BEFORE the wine object on real pages — the
# parser must not read attribute labels ("grapes":"Grapes") as data.
_L10N_JUNK = (
    '{"wine_summary":{"acidity":"Acidity","alcohol":"Alcohol content",'
    '"grapes":"Grapes","region":"Region","food_pairing":"Food pairing"},'
)

_ATTR_PAGE = _L10N_JUNK + (
    '"wine":{"id":2547,"name":"Shiraz","seo_name":"shiraz","type_id":1,'
    '"is_natural":false,'
    '"region":{"id":685,"name":"South Eastern Australia","name_en":"","seo_name":"south-eastern",'
    '"country":{"code":"au","name":"Australia","native_name":"Australia","seo_name":"australia"}},'
    '"grapes":[{"id":1,"name":"Shiraz/Syrah","seo_name":"shiraz-syrah","parent_grape_id":null,"color":5}],'
    '"foods":[{"id":4,"name":"Beef","weight":0.5,'
    '"background_image":{"location":"//x/4_beef.png","variations":{"small":"//x/4s.png"}},"seo_name":"beef"},'
    '{"id":8,"name":"Lamb","weight":0.5,'
    '"background_image":{"location":"//x/8_lamb.png","variations":{"small":"//x/8s.png"}},"seo_name":"lamb"}],'
    '"non_vintage":false,"alcohol":13.5,"sweetness_id":null,'
    '"style":{"id":926,"seo_name":"south-eastern-australia-shiraz",'
    '"baseline_structure":{"acidity":4.5,"fizziness":null,"intensity":4.5,"sweetness":1.0,"tannin":4.0}},'
    '"has_valid_ratings":true}}'
)


def test_parse_attributes_full_page():
    attrs = parse_wine_attributes(_ATTR_PAGE, 2547)
    assert attrs["grapes"] == ["Shiraz/Syrah"]
    assert attrs["foods"] == ["Beef", "Lamb"]
    assert attrs["region"] == "South Eastern Australia"
    assert attrs["country"] == "Australia"
    assert attrs["abv"] == 13.5
    assert attrs["structure"] == {
        "acidity": 4.5, "fizziness": None, "intensity": 4.5,
        "sweetness": 1.0, "tannin": 4.0,
    }


def test_parse_attributes_ignores_l10n_labels():
    """Labels like "grapes":"Grapes" before the anchor must not poison the parse."""
    attrs = parse_wine_attributes(_ATTR_PAGE, 2547)
    assert "Grapes" not in (attrs["grapes"] or [])
    assert attrs["region"] != "Region"


def test_parse_attributes_missing_wine_returns_none():
    assert parse_wine_attributes(_ATTR_PAGE, 999999) is None


def test_parse_attributes_partial_page():
    """Attributes absent from the page come back as None/empty, not crashes."""
    page = '{"wine":{"id":42,"name":"Mystery","statistics":{}}}'
    attrs = parse_wine_attributes(page, 42)
    assert attrs["grapes"] == []
    assert attrs["foods"] == []
    assert attrs["region"] is None
    assert attrs["abv"] is None
    assert attrs["structure"] is None


# ── structure_to_profile (Vivino 1-5 → GrapeMinds 1-10 convention) ──

def test_structure_to_profile_scales_and_maps():
    profile = structure_to_profile({
        "acidity": 4.5, "fizziness": None, "intensity": 4.5,
        "sweetness": 1.0, "tannin": 4.0,
    })
    assert profile == {
        "acidity": 9.0, "body": 9.0, "sweetness": 2.0, "tannins": 8.0,
        "source": "vivino",
    }


def test_structure_to_profile_skips_nulls():
    profile = structure_to_profile({"acidity": 3.0, "tannin": None,
                                    "intensity": None, "sweetness": None,
                                    "fizziness": None})
    assert profile == {"acidity": 6.0, "source": "vivino"}


def test_structure_to_profile_none_input():
    assert structure_to_profile(None) is None


def test_fetch_ratings_includes_attributes():
    """fetch_ratings must surface parsed attributes so the runner can write
    facts without a second page fetch. (vivino attribute enrichment)"""
    mock_client = AsyncMock()
    page = _WINE_PAGE_WITH_IMAGE.replace(
        '"name":"Esprit de Tablas",',
        '"name":"Esprit de Tablas",'
        '"region":{"id":1,"name":"Paso Robles","country":{"code":"us","name":"United States"}},'
        '"grapes":[{"id":9,"name":"Mourvedre"}],"alcohol":14.5,',
    )
    with patch("enrichment.vivino._get", new=AsyncMock(return_value=page)):
        stats = asyncio.run(fetch_ratings(
            {"wine_id": 2758387, "href": "/en/tablas-creek/w/2758387"},
            mock_client, delay=0,
        ))
    assert stats["attributes"]["grapes"] == ["Mourvedre"]
    assert stats["attributes"]["region"] == "Paso Robles"
    assert stats["attributes"]["abv"] == 14.5
