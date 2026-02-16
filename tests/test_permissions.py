"""Tests for the permission resolver and endpoint enforcement."""

import pytest

from vox.permissions import (
    ADMINISTRATOR,
    ALL_PERMISSIONS,
    BAN_MEMBERS,
    CHANGE_NICKNAME,
    CONNECT,
    CREATE_INVITES,
    CREATE_THREADS,
    EVERYONE_DEFAULTS,
    KICK_MEMBERS,
    MANAGE_2FA,
    MANAGE_EMOJI,
    MANAGE_MESSAGES,
    MANAGE_ROLES,
    MANAGE_SERVER,
    MANAGE_SPACES,
    MANAGE_THREADS,
    MANAGE_WEBHOOKS,
    READ_HISTORY,
    SEND_IN_THREADS,
    SEND_MESSAGES,
    VIEW_AUDIT_LOG,
    VIEW_REPORTS,
    VIEW_SPACE,
    has_permission,
)


# ---------------------------------------------------------------------------
# Unit tests for has_permission
# ---------------------------------------------------------------------------


def test_has_permission_single():
    assert has_permission(SEND_MESSAGES | READ_HISTORY, SEND_MESSAGES)
    assert not has_permission(READ_HISTORY, SEND_MESSAGES)


def test_has_permission_multiple():
    perms = SEND_MESSAGES | READ_HISTORY | VIEW_SPACE
    assert has_permission(perms, SEND_MESSAGES | READ_HISTORY)
    assert not has_permission(perms, SEND_MESSAGES | MANAGE_SPACES)


def test_has_permission_zero():
    assert has_permission(0, 0)
    assert not has_permission(0, SEND_MESSAGES)


def test_administrator_bit():
    assert ADMINISTRATOR == 1 << 62
    assert ALL_PERMISSIONS == (1 << 63) - 1


def test_everyone_defaults_include_basics():
    for perm in (VIEW_SPACE, SEND_MESSAGES, READ_HISTORY, CONNECT, CREATE_INVITES, CREATE_THREADS, SEND_IN_THREADS):
        assert has_permission(EVERYONE_DEFAULTS, perm), f"EVERYONE_DEFAULTS missing {perm}"


# ---------------------------------------------------------------------------
# Helpers for integration tests
# ---------------------------------------------------------------------------


async def _register(client, username="alice", password="test1234"):
    """Register and return (headers, user_id)."""
    r = await client.post("/api/v1/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user_id"]


async def _register_unprivileged(client, admin_headers):
    """Register a second user who only has @everyone permissions (no admin role)."""
    r = await client.post("/api/v1/auth/register", json={"username": "bob", "password": "test1234"})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user_id"]


# ---------------------------------------------------------------------------
# Resolver integration tests (via endpoint behaviour)
# ---------------------------------------------------------------------------


async def test_admin_gets_all_permissions(client):
    """First registered user (admin) can access privileged endpoints."""
    h, _ = await _register(client)
    # Admin should be able to manage spaces
    r = await client.post("/api/v1/feeds", headers=h, json={"name": "test", "type": "text"})
    assert r.status_code == 201


async def test_unprivileged_user_denied_manage_spaces(client):
    """A user with only @everyone perms cannot create feeds (requires MANAGE_SPACES)."""
    admin_h, _ = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    r = await client.post("/api/v1/feeds", headers=user_h, json={"name": "hacked", "type": "text"})
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "MISSING_PERMISSIONS"


async def test_unprivileged_user_denied_manage_roles(client):
    admin_h, _ = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    r = await client.post("/api/v1/roles", headers=user_h, json={"name": "Evil", "permissions": 0, "position": 5})
    assert r.status_code == 403


async def test_unprivileged_user_denied_manage_server(client):
    admin_h, _ = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    r = await client.patch("/api/v1/server", headers=user_h, json={"name": "pwned"})
    assert r.status_code == 403


async def test_unprivileged_user_denied_kick(client):
    admin_h, admin_uid = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    r = await client.delete(f"/api/v1/members/{admin_uid}", headers=user_h)
    assert r.status_code == 403


async def test_unprivileged_user_denied_ban(client):
    admin_h, admin_uid = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    r = await client.put(f"/api/v1/bans/{admin_uid}", headers=user_h, json={"reason": "no"})
    assert r.status_code == 403


async def test_unprivileged_user_denied_list_bans(client):
    admin_h, _ = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    r = await client.get("/api/v1/bans", headers=user_h)
    assert r.status_code == 403


async def test_unprivileged_user_denied_manage_webhooks(client):
    admin_h, _ = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    # Admin creates a feed first
    await client.post("/api/v1/feeds", headers=admin_h, json={"name": "general", "type": "text"})

    r = await client.post("/api/v1/feeds/1/webhooks", headers=user_h, json={"name": "Evil Hook"})
    assert r.status_code == 403


async def test_unprivileged_user_denied_manage_emoji(client):
    admin_h, _ = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    import io
    r = await client.post("/api/v1/emoji", headers=user_h, data={"name": "test"}, files={"image": ("test.png", io.BytesIO(b"fake"), "image/png")})
    assert r.status_code == 403


async def test_unprivileged_user_denied_view_reports(client):
    admin_h, _ = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    r = await client.get("/api/v1/reports", headers=user_h)
    assert r.status_code == 403


async def test_unprivileged_user_denied_audit_log(client):
    admin_h, _ = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    r = await client.get("/api/v1/audit-log", headers=user_h)
    assert r.status_code == 403


async def test_unprivileged_user_denied_bulk_delete(client):
    admin_h, _ = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    # Admin creates feed and sends a message
    await client.post("/api/v1/feeds", headers=admin_h, json={"name": "general", "type": "text"})
    r = await client.post("/api/v1/feeds/1/messages", headers=admin_h, json={"body": "test"})
    msg_id = r.json()["msg_id"]

    r = await client.post("/api/v1/feeds/1/messages/bulk-delete", headers=user_h, json={"msg_ids": [msg_id]})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# @everyone defaults allow basic operations
# ---------------------------------------------------------------------------


async def test_unprivileged_user_can_send_messages(client):
    """Users with @everyone perms can send messages (SEND_MESSAGES is in defaults)."""
    admin_h, _ = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    # Admin creates the feed
    await client.post("/api/v1/feeds", headers=admin_h, json={"name": "general", "type": "text"})

    r = await client.post("/api/v1/feeds/1/messages", headers=user_h, json={"body": "Hello!"})
    assert r.status_code == 201


async def test_unprivileged_user_can_read_history(client):
    admin_h, _ = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    await client.post("/api/v1/feeds", headers=admin_h, json={"name": "general", "type": "text"})

    r = await client.get("/api/v1/feeds/1/messages", headers=user_h)
    assert r.status_code == 200


async def test_unprivileged_user_can_create_invite(client):
    admin_h, _ = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    r = await client.post("/api/v1/invites", headers=user_h, json={})
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# Message delete special case: author can delete own, others need MANAGE_MESSAGES
# ---------------------------------------------------------------------------


async def test_author_can_delete_own_message(client):
    admin_h, _ = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    await client.post("/api/v1/feeds", headers=admin_h, json={"name": "general", "type": "text"})

    r = await client.post("/api/v1/feeds/1/messages", headers=user_h, json={"body": "my msg"})
    msg_id = r.json()["msg_id"]

    r = await client.delete(f"/api/v1/feeds/1/messages/{msg_id}", headers=user_h)
    assert r.status_code == 204


async def test_non_author_without_manage_messages_cannot_delete(client):
    admin_h, _ = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    await client.post("/api/v1/feeds", headers=admin_h, json={"name": "general", "type": "text"})

    # Admin sends a message
    r = await client.post("/api/v1/feeds/1/messages", headers=admin_h, json={"body": "admin msg"})
    msg_id = r.json()["msg_id"]

    # Unprivileged user tries to delete admin's message
    r = await client.delete(f"/api/v1/feeds/1/messages/{msg_id}", headers=user_h)
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "MISSING_PERMISSIONS"


async def test_admin_can_delete_others_message(client):
    admin_h, _ = await _register(client)
    user_h, _ = await _register_unprivileged(client, admin_h)

    await client.post("/api/v1/feeds", headers=admin_h, json={"name": "general", "type": "text"})

    # Regular user sends a message
    r = await client.post("/api/v1/feeds/1/messages", headers=user_h, json={"body": "user msg"})
    msg_id = r.json()["msg_id"]

    # Admin deletes it (has MANAGE_MESSAGES via ADMINISTRATOR)
    r = await client.delete(f"/api/v1/feeds/1/messages/{msg_id}", headers=admin_h)
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Permission override tests
# ---------------------------------------------------------------------------


async def test_permission_override_denies_send(client):
    """A role-level deny override on a feed should block SEND_MESSAGES."""
    admin_h, _ = await _register(client)
    user_h, user_id = await _register_unprivileged(client, admin_h)

    # Admin creates feed
    r = await client.post("/api/v1/feeds", headers=admin_h, json={"name": "readonly", "type": "text"})
    feed_id = r.json()["feed_id"]

    # Get the @everyone role id
    r = await client.get("/api/v1/roles", headers=admin_h)
    everyone_role = next(role for role in r.json()["items"] if role["name"] == "@everyone")

    # Set deny SEND_MESSAGES override for @everyone on this feed
    r = await client.put(
        f"/api/v1/feeds/{feed_id}/permissions/role/{everyone_role['role_id']}",
        headers=admin_h,
        json={"allow": 0, "deny": SEND_MESSAGES},
    )
    assert r.status_code == 204

    # Unprivileged user should be denied
    r = await client.post(f"/api/v1/feeds/{feed_id}/messages", headers=user_h, json={"body": "blocked"})
    assert r.status_code == 403


async def test_permission_override_allows_send_for_specific_role(client):
    """A role-level allow override can re-grant a denied permission."""
    admin_h, _ = await _register(client)
    user_h, user_id = await _register_unprivileged(client, admin_h)

    r = await client.post("/api/v1/feeds", headers=admin_h, json={"name": "restricted", "type": "text"})
    feed_id = r.json()["feed_id"]

    r = await client.get("/api/v1/roles", headers=admin_h)
    everyone_role = next(role for role in r.json()["items"] if role["name"] == "@everyone")

    # Deny SEND_MESSAGES for @everyone
    await client.put(
        f"/api/v1/feeds/{feed_id}/permissions/role/{everyone_role['role_id']}",
        headers=admin_h,
        json={"allow": 0, "deny": SEND_MESSAGES},
    )

    # Create a special role that allows sending
    r = await client.post("/api/v1/roles", headers=admin_h, json={"name": "Speaker", "permissions": 0, "position": 2})
    speaker_role_id = r.json()["role_id"]

    # Set allow override for Speaker role on this feed
    await client.put(
        f"/api/v1/feeds/{feed_id}/permissions/role/{speaker_role_id}",
        headers=admin_h,
        json={"allow": SEND_MESSAGES, "deny": 0},
    )

    # Assign Speaker role to user
    await client.put(f"/api/v1/members/{user_id}/roles/{speaker_role_id}", headers=admin_h)

    # Now user should be able to send
    r = await client.post(f"/api/v1/feeds/{feed_id}/messages", headers=user_h, json={"body": "allowed!"})
    assert r.status_code == 201


async def test_user_specific_override(client):
    """A user-specific override takes precedence over role overrides."""
    admin_h, _ = await _register(client)
    user_h, user_id = await _register_unprivileged(client, admin_h)

    r = await client.post("/api/v1/feeds", headers=admin_h, json={"name": "special", "type": "text"})
    feed_id = r.json()["feed_id"]

    r = await client.get("/api/v1/roles", headers=admin_h)
    everyone_role = next(role for role in r.json()["items"] if role["name"] == "@everyone")

    # Deny for @everyone role
    await client.put(
        f"/api/v1/feeds/{feed_id}/permissions/role/{everyone_role['role_id']}",
        headers=admin_h,
        json={"allow": 0, "deny": SEND_MESSAGES},
    )

    # But allow for this specific user
    await client.put(
        f"/api/v1/feeds/{feed_id}/permissions/user/{user_id}",
        headers=admin_h,
        json={"allow": SEND_MESSAGES, "deny": 0},
    )

    r = await client.post(f"/api/v1/feeds/{feed_id}/messages", headers=user_h, json={"body": "special access"})
    assert r.status_code == 201
