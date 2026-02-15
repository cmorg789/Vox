async def setup(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    return h


async def test_create_webhook(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/webhooks", headers=h, json={"name": "CI Bot"})
    assert r.status_code == 201
    assert r.json()["name"] == "CI Bot"
    assert r.json()["token"].startswith("whk_")


async def test_list_webhooks(client):
    h = await setup(client)
    await client.post("/api/v1/feeds/1/webhooks", headers=h, json={"name": "Bot 1"})
    await client.post("/api/v1/feeds/1/webhooks", headers=h, json={"name": "Bot 2"})

    r = await client.get("/api/v1/feeds/1/webhooks", headers=h)
    assert len(r.json()["webhooks"]) == 2


async def test_execute_webhook(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/webhooks", headers=h, json={"name": "CI Bot"})
    wh_id = r.json()["webhook_id"]
    token = r.json()["token"]

    # No auth needed
    r = await client.post(f"/api/v1/webhooks/{wh_id}/{token}", json={"body": "Build passed!"})
    assert r.status_code == 204

    # Verify message was posted
    r = await client.get("/api/v1/feeds/1/messages", headers=h)
    assert len(r.json()["messages"]) == 1
    assert r.json()["messages"][0]["body"] == "Build passed!"


async def test_execute_webhook_bad_token(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/webhooks", headers=h, json={"name": "CI Bot"})
    wh_id = r.json()["webhook_id"]

    r = await client.post(f"/api/v1/webhooks/{wh_id}/bad_token", json={"body": "test"})
    assert r.status_code == 422


async def test_delete_webhook(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/webhooks", headers=h, json={"name": "Temp"})
    wh_id = r.json()["webhook_id"]

    r = await client.delete(f"/api/v1/webhooks/{wh_id}", headers=h)
    assert r.status_code == 204

    r = await client.get("/api/v1/feeds/1/webhooks", headers=h)
    assert len(r.json()["webhooks"]) == 0


async def test_update_webhook(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/webhooks", headers=h, json={"name": "Old Name"})
    wh_id = r.json()["webhook_id"]

    r = await client.patch(f"/api/v1/webhooks/{wh_id}", headers=h, json={"name": "New Name", "avatar": "https://example.com/avatar.png"})
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"


async def test_update_webhook_not_found(client):
    h = await setup(client)
    r = await client.patch("/api/v1/webhooks/99999", headers=h, json={"name": "Ghost"})
    assert r.status_code == 404


async def test_delete_webhook_not_found(client):
    h = await setup(client)
    r = await client.delete("/api/v1/webhooks/99999", headers=h)
    assert r.status_code == 404
