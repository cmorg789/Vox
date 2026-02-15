async def auth(client, username="alice"):
    r = await client.post("/api/v1/auth/register", json={"username": username, "password": "test1234", "display_name": username.title()})
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user_id"]


async def test_list_members(client):
    h, _ = await auth(client)
    r = await client.get("/api/v1/members", headers=h)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1
    assert r.json()["items"][0]["display_name"] == "Alice"


async def test_update_member_nickname(client):
    h, _ = await auth(client)
    r = await client.patch("/api/v1/members/@me", headers=h, json={"nickname": "Ali"})
    assert r.status_code == 200
    assert r.json()["nickname"] == "Ali"


async def test_kick_member(client):
    h_admin, _ = await auth(client, "admin")
    _, uid_bob = await auth(client, "bob")

    r = await client.delete(f"/api/v1/members/{uid_bob}", headers=h_admin)
    assert r.status_code == 204


async def test_ban_and_unban(client):
    h_admin, _ = await auth(client, "admin")
    _, uid_bob = await auth(client, "bob")

    # Ban
    r = await client.put(f"/api/v1/bans/{uid_bob}", headers=h_admin, json={"reason": "Spam"})
    assert r.status_code == 200
    assert r.json()["reason"] == "Spam"

    # List bans
    r = await client.get("/api/v1/bans", headers=h_admin)
    assert len(r.json()["bans"]) == 1

    # Unban
    r = await client.delete(f"/api/v1/bans/{uid_bob}", headers=h_admin)
    assert r.status_code == 204

    r = await client.get("/api/v1/bans", headers=h_admin)
    assert len(r.json()["bans"]) == 0
