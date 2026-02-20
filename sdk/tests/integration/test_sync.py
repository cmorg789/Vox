"""SDK integration tests for sync endpoints."""

import time

import pytest

from .conftest import register

pytestmark = pytest.mark.anyio


class TestSync:
    async def test_sync_returns_events(self, sdk):
        await register(sdk, "alice", "password123")

        # Record timestamp before creating events
        before_ts = int(time.time() * 1000)

        feed = await sdk.channels.create_feed("sync-test")

        # Sync for feed events since before our action
        result = await sdk.sync.sync(
            since_timestamp=before_ts, categories=["feeds"]
        )
        assert result.server_timestamp > 0
        assert any(
            e.type == "feed_create" for e in result.events
        )
