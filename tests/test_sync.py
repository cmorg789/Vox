import json
import time

from vox.db.engine import get_session_factory
from vox.db.models import EventLog


async def auth(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user_id"]


async def _insert_event(event_type: str, payload: dict, timestamp: int | None = None):
    """Insert an event directly into the event_log table."""
    from vox.api.messages import _snowflake

    factory = get_session_factory()
    async with factory() as session:
        entry = EventLog(
            id=await _snowflake(),
            event_type=event_type,
            payload=json.dumps(payload),
            timestamp=timestamp or int(time.time() * 1000),
        )
        session.add(entry)
        await session.commit()


async def test_sync_returns_events(client):
    h, _ = await auth(client)
    now = int(time.time() * 1000)

    await _insert_event("member_join", {"user_id": 1}, now - 1000)
    await _insert_event("role_create", {"role_id": 1, "name": "Admin"}, now - 500)

    r = await client.post(
        "/api/v1/sync",
        headers=h,
        json={"since_timestamp": now - 2000, "categories": ["members", "roles"]},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["events"]) == 2
    assert data["events"][0]["type"] == "member_join"
    assert data["events"][1]["type"] == "role_create"
    assert "server_timestamp" in data


async def test_sync_filters_by_category(client):
    h, _ = await auth(client)
    now = int(time.time() * 1000)

    await _insert_event("member_join", {"user_id": 1}, now - 1000)
    await _insert_event("role_create", {"role_id": 1, "name": "Admin"}, now - 500)

    r = await client.post(
        "/api/v1/sync",
        headers=h,
        json={"since_timestamp": now - 2000, "categories": ["roles"]},
    )
    assert r.status_code == 200
    events = r.json()["events"]
    assert len(events) == 1
    assert events[0]["type"] == "role_create"


async def test_sync_filters_by_timestamp(client):
    h, _ = await auth(client)
    now = int(time.time() * 1000)

    await _insert_event("member_join", {"user_id": 1}, now - 5000)
    await _insert_event("member_leave", {"user_id": 2}, now - 1000)

    r = await client.post(
        "/api/v1/sync",
        headers=h,
        json={"since_timestamp": now - 2000, "categories": ["members"]},
    )
    assert r.status_code == 200
    events = r.json()["events"]
    assert len(events) == 1
    assert events[0]["type"] == "member_leave"


async def test_sync_retention_cutoff(client):
    h, _ = await auth(client)
    now = int(time.time() * 1000)
    eight_days_ago = now - (8 * 24 * 60 * 60 * 1000)

    await _insert_event("member_join", {"user_id": 1}, eight_days_ago + 100)

    r = await client.post(
        "/api/v1/sync",
        headers=h,
        json={"since_timestamp": eight_days_ago, "categories": ["members"]},
    )
    assert r.status_code == 200
    assert r.json()["events"] == []


async def test_sync_invalid_category(client):
    h, _ = await auth(client)
    now = int(time.time() * 1000)

    r = await client.post(
        "/api/v1/sync",
        headers=h,
        json={"since_timestamp": now - 1000, "categories": ["bogus"]},
    )
    assert r.status_code == 400


async def test_sync_empty_when_no_events(client):
    h, _ = await auth(client)
    now = int(time.time() * 1000)

    r = await client.post(
        "/api/v1/sync",
        headers=h,
        json={"since_timestamp": now - 1000, "categories": ["members"]},
    )
    assert r.status_code == 200
    assert r.json()["events"] == []


async def test_sync_requires_auth(client):
    now = int(time.time() * 1000)
    r = await client.post(
        "/api/v1/sync",
        json={"since_timestamp": now - 1000, "categories": ["members"]},
    )
    assert r.status_code in (401, 422)


async def test_dispatch_persists_syncable_events(client):
    """Verify that dispatching a syncable event writes to the event_log."""
    h, uid = await auth(client)

    # Creating a role dispatches role_create which is syncable
    r = await client.post(
        "/api/v1/roles",
        headers=h,
        json={"name": "Testers", "permissions": 0, "position": 0},
    )
    assert r.status_code == 201

    now = int(time.time() * 1000)
    r = await client.post(
        "/api/v1/sync",
        headers=h,
        json={"since_timestamp": now - 5000, "categories": ["roles"]},
    )
    assert r.status_code == 200
    events = r.json()["events"]
    assert any(e["type"] == "role_create" and e["payload"]["name"] == "Testers" for e in events)


async def test_emoji_dispatch_events(client):
    """Verify emoji create/delete dispatch events end up in sync."""
    h, uid = await auth(client)

    import io
    r = await client.post("/api/v1/emoji", headers=h, data={"name": "test_emoji"}, files={"image": ("test.png", io.BytesIO(b"fake"), "image/png")})
    assert r.status_code == 201
    emoji_id = r.json()["emoji_id"]

    r = await client.delete(f"/api/v1/emoji/{emoji_id}", headers=h)
    assert r.status_code == 204

    now = int(time.time() * 1000)
    r = await client.post(
        "/api/v1/sync",
        headers=h,
        json={"since_timestamp": now - 5000, "categories": ["emoji"]},
    )
    assert r.status_code == 200
    types = [e["type"] for e in r.json()["events"]]
    assert "emoji_create" in types
    assert "emoji_delete" in types


async def test_sync_no_events(client):
    """Sync with future timestamp returns empty events."""
    h, _ = await auth(client)

    # Sync with a very recent timestamp (should have no new events)
    ts = int(time.time() * 1000) + 100000  # future timestamp
    r = await client.post("/api/v1/sync", headers=h, json={"since_timestamp": ts, "categories": ["members"]})
    assert r.status_code == 200
    assert r.json()["events"] == []


async def test_role_assign_revoke_dispatch(client):
    """Verify role assign/revoke dispatch events end up in sync."""
    h, uid = await auth(client)

    r = await client.post(
        "/api/v1/roles",
        headers=h,
        json={"name": "SyncRole", "permissions": 0, "position": 0},
    )
    role_id = r.json()["role_id"]

    await client.put(f"/api/v1/members/{uid}/roles/{role_id}", headers=h)
    await client.delete(f"/api/v1/members/{uid}/roles/{role_id}", headers=h)

    now = int(time.time() * 1000)
    r = await client.post(
        "/api/v1/sync",
        headers=h,
        json={"since_timestamp": now - 5000, "categories": ["roles"]},
    )
    assert r.status_code == 200
    types = [e["type"] for e in r.json()["events"]]
    assert "role_assign" in types
    assert "role_revoke" in types
