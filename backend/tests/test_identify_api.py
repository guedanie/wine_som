"""Tests for POST /api/identify — the bottle-photo identification endpoint.

No real Anthropic calls: enrichment.label_scan.read_label is always mocked.
Real vision accuracy is validated manually against the live endpoint with
real photos, per the design doc — not something a mocked test can measure.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from unittest.mock import patch, MagicMock
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app

_JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-bytes-for-testing"


def _read_and_meta(producer="Tablas Creek", wine_name="Esprit de Tablas",
                   vintage="2021", confidence=0.9, is_wine=True):
    read = {"producer": producer, "wine_name": wine_name, "vintage": vintage,
            "appellation": "Paso Robles", "varietal": None,
            "confidence": confidence, "is_wine": is_wine}
    meta = {"latency_s": 1.4, "input_tokens": 1200, "output_tokens": 40,
            "model": "claude-haiku-4-5-20251001"}
    return read, meta


@pytest.mark.asyncio
async def test_exact_match_returns_200_with_wine():
    candidates = [{"id": "w1", "name": "Esprit de Tablas", "brand": "Tablas Creek",
                   "vintage_year": 2021, "region": "Paso Robles", "varietal": None}]
    with patch("api.routers.identify.read_label", return_value=_read_and_meta()), \
         patch("api.routers.identify._fetch_candidates", return_value=candidates):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/identify",
                                 files={"photo": ("bottle.jpg", _JPEG_BYTES, "image/jpeg")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "exact"
    assert body["wine"]["id"] == "w1"
    assert "_debug" in body
    assert body["_debug"]["model"] == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_unreadable_label_returns_200_with_unreadable_status():
    with patch("api.routers.identify.read_label", return_value=(None, _read_and_meta()[1])), \
         patch("api.routers.identify._fetch_candidates", return_value=[]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/identify",
                                 files={"photo": ("bottle.jpg", _JPEG_BYTES, "image/jpeg")})
    assert resp.status_code == 200
    assert resp.json()["status"] == "unreadable"


@pytest.mark.asyncio
async def test_non_image_upload_returns_400():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/identify",
                             files={"photo": ("notes.txt", b"hello", "text/plain")})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_vision_call_failure_returns_502():
    with patch("api.routers.identify.read_label", side_effect=Exception("Anthropic down")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/identify",
                                 files={"photo": ("bottle.jpg", _JPEG_BYTES, "image/jpeg")})
    assert resp.status_code == 502


def test_fetch_candidates_queries_name_and_brand_tokens():
    from api.routers.identify import _fetch_candidates
    mock_sb = MagicMock()
    mock_table = MagicMock()
    mock_sb.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.is_.return_value = mock_table
    mock_table.or_.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[{"id": "w1", "name": "Esprit de Tablas"}])

    read = {"producer": "Tablas Creek", "wine_name": "Esprit de Tablas"}
    result = _fetch_candidates(mock_sb, read)

    assert result == [{"id": "w1", "name": "Esprit de Tablas"}]
    mock_sb.table.assert_called_with("wines")
    mock_table.is_.assert_called_with("excluded_at", "null")
    assert mock_table.or_.called


def test_fetch_candidates_returns_empty_for_no_tokens():
    from api.routers.identify import _fetch_candidates
    mock_sb = MagicMock()
    result = _fetch_candidates(mock_sb, {"producer": None, "wine_name": None})
    assert result == []
    mock_sb.table.assert_not_called()
