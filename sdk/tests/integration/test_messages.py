"""SDK integration tests for message endpoints."""

import pytest

from vox_sdk import VoxHTTPError

from .conftest import register

pytestmark = pytest.mark.anyio


class TestMessages:
    async def test_send_list_get(self, sdk):
        reg = await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("general")
        sent = await sdk.messages.send(feed.feed_id, "hello world")
        assert sent.msg_id > 0
        assert sent.timestamp > 0

        msgs = await sdk.messages.list(feed.feed_id)
        assert any(m.msg_id == sent.msg_id for m in msgs.messages)

        got = await sdk.messages.get(feed.feed_id, sent.msg_id)
        assert got.body == "hello world"
        assert got.author_id == reg.user_id
        assert got.feed_id == feed.feed_id

    async def test_edit_message(self, sdk):
        await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("general")
        sent = await sdk.messages.send(feed.feed_id, "original")

        edited = await sdk.messages.edit(feed.feed_id, sent.msg_id, "edited")
        assert edited.msg_id == sent.msg_id
        assert edited.edit_timestamp > 0

        got = await sdk.messages.get(feed.feed_id, sent.msg_id)
        assert got.body == "edited"

    async def test_delete_message(self, sdk):
        await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("general")
        sent = await sdk.messages.send(feed.feed_id, "to delete")

        await sdk.messages.delete(feed.feed_id, sent.msg_id)
        with pytest.raises(VoxHTTPError) as exc_info:
            await sdk.messages.get(feed.feed_id, sent.msg_id)
        assert exc_info.value.status == 404

    async def test_bulk_delete(self, sdk):
        await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("general")
        ids = []
        for i in range(3):
            m = await sdk.messages.send(feed.feed_id, f"msg {i}")
            ids.append(m.msg_id)

        await sdk.messages.bulk_delete(feed.feed_id, ids)
        msgs = await sdk.messages.list(feed.feed_id)
        remaining_ids = {m.msg_id for m in msgs.messages}
        for mid in ids:
            assert mid not in remaining_ids

    async def test_reactions(self, sdk):
        reg = await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("general")
        sent = await sdk.messages.send(feed.feed_id, "react to me")

        await sdk.messages.add_reaction(feed.feed_id, sent.msg_id, "\U0001f44d")
        reactions = await sdk.messages.list_reactions(feed.feed_id, sent.msg_id)
        assert len(reactions.reactions) == 1
        assert reactions.reactions[0].emoji == "\U0001f44d"
        assert reg.user_id in reactions.reactions[0].user_ids

        await sdk.messages.remove_reaction(feed.feed_id, sent.msg_id, "\U0001f44d")
        reactions = await sdk.messages.list_reactions(feed.feed_id, sent.msg_id)
        assert len(reactions.reactions) == 0

    async def test_pins(self, sdk):
        await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("general")
        sent = await sdk.messages.send(feed.feed_id, "pin me")

        await sdk.messages.pin(feed.feed_id, sent.msg_id)
        pins = await sdk.messages.list_pins(feed.feed_id)
        assert any(m.msg_id == sent.msg_id for m in pins.messages)

        await sdk.messages.unpin(feed.feed_id, sent.msg_id)
        pins = await sdk.messages.list_pins(feed.feed_id)
        assert not any(m.msg_id == sent.msg_id for m in pins.messages)

    async def test_message_pagination(self, sdk):
        await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("general")

        sent_ids = []
        for i in range(5):
            m = await sdk.messages.send(feed.feed_id, f"page msg {i}")
            sent_ids.append(m.msg_id)

        # First page: latest 2
        page1 = await sdk.messages.list(feed.feed_id, limit=2)
        assert len(page1.messages) == 2
        page1_ids = {m.msg_id for m in page1.messages}

        # Second page: before the oldest message in page 1
        oldest_in_page1 = min(m.msg_id for m in page1.messages)
        page2 = await sdk.messages.list(feed.feed_id, limit=2, before=oldest_in_page1)
        assert len(page2.messages) == 2
        page2_ids = {m.msg_id for m in page2.messages}

        # No overlap
        assert page1_ids.isdisjoint(page2_ids)
