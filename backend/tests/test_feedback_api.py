import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from api.main import app


def _make_db_mock():
    db = MagicMock()
    upsert_resp = MagicMock()
    upsert_resp.data = [{"id": "uuid-1"}]
    db.table.return_value.upsert.return_value.execute.return_value = upsert_resp
    return db


@pytest.mark.asyncio
async def test_post_feedback_wine_card():
    with patch("api.routers.feedback.get_service_client", return_value=_make_db_mock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/feedback", json={
                "type": "wine_card",
                "entity_id": "wine-uuid-1",
                "vote": "up",
                "session_id": "sess-1",
            })
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_post_feedback_sommelier_message():
    with patch("api.routers.feedback.get_service_client", return_value=_make_db_mock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/feedback", json={
                "type": "sommelier_message",
                "entity_id": "msg-uuid-1",
                "vote": "down",
                "session_id": "sess-1",
                "zip": "78209",
            })
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_post_feedback_null_vote_deselect():
    with patch("api.routers.feedback.get_service_client", return_value=_make_db_mock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/feedback", json={
                "type": "wine_card",
                "entity_id": "wine-uuid-1",
                "vote": None,
                "session_id": "sess-1",
            })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_post_feedback_invalid_type_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/feedback", json={
            "type": "invalid_type",
            "entity_id": "wine-uuid-1",
            "vote": "up",
            "session_id": "sess-1",
        })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_feedback_supabase_error_returns_ok_false():
    """Supabase failure must return {"ok": False}, not a 500. (E1)"""
    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.side_effect = RuntimeError("connection lost")
    with patch("api.routers.feedback.get_service_client", return_value=db):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/feedback", json={
                "type": "wine_card",
                "entity_id": "wine-uuid-1",
                "vote": "up",
                "session_id": "sess-1",
            })
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
