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


async def test_search_by_author(client):
    h = await setup(client)
    r = await client.get("/api/v1/messages/search?query=Hello&author_id=1", headers=h)
    assert r.status_code == 200
    assert len(r.json()["results"]) == 1


async def test_search_before_after(client):
    h = await setup(client)
    # Get all messages to find IDs
    r = await client.get("/api/v1/messages/search?query=world", headers=h)
    results = r.json()["results"]
    assert len(results) == 2
    ids = sorted(m["msg_id"] for m in results)

    # before: only messages before the last one
    r = await client.get(f"/api/v1/messages/search?query=world&before={ids[1]}", headers=h)
    assert len(r.json()["results"]) == 1

    # after: only messages after the first one
    r = await client.get(f"/api/v1/messages/search?query=world&after={ids[0]}", headers=h)
    assert len(r.json()["results"]) == 1


async def test_search_pinned(client):
    h = await setup(client)
    # Pin a message
    r = await client.get("/api/v1/messages/search?query=Hello", headers=h)
    msg_id = r.json()["results"][0]["msg_id"]
    await client.put(f"/api/v1/feeds/1/pins/{msg_id}", headers=h)

    r = await client.get("/api/v1/messages/search?query=Hello&pinned=true", headers=h)
    assert r.status_code == 200
    assert len(r.json()["results"]) == 1


async def test_search_has_embed(client):
    h = await setup(client)
    # has_embed=true should return nothing (no embeds in test data)
    r = await client.get("/api/v1/messages/search?query=Hello&has_embed=true", headers=h)
    assert r.status_code == 200
    assert len(r.json()["results"]) == 0

    # has_embed=false should return match
    r = await client.get("/api/v1/messages/search?query=Hello&has_embed=false", headers=h)
    assert r.status_code == 200
    assert len(r.json()["results"]) == 1
