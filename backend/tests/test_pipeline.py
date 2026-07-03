import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from enrichment.pipeline import (
    enrich_wine, enrich_wine_with_refetch,
    _result_from_wine_data, EnrichmentResult, persist_candidates,
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


def test_persist_does_not_overwrite_retail_description():
    # Option 1: retail owns description/description_long; GrapeMinds enrichment
    # contributes only the structured fields and leaves the retail text intact.
    from enrichment.pipeline import _persist
    captured = {}

    class FakeTable:
        def upsert(self, record, on_conflict=None):
            captured["record"] = record
            return self
        def execute(self):
            return MagicMock(data=[])

    client = MagicMock()
    client.table.return_value = FakeTable()
    result = EnrichmentResult(
        wine_id="w1", grapeminds_id="113817",
        description="GM general description", description_long="GM long",
        tasting_notes="Dark cherry, vanilla", structure_profile={"body": 8},
    )
    with patch("enrichment.pipeline.get_service_client", return_value=client):
        _persist(result, final=True)

    assert "description" not in captured["record"]
    assert "description_long" not in captured["record"]
    assert captured["record"]["tasting_notes"] == "Dark cherry, vanilla"
    assert captured["record"]["structure_profile"] == {"body": 8}


def test_parse_detail_region_only_finalizes():
    # A wine with region (but no flavor_profile/description/tasting_notes) is still
    # "enriched enough" to finalize — GrapeMinds gave us real data.
    from enrichment.grapeminds import GrapeMindsClient
    gm = GrapeMindsClient(api_key="x")
    payload = {"data": {
        "id": 1, "display_name": "Austin Hope Cab", "color": "red",
        "region": {"name": "Paso Robles", "country": "us"},
        "flavor_profile": None, "description": None, "tasting_notes": None, "grapes": [],
    }}
    w = gm._parse_detail(payload)
    assert w.is_fully_enriched is True
    assert w.region_name == "Paso Robles"
    assert w.region_country == "us"


def test_parse_detail_truly_empty_stays_unfinished():
    from enrichment.grapeminds import GrapeMindsClient
    gm = GrapeMindsClient(api_key="x")
    payload = {"data": {"id": 1, "display_name": "X", "color": "red",
                        "region": None, "flavor_profile": None,
                        "description": None, "tasting_notes": None, "grapes": []}}
    w = gm._parse_detail(payload)
    assert w.is_fully_enriched is False


def test_result_from_wine_data_captures_region():
    from enrichment.grapeminds import GrapeMindsWine
    w = GrapeMindsWine(grapeminds_id="1", display_name="X",
                       region_name="Paso Robles", region_country="us")
    res = _result_from_wine_data("w1", w)
    assert res.region == "Paso Robles"
    assert res.region_country == "us"


def test_persist_backfills_region_on_wines_when_final():
    from enrichment.pipeline import _persist
    captured = {}

    class FakeTable:
        def __init__(self, name):
            self.name = name
        def upsert(self, record, on_conflict=None):
            captured.setdefault("upsert", {})[self.name] = record
            return self
        def update(self, vals):
            captured["update"] = (self.name, vals)
            return self
        def eq(self, *a, **k):
            return self
        def is_(self, *a, **k):
            return self
        def execute(self):
            return MagicMock(data=[])

    client = MagicMock()
    client.table.side_effect = lambda n: FakeTable(n)
    res = EnrichmentResult(wine_id="w1", grapeminds_id="1",
                           region="Paso Robles", region_country="us",
                           structure_profile={"body": 8})
    with patch("enrichment.pipeline.get_service_client", return_value=client):
        _persist(res, final=True)
    assert captured["update"][0] == "wines"
    assert captured["update"][1]["region"] == "Paso Robles"
    assert captured["update"][1]["country"] == "us"


def test_is_already_enriched_handles_no_wine_details_row():
    # Wines with no wine_details row must return False, not crash (the warm-up bug).
    from enrichment.pipeline import is_already_enriched
    client = MagicMock()
    qb = client.table.return_value
    qb.select.return_value = qb
    qb.eq.return_value = qb
    qb.limit.return_value = qb
    qb.execute.return_value = MagicMock(data=[])      # no rows
    with patch("enrichment.pipeline.get_service_client", return_value=client):
        assert is_already_enriched("w1") is False


def test_is_already_enriched_true_when_timestamp_set():
    from enrichment.pipeline import is_already_enriched
    client = MagicMock()
    qb = client.table.return_value
    qb.select.return_value = qb
    qb.eq.return_value = qb
    qb.limit.return_value = qb
    qb.execute.return_value = MagicMock(data=[{"grapeminds_enriched_at": "2026-06-14T00:00:00Z"}])
    with patch("enrichment.pipeline.get_service_client", return_value=client):
        assert is_already_enriched("w1") is True


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


def test_persist_candidates_uses_upsert_not_delete_insert():
    """persist_candidates must use upsert (atomic), not delete-then-insert. (B4)"""
    db = MagicMock()
    db.table.return_value = db
    db.upsert.return_value = db
    db.execute.return_value = MagicMock()

    candidates = [{"grapeminds_id": "123", "display_name": "Wine A", "producer_name": "Prod",
                   "color": "red", "confidence": 0.9, "rank": 1, "is_primary": True}]

    with patch("enrichment.pipeline.get_service_client", return_value=db):
        persist_candidates("wine-1", candidates)

    assert db.delete.call_count == 0, "persist_candidates must not call delete"
    assert db.upsert.call_count == 1, "persist_candidates must call upsert"
