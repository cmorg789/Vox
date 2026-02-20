"""Tests for federation admin allow/block list endpoints."""

import pytest


async def _register(client, username="alice", password="test1234"):
    r = await client.post("/api/v1/auth/register", json={"username": username, "password": password})
    return r.json()["token"], r.json()["user_id"]


async def _admin_headers(client):
    """Register first user (gets admin)."""
    token, uid = await _register(client, "admin_user")
    return {"Authorization": f"Bearer {token}"}


async def _user_headers(client):
    """Register second user (non-admin)."""
    token, uid = await _register(client, "regular_user")
    return {"Authorization": f"Bearer {token}"}


PREFIX = "/api/v1/federation"


# ---------------------------------------------------------------------------
# Allow endpoints
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_allow_add_and_list(client):
    admin_h = await _admin_headers(client)

    r = await client.post(f"{PREFIX}/admin/allow", headers=admin_h, json={"domain": "friend.example", "reason": "trusted"})
    assert r.status_code == 204

    r = await client.get(f"{PREFIX}/admin/allow", headers=admin_h)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["domain"] == "friend.example"
    assert items[0]["reason"] == "trusted"


@pytest.mark.anyio
async def test_allow_idempotent_add(client):
    admin_h = await _admin_headers(client)

    r = await client.post(f"{PREFIX}/admin/allow", headers=admin_h, json={"domain": "dup.example"})
    assert r.status_code == 204
    r = await client.post(f"{PREFIX}/admin/allow", headers=admin_h, json={"domain": "dup.example"})
    assert r.status_code == 204

    r = await client.get(f"{PREFIX}/admin/allow", headers=admin_h)
    assert len(r.json()["items"]) == 1


@pytest.mark.anyio
async def test_allow_remove(client):
    admin_h = await _admin_headers(client)

    await client.post(f"{PREFIX}/admin/allow", headers=admin_h, json={"domain": "gone.example"})
    r = await client.delete(f"{PREFIX}/admin/allow/gone.example", headers=admin_h)
    assert r.status_code == 204

    r = await client.get(f"{PREFIX}/admin/allow", headers=admin_h)
    assert len(r.json()["items"]) == 0


@pytest.mark.anyio
async def test_allow_remove_idempotent(client):
    admin_h = await _admin_headers(client)

    r = await client.delete(f"{PREFIX}/admin/allow/nonexistent.example", headers=admin_h)
    assert r.status_code == 204


@pytest.mark.anyio
async def test_allow_requires_admin(client):
    admin_h = await _admin_headers(client)
    user_h = await _user_headers(client)

    r = await client.post(f"{PREFIX}/admin/allow", headers=user_h, json={"domain": "x.example"})
    assert r.status_code == 403

    r = await client.get(f"{PREFIX}/admin/allow", headers=user_h)
    assert r.status_code == 403

    r = await client.delete(f"{PREFIX}/admin/allow/x.example", headers=user_h)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Block list / unblock endpoints
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_block_list(client):
    admin_h = await _admin_headers(client)

    # Add a block entry
    r = await client.post(f"{PREFIX}/admin/block", headers=admin_h, json={"domain": "evil.example", "reason": "spam"})
    assert r.status_code == 204

    r = await client.get(f"{PREFIX}/admin/block", headers=admin_h)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["domain"] == "evil.example"
    assert items[0]["reason"] == "spam"


@pytest.mark.anyio
async def test_unblock(client):
    admin_h = await _admin_headers(client)

    await client.post(f"{PREFIX}/admin/block", headers=admin_h, json={"domain": "redeemed.example"})
    r = await client.delete(f"{PREFIX}/admin/block/redeemed.example", headers=admin_h)
    assert r.status_code == 204

    r = await client.get(f"{PREFIX}/admin/block", headers=admin_h)
    assert len(r.json()["items"]) == 0


@pytest.mark.anyio
async def test_unblock_idempotent(client):
    admin_h = await _admin_headers(client)

    r = await client.delete(f"{PREFIX}/admin/block/nonexistent.example", headers=admin_h)
    assert r.status_code == 204


@pytest.mark.anyio
async def test_block_list_requires_admin(client):
    admin_h = await _admin_headers(client)
    user_h = await _user_headers(client)

    r = await client.get(f"{PREFIX}/admin/block", headers=user_h)
    assert r.status_code == 403

    r = await client.delete(f"{PREFIX}/admin/block/x.example", headers=user_h)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Cross-contamination: allow entries must not appear in block list
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_allow_not_in_block_list(client):
    admin_h = await _admin_headers(client)

    await client.post(f"{PREFIX}/admin/allow", headers=admin_h, json={"domain": "allowed.example"})
    await client.post(f"{PREFIX}/admin/block", headers=admin_h, json={"domain": "blocked.example"})

    r = await client.get(f"{PREFIX}/admin/block", headers=admin_h)
    domains = [i["domain"] for i in r.json()["items"]]
    assert "blocked.example" in domains
    assert "allowed.example" not in domains

    r = await client.get(f"{PREFIX}/admin/allow", headers=admin_h)
    domains = [i["domain"] for i in r.json()["items"]]
    assert "allowed.example" in domains
    assert "blocked.example" not in domains
