"""SDK integration tests for DM endpoints."""

import pytest

from .conftest import make_sdk_client, register

pytestmark = pytest.mark.anyio


class TestDMs:
    async def test_open_send_list_close(self, app, db):
        alice = await make_sdk_client(app)
        bob = await make_sdk_client(app)
        try:
            alice_reg = await register(alice, "alice", "password123")
            bob_reg = await register(bob, "bob", "password123")

            dm = await alice.dms.open(recipient_id=bob_reg.user_id)
            assert dm.dm_id > 0
            assert alice_reg.user_id in dm.participant_ids
            assert bob_reg.user_id in dm.participant_ids
            assert dm.is_group is False

            sent = await alice.dms.send_message(dm.dm_id, "hey bob")
            assert sent.msg_id > 0

            msgs = await alice.dms.list_messages(dm.dm_id)
            assert any(m.msg_id == sent.msg_id for m in msgs.messages)

            await alice.dms.close(dm.dm_id)
        finally:
            await alice.close()
            await bob.close()

    async def test_edit_delete_dm_message(self, app, db):
        alice = await make_sdk_client(app)
        bob = await make_sdk_client(app)
        try:
            await register(alice, "alice", "password123")
            bob_reg = await register(bob, "bob", "password123")

            dm = await alice.dms.open(recipient_id=bob_reg.user_id)
            sent = await alice.dms.send_message(dm.dm_id, "original dm")

            edited = await alice.dms.edit_message(dm.dm_id, sent.msg_id, "edited dm")
            assert edited.msg_id == sent.msg_id
            assert edited.edit_timestamp > 0

            await alice.dms.delete_message(dm.dm_id, sent.msg_id)
            msgs = await alice.dms.list_messages(dm.dm_id)
            assert not any(m.msg_id == sent.msg_id for m in msgs.messages)
        finally:
            await alice.close()
            await bob.close()

    async def test_dm_reactions(self, app, db):
        alice = await make_sdk_client(app)
        bob = await make_sdk_client(app)
        try:
            await register(alice, "alice", "password123")
            bob_reg = await register(bob, "bob", "password123")

            dm = await alice.dms.open(recipient_id=bob_reg.user_id)
            sent = await alice.dms.send_message(dm.dm_id, "react to this dm")

            # Add reaction and verify message is still intact
            await alice.dms.add_reaction(dm.dm_id, sent.msg_id, "\u2764\ufe0f")
            msgs = await alice.dms.list_messages(dm.dm_id)
            assert any(m.msg_id == sent.msg_id for m in msgs.messages)

            # Remove reaction should succeed without error
            await alice.dms.remove_reaction(dm.dm_id, sent.msg_id, "\u2764\ufe0f")

            # Removing a non-existent reaction should not error (idempotent)
            await alice.dms.remove_reaction(dm.dm_id, sent.msg_id, "\u2764\ufe0f")
        finally:
            await alice.close()
            await bob.close()

    async def test_list_dms(self, app, db):
        alice = await make_sdk_client(app)
        bob = await make_sdk_client(app)
        try:
            await register(alice, "alice", "password123")
            bob_reg = await register(bob, "bob", "password123")

            dm = await alice.dms.open(recipient_id=bob_reg.user_id)

            dm_list = await alice.dms.list()
            assert any(d.dm_id == dm.dm_id for d in dm_list.items)
        finally:
            await alice.close()
            await bob.close()

    async def test_group_dm(self, app, db):
        alice = await make_sdk_client(app)
        bob = await make_sdk_client(app)
        carol = await make_sdk_client(app)
        try:
            await register(alice, "alice", "password123")
            bob_reg = await register(bob, "bob", "password123")
            carol_reg = await register(carol, "carol", "password123")

            # Open 1:1 DM with Bob
            dm = await alice.dms.open(recipient_id=bob_reg.user_id)
            assert dm.is_group is False

            # Convert to group DM
            group = await alice.dms.convert_to_group(dm.dm_id)
            assert group.is_group is True

            # Add Carol
            await alice.dms.add_recipient(group.dm_id, carol_reg.user_id)
            dm_list = await alice.dms.list()
            group_dm = next(d for d in dm_list.items if d.dm_id == group.dm_id)
            assert carol_reg.user_id in group_dm.participant_ids

            # Remove Carol
            await alice.dms.remove_recipient(group.dm_id, carol_reg.user_id)
            dm_list = await alice.dms.list()
            group_dm = next(d for d in dm_list.items if d.dm_id == group.dm_id)
            assert carol_reg.user_id not in group_dm.participant_ids
        finally:
            await alice.close()
            await bob.close()
            await carol.close()
