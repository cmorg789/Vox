"""SDK integration tests for member endpoints."""

import pytest

from .conftest import make_sdk_client, register

pytestmark = pytest.mark.anyio


class TestMembers:
    async def test_list_and_get(self, sdk):
        reg = await register(sdk, "alice", "password123")
        members = await sdk.members.list()
        assert any(m.user_id == reg.user_id for m in members.items)

        member = await sdk.members.get(reg.user_id)
        assert member.user_id == reg.user_id
        assert member.display_name is None or isinstance(member.display_name, str)
        assert isinstance(member.role_ids, list)

    async def test_nickname(self, sdk):
        reg = await register(sdk, "alice", "password123")
        updated = await sdk.members.update(reg.user_id, nickname="Ali")
        assert updated.nickname == "Ali"

        member = await sdk.members.get(reg.user_id)
        assert member.nickname == "Ali"

    async def test_ban_unban(self, app, db):
        admin = await make_sdk_client(app)
        target = await make_sdk_client(app)
        try:
            await register(admin, "admin", "password123")
            target_reg = await register(target, "target", "password123")

            await admin.members.ban(target_reg.user_id, reason="testing")
            bans = await admin.members.list_bans()
            assert any(b.user_id == target_reg.user_id for b in bans.items)

            await admin.members.unban(target_reg.user_id)
            bans = await admin.members.list_bans()
            assert not any(b.user_id == target_reg.user_id for b in bans.items)
        finally:
            await admin.close()
            await target.close()
