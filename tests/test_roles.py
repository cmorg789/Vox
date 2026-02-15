async def auth(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user_id"]


async def test_create_and_list_roles(client):
    h, _ = await auth(client)
    r = await client.post("/api/v1/roles", headers=h, json={"name": "Admin", "color": 16711680, "permissions": 9223372036854775807, "position": 0})
    assert r.status_code == 201
    assert r.json()["name"] == "Admin"
    assert r.json()["color"] == 16711680

    r = await client.get("/api/v1/roles", headers=h)
    assert r.status_code == 200
    assert len(r.json()["roles"]) == 1


async def test_update_role(client):
    h, _ = await auth(client)
    r = await client.post("/api/v1/roles", headers=h, json={"name": "Mod", "permissions": 0, "position": 1})
    role_id = r.json()["role_id"]

    r = await client.patch(f"/api/v1/roles/{role_id}", headers=h, json={"name": "Senior Mod", "color": 255})
    assert r.status_code == 200
    assert r.json()["name"] == "Senior Mod"
    assert r.json()["color"] == 255


async def test_delete_role(client):
    h, _ = await auth(client)
    r = await client.post("/api/v1/roles", headers=h, json={"name": "Temp", "permissions": 0, "position": 0})
    role_id = r.json()["role_id"]

    r = await client.delete(f"/api/v1/roles/{role_id}", headers=h)
    assert r.status_code == 204

    r = await client.get("/api/v1/roles", headers=h)
    assert len(r.json()["roles"]) == 0


async def test_assign_and_revoke_role(client):
    h, uid = await auth(client)
    r = await client.post("/api/v1/roles", headers=h, json={"name": "Member", "permissions": 0, "position": 0})
    role_id = r.json()["role_id"]

    r = await client.put(f"/api/v1/members/{uid}/roles/{role_id}", headers=h)
    assert r.status_code == 204

    # Verify role shows on login
    r = await client.post("/api/v1/auth/login", json={"username": "alice", "password": "test1234"})
    assert role_id in r.json()["roles"]

    r = await client.delete(f"/api/v1/members/{uid}/roles/{role_id}", headers=h)
    assert r.status_code == 204


async def test_permission_overrides(client):
    h, _ = await auth(client)
    await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})

    # Set override
    r = await client.put("/api/v1/feeds/1/permissions/role/1", headers=h, json={"allow": 3, "deny": 12})
    assert r.status_code == 204

    # Verify in layout
    r = await client.get("/api/v1/server/layout", headers=h)
    overrides = r.json()["feeds"][0]["permission_overrides"]
    assert len(overrides) == 1
    assert overrides[0]["allow"] == 3
    assert overrides[0]["deny"] == 12

    # Delete override
    r = await client.delete("/api/v1/feeds/1/permissions/role/1", headers=h)
    assert r.status_code == 204

    r = await client.get("/api/v1/server/layout", headers=h)
    assert len(r.json()["feeds"][0]["permission_overrides"]) == 0
