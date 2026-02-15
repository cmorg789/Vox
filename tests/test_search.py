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


async def test_search_has_file(client):
    import io

    h = await setup(client)

    # Upload a file and attach it to a new message
    r = await client.post(
        "/api/v1/feeds/1/files",
        headers=h,
        files={"file": ("pic.png", io.BytesIO(b"\x89PNG"), "image/png")},
    )
    file_id = r.json()["file_id"]

    r = await client.post(
        "/api/v1/feeds/1/messages",
        headers=h,
        json={"body": "Hello with attachment", "attachments": [file_id]},
    )
    assert r.status_code == 201

    # has_file=true should return only the message with attachment
    r = await client.get("/api/v1/messages/search?query=Hello&has_file=true", headers=h)
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 1
    assert results[0]["body"] == "Hello with attachment"

    # has_file=false should exclude the message with attachment
    r = await client.get("/api/v1/messages/search?query=Hello&has_file=false", headers=h)
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 1
    assert results[0]["body"] == "Hello world"
