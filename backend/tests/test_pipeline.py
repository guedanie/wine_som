import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from enrichment.pipeline import (
    enrich_wine, enrich_wine_with_refetch,
    _result_from_wine_data, EnrichmentResult,
)
from enrichment.grapeminds import GrapeMindsWine, DrinkingPeriod


WINE_ROW = {"id": "uuid-abc", "name": "Caymus Cabernet Sauvignon", "varietal": "Cabernet Sauvignon",
            "region": "Napa", "brand": "Caymus Vineyards", "wine_type": "red"}

# A high-confidence search hit (producer + color match) so enrichment clears the gate.
CAYMUS_HIT = {"id": 113817, "display_name": "Caymus Vineyards, Cabernet Sauvignon Napa Valley",
              "producer_name": "Caymus Vineyards", "color": "red"}

FULL_WINE = GrapeMindsWine(
    grapeminds_id="113817",
    display_name="Caymus Vineyards, Cabernet Sauvignon Napa Valley",
    color="red",
    producer_name="Caymus Vineyards",
    region_name="California",
    grapes=["Cabernet Sauvignon"],
    description="Sun-drenched Napa Valley fruit.",
    description_long="Long description...",
    tasting_notes="Dark cherry, vanilla.",
    tasting_notes_long="Detailed tasting notes...",
    pairing="Great with ribeye.",
    pairing_long="Long pairing notes...",
    structure_profile={"sweetness": 3, "acidity": 4, "tannins": 6, "alcohol": 8, "body": 8, "finish": 8},
    is_fully_enriched=True,
)

PARTIAL_WINE = GrapeMindsWine(
    grapeminds_id="113817",
    display_name="Caymus Vineyards, Cabernet Sauvignon Napa Valley",
    is_fully_enriched=False,
)

DRINKING = DrinkingPeriod(from_year=3, to_year=10, statement="Drink from year 3.", young="Firm", ripe="Silky")


def test_result_from_wine_data_full():
    result = _result_from_wine_data("uuid-abc", FULL_WINE, DRINKING)
    assert result.wine_id == "uuid-abc"
    assert result.grapeminds_id == "113817"
    assert result.description == "Sun-drenched Napa Valley fruit."
    assert result.structure_profile["body"] == 8
    assert result.drinking_window_start == 3
    assert result.drinking_window_end == 10
    assert result.needs_refetch is False


def test_result_from_wine_data_partial_sets_needs_refetch():
    result = _result_from_wine_data("uuid-abc", PARTIAL_WINE)
    assert result.needs_refetch is True
    assert result.description is None


@pytest.mark.asyncio
async def test_enrich_wine_skips_already_enriched():
    with patch("enrichment.pipeline.is_already_enriched", return_value=True):
        result = await enrich_wine(WINE_ROW)
    assert result.source == "cached"
    assert result.needs_refetch is False


@pytest.mark.asyncio
async def test_enrich_wine_returns_not_found_when_no_search_hits():
    with patch("enrichment.pipeline.is_already_enriched", return_value=False), \
         patch("enrichment.pipeline.GrapeMindsClient") as MockGM:
        MockGM.return_value.search.return_value = []
        result = await enrich_wine(WINE_ROW)
    assert result.source == "not_found"


@pytest.mark.asyncio
async def test_enrich_wine_full_enrichment_on_first_fetch():
    mock_client = MagicMock()
    mock_client.search.return_value = [CAYMUS_HIT]
    mock_client.get_wine.return_value = FULL_WINE
    mock_client.get_drinking_period.return_value = DRINKING

    with patch("enrichment.pipeline.is_already_enriched", return_value=False), \
         patch("enrichment.pipeline.GrapeMindsClient", return_value=mock_client), \
         patch("enrichment.pipeline.persist_candidates"), \
         patch("enrichment.pipeline._persist") as mock_persist:
        result = await enrich_wine(WINE_ROW)

    assert result.grapeminds_id == "113817"
    assert result.description == "Sun-drenched Napa Valley fruit."
    assert result.needs_refetch is False
    mock_persist.assert_called_once_with(result, final=True)


@pytest.mark.asyncio
async def test_enrich_wine_partial_first_fetch_sets_needs_refetch():
    mock_client = MagicMock()
    mock_client.search.return_value = [CAYMUS_HIT]
    mock_client.get_wine.return_value = PARTIAL_WINE
    mock_client.get_drinking_period.return_value = None

    with patch("enrichment.pipeline.is_already_enriched", return_value=False), \
         patch("enrichment.pipeline.GrapeMindsClient", return_value=mock_client), \
         patch("enrichment.pipeline.persist_candidates"), \
         patch("enrichment.pipeline._persist") as mock_persist:
        result = await enrich_wine(WINE_ROW)

    assert result.needs_refetch is True
    mock_persist.assert_called_once_with(result, final=False)


@pytest.mark.asyncio
async def test_enrich_wine_low_confidence_skips_enrichment():
    # A poorly-matching hit scores below MIN_ENRICH_CONFIDENCE → candidates are
    # stored, but no detail fetch and no wine_details write.
    mock_client = MagicMock()
    mock_client.search.return_value = [{
        "id": 999, "display_name": "Totally Unrelated Wine",
        "producer_name": "Someone Else", "color": "white",
    }]
    mock_client.get_wine.return_value = FULL_WINE  # must NOT be called

    with patch("enrichment.pipeline.is_already_enriched", return_value=False), \
         patch("enrichment.pipeline.GrapeMindsClient", return_value=mock_client), \
         patch("enrichment.pipeline.persist_candidates") as mock_persist_cands, \
         patch("enrichment.pipeline._persist") as mock_persist:
        result = await enrich_wine(WINE_ROW)

    assert result.source == "low_confidence"
    assert result.match_confidence is not None and result.match_confidence < 0.80
    mock_persist_cands.assert_called_once()    # candidates still stored
    mock_client.get_wine.assert_not_called()   # no detail fetch
    mock_persist.assert_not_called()           # no wine_details write


@pytest.mark.asyncio
async def test_enrich_wine_with_refetch_does_second_pass():
    mock_client = MagicMock()
    mock_client.search.return_value = [CAYMUS_HIT]
    # First call returns partial, second returns full
    mock_client.get_wine.side_effect = [PARTIAL_WINE, FULL_WINE]
    mock_client.get_drinking_period.return_value = DRINKING

    with patch("enrichment.pipeline.is_already_enriched", return_value=False), \
         patch("enrichment.pipeline.GrapeMindsClient", return_value=mock_client), \
         patch("enrichment.pipeline.persist_candidates"), \
         patch("enrichment.pipeline._persist"), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        result = await enrich_wine_with_refetch(WINE_ROW, refetch_delay=0)

    assert result.description == "Sun-drenched Napa Valley fruit."
    assert mock_client.get_wine.call_count == 2
