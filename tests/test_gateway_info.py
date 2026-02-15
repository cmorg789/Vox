async def test_gateway_info_no_auth(client):
    r = await client.get("/api/v1/gateway")
    assert r.status_code == 200
    assert r.json()["protocol_version"] == 1
    assert "url" in r.json()
    assert "media_url" in r.json()
