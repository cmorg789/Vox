async def setup(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Hello world"})
    await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Goodbye world"})
    await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Something else"})
    return h


async def test_search_by_query(client):
    h = await setup(client)
    r = await client.get("/api/v1/messages/search?query=world", headers=h)
    assert r.status_code == 200
    assert len(r.json()["results"]) == 2


async def test_search_by_feed(client):
    h = await setup(client)
    r = await client.get("/api/v1/messages/search?query=Hello&feed_id=1", headers=h)
    assert len(r.json()["results"]) == 1


async def test_search_no_results(client):
    h = await setup(client)
    r = await client.get("/api/v1/messages/search?query=nonexistent", headers=h)
    assert len(r.json()["results"]) == 0
