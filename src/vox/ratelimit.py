"""Token-bucket rate limiter with per-category configs and ASGI middleware."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from vox.auth.service import get_user_by_token
from vox.db.engine import get_session_factory

# Short-lived cache: token -> (user_id, expiry_monotonic).
# Avoids opening a DB connection per request in the rate-limit middleware.
_TOKEN_CACHE: dict[str, tuple[int, float]] = {}
_TOKEN_CACHE_TTL = 30.0  # seconds

# ---------------------------------------------------------------------------
# Token bucket data
# ---------------------------------------------------------------------------


@dataclass
class Bucket:
    tokens: float
    last_refill: float


# category -> (max_tokens, refill_per_second)
CATEGORIES: dict[str, tuple[int, float]] = {
    "auth": (5, 0.1),
    "messages": (50, 1.0),
    "channels": (20, 0.5),
    "roles": (10, 0.2),
    "members": (20, 0.5),
    "invites": (10, 0.2),
    "webhooks": (10, 0.2),
    "emoji": (10, 0.2),
    "moderation": (10, 0.2),
    "voice": (30, 1.0),
    "server": (10, 0.2),
    "bots": (10, 0.2),
    "e2ee": (30, 0.5),
    "search": (10, 0.1),
    "files": (20, 0.5),
    "federation": (50, 1.0),
}

# In-memory store: (key, category) -> Bucket
_buckets: dict[tuple[str, str], Bucket] = {}

# ---------------------------------------------------------------------------
# Path -> category classifier
# ---------------------------------------------------------------------------

_PREFIX_MAP: list[tuple[str, str]] = [
    ("/api/v1/auth", "auth"),
    ("/api/v1/feeds", "channels"),
    ("/api/v1/rooms", "channels"),
    ("/api/v1/categories", "channels"),
    ("/api/v1/threads", "channels"),
    ("/api/v1/roles", "roles"),
    ("/api/v1/members", "members"),
    ("/api/v1/invites", "invites"),
    ("/api/v1/webhooks", "webhooks"),
    ("/api/v1/emoji", "emoji"),
    ("/api/v1/stickers", "emoji"),
    ("/api/v1/moderation", "moderation"),
    ("/api/v1/voice", "voice"),
    ("/api/v1/server", "server"),
    ("/api/v1/bots", "bots"),
    ("/api/v1/keys", "e2ee"),
    ("/api/v1/dms", "messages"),
    ("/api/v1/files", "files"),
    ("/api/v1/federation", "federation"),
    ("/api/v1/reports", "moderation"),
    ("/api/v1/admin", "moderation"),
    ("/api/v1/users", "members"),
]


def classify(path: str) -> str:
    """Map a URL path to a rate-limit category."""
    # Messages endpoint is nested under /feeds/.../messages
    if "/messages" in path:
        return "messages"
    # Webhook execute creates messages — use the messages rate limit.
    if path.startswith("/api/v1/webhooks/") and "/execute" in path:
        return "messages"
    if "/search" in path:
        return "search"
    for prefix, cat in _PREFIX_MAP:
        if path.startswith(prefix):
            return cat
    return "server"  # fallback


# ---------------------------------------------------------------------------
# Token bucket check
# ---------------------------------------------------------------------------


def check(key: str, category: str) -> tuple[bool, int, int, int, int]:
    """Check whether *key* may proceed for *category*.

    Returns ``(allowed, limit, remaining, reset_ts, retry_after_ms)``.
    ``retry_after_ms`` is only meaningful when ``allowed`` is False.
    """
    max_tokens, refill_rate = CATEGORIES.get(category, (10, 0.2))
    now = time.time()
    bucket_key = (key, category)
    bucket = _buckets.get(bucket_key)

    if bucket is None:
        bucket = Bucket(tokens=float(max_tokens), last_refill=now)
        _buckets[bucket_key] = bucket

    # Refill
    elapsed = now - bucket.last_refill
    bucket.tokens = min(max_tokens, bucket.tokens + elapsed * refill_rate)
    bucket.last_refill = now

    if bucket.tokens >= 1.0:
        bucket.tokens -= 1.0
        remaining = int(bucket.tokens)
        reset_ts = int(now + (max_tokens - bucket.tokens) / refill_rate) if refill_rate else int(now)
        return True, max_tokens, remaining, reset_ts, 0
    else:
        # Time until one token is available
        wait = (1.0 - bucket.tokens) / refill_rate if refill_rate else 1.0
        retry_after_ms = int(math.ceil(wait * 1000))
        return False, max_tokens, 0, int(now + wait), retry_after_ms


def reset() -> None:
    """Clear all buckets (useful for tests)."""
    _buckets.clear()


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

_SKIP_PREFIXES = ("/gateway", "/docs", "/openapi.json")


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # Skip WebSocket and docs
        for prefix in _SKIP_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        category = classify(path)

        # Determine key
        key = await self._resolve_key(request, path)

        allowed, limit, remaining, reset_ts, retry_after_ms = check(key, category)

        if not allowed:
            retry_after_s = math.ceil(retry_after_ms / 1000)
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "You are being rate limited.",
                        "retry_after_ms": retry_after_ms,
                    }
                },
                headers={
                    "Retry-After": str(retry_after_s),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_ts),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_ts)
        return response

    async def _resolve_key(self, request: Request, path: str) -> str:
        ip = request.client.host if request.client else "unknown"

        # Federation endpoints are keyed by IP only
        if path.startswith("/api/v1/federation"):
            return f"fed:{ip}"

        # Webhook execution is keyed by webhook ID (extracted from path)
        # to apply the messages rate limit per-webhook.
        if path.startswith("/api/v1/webhooks/") and "/execute" in path:
            parts = path.split("/")
            # /api/v1/webhooks/{id}/{token}/execute -> parts[4] is webhook ID
            wh_id = parts[4] if len(parts) > 4 else "unknown"
            return f"webhook:{wh_id}"

        # Try to extract user from Authorization header
        auth = request.headers.get("authorization")
        if auth:
            if auth.startswith("Bearer "):
                token = auth[7:]
            elif auth.startswith("Bot "):
                token = auth[4:]
            else:
                return f"ip:{ip}"

            # Check cache first to avoid a DB round-trip per request.
            now = time.monotonic()
            cached = _TOKEN_CACHE.get(token)
            if cached is not None:
                uid, expires = cached
                if now < expires:
                    return f"user:{uid}"
                del _TOKEN_CACHE[token]

            try:
                factory = get_session_factory()
                async with factory() as db:
                    user, _sess = await get_user_by_token(db, token)
                    if user is not None:
                        _TOKEN_CACHE[token] = (user.id, now + _TOKEN_CACHE_TTL)
                        return f"user:{user.id}"
            except Exception:
                pass

        return f"ip:{ip}"
