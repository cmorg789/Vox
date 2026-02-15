async def setup(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    await client.post("/api/v1/rooms", headers=h, json={"name": "Lounge", "type": "voice"})
    return h


async def test_join_voice(client):
    h = await setup(client)
    r = await client.post("/api/v1/rooms/1/voice/join", headers=h, json={"self_mute": False, "self_deaf": False})
    assert r.status_code == 200
    assert r.json()["media_token"].startswith("media_")
    assert "media_url" in r.json()


async def test_leave_voice(client):
    h = await setup(client)
    await client.post("/api/v1/rooms/1/voice/join", headers=h, json={})
    r = await client.post("/api/v1/rooms/1/voice/leave", headers=h)
    assert r.status_code == 204
