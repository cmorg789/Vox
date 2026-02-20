"""SDK integration tests for voice endpoints."""

import pytest

from vox_sdk import VoxHTTPError

from .conftest import make_sdk_client, register

pytestmark = pytest.mark.anyio


class TestVoice:
    async def test_join_and_leave(self, sdk, app):
        """Join voice in a room, verify response, then leave."""
        await register(sdk, "alice", "password123")
        room = await sdk.channels.create_room("voice-chat", "voice")

        join_resp = await sdk.voice.join(room.room_id)
        assert join_resp.media_url
        assert join_resp.media_token

        await sdk.voice.leave(room.room_id)

    async def test_get_voice_members(self, sdk, app):
        """Join voice, then list members and verify self is present."""
        reg = await register(sdk, "alice", "password123")
        room = await sdk.channels.create_room("voice-chat", "voice")

        await sdk.voice.join(room.room_id)

        members = await sdk.voice.get_members(room.room_id)
        assert members.room_id == room.room_id
        assert any(m.user_id == reg.user_id for m in members.members)

        await sdk.voice.leave(room.room_id)

    async def test_server_mute_and_deafen(self, sdk, app):
        """Admin server-mutes and deafens another user."""
        await register(sdk, "alice", "password123")
        room = await sdk.channels.create_room("voice-chat", "voice")

        bob = await make_sdk_client(app)
        bob_reg = await register(bob, "bob", "password123")

        try:
            await sdk.voice.join(room.room_id)
            await bob.voice.join(room.room_id)

            # Alice (admin/first user) server-mutes Bob
            await sdk.voice.server_mute(room.room_id, bob_reg.user_id, True)
            members = await sdk.voice.get_members(room.room_id)
            bob_member = next(m for m in members.members if m.user_id == bob_reg.user_id)
            assert bob_member.server_mute is True

            # Alice server-deafens Bob
            await sdk.voice.server_deafen(room.room_id, bob_reg.user_id, True)
            members = await sdk.voice.get_members(room.room_id)
            bob_member = next(m for m in members.members if m.user_id == bob_reg.user_id)
            assert bob_member.server_deaf is True
        finally:
            await bob.close()

    async def test_kick_from_voice(self, sdk, app):
        """Admin kicks another user from voice."""
        await register(sdk, "alice", "password123")
        room = await sdk.channels.create_room("voice-chat", "voice")

        bob = await make_sdk_client(app)
        bob_reg = await register(bob, "bob", "password123")

        try:
            await sdk.voice.join(room.room_id)
            await bob.voice.join(room.room_id)

            await sdk.voice.kick(room.room_id, bob_reg.user_id)

            members = await sdk.voice.get_members(room.room_id)
            assert not any(m.user_id == bob_reg.user_id for m in members.members)
        finally:
            await bob.close()

    async def test_get_media_cert_self_signed(self, sdk):
        """In test env the SFU uses a self-signed cert, so get_media_cert returns it."""
        await register(sdk, "alice", "password123")
        result = await sdk.voice.get_media_cert()
        assert result is not None
        assert result.fingerprint.startswith("sha256:")
        assert len(result.cert_der) > 0

    async def test_stage_topic(self, sdk):
        """Create a stage room, set topic, verify response."""
        await register(sdk, "alice", "password123")
        room = await sdk.channels.create_room("stage-room", "stage")

        await sdk.voice.join(room.room_id)

        resp = await sdk.voice.stage_set_topic(room.room_id, "Welcome to the stage!")
        assert resp.topic == "Welcome to the stage!"

        await sdk.voice.leave(room.room_id)
