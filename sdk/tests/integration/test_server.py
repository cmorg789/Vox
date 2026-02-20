"""SDK integration tests for server endpoints."""

import pytest

from .conftest import register

pytestmark = pytest.mark.anyio


class TestServer:
    async def test_info(self, sdk):
        await register(sdk, "alice", "password123")
        info = await sdk.server.info()
        assert isinstance(info.name, str)
        assert info.member_count >= 1

    async def test_update(self, sdk):
        await register(sdk, "alice", "password123")
        updated = await sdk.server.update(name="My New Server")
        assert updated.name == "My New Server"

        info = await sdk.server.info()
        assert info.name == "My New Server"

    async def test_layout(self, sdk):
        await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("layout-test")
        cat = await sdk.channels.create_category("Layout Cat")

        layout = await sdk.server.layout()
        assert any(f.feed_id == feed.feed_id for f in layout.feeds)
        assert any(c.category_id == cat.category_id for c in layout.categories)
