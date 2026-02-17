async def auth(client, username="alice"):
    r = await client.post("/api/v1/auth/register", json={"username": username, "password": "test1234"})
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user_id"]


async def test_create_and_list_roles(client):
    h, _ = await auth(client)
    r = await client.post("/api/v1/roles", headers=h, json={"name": "Admin", "color": 16711680, "permissions": 9223372036854775807, "position": 0})
    assert r.status_code == 201
    assert r.json()["name"] == "Admin"
    assert r.json()["color"] == 16711680

    r = await client.get("/api/v1/roles", headers=h)
    assert r.status_code == 200
    names = [role["name"] for role in r.json()["items"]]
    assert "Admin" in names


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
    names = [role["name"] for role in r.json()["items"]]
    assert "Temp" not in names


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


async def test_permission_override_update_existing(client):
    """Updating an existing feed permission override works."""
    h, _ = await auth(client)
    await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})

    # Set initial override
    r = await client.put("/api/v1/feeds/1/permissions/role/1", headers=h, json={"allow": 3, "deny": 12})
    assert r.status_code == 204

    # Update the same override
    r = await client.put("/api/v1/feeds/1/permissions/role/1", headers=h, json={"allow": 7, "deny": 0})
    assert r.status_code == 204

    r = await client.get("/api/v1/server/layout", headers=h)
    overrides = r.json()["feeds"][0]["permission_overrides"]
    assert len(overrides) == 1
    assert overrides[0]["allow"] == 7


async def test_room_permission_overrides(client):
    """Set and delete room permission overrides."""
    h, _ = await auth(client)
    r = await client.post("/api/v1/rooms", headers=h, json={"name": "Voice", "type": "voice"})
    room_id = r.json()["room_id"]

    # Set room override
    r = await client.put(f"/api/v1/rooms/{room_id}/permissions/role/1", headers=h, json={"allow": 5, "deny": 10})
    assert r.status_code == 204

    # Update existing room override
    r = await client.put(f"/api/v1/rooms/{room_id}/permissions/role/1", headers=h, json={"allow": 15, "deny": 0})
    assert r.status_code == 204

    # Delete room override
    r = await client.delete(f"/api/v1/rooms/{room_id}/permissions/role/1", headers=h)
    assert r.status_code == 204


async def test_role_not_found(client):
    """Operations on non-existent role return 404."""
    h, _ = await auth(client)

    r = await client.patch("/api/v1/roles/99999", headers=h, json={"name": "Ghost"})
    assert r.status_code == 404

    r = await client.delete("/api/v1/roles/99999", headers=h)
    assert r.status_code == 404


async def test_update_role_permissions_and_position(client):
    """Update role permissions and position fields."""
    h, _ = await auth(client)
    r = await client.post("/api/v1/roles", headers=h, json={"name": "Mod", "permissions": 0, "position": 1})
    role_id = r.json()["role_id"]

    r = await client.patch(f"/api/v1/roles/{role_id}", headers=h, json={"permissions": 255, "position": 2})
    assert r.status_code == 200
    assert r.json()["permissions"] == 255
    assert r.json()["position"] == 2


async def test_list_roles_pagination(client):
    """List roles with after cursor."""
    h, _ = await auth(client)
    await client.post("/api/v1/roles", headers=h, json={"name": "Role1", "permissions": 0, "position": 1})
    await client.post("/api/v1/roles", headers=h, json={"name": "Role2", "permissions": 0, "position": 2})

    r = await client.get("/api/v1/roles?after=1", headers=h)
    assert r.status_code == 200
    # Should not include roles with id <= 1
    for item in r.json()["items"]:
        assert item["role_id"] > 1


async def test_assign_role_not_found(client):
    """Assigning a non-existent role returns 404."""
    h, uid = await auth(client)
    r = await client.put(f"/api/v1/members/{uid}/roles/99999", headers=h)
    assert r.status_code == 404


async def test_revoke_role_not_found(client):
    """Revoking a non-existent role returns 404."""
    h, uid = await auth(client)
    r = await client.delete(f"/api/v1/members/{uid}/roles/99999", headers=h)
    assert r.status_code == 404


async def test_list_role_members(client):
    """GET /api/v1/roles/{id}/members returns assigned users with pagination."""
    h_admin, admin_uid = await auth(client, "admin")
    _, bob_uid = await auth(client, "bob")

    # Create a role
    r = await client.post("/api/v1/roles", headers=h_admin, json={"name": "Testers", "permissions": 0, "position": 5})
    assert r.status_code == 201
    role_id = r.json()["role_id"]

    # Assign both users to the role
    r = await client.put(f"/api/v1/members/{admin_uid}/roles/{role_id}", headers=h_admin)
    assert r.status_code == 204
    r = await client.put(f"/api/v1/members/{bob_uid}/roles/{role_id}", headers=h_admin)
    assert r.status_code == 204

    # List members
    r = await client.get(f"/api/v1/roles/{role_id}/members", headers=h_admin)
    assert r.status_code == 200
    member_ids = [m["user_id"] for m in r.json()["items"]]
    assert admin_uid in member_ids
    assert bob_uid in member_ids
    assert r.json()["cursor"] is not None

    # Pagination: after first user
    first_id = r.json()["items"][0]["user_id"]
    r = await client.get(f"/api/v1/roles/{role_id}/members?after={first_id}", headers=h_admin)
    assert r.status_code == 200
    for m in r.json()["items"]:
        assert m["user_id"] > first_id


async def test_list_role_members_not_found(client):
    """GET members of non-existent role returns 404."""
    h, _ = await auth(client)
    r = await client.get("/api/v1/roles/99999/members", headers=h)
    assert r.status_code == 404


async def test_revoke_role_hierarchy(client):
    """Non-admin cannot revoke a role at or above their own rank (403 ROLE_HIERARCHY)."""
    h_admin, admin_uid = await auth(client, "admin")
    h_mod, mod_uid = await auth(client, "moderator")

    # Create a low-rank (high position number) role for the moderator - gives MANAGE_ROLES
    from vox.permissions import MANAGE_ROLES
    r = await client.post("/api/v1/roles", headers=h_admin, json={
        "name": "Mod", "permissions": MANAGE_ROLES, "position": 10,
    })
    mod_role_id = r.json()["role_id"]

    # Create a high-rank role (low position number) that outranks the mod
    r = await client.post("/api/v1/roles", headers=h_admin, json={
        "name": "Senior", "permissions": 0, "position": 1,
    })
    senior_role_id = r.json()["role_id"]

    # Assign mod role to moderator
    await client.put(f"/api/v1/members/{mod_uid}/roles/{mod_role_id}", headers=h_admin)
    # Assign senior role to admin
    await client.put(f"/api/v1/members/{admin_uid}/roles/{senior_role_id}", headers=h_admin)

    # Moderator tries to revoke the senior role from admin -> should get 403
    r = await client.delete(f"/api/v1/members/{admin_uid}/roles/{senior_role_id}", headers=h_mod)
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "ROLE_HIERARCHY"


async def test_set_permission_override_invalid_target_type(client):
    """Setting a permission override with an invalid target type returns 400."""
    h, _ = await auth(client)
    await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})

    r = await client.put("/api/v1/feeds/1/permissions/badtype/1", headers=h, json={"allow": 3, "deny": 0})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "INVALID_TARGET_TYPE"
