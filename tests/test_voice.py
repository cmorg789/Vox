from unittest.mock import MagicMock

import pytest


async def _register(client, username="alice", password="test1234"):
    r = await client.post("/api/v1/auth/register", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def _create_room(client, headers, name="Lounge", room_type="voice"):
    r = await client.post("/api/v1/rooms", headers=headers, json={"name": name, "type": room_type})
    return r.json()["room_id"]


# --- Join / Leave ---


async def test_join_voice(client):
    h = await _register(client)
    room_id = await _create_room(client, h)
    r = await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h, json={"self_mute": False, "self_deaf": False})
    assert r.status_code == 200
    data = r.json()
    assert data["media_token"].startswith("media_")
    assert "media_url" in data
    assert isinstance(data["members"], list)


async def test_join_populates_members(client):
    h1 = await _register(client, "alice")
    h2 = await _register(client, "bob")
    room_id = await _create_room(client, h1)
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h1, json={})
    r = await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h2, json={})
    assert r.status_code == 200
    members = r.json()["members"]
    user_ids = [m["user_id"] for m in members]
    assert len(user_ids) == 2


async def test_already_in_voice(client):
    h = await _register(client)
    room_id = await _create_room(client, h)
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h, json={})
    r = await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h, json={})
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "ALREADY_IN_VOICE"


async def test_leave_voice(client):
    h = await _register(client)
    room_id = await _create_room(client, h)
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h, json={})
    r = await client.post(f"/api/v1/rooms/{room_id}/voice/leave", headers=h)
    assert r.status_code == 204


async def test_leave_when_not_in_room(client):
    h = await _register(client)
    room_id = await _create_room(client, h)
    r = await client.post(f"/api/v1/rooms/{room_id}/voice/leave", headers=h)
    assert r.status_code == 204


async def test_join_after_leave(client):
    h = await _register(client)
    room_id = await _create_room(client, h)
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h, json={})
    await client.post(f"/api/v1/rooms/{room_id}/voice/leave", headers=h)
    r = await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h, json={})
    assert r.status_code == 200


async def test_room_not_found(client):
    h = await _register(client)
    r = await client.post("/api/v1/rooms/9999/voice/join", headers=h, json={})
    assert r.status_code == 404


# --- Kick ---


async def test_kick_from_voice(client):
    h1 = await _register(client, "alice")
    h2 = await _register(client, "bob")
    room_id = await _create_room(client, h1)
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h1, json={})
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h2, json={})
    r = await client.post(f"/api/v1/rooms/{room_id}/voice/kick", headers=h1, json={"user_id": 2})
    assert r.status_code == 204
    # Bob can rejoin (not in voice anymore)
    r = await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h2, json={})
    assert r.status_code == 200


# --- Move ---


async def test_move_to_room(client):
    h1 = await _register(client, "alice")
    h2 = await _register(client, "bob")
    room1 = await _create_room(client, h1, "Room1")
    room2 = await _create_room(client, h1, "Room2")
    await client.post(f"/api/v1/rooms/{room1}/voice/join", headers=h2, json={})
    r = await client.post(
        f"/api/v1/rooms/{room1}/voice/move", headers=h1,
        json={"user_id": 2, "to_room_id": room2},
    )
    assert r.status_code == 204
    # Bob can't rejoin room1 without leaving room2 first since they're now in room2
    r = await client.post(f"/api/v1/rooms/{room1}/voice/join", headers=h2, json={})
    assert r.status_code == 409


# --- Voice State Flags ---


async def test_voice_state_flags(client):
    h = await _register(client)
    room_id = await _create_room(client, h)
    r = await client.post(
        f"/api/v1/rooms/{room_id}/voice/join", headers=h,
        json={"self_mute": True, "self_deaf": False},
    )
    assert r.status_code == 200
    members = r.json()["members"]
    me = [m for m in members if m["user_id"] == 1][0]
    assert me["mute"] is True
    assert me["deaf"] is False


# --- Stage ---


async def test_stage_request(client):
    h = await _register(client)
    room_id = await _create_room(client, h, "Stage", "stage")
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h, json={})
    r = await client.post(f"/api/v1/rooms/{room_id}/stage/request", headers=h)
    assert r.status_code == 204


async def test_stage_request_not_in_voice(client):
    h = await _register(client)
    room_id = await _create_room(client, h, "Stage", "stage")
    r = await client.post(f"/api/v1/rooms/{room_id}/stage/request", headers=h)
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "NOT_IN_VOICE"


async def test_stage_invite_accept(client):
    h1 = await _register(client, "alice")
    h2 = await _register(client, "bob")
    room_id = await _create_room(client, h1, "Stage", "stage")
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h1, json={})
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h2, json={})
    # Invite bob
    r = await client.post(f"/api/v1/rooms/{room_id}/stage/invite", headers=h1, json={"user_id": 2})
    assert r.status_code == 204
    # Bob accepts
    r = await client.post(f"/api/v1/rooms/{room_id}/stage/invite/respond", headers=h2, json={"accepted": True})
    assert r.status_code == 204


async def test_stage_invite_decline(client):
    h1 = await _register(client, "alice")
    h2 = await _register(client, "bob")
    room_id = await _create_room(client, h1, "Stage", "stage")
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h1, json={})
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h2, json={})
    await client.post(f"/api/v1/rooms/{room_id}/stage/invite", headers=h1, json={"user_id": 2})
    r = await client.post(f"/api/v1/rooms/{room_id}/stage/invite/respond", headers=h2, json={"accepted": False})
    assert r.status_code == 204


async def test_stage_revoke(client):
    h1 = await _register(client, "alice")
    h2 = await _register(client, "bob")
    room_id = await _create_room(client, h1, "Stage", "stage")
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h1, json={})
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h2, json={})
    await client.post(f"/api/v1/rooms/{room_id}/stage/invite", headers=h1, json={"user_id": 2})
    await client.post(f"/api/v1/rooms/{room_id}/stage/invite/respond", headers=h2, json={"accepted": True})
    r = await client.post(f"/api/v1/rooms/{room_id}/stage/revoke", headers=h1, json={"user_id": 2})
    assert r.status_code == 204


async def test_stage_topic(client):
    h = await _register(client)
    room_id = await _create_room(client, h, "Stage", "stage")
    r = await client.patch(f"/api/v1/rooms/{room_id}/stage/topic", headers=h, json={"topic": "AMA Session"})
    assert r.status_code == 200
    assert r.json()["topic"] == "AMA Session"


# --- SFU Lifecycle ---


async def test_init_sfu_and_stop_sfu(client):
    """init_sfu creates SFU and stop_sfu clears it."""
    from unittest.mock import MagicMock, patch
    from vox.voice import service as voice_service

    mock_sfu_class = MagicMock()
    mock_sfu_instance = MagicMock()
    mock_sfu_class.return_value = mock_sfu_instance

    old_sfu = voice_service._sfu
    voice_service._sfu = None
    try:
        with patch.object(voice_service, "SFU", mock_sfu_class):
            voice_service.init_sfu("0.0.0.0:4444")
            assert voice_service._sfu == mock_sfu_instance
            mock_sfu_class.assert_called_once_with("0.0.0.0:4444")

            voice_service.stop_sfu()
            assert voice_service._sfu is None
            mock_sfu_instance.stop.assert_called_once()
    finally:
        voice_service._sfu = old_sfu


async def test_init_sfu_replaces_existing(client):
    """init_sfu stops existing SFU before creating new one."""
    from unittest.mock import MagicMock, patch
    from vox.voice import service as voice_service

    mock_sfu_class = MagicMock()
    old_mock = MagicMock()
    new_mock = MagicMock()
    mock_sfu_class.side_effect = [new_mock]

    old_sfu = voice_service._sfu
    voice_service._sfu = old_mock
    try:
        with patch.object(voice_service, "SFU", mock_sfu_class):
            voice_service.init_sfu("0.0.0.0:4445")
            old_mock.stop.assert_called_once()
            assert voice_service._sfu == new_mock
    finally:
        voice_service._sfu = old_sfu


async def test_join_room_sfu_exception(client):
    """join_room handles SFU add_room exception gracefully."""
    from unittest.mock import MagicMock, patch
    from vox.voice import service as voice_service

    h = await _register(client)
    room_id = await _create_room(client, h)

    # Mock SFU to raise on add_room but succeed on admit_user
    mock_sfu = MagicMock()
    mock_sfu.add_room.side_effect = Exception("room exists")
    mock_sfu.admit_user.return_value = None
    mock_sfu.start.return_value = None

    old_sfu = voice_service._sfu
    voice_service._sfu = mock_sfu
    try:
        r = await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h, json={})
        assert r.status_code == 200
        mock_sfu.add_room.assert_called_once()
        mock_sfu.admit_user.assert_called_once()
    finally:
        voice_service._sfu = old_sfu


async def test_leave_room_sfu_exception(client):
    """leave_room handles SFU remove_user exception gracefully."""
    from unittest.mock import MagicMock, patch
    from vox.voice import service as voice_service

    h = await _register(client)
    room_id = await _create_room(client, h)

    # Join first with working SFU
    mock_sfu = MagicMock()
    mock_sfu.add_room.return_value = None
    mock_sfu.admit_user.return_value = None
    mock_sfu.start.return_value = None

    old_sfu = voice_service._sfu
    voice_service._sfu = mock_sfu
    try:
        r = await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h, json={})
        assert r.status_code == 200

        # Now make SFU raise on remove
        mock_sfu.remove_user.side_effect = Exception("user not found")
        mock_sfu.get_room_users.side_effect = Exception("room not found")

        r = await client.post(f"/api/v1/rooms/{room_id}/voice/leave", headers=h)
        assert r.status_code == 204
    finally:
        voice_service._sfu = old_sfu


async def test_init_sfu_no_module(client):
    """init_sfu raises RuntimeError when vox_sfu not installed."""
    from vox.voice import service

    original_sfu_class = service.SFU
    service.SFU = None
    try:
        with pytest.raises(RuntimeError, match="vox_sfu is not installed"):
            service.init_sfu("0.0.0.0:4443")
    finally:
        service.SFU = original_sfu_class


async def test_get_sfu_no_module(client):
    """get_sfu raises RuntimeError when vox_sfu not installed and no existing."""
    from vox.voice import service

    original_sfu_class = service.SFU
    original_sfu = service._sfu
    service.SFU = None
    service._sfu = None
    try:
        with pytest.raises(RuntimeError, match="vox_sfu is not installed"):
            service.get_sfu()
    finally:
        service.SFU = original_sfu_class
        service._sfu = original_sfu


async def test_reset_sfu(client):
    """reset() clears the SFU instance."""
    from vox.voice import service

    mock_sfu = MagicMock()
    service._sfu = mock_sfu
    service.reset()
    assert service._sfu is None
    mock_sfu.stop.assert_called_once()


async def test_reset_sfu_stop_exception(client):
    """reset() handles exception from sfu.stop() gracefully."""
    from vox.voice import service

    mock_sfu = MagicMock()
    mock_sfu.stop.side_effect = Exception("oops")
    service._sfu = mock_sfu
    service.reset()
    assert service._sfu is None


async def test_move_user_sfu_exceptions(client):
    """move_user handles SFU exceptions in both leave and join phases."""
    from unittest.mock import MagicMock, patch
    from vox.voice import service as voice_service

    h1 = await _register(client, "alice")
    h2 = await _register(client, "bob")
    room1 = await _create_room(client, h1, "Room1")
    room2 = await _create_room(client, h1, "Room2")

    mock_sfu = MagicMock()
    mock_sfu.add_room.return_value = None
    mock_sfu.admit_user.return_value = None
    mock_sfu.start.return_value = None
    # remove_user raises for the old room
    mock_sfu.remove_user.side_effect = Exception("not found")
    mock_sfu.get_room_users.side_effect = Exception("room error")

    old_sfu = voice_service._sfu
    voice_service._sfu = mock_sfu
    try:
        # First join bob to room1
        mock_sfu.remove_user.side_effect = None
        mock_sfu.get_room_users.side_effect = None
        r = await client.post(f"/api/v1/rooms/{room1}/voice/join", headers=h2, json={})
        assert r.status_code == 200

        # Now make SFU raise for the move
        mock_sfu.remove_user.side_effect = Exception("not found")
        mock_sfu.get_room_users.side_effect = Exception("room error")
        mock_sfu.add_room.side_effect = Exception("exists")

        r = await client.post(
            f"/api/v1/rooms/{room1}/voice/move", headers=h1,
            json={"user_id": 2, "to_room_id": room2},
        )
        assert r.status_code == 204
    finally:
        voice_service._sfu = old_sfu


# --- GET voice members ---


async def test_get_voice_members(client):
    h = await _register(client)
    room_id = await _create_room(client, h)
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h, json={})
    r = await client.get(f"/api/v1/rooms/{room_id}/voice", headers=h)
    assert r.status_code == 200
    assert r.json()["room_id"] == room_id
    assert len(r.json()["members"]) == 1


# --- Token refresh ---


async def test_refresh_media_token(client):
    h = await _register(client)
    room_id = await _create_room(client, h)
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h, json={})
    r = await client.post(f"/api/v1/rooms/{room_id}/voice/token-refresh", headers=h)
    assert r.status_code == 200
    assert "media_token" in r.json()


# --- Server mute / deafen ---


async def test_server_mute(client):
    h1 = await _register(client, "alice")
    h2 = await _register(client, "bob")
    room_id = await _create_room(client, h1)
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h2, json={})
    r = await client.post(f"/api/v1/rooms/{room_id}/voice/mute", headers=h1, json={"user_id": 2, "muted": True})
    assert r.status_code == 204


async def test_server_mute_not_in_voice(client):
    h1 = await _register(client, "alice")
    await _register(client, "bob")
    room_id = await _create_room(client, h1)
    r = await client.post(f"/api/v1/rooms/{room_id}/voice/mute", headers=h1, json={"user_id": 2, "muted": True})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "NOT_IN_VOICE"


async def test_server_deafen(client):
    h1 = await _register(client, "alice")
    h2 = await _register(client, "bob")
    room_id = await _create_room(client, h1)
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h2, json={})
    r = await client.post(f"/api/v1/rooms/{room_id}/voice/deafen", headers=h1, json={"user_id": 2, "deafened": True})
    assert r.status_code == 204


async def test_server_deafen_not_in_voice(client):
    h1 = await _register(client, "alice")
    await _register(client, "bob")
    room_id = await _create_room(client, h1)
    r = await client.post(f"/api/v1/rooms/{room_id}/voice/deafen", headers=h1, json={"user_id": 2, "deafened": True})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "NOT_IN_VOICE"


# --- Stage edge cases ---


async def test_stage_invite_not_in_voice(client):
    h1 = await _register(client, "alice")
    h2 = await _register(client, "bob")
    room_id = await _create_room(client, h1, "Stage", "stage")
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h1, json={})
    # Bob is NOT in voice, so invite should fail
    r = await client.post(f"/api/v1/rooms/{room_id}/stage/invite", headers=h1, json={"user_id": 2})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "NOT_IN_VOICE"


async def test_stage_respond_no_pending_invite(client):
    h1 = await _register(client, "alice")
    room_id = await _create_room(client, h1, "Stage", "stage")
    await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h1, json={})
    r = await client.post(f"/api/v1/rooms/{room_id}/stage/invite/respond", headers=h1, json={"accepted": True})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "NO_PENDING_INVITE"


async def test_stage_set_topic_room_not_found(client):
    h = await _register(client)
    r = await client.patch("/api/v1/rooms/99999/stage/topic", headers=h, json={"topic": "Test"})
    assert r.status_code == 404
