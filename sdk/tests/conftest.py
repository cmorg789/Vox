"""Shared test fixtures for SDK tests."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from vox_sdk.http import HTTPClient


@pytest.fixture
def mock_transport():
    """Returns an httpx mock transport that records requests."""
    calls: list[dict[str, Any]] = []
    default_response = httpx.Response(200, json={})

    class RecordingTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.response = default_response

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = None
            if request.content:
                try:
                    body = json.loads(request.content)
                except Exception:
                    body = request.content
            calls.append({
                "method": request.method,
                "url": str(request.url),
                "path": request.url.path,
                "headers": dict(request.headers),
                "body": body,
            })
            return self.response

    transport = RecordingTransport()
    return transport, calls


@pytest.fixture
def http_client(mock_transport):
    """HTTPClient with a mock transport."""
    transport, calls = mock_transport
    client = HTTPClient("https://vox.test", token="test-token")
    # Replace the inner httpx client with one using our mock transport
    client._client = httpx.AsyncClient(
        base_url="https://vox.test",
        transport=transport,
    )
    return client, transport, calls
