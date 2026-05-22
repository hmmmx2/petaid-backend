"""In-memory rate limiting for abuse prevention (anti-spam).

A process-local sliding-window counter. This matches the prototype's existing
in-memory state (login lockout, verification codes) and is correct for a
single-instance deployment. For a horizontally-scaled deployment the same
interface should be backed by a shared store (e.g. Redis) so limits hold
across instances.

Two ways to apply a limit:

* :func:`rate_limit_ip` — a FastAPI dependency for *pre-auth* endpoints
  (register / login / resend) where the only identity is the client IP.
* :func:`enforce` — called inside a handler once the authenticated account is
  known, to scope a limit per-account (donations / chats / messages / …).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import get_settings
from app.domain.exceptions import RateLimitedException


class _SlidingWindowLimiter:
    """Thread-safe sliding-window limiter keyed by an arbitrary string."""

    # Hard cap on tracked keys so a flood of unique identities (e.g. spoofed
    # IPs) cannot grow memory unbounded; oldest keys are dropped when exceeded.
    _MAX_KEYS = 50_000

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, max_requests: int, window_seconds: float) -> None:
        """Record one event for ``key``; raise if it exceeds the window budget."""
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            if len(self._hits) > self._MAX_KEYS:
                self._hits.clear()  # cheap, bounded reset under pathological load
            dq = self._hits[key]
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= max_requests:
                retry = int(dq[0] + window_seconds - now) + 1
                raise RateLimitedException(retry_after_seconds=max(retry, 1))
            dq.append(now)
            if not dq:
                self._hits.pop(key, None)


_limiter = _SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    """Best-effort client IP.

    Honours the first hop of ``X-Forwarded-For`` (set by Railway/Vercel and
    other trusted reverse proxies). NB: a client can spoof this header when the
    app is reached directly without a trusted proxy in front — rate limiting is
    therefore defence-in-depth, not the sole control.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def enforce(scope: str, identity: str, max_requests: int, window_seconds: float) -> None:
    """Apply a rate limit inside a handler (e.g. per authenticated account)."""
    if not get_settings().rate_limit_enabled:
        return
    _limiter.hit(f"{scope}:{identity}", max_requests, window_seconds)


def rate_limit_ip(scope: str, max_requests: int, window_seconds: float):
    """Build a FastAPI dependency that limits a route by client IP."""

    async def _dependency(request: Request) -> None:
        if not get_settings().rate_limit_enabled:
            return
        _limiter.hit(f"{scope}:ip:{client_ip(request)}", max_requests, window_seconds)

    return _dependency
