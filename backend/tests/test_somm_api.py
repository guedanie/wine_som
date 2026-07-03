import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from api.main import app

_WINE = {
    "wine_name": "Esprit de Tablas",
    "producer": "Tablas Creek",
    "vintage": 2021,
    "price": 55.0,
    "store": "Spec's",
    "tags": ["dark cherry", "garrigue", "leather"],
    "region": "Paso Robles",
    "wine_type": "Red Wine",
}


def _mock_stream(tokens):
    """Return a mock anthropic streaming context manager yielding text chunks."""
    from unittest.mock import MagicMock

    class FakeEvent:
        def __init__(self, t):
            self.type = "content_block_delta"
            self.delta = MagicMock()
            self.delta.type = "text_delta"
            self.delta.text = t

    class FakeStream:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def __iter__(self):
            for t in tokens:
                yield FakeEvent(t)

    return FakeStream()


@pytest.mark.asyncio
async def test_somm_streams_tokens():
    with patch("api.routers.somm.anthropic_client") as mock_client:
        mock_client.messages.stream.return_value = _mock_stream(["A great", " wine."])
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/somm", json={"wine": _WINE, "message": "Tell me about this."})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert '"type": "token"' in body
    assert "A great" in body
    assert "[DONE]" in body


@pytest.mark.asyncio
async def test_somm_empty_message_still_streams():
    with patch("api.routers.somm.anthropic_client") as mock_client:
        mock_client.messages.stream.return_value = _mock_stream(["Lovely structure."])
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/somm", json={"wine": _WINE, "message": ""})
    assert resp.status_code == 200
    assert "Lovely structure." in resp.text


@pytest.mark.asyncio
async def test_somm_missing_wine_name_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/somm", json={"wine": {}, "message": "hi"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_somm_error_does_not_expose_exception_detail():
    """When Claude raises, the SSE error event must not contain raw exception text. (E4)"""
    import json as _json

    with patch("api.routers.somm.anthropic_client") as mock_client:
        mock_client.messages.stream.side_effect = Exception(
            "credit_balance_too_low api_key=sk-ant-SECRET-XYZ"
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/somm", json={"wine": _WINE, "message": "Tell me about this."})

    assert resp.status_code == 200
    error_events = []
    for line in resp.text.splitlines():
        if line.startswith("data: ") and line[6:] != "[DONE]":
            event = _json.loads(line[6:])
            if event.get("type") == "error":
                error_events.append(event)
    assert len(error_events) == 1
    assert "sk-ant" not in error_events[0]["message"]
    assert "credit_balance" not in error_events[0]["message"]


def test_system_prompt_includes_vivino_rating_when_present():
    """_system_prompt must surface Vivino rating so Somm can cite community credibility."""
    from api.routers.somm import _system_prompt
    from api.schemas import SommWineContext
    wine = SommWineContext(
        wine_name="Esprit de Tablas",
        vivino_rating=4.1,
        vivino_ratings_count=26908,
    )
    prompt = _system_prompt(wine)
    assert "4.1" in prompt
    assert "Vivino" in prompt
    assert "26908" in prompt or "26,908" in prompt


def test_system_prompt_omits_vivino_when_absent():
    """_system_prompt must not mention Vivino when no rating is available."""
    from api.routers.somm import _system_prompt
    from api.schemas import SommWineContext
    wine = SommWineContext(wine_name="Obscure Cuvée")
    prompt = _system_prompt(wine)
    assert "Vivino" not in prompt


@pytest.mark.asyncio
async def test_somm_with_history():
    with patch("api.routers.somm.anthropic_client") as mock_client:
        mock_client.messages.stream.return_value = _mock_stream(["Yes, decant it."])
        history = [
            {"role": "user", "content": "Should I decant it?"},
        ]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/somm", json={"wine": _WINE, "message": "How long?", "history": history})
    assert resp.status_code == 200
    assert "Yes, decant it." in resp.text
    # Verify history was passed to Claude
    call_kwargs = mock_client.messages.stream.call_args[1]
    messages_sent = call_kwargs["messages"]
    assert any(m["role"] == "user" and "Should I decant it?" in m["content"] for m in messages_sent)
