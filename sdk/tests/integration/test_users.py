"""SDK integration tests for user endpoints."""

import pytest

from .conftest import make_sdk_client, register

pytestmark = pytest.mark.anyio


class TestUsers:
    async def test_get_profile(self, sdk):
        reg = await register(sdk, "alice", "password123")
        user = await sdk.users.get(reg.user_id)
        assert user.user_id == reg.user_id
        assert user.username == "alice"
        assert isinstance(user.created_at, int)

    async def test_update_profile(self, sdk):
        reg = await register(sdk, "alice", "password123")
        updated = await sdk.users.update_profile(
            reg.user_id, display_name="Alice W", bio="hello world"
        )
        assert updated.display_name == "Alice W"
        assert updated.bio == "hello world"

        user = await sdk.users.get(reg.user_id)
        assert user.display_name == "Alice W"
        assert user.bio == "hello world"

    async def test_friends_lifecycle(self, app, db):
        alice = await make_sdk_client(app)
        bob = await make_sdk_client(app)
        try:
            alice_reg = await register(alice, "alice", "password123")
            bob_reg = await register(bob, "bob", "password123")

            # Alice sends friend request to Bob
            await alice.users.add_friend(alice_reg.user_id, bob_reg.user_id)

            # Bob accepts
            await bob.users.accept_friend(bob_reg.user_id, alice_reg.user_id)

            # Both should see each other in friends list
            alice_friends = await alice.users.list_friends(alice_reg.user_id)
            assert any(f.user_id == bob_reg.user_id for f in alice_friends.items)

            # Remove friend
            await alice.users.remove_friend(alice_reg.user_id, bob_reg.user_id)
            alice_friends = await alice.users.list_friends(alice_reg.user_id)
            assert not any(f.user_id == bob_reg.user_id for f in alice_friends.items)
        finally:
            await alice.close()
            await bob.close()

    async def test_block_unblock(self, app, db):
        alice = await make_sdk_client(app)
        bob = await make_sdk_client(app)
        try:
            alice_reg = await register(alice, "alice", "password123")
            bob_reg = await register(bob, "bob", "password123")

            await alice.users.block(alice_reg.user_id, bob_reg.user_id)

            blocks = await alice.users.list_blocks(alice_reg.user_id)
            assert bob_reg.user_id in blocks.blocked_user_ids

            await alice.users.unblock(alice_reg.user_id, bob_reg.user_id)
            blocks = await alice.users.list_blocks(alice_reg.user_id)
            assert bob_reg.user_id not in blocks.blocked_user_ids
        finally:
            await alice.close()
            await bob.close()
