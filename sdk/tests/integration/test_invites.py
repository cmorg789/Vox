"""SDK integration tests for invite endpoints."""

import pytest

from .conftest import make_sdk_client, register

pytestmark = pytest.mark.anyio


class TestInvites:
    async def test_crud(self, sdk):
        reg = await register(sdk, "alice", "password123")
        invite = await sdk.invites.create()
        assert invite.code
        assert invite.creator_id == reg.user_id
        assert invite.uses == 0

        preview = await sdk.invites.resolve(invite.code)
        assert preview.code == invite.code

        inv_list = await sdk.invites.list()
        assert any(i.code == invite.code for i in inv_list.items)

        await sdk.invites.delete(invite.code)

    async def test_join_via_invite(self, app, db):
        alice = await make_sdk_client(app)
        bob = await make_sdk_client(app)
        try:
            await register(alice, "alice", "password123")
            invite = await alice.invites.create()

            bob_reg = await register(bob, "bob", "password123")
            await bob.members.join(invite.code)

            members = await alice.members.list()
            assert any(m.user_id == bob_reg.user_id for m in members.items)
        finally:
            await alice.close()
            await bob.close()
