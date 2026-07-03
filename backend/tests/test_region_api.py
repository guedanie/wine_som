import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from api.main import app

# ── fixtures ─────────────────────────────────────────────────────────────────

_STORE = {"id": "store-uuid-1", "retailer_name": "Spec's"}

_INV_ROW = {
    "price": 28.0,
    "wine_id": "wine-uuid-1",
    "stores": {"retailer_name": "Spec's", "address": "1234 Main St"},
    "wines": {
        "id": "wine-uuid-1",
        "name": "Test Chianti",
        "varietal": "Sangiovese",
        "region": "Tuscany",
        "country": "Italy",
        "wine_type": "red",
        "grapes": ["Sangiovese"],
        "image_url": None,
        "wine_details": [{"flavor_profile": ["dark cherry", "leather"]}],
    },
}

def _make_db_mock(inv_rows=None, store_rows=None):
    db = MagicMock()
    # stores query
    stores_resp = MagicMock()
    stores_resp.data = store_rows if store_rows is not None else [_STORE]
    db.table.return_value.select.return_value.in_.return_value.execute.return_value = stores_resp
    # inventory query — chain: .in_().eq(in_stock).eq(wines.region).gte().lte().limit().execute()
    inv_resp = MagicMock()
    inv_resp.data = inv_rows if inv_rows is not None else [_INV_ROW]
    q = db.table.return_value.select.return_value
    q.in_.return_value.eq.return_value.eq.return_value.gte.return_value.lte.return_value.limit.return_value.execute.return_value = inv_resp
    return db


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_region_returns_200_with_wines():
    with (
        patch("api.routers.region.get_supabase_client", return_value=_make_db_mock()),
        patch("api.routers.region.zip_to_centroid", return_value=(29.48, -98.42)),
        patch("api.routers.region.find_nearby_store_ids", return_value=["store-uuid-1"]),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/region/Tuscany?zip=78209")
    assert resp.status_code == 200
    body = resp.json()
    assert body["region"] == "Tuscany"
    assert len(body["retailers"]) == 1
    assert body["retailers"][0]["retailer"] == "Spec's"
    assert body["retailers"][0]["wines"][0]["name"] == "Test Chianti"


@pytest.mark.asyncio
async def test_region_400_on_unknown_zip():
    with patch("api.routers.region.zip_to_centroid", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/region/Tuscany?zip=00000")
    assert resp.status_code == 400
    assert "zip" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_region_404_when_no_wines():
    with (
        patch("api.routers.region.get_supabase_client", return_value=_make_db_mock(inv_rows=[])),
        patch("api.routers.region.zip_to_centroid", return_value=(29.48, -98.42)),
        patch("api.routers.region.find_nearby_store_ids", return_value=["store-uuid-1"]),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/region/Tuscany?zip=78209")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_region_alias_rhone_valley():
    """'Rhône Valley' in the URL maps to 'Rhône' in the DB filter."""
    rhone_row = {
        "price": 32.0,
        "wine_id": "wine-uuid-2",
        "stores": {"retailer_name": "Spec's", "address": "1234 Main St"},
        "wines": {
            "id": "wine-uuid-2",
            "name": "Test Côtes du Rhône",
            "varietal": "Grenache",
            "region": "Rhône",
            "country": "France",
            "wine_type": "red",
            "grapes": ["Grenache"],
            "image_url": None,
            "wine_details": [{"flavor_profile": ["dark fruit", "pepper"]}],
        },
    }
    with (
        patch("api.routers.region.get_supabase_client", return_value=_make_db_mock(inv_rows=[rhone_row])),
        patch("api.routers.region.zip_to_centroid", return_value=(29.48, -98.42)),
        patch("api.routers.region.find_nearby_store_ids", return_value=["store-uuid-1"]),
        patch("api.routers.region._db_region_name", return_value="Rhône"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/region/Rh%C3%B4ne%20Valley?zip=78209")
    assert resp.status_code == 200
    assert resp.json()["region"] == "Rhône Valley"




# ── sub-region counts ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subregion_counts():
    """GET /api/region/{name}/subregions returns wine counts grouped by sub_region."""
    db = MagicMock()
    resp_mock = MagicMock()
    resp_mock.data = [
        {"sub_region": "Chianti Classico"},
        {"sub_region": "Chianti Classico"},
        {"sub_region": "Montalcino"},
        {"sub_region": None},
    ]
    (db.table.return_value.select.return_value.eq.return_value
     .limit.return_value.execute.return_value) = resp_mock
    with patch("api.routers.region.get_supabase_client", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/region/Tuscany/subregions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["region"] == "Tuscany"
    assert body["counts"]["Chianti Classico"] == 2
    assert body["counts"]["Montalcino"] == 1
    assert None not in body["counts"]


@pytest.mark.asyncio
async def test_subregion_counts_uses_region_alias():
    """Rhône Valley must query the DB under its alias 'Rhône'."""
    db = MagicMock()
    resp_mock = MagicMock()
    resp_mock.data = []
    eq_mock = db.table.return_value.select.return_value.eq
    eq_mock.return_value.limit.return_value.execute.return_value = resp_mock
    with patch("api.routers.region.get_supabase_client", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/region/Rh%C3%B4ne%20Valley/subregions")
    assert resp.status_code == 200
    eq_mock.assert_called_with("region", "Rhône")
