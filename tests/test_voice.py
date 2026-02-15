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
