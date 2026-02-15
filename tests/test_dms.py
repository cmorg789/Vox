async def setup(client):
    r1 = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    r2 = await client.post("/api/v1/auth/register", json={"username": "bob", "password": "test1234"})
    h1 = {"Authorization": f"Bearer {r1.json()['token']}"}
    h2 = {"Authorization": f"Bearer {r2.json()['token']}"}
    return h1, r1.json()["user_id"], h2, r2.json()["user_id"]


async def test_open_1v1_dm(client):
    h1, _, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    assert r.status_code == 201
    assert r.json()["is_group"] is False
    assert set(r.json()["participant_ids"]) == {1, uid2}


async def test_open_1v1_dm_idempotent(client):
    h1, _, h2, uid2 = await setup(client)
    r1 = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    r2 = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    assert r1.json()["dm_id"] == r2.json()["dm_id"]


async def test_open_group_dm(client):
    h1, uid1, h2, uid2 = await setup(client)
    r3 = await client.post("/api/v1/auth/register", json={"username": "charlie", "password": "test1234"})
    uid3 = r3.json()["user_id"]

    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_ids": [uid2, uid3], "name": "Team"})
    assert r.status_code == 201
    assert r.json()["is_group"] is True
    assert r.json()["name"] == "Team"
    assert len(r.json()["participant_ids"]) == 3


async def test_list_dms(client):
    h1, _, h2, uid2 = await setup(client)
    await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})

    r = await client.get("/api/v1/dms", headers=h1)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1


async def test_close_dm(client):
    h1, _, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.delete(f"/api/v1/dms/{dm_id}", headers=h1)
    assert r.status_code == 204

    r = await client.get("/api/v1/dms", headers=h1)
    assert len(r.json()["items"]) == 0


async def test_dm_messages(client):
    h1, _, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "Hello Bob!"})
    assert r.status_code == 201

    r = await client.get(f"/api/v1/dms/{dm_id}/messages", headers=h2)
    assert len(r.json()["messages"]) == 1
    assert r.json()["messages"][0]["body"] == "Hello Bob!"


async def test_dm_read_receipt(client):
    h1, _, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]
    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "Hi"})
    msg_id = r.json()["msg_id"]

    r = await client.post(f"/api/v1/dms/{dm_id}/read", headers=h2, json={"up_to_msg_id": msg_id})
    assert r.status_code == 204


async def test_dm_settings(client):
    h1, _, _, _ = await setup(client)

    r = await client.get("/api/v1/users/@me/dm-settings", headers=h1)
    assert r.status_code == 200
    assert r.json()["dm_permission"] == "everyone"

    r = await client.patch("/api/v1/users/@me/dm-settings", headers=h1, json={"dm_permission": "friends_only"})
    assert r.status_code == 200
    assert r.json()["dm_permission"] == "friends_only"


async def test_update_group_dm(client):
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_ids": [uid2], "name": "Old"})
    dm_id = r.json()["dm_id"]

    r = await client.patch(f"/api/v1/dms/{dm_id}", headers=h1, json={"name": "New Name"})
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"


async def test_add_dm_recipient(client):
    h1, uid1, h2, uid2 = await setup(client)
    r3 = await client.post("/api/v1/auth/register", json={"username": "charlie", "password": "test1234"})
    uid3 = r3.json()["user_id"]

    # Create group DM
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_ids": [uid2], "name": "Group"})
    dm_id = r.json()["dm_id"]

    # Add charlie
    r = await client.put(f"/api/v1/dms/{dm_id}/recipients/{uid3}", headers=h1)
    assert r.status_code == 204


async def test_remove_dm_recipient(client):
    h1, uid1, h2, uid2 = await setup(client)
    r3 = await client.post("/api/v1/auth/register", json={"username": "charlie", "password": "test1234"})
    uid3 = r3.json()["user_id"]

    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_ids": [uid2, uid3], "name": "Group"})
    dm_id = r.json()["dm_id"]

    # Remove charlie
    r = await client.delete(f"/api/v1/dms/{dm_id}/recipients/{uid3}", headers=h1)
    assert r.status_code == 204


async def test_edit_dm_message(client):
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "original"})
    msg_id = r.json()["msg_id"]

    # Edit own message
    r = await client.patch(f"/api/v1/dms/{dm_id}/messages/{msg_id}", headers=h1, json={"body": "edited"})
    assert r.status_code == 200
    assert r.json()["edit_timestamp"] is not None


async def test_edit_dm_message_not_found(client):
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.patch(f"/api/v1/dms/{dm_id}/messages/999999", headers=h1, json={"body": "edited"})
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "MESSAGE_NOT_FOUND"


async def test_edit_dm_message_wrong_author(client):
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "alice's msg"})
    msg_id = r.json()["msg_id"]

    # Bob tries to edit alice's message
    r = await client.patch(f"/api/v1/dms/{dm_id}/messages/{msg_id}", headers=h2, json={"body": "hacked"})
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "FORBIDDEN"


async def test_delete_dm_message(client):
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "to delete"})
    msg_id = r.json()["msg_id"]

    r = await client.delete(f"/api/v1/dms/{dm_id}/messages/{msg_id}", headers=h1)
    assert r.status_code == 204


async def test_delete_dm_message_not_found(client):
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.delete(f"/api/v1/dms/{dm_id}/messages/999999", headers=h1)
    assert r.status_code == 404


async def test_delete_dm_message_wrong_author(client):
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "alice's msg"})
    msg_id = r.json()["msg_id"]

    r = await client.delete(f"/api/v1/dms/{dm_id}/messages/{msg_id}", headers=h2)
    assert r.status_code == 403


async def test_update_group_dm_not_found(client):
    h1, uid1, h2, uid2 = await setup(client)

    r = await client.patch("/api/v1/dms/99999", headers=h1, json={"name": "New"})
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "SPACE_NOT_FOUND"


async def test_send_dm_message_invalid_attachment(client):
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "hi", "attachments": ["nonexistent_file_id"]})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "INVALID_ATTACHMENT"
