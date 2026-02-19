async def auth(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


# --- Feeds ---

async def test_create_and_get_feed(client):
    h = await auth(client)
    r = await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    assert r.status_code == 201
    feed_id = r.json()["feed_id"]

    r = await client.get(f"/api/v1/feeds/{feed_id}", headers=h)
    assert r.status_code == 200
    assert r.json()["name"] == "general"
    assert r.json()["type"] == "text"


async def test_update_feed(client):
    h = await auth(client)
    r = await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    feed_id = r.json()["feed_id"]

    r = await client.patch(f"/api/v1/feeds/{feed_id}", headers=h, json={"name": "news", "topic": "Latest updates"})
    assert r.status_code == 200
    assert r.json()["name"] == "news"
    assert r.json()["topic"] == "Latest updates"


async def test_delete_feed(client):
    h = await auth(client)
    r = await client.post("/api/v1/feeds", headers=h, json={"name": "temp", "type": "text"})
    feed_id = r.json()["feed_id"]

    r = await client.delete(f"/api/v1/feeds/{feed_id}", headers=h)
    assert r.status_code == 204

    r = await client.get(f"/api/v1/feeds/{feed_id}", headers=h)
    assert r.status_code == 404


# --- Rooms ---

async def test_create_room(client):
    h = await auth(client)
    r = await client.post("/api/v1/rooms", headers=h, json={"name": "Lounge", "type": "voice"})
    assert r.status_code == 201
    assert r.json()["name"] == "Lounge"
    assert r.json()["type"] == "voice"


async def test_update_room(client):
    h = await auth(client)
    r = await client.post("/api/v1/rooms", headers=h, json={"name": "Lounge", "type": "voice"})
    room_id = r.json()["room_id"]

    r = await client.patch(f"/api/v1/rooms/{room_id}", headers=h, json={"name": "Gaming"})
    assert r.status_code == 200
    assert r.json()["name"] == "Gaming"


async def test_delete_room(client):
    h = await auth(client)
    r = await client.post("/api/v1/rooms", headers=h, json={"name": "Temp", "type": "voice"})
    room_id = r.json()["room_id"]

    r = await client.delete(f"/api/v1/rooms/{room_id}", headers=h)
    assert r.status_code == 204


# --- Categories ---

async def test_create_category(client):
    h = await auth(client)
    r = await client.post("/api/v1/categories", headers=h, json={"name": "Projects", "position": 0})
    assert r.status_code == 201
    assert r.json()["name"] == "Projects"


async def test_update_category(client):
    h = await auth(client)
    r = await client.post("/api/v1/categories", headers=h, json={"name": "Projects", "position": 0})
    cat_id = r.json()["category_id"]

    r = await client.patch(f"/api/v1/categories/{cat_id}", headers=h, json={"name": "Active Projects"})
    assert r.status_code == 200
    assert r.json()["name"] == "Active Projects"


async def test_delete_category(client):
    h = await auth(client)
    r = await client.post("/api/v1/categories", headers=h, json={"name": "Temp", "position": 0})
    cat_id = r.json()["category_id"]

    r = await client.delete(f"/api/v1/categories/{cat_id}", headers=h)
    assert r.status_code == 204


# --- Threads ---

async def test_create_thread(client):
    h = await auth(client)
    await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Hello"})
    msg_id = r.json()["msg_id"]

    r = await client.post("/api/v1/feeds/1/threads", headers=h, json={"parent_msg_id": msg_id, "name": "Discussion"})
    assert r.status_code == 201
    assert r.json()["name"] == "Discussion"
    assert r.json()["parent_feed_id"] == 1


async def test_update_thread(client):
    h = await auth(client)
    await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Hello"})
    msg_id = r.json()["msg_id"]
    r = await client.post("/api/v1/feeds/1/threads", headers=h, json={"parent_msg_id": msg_id, "name": "Discussion"})
    thread_id = r.json()["thread_id"]

    r = await client.patch(f"/api/v1/threads/{thread_id}", headers=h, json={"archived": True})
    assert r.status_code == 200
    assert r.json()["archived"] is True


# --- Not Found errors ---

async def test_update_feed_not_found(client):
    h = await auth(client)
    r = await client.patch("/api/v1/feeds/99999", headers=h, json={"name": "ghost"})
    assert r.status_code == 404


async def test_delete_feed_not_found(client):
    h = await auth(client)
    r = await client.delete("/api/v1/feeds/99999", headers=h)
    assert r.status_code == 404


async def test_update_room_not_found(client):
    h = await auth(client)
    r = await client.patch("/api/v1/rooms/99999", headers=h, json={"name": "ghost"})
    assert r.status_code == 404


async def test_delete_room_not_found(client):
    h = await auth(client)
    r = await client.delete("/api/v1/rooms/99999", headers=h)
    assert r.status_code == 404


async def test_update_category_not_found(client):
    h = await auth(client)
    r = await client.patch("/api/v1/categories/99999", headers=h, json={"name": "ghost"})
    assert r.status_code == 404


async def test_delete_category_not_found(client):
    h = await auth(client)
    r = await client.delete("/api/v1/categories/99999", headers=h)
    assert r.status_code == 404


async def test_update_category_position(client):
    h = await auth(client)
    r = await client.post("/api/v1/categories", headers=h, json={"name": "Cat", "position": 0})
    cat_id = r.json()["category_id"]
    r = await client.patch(f"/api/v1/categories/{cat_id}", headers=h, json={"position": 5})
    assert r.status_code == 200
    assert r.json()["position"] == 5


# --- Thread operations ---

async def test_update_thread_name_and_locked(client):
    h = await auth(client)
    await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Hello"})
    msg_id = r.json()["msg_id"]
    r = await client.post("/api/v1/feeds/1/threads", headers=h, json={"parent_msg_id": msg_id, "name": "Discussion"})
    thread_id = r.json()["thread_id"]

    r = await client.patch(f"/api/v1/threads/{thread_id}", headers=h, json={"name": "Renamed", "locked": True})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"
    assert r.json()["locked"] is True


async def test_update_thread_not_found(client):
    h = await auth(client)
    r = await client.patch("/api/v1/threads/99999", headers=h, json={"name": "ghost"})
    assert r.status_code == 404


async def test_delete_thread(client):
    h = await auth(client)
    await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Hello"})
    msg_id = r.json()["msg_id"]
    r = await client.post("/api/v1/feeds/1/threads", headers=h, json={"parent_msg_id": msg_id, "name": "Temp"})
    thread_id = r.json()["thread_id"]

    r = await client.delete(f"/api/v1/threads/{thread_id}", headers=h)
    assert r.status_code == 204


async def test_delete_thread_not_found(client):
    h = await auth(client)
    r = await client.delete("/api/v1/threads/99999", headers=h)
    assert r.status_code == 404


async def test_thread_subscribe_unsubscribe(client):
    h = await auth(client)
    await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Hello"})
    msg_id = r.json()["msg_id"]
    r = await client.post("/api/v1/feeds/1/threads", headers=h, json={"parent_msg_id": msg_id, "name": "Thread"})
    thread_id = r.json()["thread_id"]

    r = await client.put(f"/api/v1/feeds/1/threads/{thread_id}/subscribers", headers=h)
    assert r.status_code == 204

    r = await client.delete(f"/api/v1/feeds/1/threads/{thread_id}/subscribers", headers=h)
    assert r.status_code == 204


async def test_get_room(client):
    """Get room by ID."""
    h = await auth(client)
    r = await client.post("/api/v1/rooms", headers=h, json={"name": "Lounge", "type": "voice"})
    room_id = r.json()["room_id"]
    r = await client.get(f"/api/v1/rooms/{room_id}", headers=h)
    assert r.status_code == 200
    assert r.json()["name"] == "Lounge"


async def test_get_room_not_found(client):
    """Get non-existent room returns 404."""
    h = await auth(client)
    r = await client.get("/api/v1/rooms/99999", headers=h)
    assert r.status_code == 404


# --- Feed subscriptions ---


async def test_subscribe_feed(client):
    h = await auth(client)
    r = await client.post("/api/v1/feeds", headers=h, json={"name": "news", "type": "text"})
    feed_id = r.json()["feed_id"]
    r = await client.put(f"/api/v1/feeds/{feed_id}/subscribers", headers=h)
    assert r.status_code == 204


async def test_subscribe_feed_not_found(client):
    h = await auth(client)
    r = await client.put("/api/v1/feeds/99999/subscribers", headers=h)
    assert r.status_code == 404


async def test_unsubscribe_feed(client):
    h = await auth(client)
    r = await client.post("/api/v1/feeds", headers=h, json={"name": "news", "type": "text"})
    feed_id = r.json()["feed_id"]
    await client.put(f"/api/v1/feeds/{feed_id}/subscribers", headers=h)
    r = await client.delete(f"/api/v1/feeds/{feed_id}/subscribers", headers=h)
    assert r.status_code == 204


async def test_unsubscribe_feed_not_found(client):
    h = await auth(client)
    r = await client.delete("/api/v1/feeds/99999/subscribers", headers=h)
    assert r.status_code == 404


# --- Permission overrides ---


async def test_create_feed_with_permission_overrides(client):
    h = await auth(client)
    overrides = [{"target_type": "role", "target_id": 1, "allow": 1, "deny": 0}]
    r = await client.post("/api/v1/feeds", headers=h, json={"name": "restricted", "type": "text", "permission_overrides": overrides})
    assert r.status_code == 201
    assert len(r.json()["permission_overrides"]) == 1
    assert r.json()["permission_overrides"][0]["target_type"] == "role"


async def test_create_room_with_permission_overrides(client):
    h = await auth(client)
    overrides = [{"target_type": "role", "target_id": 1, "allow": 2, "deny": 0}]
    r = await client.post("/api/v1/rooms", headers=h, json={"name": "Private", "type": "voice", "permission_overrides": overrides})
    assert r.status_code == 201
    assert len(r.json()["permission_overrides"]) == 1


# --- Categories list/get ---


async def test_list_categories(client):
    h = await auth(client)
    await client.post("/api/v1/categories", headers=h, json={"name": "Cat1", "position": 0})
    await client.post("/api/v1/categories", headers=h, json={"name": "Cat2", "position": 1})
    r = await client.get("/api/v1/categories", headers=h)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2


async def test_get_category(client):
    h = await auth(client)
    r = await client.post("/api/v1/categories", headers=h, json={"name": "Projects", "position": 0})
    cat_id = r.json()["category_id"]
    r = await client.get(f"/api/v1/categories/{cat_id}", headers=h)
    assert r.status_code == 200
    assert r.json()["name"] == "Projects"


async def test_get_category_not_found(client):
    h = await auth(client)
    r = await client.get("/api/v1/categories/99999", headers=h)
    assert r.status_code == 404


# --- Thread get/list ---


async def test_get_thread(client):
    h = await auth(client)
    await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Hello"})
    msg_id = r.json()["msg_id"]
    r = await client.post("/api/v1/feeds/1/threads", headers=h, json={"parent_msg_id": msg_id, "name": "Talk"})
    thread_id = r.json()["thread_id"]
    r = await client.get(f"/api/v1/threads/{thread_id}", headers=h)
    assert r.status_code == 200
    assert r.json()["name"] == "Talk"


async def test_get_thread_not_found(client):
    h = await auth(client)
    r = await client.get("/api/v1/threads/99999", headers=h)
    assert r.status_code == 404


async def test_list_feed_threads(client):
    h = await auth(client)
    await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "A"})
    mid1 = r.json()["msg_id"]
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "B"})
    mid2 = r.json()["msg_id"]

    r1 = await client.post("/api/v1/feeds/1/threads", headers=h, json={"parent_msg_id": mid1, "name": "T1"})
    tid1 = r1.json()["thread_id"]
    await client.post("/api/v1/feeds/1/threads", headers=h, json={"parent_msg_id": mid2, "name": "T2"})

    # List all
    r = await client.get("/api/v1/feeds/1/threads", headers=h)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2
    assert r.json()["cursor"] is not None

    # Pagination with after cursor
    r = await client.get(f"/api/v1/feeds/1/threads?after={tid1}", headers=h)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1


async def test_subscribe_thread_not_found(client):
    h = await auth(client)
    r = await client.put("/api/v1/feeds/1/threads/99999/subscribers", headers=h)
    assert r.status_code == 404


async def test_unsubscribe_thread_not_found(client):
    h = await auth(client)
    r = await client.delete("/api/v1/feeds/1/threads/99999/subscribers", headers=h)
    assert r.status_code == 404
