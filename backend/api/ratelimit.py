"""Minimal in-memory per-IP rate limiting.

Every /api/recommend call costs a Sonnet invocation and /api/somm streams
Haiku — a public URL needs a spend ceiling. Sliding-window counters in
process memory: fine for a single instance (Railway hobby), revisit if we
ever scale horizontally.
"""
import os
import time
from collections import defaultdict, deque
from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window = window_seconds
        self._hits = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        dq = self._hits[key]
        while dq and now - dq[0] > self.window:
            dq.popleft()
        if len(dq) >= self.limit:
            return False
        dq.append(now)
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
        if not limiter.allow(f"{name}:{client_ip(request)}"):
            raise HTTPException(
                status_code=429,
                detail="Easy there — give the sommelier a minute to breathe.",
            )
    return _check
