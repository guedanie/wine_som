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
async def test_get_wine_returns_price_context_and_annotated_availability():
    """The dossier payload carries price_context (movement + cheapest) and
    availability rows annotated with is_cheapest / was_price."""
    from unittest.mock import MagicMock, patch

    qb = MagicMock()
    for m in ("table", "select", "eq", "maybe_single", "order", "gte", "in_"):
        getattr(qb, m).return_value = qb
    wine_res = MagicMock(data={"id": "w1", "name": "Test Malbec"})
    inv_res = MagicMock(data=[
        {"price": 19.99, "stores": {"id": "s1", "retailer_name": "H-E-B", "address": "123 Main"}},
        {"price": 22.99, "stores": {"id": "s2", "retailer_name": "Spec's", "address": "9 Elm"}},
    ])
    from datetime import datetime, timedelta, timezone
    fresh = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    hist_res = MagicMock(data=[
        {"store_ref": "s1", "price": 24.99, "recorded_at": "2026-06-07T10:00:00+00:00"},
        {"store_ref": "s1", "price": 19.99, "recorded_at": fresh},
    ])
    qb.execute.side_effect = [wine_res, inv_res, hist_res]

    with patch("api.routers.wines.get_supabase_client", return_value=qb):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/wines/w1")
    assert response.status_code == 200
    body = response.json()
    ctx = body["price_context"]
    assert ctx["variant"] == "drop"
    assert ctx["amount"] == 5.0
    assert ctx["store"] == "H-E-B"
    assert ctx["cheapest"]["retailer"] == "H-E-B"
    rows = {r["retailer"]: r for r in body["availability"]}
    assert rows["H-E-B"]["is_cheapest"] is True
    assert rows["H-E-B"]["was_price"] == 24.99
    assert rows["Spec's"]["was_price"] is None


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
