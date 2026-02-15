async def setup(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    uid = r.json()["user_id"]
    return h, uid


async def test_add_and_remove_device(client):
    h, _ = await setup(client)

    r = await client.post("/api/v1/keys/devices", headers=h, json={"device_id": "dev_abc", "device_name": "Laptop"})
    assert r.status_code == 201
    assert r.json()["device_id"] == "dev_abc"

    r = await client.delete("/api/v1/keys/devices/dev_abc", headers=h)
    assert r.status_code == 204


async def test_upload_and_fetch_prekeys(client):
    h1, uid1 = await setup(client)
    r2 = await client.post("/api/v1/auth/register", json={"username": "bob", "password": "test1234"})
    h2 = {"Authorization": f"Bearer {r2.json()['token']}"}

    # Alice adds device and uploads prekeys
    await client.post("/api/v1/keys/devices", headers=h1, json={"device_id": "dev_a1", "device_name": "Phone"})
    r = await client.put("/api/v1/keys/prekeys", headers=h1, json={
        "identity_key": "aWRrZXk=",
        "signed_prekey": "c3BrZXk=",
        "one_time_prekeys": ["b3RwMQ==", "b3RwMg=="],
    })
    assert r.status_code == 204

    # Bob fetches Alice's prekeys
    r = await client.get(f"/api/v1/keys/prekeys/{uid1}", headers=h2)
    assert r.status_code == 200
    assert r.json()["user_id"] == uid1
    assert len(r.json()["devices"]) == 1
    assert r.json()["devices"][0]["identity_key"] == "aWRrZXk="
    assert r.json()["devices"][0]["one_time_prekey"] == "b3RwMQ=="

    # Second fetch gets next OTP
    r = await client.get(f"/api/v1/keys/prekeys/{uid1}", headers=h2)
    assert r.json()["devices"][0]["one_time_prekey"] == "b3RwMg=="

    # Third fetch - OTPs exhausted
    r = await client.get(f"/api/v1/keys/prekeys/{uid1}", headers=h2)
    assert r.json()["devices"][0]["one_time_prekey"] is None


async def test_key_backup(client):
    h, _ = await setup(client)

    # No backup yet
    r = await client.get("/api/v1/keys/backup", headers=h)
    assert r.status_code == 404

    # Upload
    r = await client.put("/api/v1/keys/backup", headers=h, json={"encrypted_blob": "c2VjcmV0"})
    assert r.status_code == 204

    # Download
    r = await client.get("/api/v1/keys/backup", headers=h)
    assert r.status_code == 200
    assert r.json()["encrypted_blob"] == "c2VjcmV0"

    # Overwrite
    r = await client.put("/api/v1/keys/backup", headers=h, json={"encrypted_blob": "bmV3"})
    assert r.status_code == 204
    r = await client.get("/api/v1/keys/backup", headers=h)
    assert r.json()["encrypted_blob"] == "bmV3"


async def test_initiate_pairing(client):
    h, _ = await setup(client)
    r = await client.post("/api/v1/keys/devices/pair", headers=h, json={"device_name": "Phone", "method": "cpace"})
    assert r.status_code == 201
    assert r.json()["pair_id"].startswith("pair_")
