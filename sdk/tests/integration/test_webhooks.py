"""SDK integration tests for webhook endpoints."""

import pytest

from vox_sdk import VoxHTTPError

from .conftest import register

pytestmark = pytest.mark.anyio


class TestWebhooks:
    async def test_webhook_crud(self, sdk):
        await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("hooks")

        wh = await sdk.webhooks.create(feed.feed_id, "My Hook")
        assert wh.webhook_id > 0
        assert wh.name == "My Hook"
        assert wh.feed_id == feed.feed_id
        assert isinstance(wh.token, str) and len(wh.token) > 0

        wh_list = await sdk.webhooks.list(feed.feed_id)
        assert any(w.webhook_id == wh.webhook_id for w in wh_list.webhooks)

        got = await sdk.webhooks.get(wh.webhook_id)
        assert got.webhook_id == wh.webhook_id

        updated = await sdk.webhooks.update(wh.webhook_id, name="Renamed Hook")
        assert updated.name == "Renamed Hook"

        await sdk.webhooks.delete(wh.webhook_id)
        with pytest.raises(VoxHTTPError) as exc_info:
            await sdk.webhooks.get(wh.webhook_id)
        assert exc_info.value.status == 404

    async def test_webhook_execute(self, sdk):
        await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("hooks")

        wh = await sdk.webhooks.create(feed.feed_id, "Poster")
        await sdk.webhooks.execute(wh.webhook_id, wh.token, "webhook says hi")

        msgs = await sdk.messages.list(feed.feed_id)
        assert any(m.body == "webhook says hi" for m in msgs.messages)
