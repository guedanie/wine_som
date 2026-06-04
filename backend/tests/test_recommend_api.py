import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from api.main import app


WINE_ROW = {
    "price": 22.0,
    "retailer_name": "Geraldine's",
    "wine_id": "abc-123",
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


def _make_db_mock(data):
    qb = MagicMock()
    qb.table.return_value = qb
    qb.select.return_value = qb
    qb.eq.return_value = qb
    qb.gte.return_value = qb
    qb.lte.return_value = qb
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
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])):
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
    with patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([])):
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
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([WINE_ROW])):
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
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
            })
    assert response.status_code == 200
    for pick in response.json()["picks"]:
        assert all(k in pick for k in ["wine_id", "name", "price", "retailer", "why"])
