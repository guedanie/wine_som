import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import os
import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from api.ratelimit import RateLimiter
from api.main import app


# ── RateLimiter unit ─────────────────────────────────────────────

def test_rate_limiter_allows_up_to_limit():
    rl = RateLimiter(limit=3, window_seconds=60)
    assert all(rl.allow("k") for _ in range(3))
    assert rl.allow("k") is False


def test_rate_limiter_window_expires(monkeypatch):
    rl = RateLimiter(limit=1, window_seconds=0.01)
    assert rl.allow("k") is True
    assert rl.allow("k") is False
    time.sleep(0.02)
    assert rl.allow("k") is True


def test_rate_limiter_keys_are_independent():
    rl = RateLimiter(limit=1, window_seconds=60)
    assert rl.allow("a") is True
    assert rl.allow("b") is True


# ── recommend endpoint enforces the limit ───────────────────────

@pytest.mark.asyncio
async def test_recommend_returns_429_when_limited():
    # The route dependency closes over the limiter OBJECT at import time —
    # patch the method on that object, not the module attribute.
    import api.routers.recommend as rec
    with patch.object(rec._recommend_limiter, "allow", return_value=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            resp = await ac.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 10, "budget_max": 50,
                "message": "Recommend wines based on my preferences",
            })
    assert resp.status_code == 429


# ── enrichment endpoints require admin token when configured ────

@pytest.mark.asyncio
async def test_enrich_403_without_token_when_configured():
    with patch.dict(os.environ, {"ADMIN_TOKEN": "sekrit"}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            resp = await ac.post("/api/enrich/some-wine-id")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_enrich_wrong_token_403():
    with patch.dict(os.environ, {"ADMIN_TOKEN": "sekrit"}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            resp = await ac.post("/api/enrich/some-wine-id",
                                 headers={"X-Admin-Token": "wrong"})
    assert resp.status_code == 403


# ── rate-limit observability: blocks must be measurable ─────────

def test_rate_limiter_alerts_once_per_window():
    rl = RateLimiter(limit=1, window_seconds=60)
    assert rl.should_alert("k") is True     # first block this window → alert
    assert rl.should_alert("k") is False    # repeat blocks stay quiet
    assert rl.should_alert("k2") is True    # other keys independent


@pytest.mark.asyncio
async def test_blocked_request_logs_and_notifies_slack_once(caplog):
    import logging
    import api.routers.recommend as rec
    rec._recommend_limiter._alerted.clear()
    with patch.object(rec._recommend_limiter, "allow", return_value=False), \
         patch("api.ratelimit._notify_slack") as slack, \
         caplog.at_level(logging.WARNING, logger="api.ratelimit"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            for _ in range(2):
                resp = await ac.post("/api/recommend", json={
                    "zip_code": "78209", "budget_min": 10, "budget_max": 50,
                    "message": "Recommend wines based on my preferences",
                })
    assert resp.status_code == 429
    blocked_logs = [r for r in caplog.records if "RATE_LIMITED" in r.getMessage()]
    assert len(blocked_logs) == 2           # every block logged
    assert slack.call_count == 1            # but Slack pinged once per window
