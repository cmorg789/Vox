"""Tests for completeness fixes: validation, pagination, device limits,
forum auto-threading, announcement restriction, ban message deletion,
role hierarchy enforcement, and session logout.
"""

import time


# --- Helpers ---

async def auth(client, username="alice"):
    r = await client.post("/api/v1/auth/register", json={"username": username, "password": "test1234", "display_name": username.title()})
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user_id"], r.json()["token"]


async def setup_feed(client, h, name="general", feed_type="text"):
    r = await client.post("/api/v1/feeds", headers=h, json={"name": name, "type": feed_type})
    return r.json()["feed_id"]


# ==========================================================================
# Step 1: Input Validation
# ==========================================================================


async def test_register_username_too_long(client):
    r = await client.post("/api/v1/auth/register", json={
        "username": "a" * 33,
        "password": "test1234",
    })
    assert r.status_code == 422


async def test_register_password_too_short(client):
    r = await client.post("/api/v1/auth/register", json={
        "username": "alice",
        "password": "short",
    })
    assert r.status_code == 422


async def test_register_password_too_long(client):
    r = await client.post("/api/v1/auth/register", json={
        "username": "alice",
        "password": "x" * 129,
    })
    assert r.status_code == 422


async def test_register_display_name_too_long(client):
    r = await client.post("/api/v1/auth/register", json={
        "username": "alice",
        "password": "test1234",
        "display_name": "x" * 65,
    })
    assert r.status_code == 422


async def test_message_body_too_long(client):
    h, _, _ = await auth(client)
    fid = await setup_feed(client, h)
    r = await client.post(f"/api/v1/feeds/{fid}/messages", headers=h, json={"body": "x" * 4001})
    assert r.status_code == 422


async def test_edit_message_body_too_long(client):
    h, _, _ = await auth(client)
    fid = await setup_feed(client, h)
    r = await client.post(f"/api/v1/feeds/{fid}/messages", headers=h, json={"body": "hello"})
    msg_id = r.json()["msg_id"]
    r = await client.patch(f"/api/v1/feeds/{fid}/messages/{msg_id}", headers=h, json={"body": "x" * 4001})
    assert r.status_code == 422


async def test_bulk_delete_too_many(client):
    h, _, _ = await auth(client)
    fid = await setup_feed(client, h)
    r = await client.post(f"/api/v1/feeds/{fid}/messages/bulk-delete", headers=h, json={"msg_ids": list(range(101))})
    assert r.status_code == 422


async def test_update_profile_bio_too_long(client):
    h, uid, _ = await auth(client)
    r = await client.patch(f"/api/v1/users/{uid}", headers=h, json={"bio": "x" * 257})
    assert r.status_code == 422


async def test_update_profile_avatar_too_long(client):
    h, uid, _ = await auth(client)
    r = await client.patch(f"/api/v1/users/{uid}", headers=h, json={"avatar": "x" * 513})
    assert r.status_code == 422


async def test_create_feed_name_too_long(client):
    h, _, _ = await auth(client)
    r = await client.post("/api/v1/feeds", headers=h, json={"name": "x" * 65, "type": "text"})
    assert r.status_code == 422


async def test_create_feed_name_empty(client):
    h, _, _ = await auth(client)
    r = await client.post("/api/v1/feeds", headers=h, json={"name": "", "type": "text"})
    assert r.status_code == 422


async def test_create_role_name_too_long(client):
    h, _, _ = await auth(client)
    r = await client.post("/api/v1/roles", headers=h, json={"name": "x" * 65, "permissions": 0, "position": 5})
    assert r.status_code == 422


async def test_ban_delete_msg_days_too_large(client):
    h, _, _ = await auth(client, "admin")
    _, uid, _ = await auth(client, "bob")
    r = await client.put(f"/api/v1/bans/{uid}", headers=h, json={"reason": "bad", "delete_msg_days": 15})
    assert r.status_code == 422


async def test_ban_delete_msg_days_negative(client):
    h, _, _ = await auth(client, "admin")
    _, uid, _ = await auth(client, "bob")
    r = await client.put(f"/api/v1/bans/{uid}", headers=h, json={"reason": "bad", "delete_msg_days": -1})
    assert r.status_code == 422


async def test_invite_max_uses_too_large(client):
    h, _, _ = await auth(client)
    r = await client.post("/api/v1/invites", headers=h, json={"max_uses": 10001})
    assert r.status_code == 422


async def test_invite_max_age_too_large(client):
    h, _, _ = await auth(client)
    r = await client.post("/api/v1/invites", headers=h, json={"max_age": 2592001})
    assert r.status_code == 422


async def test_group_dm_too_many_recipients(client):
    h, uid, _ = await auth(client)
    r = await client.post("/api/v1/dms", headers=h, json={"recipient_ids": list(range(11))})
    assert r.status_code == 422


async def test_update_server_name_too_long(client):
    h, _, _ = await auth(client)
    r = await client.patch("/api/v1/server", headers=h, json={"name": "x" * 65})
    assert r.status_code == 422


async def test_report_reason_too_long(client):
    h, uid, _ = await auth(client)
    r = await client.post("/api/v1/reports", headers=h, json={
        "reported_user_id": uid,
        "reason": "x" * 65,
    })
    assert r.status_code == 422


async def test_nickname_too_long(client):
    h, uid, _ = await auth(client)
    r = await client.patch(f"/api/v1/members/{uid}", headers=h, json={"nickname": "x" * 65})
    assert r.status_code == 422


# ==========================================================================
# Step 2: Pagination Limit Caps
# ==========================================================================


async def test_feed_messages_limit_capped(client):
    h, _, _ = await auth(client)
    fid = await setup_feed(client, h)
    r = await client.get(f"/api/v1/feeds/{fid}/messages?limit=200", headers=h)
    assert r.status_code == 200  # clamped to runtime limit, not rejected


async def test_feed_messages_limit_zero(client):
    h, _, _ = await auth(client)
    fid = await setup_feed(client, h)
    r = await client.get(f"/api/v1/feeds/{fid}/messages?limit=0", headers=h)
    assert r.status_code == 422


async def test_members_limit_capped(client):
    h, _, _ = await auth(client)
    r = await client.get("/api/v1/members?limit=300", headers=h)
    assert r.status_code == 200  # clamped to runtime limit, not rejected


async def test_search_limit_capped(client):
    h, _, _ = await auth(client)
    r = await client.get("/api/v1/messages/search?query=test&limit=200", headers=h)
    assert r.status_code == 200  # clamped to runtime limit, not rejected


async def test_valid_pagination_limit(client):
    h, _, _ = await auth(client)
    fid = await setup_feed(client, h)
    r = await client.get(f"/api/v1/feeds/{fid}/messages?limit=1", headers=h)
    assert r.status_code == 200


# ==========================================================================
# Step 3: Device Limit Enforcement
# ==========================================================================


async def test_device_limit(client):
    from vox.ratelimit import reset as reset_ratelimit
    h, _, _ = await auth(client)
    # Add MAX_DEVICES (10) devices
    for i in range(10):
        reset_ratelimit()  # prevent rate limiting from interfering
        r = await client.post("/api/v1/keys/devices", headers=h, json={"device_id": f"dev_{i}", "device_name": f"Device {i}"})
        assert r.status_code == 201, f"Failed on device {i}: {r.status_code}"

    # 11th device should fail
    reset_ratelimit()
    r = await client.post("/api/v1/keys/devices", headers=h, json={"device_id": "dev_10", "device_name": "Device 10"})
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "DEVICE_LIMIT_REACHED"


async def test_device_limit_after_removal(client):
    from vox.ratelimit import reset as reset_ratelimit
    h, _, _ = await auth(client)
    for i in range(10):
        reset_ratelimit()
        await client.post("/api/v1/keys/devices", headers=h, json={"device_id": f"dev_{i}", "device_name": f"Device {i}"})

    # Remove one device
    reset_ratelimit()
    r = await client.delete("/api/v1/keys/devices/dev_0", headers=h)
    assert r.status_code == 204

    # Now adding one more should work
    reset_ratelimit()
    r = await client.post("/api/v1/keys/devices", headers=h, json={"device_id": "dev_new", "device_name": "New Device"})
    assert r.status_code == 201


# ==========================================================================
# Step 4: Forum Feed Auto-Threading
# ==========================================================================


async def test_forum_feed_auto_creates_thread(client):
    h, _, _ = await auth(client)
    fid = await setup_feed(client, h, name="forum-feed", feed_type="forum")

    # Send a message in the forum feed
    r = await client.post(f"/api/v1/feeds/{fid}/messages", headers=h, json={"body": "My forum post"})
    assert r.status_code == 201

    # The server layout should show a thread was created
    from vox.db.engine import get_session_factory
    from vox.db.models import Thread
    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(select(Thread).where(Thread.feed_id == fid))
        threads = result.scalars().all()
        assert len(threads) == 1
        assert threads[0].name == "My forum post"


async def test_text_feed_no_auto_thread(client):
    h, _, _ = await auth(client)
    fid = await setup_feed(client, h, name="text-feed", feed_type="text")

    r = await client.post(f"/api/v1/feeds/{fid}/messages", headers=h, json={"body": "Normal message"})
    assert r.status_code == 201

    from vox.db.engine import get_session_factory
    from vox.db.models import Thread
    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(select(Thread).where(Thread.feed_id == fid))
        threads = result.scalars().all()
        assert len(threads) == 0


# ==========================================================================
# Step 5: Announcement Feed Write Restriction
# ==========================================================================


async def test_announcement_feed_admin_can_post(client):
    h, _, _ = await auth(client)  # First user = admin
    fid = await setup_feed(client, h, name="announcements", feed_type="announcement")

    r = await client.post(f"/api/v1/feeds/{fid}/messages", headers=h, json={"body": "Important news"})
    assert r.status_code == 201


async def test_announcement_feed_non_mod_cannot_post(client):
    h_admin, _, _ = await auth(client, "admin")
    fid = await setup_feed(client, h_admin, name="announcements", feed_type="announcement")

    # Register a normal user (not admin)
    h_user, _, _ = await auth(client, "user")

    r = await client.post(f"/api/v1/feeds/{fid}/messages", headers=h_user, json={"body": "Try to post"})
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "FORBIDDEN"


# ==========================================================================
# Step 6: Ban delete_msg_days Implementation
# ==========================================================================


async def test_ban_deletes_messages(client):
    h_admin, _, _ = await auth(client, "admin")
    h_bob, uid_bob, _ = await auth(client, "bob")
    fid = await setup_feed(client, h_admin, name="general")

    # Bob sends some messages
    for i in range(3):
        r = await client.post(f"/api/v1/feeds/{fid}/messages", headers=h_bob, json={"body": f"Bob message {i}"})
        assert r.status_code == 201

    # Verify messages exist
    r = await client.get(f"/api/v1/feeds/{fid}/messages", headers=h_admin)
    msgs_before = [m for m in r.json()["messages"] if m["author_id"] == uid_bob]
    assert len(msgs_before) == 3

    # Ban bob with delete_msg_days=1
    r = await client.put(f"/api/v1/bans/{uid_bob}", headers=h_admin, json={"reason": "Spam", "delete_msg_days": 1})
    assert r.status_code == 200

    # Verify messages were deleted
    r = await client.get(f"/api/v1/feeds/{fid}/messages", headers=h_admin)
    msgs_after = [m for m in r.json()["messages"] if m["author_id"] == uid_bob]
    assert len(msgs_after) == 0


async def test_ban_without_delete_keeps_messages(client):
    h_admin, _, _ = await auth(client, "admin")
    h_bob, uid_bob, _ = await auth(client, "bob")
    fid = await setup_feed(client, h_admin, name="general")

    # Bob sends a message
    r = await client.post(f"/api/v1/feeds/{fid}/messages", headers=h_bob, json={"body": "Bob message"})
    assert r.status_code == 201

    # Ban bob without delete_msg_days
    r = await client.put(f"/api/v1/bans/{uid_bob}", headers=h_admin, json={"reason": "Spam"})
    assert r.status_code == 200

    # Messages should still be there
    r = await client.get(f"/api/v1/feeds/{fid}/messages", headers=h_admin)
    msgs = [m for m in r.json()["messages"] if m["author_id"] == uid_bob]
    assert len(msgs) == 1


# ==========================================================================
# Step 7: Role Hierarchy Enforcement
# ==========================================================================


async def test_role_hierarchy_kick_blocked(client):
    """A lower-ranked user cannot kick a higher-ranked user."""
    h_admin, admin_uid, _ = await auth(client, "admin")
    h_mod, mod_uid, _ = await auth(client, "mod")

    # Create mod role at position 5 (lower rank than admin at position 1)
    r = await client.post("/api/v1/roles", headers=h_admin, json={"name": "Moderator", "permissions": (1 << 29), "position": 5})
    mod_role_id = r.json()["role_id"]

    # Assign mod role to mod user
    r = await client.put(f"/api/v1/members/{mod_uid}/roles/{mod_role_id}", headers=h_admin)
    assert r.status_code == 204

    # Mod tries to kick admin -> should fail
    r = await client.delete(f"/api/v1/members/{admin_uid}", headers=h_mod)
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "ROLE_HIERARCHY"


async def test_role_hierarchy_kick_allowed(client):
    """A higher-ranked user can kick a lower-ranked user."""
    h_admin, _, _ = await auth(client, "admin")
    h_user, user_uid, _ = await auth(client, "user")

    # Admin kicks user (no special role) -> should succeed
    r = await client.delete(f"/api/v1/members/{user_uid}", headers=h_admin)
    assert r.status_code == 204


async def test_role_hierarchy_ban_blocked(client):
    """A lower-ranked user cannot ban a higher-ranked user."""
    h_admin, admin_uid, _ = await auth(client, "admin")
    h_mod, mod_uid, _ = await auth(client, "mod")

    r = await client.post("/api/v1/roles", headers=h_admin, json={"name": "Moderator", "permissions": (1 << 30), "position": 5})
    mod_role_id = r.json()["role_id"]
    await client.put(f"/api/v1/members/{mod_uid}/roles/{mod_role_id}", headers=h_admin)

    # Mod tries to ban admin -> should fail
    r = await client.put(f"/api/v1/bans/{admin_uid}", headers=h_mod, json={"reason": "test"})
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "ROLE_HIERARCHY"


async def test_role_hierarchy_non_admin_cannot_edit_higher_role(client):
    """A non-admin user cannot edit a role at or above their own position."""
    h_admin, _, _ = await auth(client, "admin")
    h_mod, mod_uid, _ = await auth(client, "mod")

    # Create two roles: mod at position 5, senior at position 3
    r = await client.post("/api/v1/roles", headers=h_admin, json={"name": "Moderator", "permissions": (1 << 25), "position": 5})
    mod_role_id = r.json()["role_id"]
    r = await client.post("/api/v1/roles", headers=h_admin, json={"name": "Senior", "permissions": 0, "position": 3})
    senior_role_id = r.json()["role_id"]

    await client.put(f"/api/v1/members/{mod_uid}/roles/{mod_role_id}", headers=h_admin)

    # Mod tries to edit senior role (higher rank) -> should fail
    r = await client.patch(f"/api/v1/roles/{senior_role_id}", headers=h_mod, json={"name": "Renamed"})
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "ROLE_HIERARCHY"


async def test_role_hierarchy_non_admin_cannot_assign_higher_role(client):
    """A non-admin user cannot assign a role at or above their own position."""
    h_admin, _, _ = await auth(client, "admin")
    h_mod, mod_uid, _ = await auth(client, "mod")
    _, user_uid, _ = await auth(client, "user")

    r = await client.post("/api/v1/roles", headers=h_admin, json={"name": "Moderator", "permissions": (1 << 25), "position": 5})
    mod_role_id = r.json()["role_id"]
    r = await client.post("/api/v1/roles", headers=h_admin, json={"name": "Senior", "permissions": 0, "position": 3})
    senior_role_id = r.json()["role_id"]

    await client.put(f"/api/v1/members/{mod_uid}/roles/{mod_role_id}", headers=h_admin)

    # Mod tries to assign senior role -> should fail
    r = await client.put(f"/api/v1/members/{user_uid}/roles/{senior_role_id}", headers=h_mod)
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "ROLE_HIERARCHY"


# ==========================================================================
# Step 8: Session Logout
# ==========================================================================


async def test_logout_invalidates_token(client):
    h, _, token = await auth(client)

    # Token works before logout
    r = await client.get("/api/v1/members", headers=h)
    assert r.status_code == 200

    # Logout
    r = await client.post("/api/v1/auth/logout", headers=h)
    assert r.status_code == 204

    # Token should no longer work
    r = await client.get("/api/v1/members", headers=h)
    assert r.status_code == 401


async def test_logout_only_invalidates_current_session(client):
    # Register user
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    token1 = r.json()["token"]
    h1 = {"Authorization": f"Bearer {token1}"}

    # Login again to get a second token
    r = await client.post("/api/v1/auth/login", json={"username": "alice", "password": "test1234"})
    token2 = r.json()["token"]
    h2 = {"Authorization": f"Bearer {token2}"}

    # Logout with first token
    r = await client.post("/api/v1/auth/logout", headers=h1)
    assert r.status_code == 204

    # First token should be invalid
    r = await client.get("/api/v1/members", headers=h1)
    assert r.status_code == 401

    # Second token should still work
    r = await client.get("/api/v1/members", headers=h2)
    assert r.status_code == 200
