"""Header-driven rate-limit tracker mirroring the server's bucket categories."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import httpx


# ---------------------------------------------------------------------------
# Path → category classifier (mirrors server ratelimit.py)
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
    if "/messages" in path:
        return "messages"
    if "/search" in path:
        return "search"
    for prefix, cat in _PREFIX_MAP:
        if path.startswith(prefix):
            return cat
    return "server"


# ---------------------------------------------------------------------------
# Bucket info parsed from response headers
# ---------------------------------------------------------------------------

@dataclass
class BucketInfo:
    limit: int = 0
    remaining: int = 0
    reset: float = 0.0  # unix timestamp


# ---------------------------------------------------------------------------
# Rate-limit store
# ---------------------------------------------------------------------------

class RateLimiter:
    """Tracks per-category rate limits from response headers and pre-emptively waits."""

    def __init__(self) -> None:
        self._buckets: dict[str, BucketInfo] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, category: str) -> asyncio.Lock:
        if category not in self._locks:
            self._locks[category] = asyncio.Lock()
        return self._locks[category]

    def update_from_response(self, path: str, response: httpx.Response) -> None:
        """Update bucket info from X-RateLimit-* headers."""
        headers = response.headers
        limit = headers.get("x-ratelimit-limit")
        remaining = headers.get("x-ratelimit-remaining")
        reset = headers.get("x-ratelimit-reset")
        if limit is None:
            return
        category = classify(path)
        self._buckets[category] = BucketInfo(
            limit=int(limit),
            remaining=int(remaining) if remaining else 0,
            reset=float(reset) if reset else 0.0,
        )

    async def wait_if_needed(self, path: str) -> None:
        """Sleep if the bucket for this path is exhausted."""
        category = classify(path)
        bucket = self._buckets.get(category)
        if bucket is None:
            return
        if bucket.remaining > 0:
            return
        now = time.time()
        delay = bucket.reset - now
        if delay > 0:
            async with self._lock_for(category):
                # Re-check after acquiring lock
                bucket = self._buckets.get(category)
                if bucket and bucket.remaining <= 0:
                    delay = bucket.reset - time.time()
                    if delay > 0:
                        await asyncio.sleep(delay)
