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
    h1, uid1, _, _ = await setup(client)

    r = await client.get(f"/api/v1/users/{uid1}/dm-settings", headers=h1)
    assert r.status_code == 200
    assert r.json()["dm_permission"] == "everyone"

    r = await client.patch(f"/api/v1/users/{uid1}/dm-settings", headers=h1, json={"dm_permission": "friends_only"})
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
    assert r.json()["error"]["code"] == "MESSAGE_NOT_FOUND"


async def test_edit_dm_message_wrong_author(client):
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "alice's msg"})
    msg_id = r.json()["msg_id"]

    # Bob tries to edit alice's message
    r = await client.patch(f"/api/v1/dms/{dm_id}/messages/{msg_id}", headers=h2, json={"body": "hacked"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


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

    # Non-existent DM returns 403 (participant check) — doesn't leak existence
    r = await client.patch("/api/v1/dms/99999", headers=h1, json={"name": "New"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "NOT_DM_PARTICIPANT"


async def test_send_dm_message_invalid_attachment(client):
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "hi", "attachments": ["nonexistent_file_id"]})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_ATTACHMENT"


async def test_open_dm_blocked(client):
    """Opening a DM when blocked by recipient returns 403."""
    h1, uid1, h2, uid2 = await setup(client)
    # Bob blocks Alice
    await client.put(f"/api/v1/users/{uid2}/blocks/{uid1}", headers=h2)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "USER_BLOCKED"


async def test_open_dm_permission_nobody(client):
    """Opening a DM when recipient has dm_permission=nobody returns 403."""
    h1, uid1, h2, uid2 = await setup(client)
    await client.patch(f"/api/v1/users/{uid2}/dm-settings", headers=h2, json={"dm_permission": "nobody"})
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "DM_PERMISSION_DENIED"


async def test_open_dm_permission_friends_only(client):
    """Opening a DM when recipient has friends_only and sender is not a friend returns 403."""
    h1, uid1, h2, uid2 = await setup(client)
    await client.patch(f"/api/v1/users/{uid2}/dm-settings", headers=h2, json={"dm_permission": "friends_only"})
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "DM_PERMISSION_DENIED"


async def test_open_dm_friends_only_accepted(client):
    """Opening a DM with friends_only succeeds when users are accepted friends."""
    h1, uid1, h2, uid2 = await setup(client)
    await client.patch(f"/api/v1/users/{uid2}/dm-settings", headers=h2, json={"dm_permission": "friends_only"})
    # Bob sends friend request to Alice, Alice accepts
    await client.put(f"/api/v1/users/{uid2}/friends/{uid1}", headers=h2)
    await client.post(f"/api/v1/users/{uid1}/friends/{uid2}/accept", headers=h1)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    assert r.status_code == 201


async def test_open_dm_no_recipient(client):
    """Opening a DM without recipient_id or recipient_ids returns 400."""
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={})
    assert r.status_code == 400


async def test_list_dms_with_after(client):
    """Pagination cursor works for DM listing."""
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.get(f"/api/v1/dms?after={dm_id}", headers=h1)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 0


async def test_update_group_dm_icon(client):
    """Updating group DM icon works."""
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_ids": [uid2], "name": "Group"})
    dm_id = r.json()["dm_id"]

    r = await client.patch(f"/api/v1/dms/{dm_id}", headers=h1, json={"icon": "new_icon.png"})
    assert r.status_code == 200


async def test_add_dm_recipient_not_participant(client):
    """Adding a recipient when caller is not a participant returns 403."""
    h1, uid1, h2, uid2 = await setup(client)
    r3 = await client.post("/api/v1/auth/register", json={"username": "charlie", "password": "test1234"})
    h3 = {"Authorization": f"Bearer {r3.json()['token']}"}
    uid3 = r3.json()["user_id"]

    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_ids": [uid2], "name": "Group"})
    dm_id = r.json()["dm_id"]

    # Charlie (not a participant) tries to add
    r = await client.put(f"/api/v1/dms/{dm_id}/recipients/{uid2}", headers=h3)
    assert r.status_code == 403


async def test_remove_dm_recipient_not_participant(client):
    """Removing a recipient when caller is not a participant returns 403."""
    h1, uid1, h2, uid2 = await setup(client)
    r3 = await client.post("/api/v1/auth/register", json={"username": "charlie", "password": "test1234"})
    h3 = {"Authorization": f"Bearer {r3.json()['token']}"}
    uid3 = r3.json()["user_id"]

    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_ids": [uid2], "name": "Group"})
    dm_id = r.json()["dm_id"]

    r = await client.delete(f"/api/v1/dms/{dm_id}/recipients/{uid2}", headers=h3)
    assert r.status_code == 403


async def test_dm_read_receipt_update_existing(client):
    """Sending a read receipt twice updates the existing state."""
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "msg1"})
    msg1_id = r.json()["msg_id"]
    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "msg2"})
    msg2_id = r.json()["msg_id"]

    r = await client.post(f"/api/v1/dms/{dm_id}/read", headers=h2, json={"up_to_msg_id": msg1_id})
    assert r.status_code == 204
    r = await client.post(f"/api/v1/dms/{dm_id}/read", headers=h2, json={"up_to_msg_id": msg2_id})
    assert r.status_code == 204


async def test_get_dm_messages_pagination(client):
    """DM message pagination with before/after params."""
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "msg1"})
    msg1_id = r.json()["msg_id"]
    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "msg2"})
    msg2_id = r.json()["msg_id"]

    r = await client.get(f"/api/v1/dms/{dm_id}/messages?before={msg2_id}", headers=h1)
    assert r.status_code == 200
    assert len(r.json()["messages"]) == 1

    r = await client.get(f"/api/v1/dms/{dm_id}/messages?after={msg1_id}", headers=h1)
    assert r.status_code == 200
    assert len(r.json()["messages"]) == 1


async def test_dm_reactions(client):
    """Add and remove DM reactions."""
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "react to this"})
    msg_id = r.json()["msg_id"]

    # Add reaction
    r = await client.put(f"/api/v1/dms/{dm_id}/messages/{msg_id}/reactions/%F0%9F%91%8D", headers=h1)
    assert r.status_code == 204

    # Remove reaction
    r = await client.delete(f"/api/v1/dms/{dm_id}/messages/{msg_id}/reactions/%F0%9F%91%8D", headers=h1)
    assert r.status_code == 204


async def test_dm_reaction_not_participant(client):
    """Non-participant cannot add DM reactions."""
    h1, uid1, h2, uid2 = await setup(client)
    r3 = await client.post("/api/v1/auth/register", json={"username": "charlie", "password": "test1234"})
    h3 = {"Authorization": f"Bearer {r3.json()['token']}"}

    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]
    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "hi"})
    msg_id = r.json()["msg_id"]

    r = await client.put(f"/api/v1/dms/{dm_id}/messages/{msg_id}/reactions/%F0%9F%91%8D", headers=h3)
    assert r.status_code == 403


async def test_dm_reaction_message_not_found(client):
    """Reaction on non-existent message returns 404."""
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.put(f"/api/v1/dms/{dm_id}/messages/999999/reactions/%F0%9F%91%8D", headers=h1)
    assert r.status_code == 404


async def test_dm_remove_reaction_not_participant(client):
    """Non-participant cannot remove DM reactions."""
    h1, uid1, h2, uid2 = await setup(client)
    r3 = await client.post("/api/v1/auth/register", json={"username": "charlie", "password": "test1234"})
    h3 = {"Authorization": f"Bearer {r3.json()['token']}"}

    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]
    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": "hi"})
    msg_id = r.json()["msg_id"]

    r = await client.delete(f"/api/v1/dms/{dm_id}/messages/{msg_id}/reactions/%F0%9F%91%8D", headers=h3)
    assert r.status_code == 403


async def test_dm_remove_reaction_message_not_found(client):
    """Remove reaction on non-existent message returns 404."""
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r = await client.delete(f"/api/v1/dms/{dm_id}/messages/999999/reactions/%F0%9F%91%8D", headers=h1)
    assert r.status_code == 404


async def test_update_dm_settings_existing(client):
    """Updating DM settings when a row already exists."""
    h1, uid1, _, _ = await setup(client)
    await client.patch(f"/api/v1/users/{uid1}/dm-settings", headers=h1, json={"dm_permission": "friends_only"})
    r = await client.patch(f"/api/v1/users/{uid1}/dm-settings", headers=h1, json={"dm_permission": "nobody"})
    assert r.status_code == 200
    assert r.json()["dm_permission"] == "nobody"


async def test_send_dm_not_participant(client):
    """Non-participant cannot send messages to a DM."""
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    # Register a third user who is NOT a participant
    r3 = await client.post("/api/v1/auth/register", json={"username": "charlie", "password": "test1234"})
    h3 = {"Authorization": f"Bearer {r3.json()['token']}"}

    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h3, json={"body": "hi"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "NOT_DM_PARTICIPANT"


async def test_get_dm_messages_not_participant(client):
    """Non-participant cannot read messages from a DM."""
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r3 = await client.post("/api/v1/auth/register", json={"username": "charlie", "password": "test1234"})
    h3 = {"Authorization": f"Bearer {r3.json()['token']}"}

    r = await client.get(f"/api/v1/dms/{dm_id}/messages", headers=h3)
    assert r.status_code == 403


async def test_close_dm_not_participant(client):
    """Non-participant cannot close a DM."""
    h1, uid1, h2, uid2 = await setup(client)
    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    r3 = await client.post("/api/v1/auth/register", json={"username": "charlie", "password": "test1234"})
    h3 = {"Authorization": f"Bearer {r3.json()['token']}"}

    r = await client.delete(f"/api/v1/dms/{dm_id}", headers=h3)
    assert r.status_code == 403


async def test_update_group_dm_not_participant(client):
    """Non-participant cannot update a group DM."""
    h1, uid1, h2, uid2 = await setup(client)
    r3 = await client.post("/api/v1/auth/register", json={"username": "charlie", "password": "test1234"})
    uid3 = r3.json()["user_id"]

    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_ids": [uid2, uid3], "name": "Group"})
    dm_id = r.json()["dm_id"]

    # Register a fourth user who is NOT a participant
    r4 = await client.post("/api/v1/auth/register", json={"username": "dave", "password": "test1234"})
    h4 = {"Authorization": f"Bearer {r4.json()['token']}"}

    r = await client.patch(f"/api/v1/dms/{dm_id}", headers=h4, json={"name": "test"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "NOT_DM_PARTICIPANT"
