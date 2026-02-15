async def auth(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def test_create_and_list_emoji(client):
    h = await auth(client)
    r = await client.post("/api/v1/emoji?name=pepethink", headers=h)
    assert r.status_code == 201
    assert r.json()["name"] == "pepethink"

    r = await client.get("/api/v1/emoji", headers=h)
    assert len(r.json()["emoji"]) == 1


async def test_delete_emoji(client):
    h = await auth(client)
    r = await client.post("/api/v1/emoji?name=temp", headers=h)
    eid = r.json()["emoji_id"]

    r = await client.delete(f"/api/v1/emoji/{eid}", headers=h)
    assert r.status_code == 204

    r = await client.get("/api/v1/emoji", headers=h)
    assert len(r.json()["emoji"]) == 0


async def test_create_and_list_stickers(client):
    h = await auth(client)
    r = await client.post("/api/v1/stickers?name=wave", headers=h)
    assert r.status_code == 201

    r = await client.get("/api/v1/stickers", headers=h)
    assert len(r.json()["stickers"]) == 1


async def test_delete_sticker(client):
    h = await auth(client)
    r = await client.post("/api/v1/stickers?name=temp", headers=h)
    sid = r.json()["sticker_id"]

    r = await client.delete(f"/api/v1/stickers/{sid}", headers=h)
    assert r.status_code == 204
