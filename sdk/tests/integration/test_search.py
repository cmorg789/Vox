"""SDK integration tests for search endpoints."""

import pytest

from .conftest import register

pytestmark = pytest.mark.anyio


class TestSearch:
    async def test_search_messages(self, sdk):
        await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("searchable")

        await sdk.messages.send(feed.feed_id, "the quick brown fox")
        await sdk.messages.send(feed.feed_id, "lazy dog sleeping")

        results = await sdk.search.messages(query="fox", feed_id=feed.feed_id)
        assert any("fox" in (r.body or "") for r in results.results)
