"""Tests for the HTTP client."""

import json

import httpx
import pytest

from vox_sdk.errors import VoxHTTPError, VoxNetworkError
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


@pytest.mark.asyncio
async def test_retry_429_uses_correct_delay(http_client, monkeypatch):
    """429 retry should sleep for retry_after_ms / 1000."""
    client, transport, calls = http_client
    import asyncio

    sleep_delays: list[float] = []
    real_sleep = asyncio.sleep

    async def recording_sleep(delay):
        sleep_delays.append(delay)
        # Don't actually sleep

    monkeypatch.setattr(asyncio, "sleep", recording_sleep)

    attempt = {"count": 0}

    class RetryTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            attempt["count"] += 1
            if attempt["count"] < 2:
                return httpx.Response(
                    429,
                    json={"error": {"code": "RATE_LIMITED", "message": "Slow down.", "retry_after_ms": 2500}},
                    headers={"x-ratelimit-limit": "5", "x-ratelimit-remaining": "0", "x-ratelimit-reset": "0"},
                )
            return httpx.Response(200, json={"ok": True})

    client._client = httpx.AsyncClient(base_url="https://vox.test", transport=RetryTransport())
    await client.get("/api/v1/server")

    assert len(sleep_delays) == 1
    assert sleep_delays[0] == 2.5  # 2500ms / 1000


@pytest.mark.asyncio
async def test_retry_429_header_fallback(http_client, monkeypatch):
    """429 with unparseable JSON body falls back to retry-after header."""
    client, transport, calls = http_client
    import asyncio

    sleep_delays: list[float] = []

    async def recording_sleep(delay):
        sleep_delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", recording_sleep)

    attempt = {"count": 0}

    class RetryTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            attempt["count"] += 1
            if attempt["count"] < 2:
                return httpx.Response(
                    429,
                    content=b"not json",
                    headers={
                        "content-type": "text/plain",
                        "retry-after": "2",
                        "x-ratelimit-limit": "5",
                        "x-ratelimit-remaining": "0",
                        "x-ratelimit-reset": "0",
                    },
                )
            return httpx.Response(200, json={"ok": True})

    client._client = httpx.AsyncClient(base_url="https://vox.test", transport=RetryTransport())
    await client.get("/api/v1/server")

    assert len(sleep_delays) == 1
    assert sleep_delays[0] == 2.0


@pytest.mark.asyncio
async def test_retry_exhaustion_raises(http_client, monkeypatch):
    """All 3 attempts return 429 → raises VoxHTTPError with status 429."""
    client, transport, calls = http_client
    import asyncio

    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _: real_sleep(0))

    class AlwaysRateLimited(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return httpx.Response(
                429,
                json={"error": {"code": "RATE_LIMITED", "message": "Slow down.", "retry_after_ms": 10}},
                headers={"x-ratelimit-limit": "5", "x-ratelimit-remaining": "0", "x-ratelimit-reset": "0"},
            )

    client._client = httpx.AsyncClient(base_url="https://vox.test", transport=AlwaysRateLimited())

    with pytest.raises(VoxHTTPError) as exc_info:
        await client.get("/api/v1/server")
    assert exc_info.value.status == 429


@pytest.mark.asyncio
async def test_put_sends_request(http_client):
    client, transport, calls = http_client
    transport.response = httpx.Response(204, json={})
    await client.put("/api/v1/feeds/1/pins/5")
    assert calls[0]["method"] == "PUT"
    assert calls[0]["path"] == "/api/v1/feeds/1/pins/5"


@pytest.mark.asyncio
async def test_patch_sends_request(http_client):
    client, transport, calls = http_client
    transport.response = httpx.Response(200, json={"ok": True})
    await client.patch("/api/v1/server", json={"name": "Updated"})
    assert calls[0]["method"] == "PATCH"
    assert calls[0]["body"] == {"name": "Updated"}


@pytest.mark.asyncio
async def test_delete_sends_request(http_client):
    client, transport, calls = http_client
    transport.response = httpx.Response(204, json={})
    await client.delete("/api/v1/feeds/1")
    assert calls[0]["method"] == "DELETE"
    assert calls[0]["path"] == "/api/v1/feeds/1"


@pytest.mark.asyncio
async def test_custom_headers_merged(http_client):
    client, transport, calls = http_client
    transport.response = httpx.Response(200, json={})
    await client.request("GET", "/api/v1/server", headers={"x-custom": "val"})
    assert calls[0]["headers"]["x-custom"] == "val"
    assert calls[0]["headers"]["authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_params_forwarded(http_client):
    client, transport, calls = http_client
    transport.response = httpx.Response(200, json={})
    await client.get("/api/v1/members", params={"limit": "10", "after": "5"})
    url = calls[0]["url"]
    assert "limit=10" in url
    assert "after=5" in url


@pytest.mark.asyncio
async def test_close_closes_inner_client(http_client):
    client, transport, calls = http_client
    assert not client._client.is_closed
    await client.close()
    assert client._client.is_closed


# --- 5xx retry tests ---


@pytest.mark.asyncio
async def test_retry_on_500(http_client, monkeypatch):
    """500 status should be retried with backoff."""
    client, transport, calls = http_client
    import asyncio

    sleep_delays: list[float] = []

    async def recording_sleep(delay):
        sleep_delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", recording_sleep)

    attempt = {"count": 0}

    class RetryTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            attempt["count"] += 1
            if attempt["count"] < 3:
                return httpx.Response(500, text="Internal Server Error")
            return httpx.Response(200, json={"ok": True})

    client._client = httpx.AsyncClient(base_url="https://vox.test", transport=RetryTransport())
    response = await client.get("/api/v1/server")
    assert response.status_code == 200
    assert attempt["count"] == 3
    # 2 retries: delay = 1*2^0=1, 1*2^1=2
    assert len(sleep_delays) == 2
    assert sleep_delays[0] == 1.0
    assert sleep_delays[1] == 2.0


@pytest.mark.asyncio
async def test_retry_on_503_exhaustion(http_client, monkeypatch):
    """All 3 attempts return 503 → raises VoxHTTPError."""
    client, transport, calls = http_client
    import asyncio

    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _: real_sleep(0))

    class AlwaysUnavailable(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return httpx.Response(503, text="Service Unavailable")

    client._client = httpx.AsyncClient(base_url="https://vox.test", transport=AlwaysUnavailable())
    with pytest.raises(VoxHTTPError) as exc_info:
        await client.get("/api/v1/server")
    assert exc_info.value.status == 503


# --- Transport error wrapping ---


@pytest.mark.asyncio
async def test_transport_error_wrapped():
    """Transport errors (connect timeout, etc.) are wrapped in VoxNetworkError."""

    class FailingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ConnectTimeout("Connection timed out")

    client = HTTPClient("https://vox.test", token="test-token")
    client._client = httpx.AsyncClient(base_url="https://vox.test", transport=FailingTransport())

    with pytest.raises(VoxNetworkError) as exc_info:
        await client.get("/api/v1/server")
    assert "Connection timed out" in str(exc_info.value)
    assert exc_info.value.__cause__ is not None
    await client.close()


@pytest.mark.asyncio
async def test_connect_error_wrapped():
    """Connection refused is wrapped in VoxNetworkError."""

    class RefusingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ConnectError("Connection refused")

    client = HTTPClient("https://vox.test", token="test-token")
    client._client = httpx.AsyncClient(base_url="https://vox.test", transport=RefusingTransport())

    with pytest.raises(VoxNetworkError):
        await client.get("/api/v1/server")
    await client.close()
