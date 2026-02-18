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
    r = await client.patch(f"/api/v1/users/{uid}", headers={"Authorization": f"Bearer {token}"}, json={"display_name": "New Name", "bio": "Hello"})
    assert r.status_code == 200
    assert r.json()["display_name"] == "New Name"
    assert r.json()["bio"] == "Hello"


async def test_friends(client):
    token_a, uid_a = await register(client, "alice")
    token_b, uid_b = await register(client, "bob")

    # Add friend
    r = await client.put(f"/api/v1/users/{uid_a}/friends/{uid_b}", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 204

    # List friends
    r = await client.get(f"/api/v1/users/{uid_a}/friends", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1
    assert r.json()["items"][0]["user_id"] == uid_b

    # Remove friend
    r = await client.delete(f"/api/v1/users/{uid_a}/friends/{uid_b}", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 204

    r = await client.get(f"/api/v1/users/{uid_a}/friends", headers={"Authorization": f"Bearer {token_a}"})
    assert len(r.json()["items"]) == 0


async def test_block_unblock(client):
    token_a, uid_a = await register(client, "alice")
    _, uid_b = await register(client, "bob")

    r = await client.put(f"/api/v1/users/{uid_a}/blocks/{uid_b}", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 204

    r = await client.delete(f"/api/v1/users/{uid_a}/blocks/{uid_b}", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 204


async def test_get_user_presence(client):
    """Get user presence returns a dict."""
    token, uid = await register(client)
    r = await client.get(f"/api/v1/users/{uid}/presence", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


async def test_update_profile_avatar(client):
    """Update avatar field."""
    token, uid = await register(client)
    r = await client.patch(f"/api/v1/users/{uid}", headers={"Authorization": f"Bearer {token}"}, json={"avatar": "avatar.png"})
    assert r.status_code == 200
    assert r.json()["avatar"] == "avatar.png"


async def test_block_self(client):
    """Cannot block yourself."""
    token, uid = await register(client)
    r = await client.put(f"/api/v1/users/{uid}/blocks/{uid}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400


async def test_add_friend_self(client):
    """Cannot add yourself as friend."""
    token, uid = await register(client)
    r = await client.put(f"/api/v1/users/{uid}/friends/{uid}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400


async def test_friends_pagination(client):
    """Friends list pagination with after cursor."""
    token_a, uid_a = await register(client, "alice")
    token_b, uid_b = await register(client, "bob")
    await client.put(f"/api/v1/users/{uid_a}/friends/{uid_b}", headers={"Authorization": f"Bearer {token_a}"})

    r = await client.get(f"/api/v1/users/{uid_a}/friends?after={uid_b}", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200
    assert len(r.json()["items"]) == 0


async def test_friend_request_pending(client):
    """Sending a friend request shows as pending in the sender's friend list."""
    token_a, uid_a = await register(client, "alice")
    token_b, uid_b = await register(client, "bob")

    r = await client.put(f"/api/v1/users/{uid_a}/friends/{uid_b}", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 204

    r = await client.get(f"/api/v1/users/{uid_a}/friends?status=pending", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1
    assert r.json()["items"][0]["user_id"] == uid_b
    assert r.json()["items"][0]["status"] == "pending"


async def test_friend_accept(client):
    """Accepting a friend request makes both users see each other as accepted."""
    token_a, uid_a = await register(client, "alice")
    token_b, uid_b = await register(client, "bob")

    # Alice sends friend request to Bob
    await client.put(f"/api/v1/users/{uid_a}/friends/{uid_b}", headers={"Authorization": f"Bearer {token_a}"})

    # Bob accepts
    r = await client.post(f"/api/v1/users/{uid_b}/friends/{uid_a}/accept", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 204

    # Both users should see each other as accepted
    r = await client.get(f"/api/v1/users/{uid_a}/friends", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1
    assert r.json()["items"][0]["user_id"] == uid_b
    assert r.json()["items"][0]["status"] == "accepted"

    r = await client.get(f"/api/v1/users/{uid_b}/friends", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1
    assert r.json()["items"][0]["user_id"] == uid_a
    assert r.json()["items"][0]["status"] == "accepted"


async def test_friend_reject(client):
    """Rejecting a friend request removes it from the pending list."""
    token_a, uid_a = await register(client, "alice")
    token_b, uid_b = await register(client, "bob")

    # Alice sends friend request to Bob
    await client.put(f"/api/v1/users/{uid_a}/friends/{uid_b}", headers={"Authorization": f"Bearer {token_a}"})

    # Bob rejects
    r = await client.post(f"/api/v1/users/{uid_b}/friends/{uid_a}/reject", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 204

    # Bob's pending list should be empty
    r = await client.get(f"/api/v1/users/{uid_b}/friends?status=pending", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 200
    assert len(r.json()["items"]) == 0
