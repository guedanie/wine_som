"""Minimal in-memory per-IP rate limiting.

Every /api/recommend call costs a Sonnet invocation and /api/somm streams
Haiku — a public URL needs a spend ceiling. Sliding-window counters in
process memory: fine for a single instance (Railway hobby), revisit if we
ever scale horizontally.

Blocks are observable by design: every 429 logs, and the FIRST block per
key per window pings Slack — the 15/hr recommend limit is deliberately kept
through beta to measure how much it throttles real aisle sessions, which
only works if blocks are visible.
"""
import json
import logging
import os
import time
import urllib.request
from collections import defaultdict, deque
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def _notify_slack(text: str) -> None:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return
    try:
        req = urllib.request.Request(
            url, data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window = window_seconds
        self._hits = defaultdict(deque)
        self._alerted = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        dq = self._hits[key]
        while dq and now - dq[0] > self.window:
            dq.popleft()
        if len(dq) >= self.limit:
            return False
        dq.append(now)
        return True

    def should_alert(self, key: str) -> bool:
        """True on the first block for `key` in the current window — repeat
        blocks stay quiet so a hammering client can't spam Slack."""
        now = time.monotonic()
        last = self._alerted.get(key)
        if last is not None and now - last <= self.window:
            return False
        self._alerted[key] = now
        return True


def client_ip(request: Request) -> str:
    """Real client IP behind Railway/Vercel proxies (first X-Forwarded-For hop)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def limit_dependency(limiter: RateLimiter, name: str):
    """FastAPI dependency enforcing `limiter` per client IP. Disabled when
    RATE_LIMITS_OFF=1 (local dev / tests that hammer endpoints)."""
    async def _check(request: Request):
        if os.environ.get("RATE_LIMITS_OFF") == "1":
            return
        ip = client_ip(request)
        key = f"{name}:{ip}"
        if not limiter.allow(key):
            logger.warning("RATE_LIMITED | endpoint=%s ip=%s limit=%d/%.0fs",
                           name, ip, limiter.limit, limiter.window)
            if limiter.should_alert(key):
                _notify_slack(
                    f":hourglass: rate limit hit — `{name}` ip={ip} "
                    f"({limiter.limit}/{limiter.window / 3600:.0g}h). "
                    f"First block this window; further blocks logged only.")
            raise HTTPException(
                status_code=429,
                detail="Easy there — give the sommelier a minute to breathe.",
            )
    return _check
