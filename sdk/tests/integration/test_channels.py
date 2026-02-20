"""SDK integration tests for channel endpoints (feeds, categories, threads, rooms)."""

import pytest

from vox_sdk import VoxHTTPError

from .conftest import register

pytestmark = pytest.mark.anyio


class TestChannels:
    async def test_feed_crud(self, sdk):
        await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("general")
        assert feed.name == "general"
        assert feed.feed_id > 0
        assert feed.type == "text"
        assert isinstance(feed.position, int)
        assert isinstance(feed.permission_overrides, list)

        got = await sdk.channels.get_feed(feed.feed_id)
        assert got.feed_id == feed.feed_id

        updated = await sdk.channels.update_feed(feed.feed_id, name="renamed")
        assert updated.name == "renamed"

        await sdk.channels.delete_feed(feed.feed_id)
        with pytest.raises(VoxHTTPError) as exc_info:
            await sdk.channels.get_feed(feed.feed_id)
        assert exc_info.value.status == 404

    async def test_category_crud(self, sdk):
        await register(sdk, "alice", "password123")
        cat = await sdk.channels.create_category("Text Channels")
        assert cat.name == "Text Channels"

        cats = await sdk.channels.list_categories()
        assert any(c.category_id == cat.category_id for c in cats.items)

        updated = await sdk.channels.update_category(cat.category_id, name="Voice Channels")
        assert updated.name == "Voice Channels"

        await sdk.channels.delete_category(cat.category_id)

    async def test_thread_lifecycle(self, sdk):
        await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("general")
        msg = await sdk.messages.send(feed.feed_id, "parent message")

        thread = await sdk.channels.create_thread(feed.feed_id, msg.msg_id, "discussion")
        assert thread.name == "discussion"
        assert thread.parent_msg_id == msg.msg_id
        assert thread.archived is False
        assert thread.locked is False

        thread_msg = await sdk.messages.send_thread(feed.feed_id, thread.thread_id, "reply")
        assert thread_msg.msg_id > 0

        thread_msgs = await sdk.messages.list_thread(feed.feed_id, thread.thread_id)
        assert any(m.msg_id == thread_msg.msg_id for m in thread_msgs.messages)

        # Archive the thread
        archived = await sdk.channels.update_thread(thread.thread_id, archived=True)
        assert archived.archived is True

        # Delete the thread
        await sdk.channels.delete_thread(thread.thread_id)
        with pytest.raises(VoxHTTPError) as exc_info:
            await sdk.channels.get_thread(thread.thread_id)
        assert exc_info.value.status == 404

    async def test_room_crud(self, sdk):
        await register(sdk, "alice", "password123")
        room = await sdk.channels.create_room("Voice Lounge")
        assert room.name == "Voice Lounge"
        assert room.room_id > 0
        assert room.type == "voice"

        got = await sdk.channels.get_room(room.room_id)
        assert got.room_id == room.room_id

        updated = await sdk.channels.update_room(room.room_id, name="Renamed Room")
        assert updated.name == "Renamed Room"

        await sdk.channels.delete_room(room.room_id)
        with pytest.raises(VoxHTTPError) as exc_info:
            await sdk.channels.get_room(room.room_id)
        assert exc_info.value.status == 404

    async def test_list_threads(self, sdk):
        await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("general")
        msg = await sdk.messages.send(feed.feed_id, "parent for thread list")
        thread = await sdk.channels.create_thread(feed.feed_id, msg.msg_id, "listed thread")

        threads = await sdk.channels.list_threads(feed.feed_id)
        assert any(t.thread_id == thread.thread_id for t in threads.items)

    async def test_feed_subscription(self, sdk):
        await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("subscribable")

        # These should not error
        await sdk.channels.subscribe_feed(feed.feed_id)
        await sdk.channels.unsubscribe_feed(feed.feed_id)
