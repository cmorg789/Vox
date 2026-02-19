"""Tests for cursor-based pagination."""

import json

import httpx
import pytest

from vox_sdk.http import HTTPClient
from vox_sdk.models.members import MemberResponse
from vox_sdk.pagination import PaginatedIterator


@pytest.mark.asyncio
async def test_single_page():
    """Pagination with a single page (no cursor)."""
    page_data = {
        "items": [
            {"user_id": 1, "display_name": "Alice", "role_ids": []},
            {"user_id": 2, "display_name": "Bob", "role_ids": []},
        ],
        "cursor": None,
    }

    class MockTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return httpx.Response(200, json=page_data)

    client = HTTPClient("https://vox.test", token="t")
    client._client = httpx.AsyncClient(base_url="https://vox.test", transport=MockTransport())

    items = await PaginatedIterator(
        client, "/api/v1/members", MemberResponse
    ).flatten()

    assert len(items) == 2
    assert items[0].user_id == 1
    assert items[1].display_name == "Bob"
    await client.close()


@pytest.mark.asyncio
async def test_multi_page():
    """Pagination across two pages."""
    call_count = {"n": 0}

    class MockTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            call_count["n"] += 1
            url = str(request.url)
            if "cursor=page2" in url:
                return httpx.Response(200, json={
                    "items": [{"user_id": 3, "display_name": "Charlie", "role_ids": []}],
                    "cursor": None,
                })
            return httpx.Response(200, json={
                "items": [
                    {"user_id": 1, "display_name": "Alice", "role_ids": []},
                    {"user_id": 2, "display_name": "Bob", "role_ids": []},
                ],
                "cursor": "page2",
            })

    client = HTTPClient("https://vox.test", token="t")
    client._client = httpx.AsyncClient(base_url="https://vox.test", transport=MockTransport())

    items = await PaginatedIterator(
        client, "/api/v1/members", MemberResponse
    ).flatten()

    assert len(items) == 3
    assert call_count["n"] == 2
    await client.close()


@pytest.mark.asyncio
async def test_empty_result():
    """Pagination with zero results."""

    class MockTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return httpx.Response(200, json={"items": [], "cursor": None})

    client = HTTPClient("https://vox.test", token="t")
    client._client = httpx.AsyncClient(base_url="https://vox.test", transport=MockTransport())

    items = await PaginatedIterator(
        client, "/api/v1/members", MemberResponse
    ).flatten()

    assert items == []
    await client.close()
