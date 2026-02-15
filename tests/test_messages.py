async def setup(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    return h


async def test_send_and_get_messages(client):
    h = await setup(client)

    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Hello!"})
    assert r.status_code == 201
    msg_id = r.json()["msg_id"]
    assert r.json()["timestamp"] > 0

    r = await client.get("/api/v1/feeds/1/messages", headers=h)
    assert r.status_code == 200
    assert len(r.json()["messages"]) == 1
    assert r.json()["messages"][0]["msg_id"] == msg_id
    assert r.json()["messages"][0]["body"] == "Hello!"


async def test_edit_message(client):
    h = await setup(client)

    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Original"})
    msg_id = r.json()["msg_id"]

    r = await client.patch(f"/api/v1/feeds/1/messages/{msg_id}", headers=h, json={"body": "Edited"})
    assert r.status_code == 200
    assert r.json()["edit_timestamp"] > 0


async def test_edit_message_not_author(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Original"})
    msg_id = r.json()["msg_id"]

    # Register second user
    r2 = await client.post("/api/v1/auth/register", json={"username": "bob", "password": "test1234"})
    h2 = {"Authorization": f"Bearer {r2.json()['token']}"}

    r = await client.patch(f"/api/v1/feeds/1/messages/{msg_id}", headers=h2, json={"body": "Hacked"})
    assert r.status_code == 403


async def test_delete_message(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Delete me"})
    msg_id = r.json()["msg_id"]

    r = await client.delete(f"/api/v1/feeds/1/messages/{msg_id}", headers=h)
    assert r.status_code == 204

    r = await client.get("/api/v1/feeds/1/messages", headers=h)
    assert len(r.json()["messages"]) == 0


async def test_bulk_delete(client):
    h = await setup(client)
    ids = []
    for i in range(3):
        r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": f"msg {i}"})
        ids.append(r.json()["msg_id"])

    r = await client.post("/api/v1/feeds/1/messages/bulk-delete", headers=h, json={"msg_ids": ids})
    assert r.status_code == 204

    r = await client.get("/api/v1/feeds/1/messages", headers=h)
    assert len(r.json()["messages"]) == 0


async def test_reactions(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "React to this"})
    msg_id = r.json()["msg_id"]

    r = await client.put(f"/api/v1/feeds/1/messages/{msg_id}/reactions/%F0%9F%91%8D", headers=h)
    assert r.status_code == 204

    r = await client.delete(f"/api/v1/feeds/1/messages/{msg_id}/reactions/%F0%9F%91%8D", headers=h)
    assert r.status_code == 204


async def test_pins(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Pin me"})
    msg_id = r.json()["msg_id"]

    r = await client.put(f"/api/v1/feeds/1/pins/{msg_id}", headers=h)
    assert r.status_code == 204

    r = await client.get("/api/v1/feeds/1/pins", headers=h)
    assert r.status_code == 200
    assert len(r.json()["messages"]) == 1

    r = await client.delete(f"/api/v1/feeds/1/pins/{msg_id}", headers=h)
    assert r.status_code == 204

    r = await client.get("/api/v1/feeds/1/pins", headers=h)
    assert len(r.json()["messages"]) == 0


async def test_thread_messages(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Parent"})
    msg_id = r.json()["msg_id"]

    r = await client.post("/api/v1/feeds/1/threads", headers=h, json={"parent_msg_id": msg_id, "name": "Thread"})
    thread_id = r.json()["thread_id"]

    r = await client.post(f"/api/v1/feeds/1/threads/{thread_id}/messages", headers=h, json={"body": "In thread"})
    assert r.status_code == 201

    r = await client.get(f"/api/v1/feeds/1/threads/{thread_id}/messages", headers=h)
    assert len(r.json()["messages"]) == 1
    assert r.json()["messages"][0]["body"] == "In thread"
