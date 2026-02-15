async def register(client, username="alice", password="test1234"):
    r = await client.post("/api/v1/auth/register", json={"username": username, "password": password, "display_name": username.title()})
    return r.json()["token"], r.json()["user_id"]


async def test_get_user(client):
    token, uid = await register(client)
    r = await client.get(f"/api/v1/users/{uid}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["user_id"] == uid
    assert r.json()["display_name"] == "Alice"


async def test_get_user_not_found(client):
    token, _ = await register(client)
    r = await client.get("/api/v1/users/9999", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


async def test_update_profile(client):
    token, uid = await register(client)
    r = await client.patch("/api/v1/users/@me", headers={"Authorization": f"Bearer {token}"}, json={"display_name": "New Name", "bio": "Hello"})
    assert r.status_code == 200
    assert r.json()["display_name"] == "New Name"
    assert r.json()["bio"] == "Hello"


async def test_friends(client):
    token_a, uid_a = await register(client, "alice")
    token_b, uid_b = await register(client, "bob")

    # Add friend
    r = await client.put(f"/api/v1/users/@me/friends/{uid_b}", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 204

    # List friends
    r = await client.get("/api/v1/users/@me/friends", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200
    assert len(r.json()["friends"]) == 1
    assert r.json()["friends"][0]["user_id"] == uid_b

    # Remove friend
    r = await client.delete(f"/api/v1/users/@me/friends/{uid_b}", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 204

    r = await client.get("/api/v1/users/@me/friends", headers={"Authorization": f"Bearer {token_a}"})
    assert len(r.json()["friends"]) == 0


async def test_block_unblock(client):
    token_a, _ = await register(client, "alice")
    _, uid_b = await register(client, "bob")

    r = await client.put(f"/api/v1/users/@me/blocks/{uid_b}", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 204

    r = await client.delete(f"/api/v1/users/@me/blocks/{uid_b}", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 204
