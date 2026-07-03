import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_search_wines_returns_list():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/wines/search?q=cabernet")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_search_wines_missing_query_returns_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/wines/search")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_wine_missing_returns_404():
    """GET /api/wines/{id} with a non-existent ID must return 404, not 500."""
    from unittest.mock import MagicMock, patch

    qb = MagicMock()
    qb.table.return_value = qb
    qb.select.return_value = qb
    qb.eq.return_value = qb
    qb.maybe_single.return_value = qb
    qb.order.return_value = qb
    qb.gte.return_value = qb
    execute_result = MagicMock()
    execute_result.data = None  # maybe_single() returns None when no row found
    qb.execute.return_value = execute_result

    with patch("api.routers.wines.get_supabase_client", return_value=qb):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/wines/does-not-exist")
    assert response.status_code == 404
