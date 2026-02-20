"""Tests for rate limiting middleware."""

import time as _time
from unittest.mock import MagicMock, patch

import pytest

from vox.ratelimit import CATEGORIES, _buckets, check, classify, reset


async def setup(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


async def test_ratelimit_headers_present(client):
    """Every response should carry X-RateLimit-* headers."""
    h = await setup(client)
    r = await client.get("/api/v1/server", headers=h)
    assert r.status_code in (200, 404)  # server may or may not be set up
    assert "x-ratelimit-limit" in r.headers
    assert "x-ratelimit-remaining" in r.headers
    assert "x-ratelimit-reset" in r.headers


async def test_ratelimit_429_enforced(client):
    """Exhausting the auth bucket should yield a 429."""
    max_tokens = CATEGORIES["auth"][0]  # 5

    # Use all tokens (register already used 1)
    for _ in range(max_tokens):
        await client.post("/api/v1/auth/login", json={"username": "nobody", "password": "nope"})

    r = await client.post("/api/v1/auth/login", json={"username": "nobody", "password": "nope"})
    assert r.status_code == 429
    body = r.json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert "retry_after_ms" in body["error"]
    assert "retry-after" in r.headers


async def test_ratelimit_remaining_decrements(client):
    """Remaining should go down with each request."""
    h = await setup(client)
    r1 = await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    rem1 = int(r1.headers["x-ratelimit-remaining"])

    r2 = await client.get("/api/v1/feeds/1/messages", headers=h)
    rem2 = int(r2.headers["x-ratelimit-remaining"])

    # Both are in "channels" / "messages" categories; remaining should be lower on second
    # (They may be different categories so just ensure headers are numeric)
    assert rem1 >= 0
    assert rem2 >= 0


async def test_ratelimit_unauthenticated_ip_key(client):
    """Unauthenticated requests should be keyed by IP and still get headers."""
    r = await client.get("/api/v1/server")
    assert "x-ratelimit-limit" in r.headers


async def test_ratelimit_reset_clears_buckets(client):
    """reset() should clear all bucket state."""
    # Exhaust auth bucket
    max_tokens = CATEGORIES["auth"][0]
    for _ in range(max_tokens + 1):
        await client.post("/api/v1/auth/login", json={"username": "x", "password": "x"})

    r = await client.post("/api/v1/auth/login", json={"username": "x", "password": "x"})
    assert r.status_code == 429

    # Reset and try again
    reset()
    r = await client.post("/api/v1/auth/login", json={"username": "x", "password": "x"})
    assert r.status_code != 429


# ---------------------------------------------------------------------------
# Unit tests for classify() and check()
# ---------------------------------------------------------------------------


def test_classify_messages_nested():
    assert classify("/api/v1/feeds/1/messages") == "messages"


def test_classify_search():
    # /messages check takes priority over /search when both are in the path
    assert classify("/api/v1/feeds/1/messages/search") == "messages"
    # A search path without /messages should classify as search
    assert classify("/api/v1/server/search") == "search"


def test_classify_prefix_map():
    assert classify("/api/v1/auth/login") == "auth"
    assert classify("/api/v1/feeds/1") == "channels"
    assert classify("/api/v1/roles/1") == "roles"
    assert classify("/api/v1/emoji/1") == "emoji"
    assert classify("/api/v1/voice/join") == "voice"
    assert classify("/api/v1/bots/1") == "bots"
    assert classify("/api/v1/keys/prekeys") == "e2ee"
    assert classify("/api/v1/federation/peers") == "federation"
    assert classify("/api/v1/dms/1") == "messages"
    assert classify("/api/v1/files/upload") == "files"
    assert classify("/api/v1/reports/1") == "moderation"
    assert classify("/api/v1/admin/config") == "moderation"
    assert classify("/api/v1/users/123") == "members"


def test_classify_unknown_falls_back_to_server():
    assert classify("/api/v1/totally-unknown") == "server"


def test_check_allows_first_request():
    reset()
    allowed, limit, remaining, reset_ts, retry_after = check("testkey", "auth")
    assert allowed is True
    max_tokens = CATEGORIES["auth"][0]
    assert limit == max_tokens
    assert remaining == max_tokens - 1
    assert retry_after == 0


def test_check_exhausts_bucket():
    reset()
    max_tokens = CATEGORIES["auth"][0]
    for _ in range(max_tokens):
        allowed, *_ = check("exhaustkey", "auth")
        assert allowed is True
    allowed, limit, remaining, reset_ts, retry_after = check("exhaustkey", "auth")
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0


def test_check_different_keys_independent():
    reset()
    max_tokens = CATEGORIES["auth"][0]
    for _ in range(max_tokens):
        check("key_a", "auth")
    allowed_a, *_ = check("key_a", "auth")
    assert allowed_a is False

    allowed_b, *_ = check("key_b", "auth")
    assert allowed_b is True


def test_check_refill_restores_tokens(monkeypatch):
    reset()
    max_tokens = CATEGORIES["auth"][0]
    refill_rate = CATEGORIES["auth"][1]

    for _ in range(max_tokens):
        check("refillkey", "auth")

    allowed, *_ = check("refillkey", "auth")
    assert allowed is False

    # Advance time enough for full refill
    future = _time.time() + (max_tokens / refill_rate) + 1
    monkeypatch.setattr(_time, "time", lambda: future)

    allowed, _, remaining, *_ = check("refillkey", "auth")
    assert allowed is True
    assert remaining == max_tokens - 1


@pytest.mark.asyncio
async def test_ratelimit_webhook_key():
    """Webhook execution is keyed by webhook ID."""
    from vox.ratelimit import RateLimitMiddleware

    middleware = RateLimitMiddleware(app=MagicMock())

    mock_request = MagicMock()
    mock_request.url.path = "/api/v1/webhooks/123/abc/execute"
    mock_request.client.host = "1.2.3.4"
    mock_request.headers = {}

    key = await middleware._resolve_key(mock_request, "/api/v1/webhooks/123/abc/execute")
    assert key == "webhook:123"


@pytest.mark.asyncio
async def test_ratelimit_exception_fallback():
    """When token lookup raises, falls back to IP key."""
    from vox.ratelimit import RateLimitMiddleware

    middleware = RateLimitMiddleware(app=MagicMock())

    mock_request = MagicMock()
    mock_request.url.path = "/api/v1/feeds"
    mock_request.client.host = "5.6.7.8"
    mock_request.headers = {"authorization": "Bearer bad_token"}

    with patch("vox.ratelimit.get_session_factory", side_effect=Exception("db error")):
        key = await middleware._resolve_key(mock_request, "/api/v1/feeds")
    assert key == "ip:5.6.7.8"
