"""SDK integration tests for role endpoints."""

import pytest

from .conftest import make_sdk_client, register

pytestmark = pytest.mark.anyio


class TestRoles:
    async def test_crud(self, sdk):
        await register(sdk, "alice", "password123")
        role = await sdk.roles.create("Moderator", color=0xFF0000)
        assert role.name == "Moderator"
        assert role.color == 0xFF0000
        assert isinstance(role.permissions, int)

        roles = await sdk.roles.list()
        assert any(r.role_id == role.role_id for r in roles.items)

        updated = await sdk.roles.update(role.role_id, name="Admin")
        assert updated.name == "Admin"

        await sdk.roles.delete(role.role_id)

    async def test_assign_revoke(self, sdk):
        reg = await register(sdk, "alice", "password123")
        role = await sdk.roles.create("Mod")

        await sdk.roles.assign(reg.user_id, role.role_id)
        member = await sdk.members.get(reg.user_id)
        assert role.role_id in member.role_ids

        await sdk.roles.revoke(reg.user_id, role.role_id)
        member = await sdk.members.get(reg.user_id)
        assert role.role_id not in member.role_ids

    async def test_list_members_by_role(self, app, db):
        admin = await make_sdk_client(app)
        target = await make_sdk_client(app)
        try:
            await register(admin, "admin", "password123")
            target_reg = await register(target, "target", "password123")

            role = await admin.roles.create("Testers")
            await admin.roles.assign(target_reg.user_id, role.role_id)

            members = await admin.roles.list_members(role.role_id)
            assert any(m.user_id == target_reg.user_id for m in members.items)
        finally:
            await admin.close()
            await target.close()

    async def test_feed_permission_override(self, sdk):
        await register(sdk, "alice", "password123")
        feed = await sdk.channels.create_feed("restricted")
        role = await sdk.roles.create("Viewers")

        # Set a permission override for the role on this feed
        await sdk.roles.set_feed_override(
            feed.feed_id, "role", role.role_id, allow=1, deny=0
        )

        # Verify the override appears on the feed
        got = await sdk.channels.get_feed(feed.feed_id)
        assert any(
            o.target_type == "role" and o.target_id == role.role_id
            for o in got.permission_overrides
        )

        # Delete the override
        await sdk.roles.delete_feed_override(feed.feed_id, "role", role.role_id)

        got = await sdk.channels.get_feed(feed.feed_id)
        assert not any(
            o.target_type == "role" and o.target_id == role.role_id
            for o in got.permission_overrides
        )
