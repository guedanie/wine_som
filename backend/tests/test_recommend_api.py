import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from api.main import app


WINE_ROW = {
    "price": 22.0,
    "curbside_price": None,
    "wine_id": "abc-123",
    "stores": {"retailer_name": "Geraldine's", "store_name": "Geraldine's", "zip_code": "78209"},
    "wines": {
        "id": "abc-123",
        "name": "Test Malbec",
        "varietal": "Malbec",
        "region": "Mendoza",
        "country": "Argentina",
        "wine_type": "red",
        "wine_details": [{
            "tasting_notes": "dark fruit, plum, chocolate",
            "flavor_profile": ["dark fruit", "plum"],
            "structure_profile": {"body": 8, "tannins": 7, "acidity": 5},
            "grapeminds_enriched_at": "2026-06-03T00:00:00Z",
        }],
    },
}

PICKS = [{
    "wine_id": "abc-123",
    "name": "Test Malbec",
    "price": 22.0,
    "retailer": "Geraldine's",
    "why": "A classic Mendoza Malbec from Argentina with bold dark fruit.",
}]


def _wine_row(name="Test Malbec", wine_id="abc-123", enriched=True, varietal="Malbec",
              region="Mendoza", grapes=None, body="full", price=22.0):
    return {
        "price": price, "curbside_price": None, "wine_id": wine_id,
        "stores": {"retailer_name": "Spec's", "store_name": "Spec's", "zip_code": "78209"},
        "wines": {
            "id": wine_id, "name": name, "varietal": varietal, "region": region,
            "country": "Argentina", "wine_type": "red", "grapes": grapes or ["Malbec"],
            "body": body,
            "wine_details": [{
                "tasting_notes": "dark fruit, plum",
                "flavor_profile": ["dark fruit"],
                "structure_profile": {},
                "grapeminds_enriched_at": "2026-06-03T00:00:00Z" if enriched else None,
            }],
        },
    }


def _make_db_mock(data):
    qb = MagicMock()
    qb.table.return_value = qb
    qb.select.return_value = qb
    qb.eq.return_value = qb
    qb.gte.return_value = qb
    qb.lte.return_value = qb
    qb.in_.return_value = qb
    qb.limit.return_value = qb
    qb.insert.return_value = qb
    execute_result = MagicMock()
    execute_result.data = data
    qb.execute.return_value = execute_result
    return qb


def _make_anthropic_mock(narrative="Here are my top picks.", picks=None):
    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.input = {"narrative": narrative, "picks": picks or PICKS}
    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_cls = MagicMock()
    mock_cls.return_value.messages.create.return_value = mock_response
    return mock_cls


@pytest.mark.asyncio
async def test_recommend_returns_200():
    with patch("recommendation.claude_client.anthropic.Anthropic", _make_anthropic_mock()), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([WINE_ROW])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
                "style_preferences": ["bold", "earthy"],
                "avoid": [],
            })
    assert response.status_code == 200
    body = response.json()
    assert "narrative" in body
    assert "picks" in body
    assert "session_id" in body


@pytest.mark.asyncio
async def test_recommend_no_enriched_wines_returns_400():
    with patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
            })
    assert response.status_code == 400
    assert "No enriched wines" in response.json()["detail"]


@pytest.mark.asyncio
async def test_recommend_missing_zip_returns_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/recommend", json={
            "budget_min": 15.0,
            "budget_max": 35.0,
        })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recommend_claude_failure_returns_500():
    with patch("api.routers.recommend.get_recommendations", side_effect=Exception("API down")), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([WINE_ROW])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
            })
    assert response.status_code == 500
    assert "unavailable" in response.json()["detail"]


@pytest.mark.asyncio
async def test_recommend_picks_have_required_fields():
    with patch("recommendation.claude_client.anthropic.Anthropic", _make_anthropic_mock()), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([WINE_ROW])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
            })
    assert response.status_code == 200
    for pick in response.json()["picks"]:
        assert all(k in pick for k in ["wine_id", "name", "price", "retailer", "why"])


@pytest.mark.asyncio
async def test_recommend_unknown_zip_returns_400():
    with patch("api.routers.recommend.zip_to_centroid", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "00000",
                "budget_min": 15.0,
                "budget_max": 35.0,
            })
    assert response.status_code == 400
    assert "don't recognize" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_recommend_no_stores_nearby_returns_400():
    with patch("api.routers.recommend.zip_to_centroid", return_value=(29.47, -98.46)), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=[]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
            })
    assert response.status_code == 400
    assert "no stores found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_recommend_includes_extractor_only_tier2_wine():
    """A wine with no GrapeMinds enrichment but with varietal/region is still a candidate."""
    row = _wine_row(enriched=False)   # tier 2
    with patch("recommendation.claude_client.anthropic.Anthropic", _make_anthropic_mock()), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([row])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 15.0, "budget_max": 35.0})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_recommend_parses_nl_message_and_merges():
    captured = {}
    def fake_parse(msg):
        captured["msg"] = msg
        return {"wine_type": "white", "body": "light", "flavors": ["earthy"],
                "grapes": [], "region": None, "max_price": None, "avoid": []}
    with patch("recommendation.claude_client.anthropic.Anthropic", _make_anthropic_mock()), \
         patch("api.routers.recommend.parse_message", side_effect=fake_parse), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([_wine_row()])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 15.0, "budget_max": 35.0,
                "wine_type": "red", "message": "something earthy"})
    assert response.status_code == 200
    assert captured["msg"] == "something earthy"


@pytest.mark.asyncio
async def test_recommend_fail_soft_when_parse_errors():
    with patch("recommendation.claude_client.anthropic.Anthropic", _make_anthropic_mock()), \
         patch("api.routers.recommend.parse_message", return_value=None), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([_wine_row()])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 15.0, "budget_max": 35.0,
                "message": "anything"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_recommend_reattaches_retailer_from_candidate_not_model():
    """The model only sees wines as text; the response must use the candidate's
    authoritative retailer/name/price keyed by wine_id, not whatever the model echoes."""
    # Model returns a pick with the correct wine_id but a WRONG retailer/name.
    bad_pick = [{"wine_id": "abc-123", "name": "Model Hallucinated Name",
                 "price": 999.0, "retailer": "WRONG-RETAILER", "why": "because"}]
    with patch("recommendation.claude_client.anthropic.Anthropic",
               _make_anthropic_mock(picks=bad_pick)), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([_wine_row()])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 15.0, "budget_max": 35.0})
    assert response.status_code == 200
    pick = response.json()["picks"][0]
    assert pick["retailer"] == "Spec's"          # from candidate (_wine_row), not "WRONG-RETAILER"
    assert pick["name"] == "Test Malbec"          # authoritative name
    assert pick["price"] == 22.0                  # authoritative price
    assert pick["why"] == "because"               # model's narrative kept


def test_recommend_request_accepts_wine_types():
    from api.schemas import RecommendRequest
    req = RecommendRequest(zip_code="78209", wine_types=["red", "white"])
    assert req.wine_types == ["red", "white"]


def test_recommend_request_wine_types_defaults_empty():
    from api.schemas import RecommendRequest
    req = RecommendRequest(zip_code="78209")
    assert req.wine_types == []


def test_recommend_request_accepts_grapes():
    from api.schemas import RecommendRequest
    req = RecommendRequest(zip_code="78209", grapes=["Cabernet Sauvignon", "Merlot"])
    assert req.grapes == ["Cabernet Sauvignon", "Merlot"]


def test_recommend_request_grapes_defaults_empty():
    from api.schemas import RecommendRequest
    req = RecommendRequest(zip_code="78209")
    assert req.grapes == []
