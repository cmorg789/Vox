"""Integration tests for gateway/notify.py notification dispatch pipeline."""

from unittest.mock import AsyncMock, patch

import pytest

from vox.db.engine import get_session_factory
from vox.db.models import DM, Feed, Message, Role, User, dm_participants, feed_subscribers, role_members
from vox.gateway.notify import notify_for_message, notify_for_reaction

pytestmark = pytest.mark.asyncio


async def _setup_user(db, username, user_id):
    """Insert a user row directly."""
    from datetime import datetime, timezone
    user = User(id=user_id, username=username, display_name=username, federated=False, created_at=datetime.now(timezone.utc))
    db.add(user)
    await db.flush()
    return user


async def _setup_feed(db, feed_id=1, name="general"):
    feed = Feed(id=feed_id, name=name, type="text", position=0)
    db.add(feed)
    await db.flush()
    return feed


async def _setup_message(db, msg_id, feed_id=None, dm_id=None, author_id=1, body="hello", reply_to=None):
    import time
    msg = Message(
        id=msg_id, feed_id=feed_id, dm_id=dm_id, author_id=author_id,
        body=body, timestamp=int(time.time() * 1000), reply_to=reply_to,
    )
    db.add(msg)
    await db.flush()
    return msg


async def test_notify_mention_everyone_dm(client):
    """@everyone mention in DM notifies all other DM participants."""
    factory = get_session_factory()
    dispatched = []

    async def mock_dispatch(event, user_ids=None):
        dispatched.append((event, user_ids))

    async with factory() as db:
        alice = await _setup_user(db, "alice", 1)
        bob = await _setup_user(db, "bob", 2)
        carol = await _setup_user(db, "carol", 3)

        # Create DM with 3 participants
        from datetime import datetime, timezone
        dm = DM(id=1, is_group=True, created_at=datetime.now(timezone.utc))
        db.add(dm)
        await db.flush()
        await db.execute(dm_participants.insert().values([
            {"dm_id": 1, "user_id": 1},
            {"dm_id": 1, "user_id": 2},
            {"dm_id": 1, "user_id": 3},
        ]))
        await db.flush()

        msg = await _setup_message(db, msg_id=100, dm_id=1, author_id=1, body="hey @everyone")
        await db.commit()

        with patch("vox.gateway.notify.dispatch", mock_dispatch):
            await notify_for_message(
                db, msg_id=100, feed_id=None, thread_id=None, dm_id=1,
                author_id=1, body="hey @everyone", reply_to=None,
                mentions=[0],  # 0 = @everyone
            )

    # Bob and Carol should get mention notifications (not Alice the author)
    notified_users = {call[1][0] for call in dispatched}
    assert notified_users == {2, 3}
    for event, user_ids in dispatched:
        assert event["type"] == "notification_create"
        assert event["d"]["type"] == "mention"
        assert event["d"]["actor_id"] == 1


async def test_notify_individual_mention(client):
    """Specific user mention sends targeted notification."""
    factory = get_session_factory()
    dispatched = []

    async def mock_dispatch(event, user_ids=None):
        dispatched.append((event, user_ids))

    async with factory() as db:
        await _setup_user(db, "alice", 1)
        await _setup_user(db, "bob", 2)
        await _setup_feed(db)
        await _setup_message(db, msg_id=200, feed_id=1, author_id=1, body="hey @bob")
        await db.commit()

        with patch("vox.gateway.notify.dispatch", mock_dispatch):
            await notify_for_message(
                db, msg_id=200, feed_id=1, thread_id=None, dm_id=None,
                author_id=1, body="hey @bob", reply_to=None,
                mentions=[2],
            )

    assert len(dispatched) == 1
    event, user_ids = dispatched[0]
    assert event["d"]["type"] == "mention"
    assert user_ids == [2]


async def test_notify_reply_to_author(client):
    """Replying to a message notifies the original author."""
    factory = get_session_factory()
    dispatched = []

    async def mock_dispatch(event, user_ids=None):
        dispatched.append((event, user_ids))

    async with factory() as db:
        await _setup_user(db, "alice", 1)
        await _setup_user(db, "bob", 2)
        await _setup_feed(db)
        original = await _setup_message(db, msg_id=300, feed_id=1, author_id=1, body="original msg")
        reply = await _setup_message(db, msg_id=301, feed_id=1, author_id=2, body="replying", reply_to=300)
        await db.commit()

        with patch("vox.gateway.notify.dispatch", mock_dispatch):
            await notify_for_message(
                db, msg_id=301, feed_id=1, thread_id=None, dm_id=None,
                author_id=2, body="replying", reply_to=300,
                mentions=None,
            )

    assert len(dispatched) == 1
    event, user_ids = dispatched[0]
    assert event["d"]["type"] == "reply"
    assert user_ids == [1]
    assert event["d"]["actor_id"] == 2


async def test_notify_feed_subscribers(client):
    """Feed subscribers get message notification (excluding author)."""
    factory = get_session_factory()
    dispatched = []

    async def mock_dispatch(event, user_ids=None):
        dispatched.append((event, user_ids))

    async with factory() as db:
        await _setup_user(db, "alice", 1)
        await _setup_user(db, "bob", 2)
        await _setup_user(db, "carol", 3)
        await _setup_feed(db)

        # Bob and Carol subscribe to the feed, Alice is the author
        await db.execute(feed_subscribers.insert().values([
            {"feed_id": 1, "user_id": 2},
            {"feed_id": 1, "user_id": 3},
        ]))
        await _setup_message(db, msg_id=400, feed_id=1, author_id=1, body="new post")
        await db.commit()

        with patch("vox.gateway.notify.dispatch", mock_dispatch):
            await notify_for_message(
                db, msg_id=400, feed_id=1, thread_id=None, dm_id=None,
                author_id=1, body="new post", reply_to=None,
                mentions=None,
            )

    notified_users = {call[1][0] for call in dispatched}
    assert notified_users == {2, 3}
    for event, _ in dispatched:
        assert event["d"]["type"] == "message"


async def test_notify_reaction(client):
    """Reacting to someone's message notifies the message author."""
    factory = get_session_factory()
    dispatched = []

    async def mock_dispatch(event, user_ids=None):
        dispatched.append((event, user_ids))

    async with factory() as db:
        await _setup_user(db, "alice", 1)
        await _setup_user(db, "bob", 2)
        await _setup_feed(db)
        await _setup_message(db, msg_id=500, feed_id=1, author_id=1, body="nice post")
        await db.commit()

        with patch("vox.gateway.notify.dispatch", mock_dispatch):
            await notify_for_reaction(db, msg_id=500, reactor_id=2, emoji="thumbsup")

    assert len(dispatched) == 1
    event, user_ids = dispatched[0]
    assert event["d"]["type"] == "reaction"
    assert user_ids == [1]
    assert event["d"]["body_preview"] == "thumbsup"
    assert event["d"]["actor_id"] == 2


async def test_notify_self_react_ignored(client):
    """Reacting to your own message produces no notification."""
    factory = get_session_factory()
    dispatched = []

    async def mock_dispatch(event, user_ids=None):
        dispatched.append((event, user_ids))

    async with factory() as db:
        await _setup_user(db, "alice", 1)
        await _setup_feed(db)
        await _setup_message(db, msg_id=600, feed_id=1, author_id=1, body="my post")
        await db.commit()

        with patch("vox.gateway.notify.dispatch", mock_dispatch):
            await notify_for_reaction(db, msg_id=600, reactor_id=1, emoji="thumbsup")

    assert len(dispatched) == 0


async def test_notify_reply_to_self_ignored(client):
    """Replying to your own message does not send a reply notification."""
    factory = get_session_factory()
    dispatched = []

    async def mock_dispatch(event, user_ids=None):
        dispatched.append((event, user_ids))

    async with factory() as db:
        await _setup_user(db, "alice", 1)
        await _setup_feed(db)
        await _setup_message(db, msg_id=700, feed_id=1, author_id=1, body="original")
        await _setup_message(db, msg_id=701, feed_id=1, author_id=1, body="self reply", reply_to=700)
        await db.commit()

        with patch("vox.gateway.notify.dispatch", mock_dispatch):
            await notify_for_message(
                db, msg_id=701, feed_id=1, thread_id=None, dm_id=None,
                author_id=1, body="self reply", reply_to=700,
                mentions=None,
            )

    assert len(dispatched) == 0


async def test_notify_subscriber_not_duplicated_with_mention(client):
    """A subscriber who is also mentioned only gets a mention notification, not both."""
    factory = get_session_factory()
    dispatched = []

    async def mock_dispatch(event, user_ids=None):
        dispatched.append((event, user_ids))

    async with factory() as db:
        await _setup_user(db, "alice", 1)
        await _setup_user(db, "bob", 2)
        await _setup_feed(db)

        # Bob subscribes to the feed
        await db.execute(feed_subscribers.insert().values({"feed_id": 1, "user_id": 2}))
        await _setup_message(db, msg_id=800, feed_id=1, author_id=1, body="hey @bob")
        await db.commit()

        with patch("vox.gateway.notify.dispatch", mock_dispatch):
            await notify_for_message(
                db, msg_id=800, feed_id=1, thread_id=None, dm_id=None,
                author_id=1, body="hey @bob", reply_to=None,
                mentions=[2],
            )

    # Bob should only get ONE notification (mention), not both mention+subscriber
    assert len(dispatched) == 1
    assert dispatched[0][0]["d"]["type"] == "mention"
