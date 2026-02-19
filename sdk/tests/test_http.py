"""Tests for the HTTP client."""

import json

import httpx
import pytest

from vox_sdk.errors import VoxHTTPError
from vox_sdk.http import HTTPClient


@pytest.mark.asyncio
async def test_get_adds_auth_header(http_client):
    client, transport, calls = http_client
    transport.response = httpx.Response(200, json={"ok": True})

    response = await client.get("/api/v1/server")
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["headers"]["authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_post_sends_json(http_client):
    client, transport, calls = http_client
    transport.response = httpx.Response(201, json={"user_id": 1, "token": "abc"})

    response = await client.post(
        "/api/v1/auth/register",
        json={"username": "test", "password": "pass"},
    )
    assert response.status_code == 201
    assert calls[0]["body"] == {"username": "test", "password": "pass"}


@pytest.mark.asyncio
async def test_raises_on_4xx(http_client):
    client, transport, calls = http_client
    transport.response = httpx.Response(
        404,
        json={"error": {"code": "NOT_FOUND", "message": "Not found."}},
    )

    with pytest.raises(VoxHTTPError) as exc_info:
        await client.get("/api/v1/users/999")

    assert exc_info.value.status == 404
    assert exc_info.value.code.value == "NOT_FOUND"


@pytest.mark.asyncio
async def test_retry_on_429(http_client, monkeypatch):
    client, transport, calls = http_client
    import asyncio

    # Speed up the test by making sleep instant
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _: real_sleep(0))

    attempt = {"count": 0}
    original_response = httpx.Response(
        429,
        json={"error": {"code": "RATE_LIMITED", "message": "Slow down.", "retry_after_ms": 10}},
        headers={"retry-after": "1", "x-ratelimit-limit": "5", "x-ratelimit-remaining": "0", "x-ratelimit-reset": "0"},
    )
    success_response = httpx.Response(200, json={"ok": True})

    class RetryTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            attempt["count"] += 1
            if attempt["count"] < 3:
                return original_response
            return success_response

    client._client = httpx.AsyncClient(
        base_url="https://vox.test",
        transport=RetryTransport(),
    )

    response = await client.get("/api/v1/server")
    assert response.status_code == 200
    assert attempt["count"] == 3  # 2 retries + 1 success


@pytest.mark.asyncio
async def test_no_auth_header_when_no_token():
    client = HTTPClient("https://vox.test", token=None)
    headers = client._headers()
    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_token_setter():
    client = HTTPClient("https://vox.test")
    assert client.token is None
    client.token = "new-token"
    assert client.token == "new-token"
    headers = client._headers()
    assert headers["Authorization"] == "Bearer new-token"
    await client.close()
