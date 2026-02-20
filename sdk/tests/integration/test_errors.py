"""SDK integration tests for error handling."""

import pytest

from vox_sdk import VoxHTTPError

from .conftest import make_sdk_client, register

pytestmark = pytest.mark.anyio


class TestErrors:
    async def test_404_raises_http_error(self, sdk):
        await register(sdk, "alice", "password123")
        with pytest.raises(VoxHTTPError) as exc_info:
            await sdk.channels.get_feed(999999999)
        assert exc_info.value.status == 404

    async def test_403_forbidden(self, app, db):
        """Non-authors without MANAGE_MESSAGES permission get 403 on delete."""
        alice = await make_sdk_client(app)
        bob = await make_sdk_client(app)
        try:
            await register(alice, "alice", "password123")
            feed = await alice.channels.create_feed("private")
            sent = await alice.messages.send(feed.feed_id, "mine")

            await register(bob, "bob", "password123")
            with pytest.raises(VoxHTTPError) as exc_info:
                await bob.messages.delete(feed.feed_id, sent.msg_id)
            assert exc_info.value.status == 403
        finally:
            await alice.close()
            await bob.close()

    async def test_duplicate_registration(self, sdk):
        await register(sdk, "alice", "password123")
        with pytest.raises(VoxHTTPError) as exc_info:
            await sdk.auth.register("alice", "password123")
        assert exc_info.value.status == 409

    async def test_wrong_password_login(self, sdk):
        await register(sdk, "alice", "password123")
        sdk.http.token = None
        with pytest.raises(VoxHTTPError) as exc_info:
            await sdk.auth.login("alice", "wrongpassword")
        assert exc_info.value.status == 401

    async def test_unauthenticated_access(self, sdk):
        # No registration, no token — should be rejected
        with pytest.raises(VoxHTTPError) as exc_info:
            await sdk.members.list()
        # Server returns 422 (missing authorization header) or 401
        assert exc_info.value.status in (401, 422)

    async def test_banned_user_cannot_act(self, app, db):
        admin = await make_sdk_client(app)
        target = await make_sdk_client(app)
        try:
            await register(admin, "admin", "password123")
            target_reg = await register(target, "target", "password123")

            await admin.members.ban(target_reg.user_id, reason="test ban")

            with pytest.raises(VoxHTTPError) as exc_info:
                await target.channels.create_feed("should-fail")
            assert exc_info.value.status == 403
        finally:
            await admin.close()
            await target.close()
