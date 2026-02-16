async def test_gateway_info_no_auth(client):
    r = await client.get("/api/v1/gateway")
    assert r.status_code == 200
    assert r.json()["protocol_version"] == 1
    assert "url" in r.json()
    assert "media_url" in r.json()


async def test_gateway_info_response_schema(client):
    r = await client.get("/api/v1/gateway")
    body = r.json()
    assert isinstance(body["url"], str)
    assert isinstance(body["media_url"], str)
    assert isinstance(body["protocol_version"], int)
    assert isinstance(body["min_version"], int)
    assert isinstance(body["max_version"], int)


async def test_gateway_info_version_ordering(client):
    r = await client.get("/api/v1/gateway")
    body = r.json()
    assert body["min_version"] <= body["protocol_version"] <= body["max_version"]
