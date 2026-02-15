async def auth(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def test_create_invite(client):
    h = await auth(client)
    r = await client.post("/api/v1/invites", headers=h, json={"max_uses": 10})
    assert r.status_code == 201
    assert r.json()["uses"] == 0
    assert r.json()["max_uses"] == 10
    assert len(r.json()["code"]) > 0


async def test_resolve_invite_no_auth(client):
    h = await auth(client)
    r = await client.post("/api/v1/invites", headers=h, json={})
    code = r.json()["code"]

    # No auth needed for resolve
    r = await client.get(f"/api/v1/invites/{code}")
    assert r.status_code == 200
    assert r.json()["code"] == code
    assert r.json()["server_name"] == "Vox Server"


async def test_list_invites(client):
    h = await auth(client)
    await client.post("/api/v1/invites", headers=h, json={})
    await client.post("/api/v1/invites", headers=h, json={})

    r = await client.get("/api/v1/invites", headers=h)
    assert r.status_code == 200
    assert len(r.json()["invites"]) == 2


async def test_delete_invite(client):
    h = await auth(client)
    r = await client.post("/api/v1/invites", headers=h, json={})
    code = r.json()["code"]

    r = await client.delete(f"/api/v1/invites/{code}", headers=h)
    assert r.status_code == 204

    r = await client.get(f"/api/v1/invites/{code}")
    assert r.status_code == 404
