import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport
from api.main import app

_STORES = [
    {"id": "s1", "retailer_name": "H-E-B", "name": "H-E-B Lincoln Heights",
     "address": "999 E Basse Rd", "latitude": 29.49, "longitude": -98.46},
    {"id": "s2", "retailer_name": "Spec's", "name": "Spec's Broadway",
     "address": "5219 Broadway", "latitude": 29.47, "longitude": -98.47},
]


def _mock_sb():
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.execute.return_value.data = _STORES
    return sb


@pytest.mark.asyncio
async def test_nearby_stores_sorted_by_distance():
    with patch("api.routers.stores.get_supabase_client", return_value=_mock_sb()), \
         patch("api.routers.stores.zip_to_centroid", return_value=(29.4889, -98.4646)), \
         patch("api.routers.stores.find_nearby_store_ids", return_value=["s1", "s2"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            resp = await ac.get("/api/stores/nearby?zip=78209")
    assert resp.status_code == 200
    body = resp.json()
    assert [s["id"] for s in body["stores"]] == ["s1", "s2"]  # s1 is nearer the centroid
    assert body["stores"][0]["distance_miles"] is not None
    assert body["stores"][0]["retailer_name"] == "H-E-B"


@pytest.mark.asyncio
async def test_nearby_stores_unknown_zip_400():
    with patch("api.routers.stores.zip_to_centroid", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            resp = await ac.get("/api/stores/nearby?zip=00000")
    assert resp.status_code == 400
