import pytest


async def auth(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def test_get_server_info(client):
    h = await auth(client)
    r = await client.get("/api/v1/server", headers=h)
    assert r.status_code == 200
    assert r.json()["name"] == "Vox Server"
    assert r.json()["member_count"] == 1


async def test_update_server(client):
    h = await auth(client)
    r = await client.patch("/api/v1/server", headers=h, json={"name": "My Community", "description": "Cool place"})
    assert r.status_code == 200
    assert r.json()["name"] == "My Community"
    assert r.json()["description"] == "Cool place"

    r = await client.get("/api/v1/server", headers=h)
    assert r.json()["name"] == "My Community"
    assert r.json()["description"] == "Cool place"


async def test_layout_empty(client):
    h = await auth(client)
    r = await client.get("/api/v1/server/layout", headers=h)
    assert r.status_code == 200
    assert r.json()["categories"] == []
    assert r.json()["feeds"] == []
    assert r.json()["rooms"] == []


async def test_layout_with_content(client):
    h = await auth(client)

    await client.post("/api/v1/categories", headers=h, json={"name": "General", "position": 0})
    await client.post("/api/v1/feeds", headers=h, json={"name": "welcome", "type": "text", "category_id": 1})
    await client.post("/api/v1/rooms", headers=h, json={"name": "Lounge", "type": "voice", "category_id": 1})

    r = await client.get("/api/v1/server/layout", headers=h)
    assert r.status_code == 200
    assert len(r.json()["categories"]) == 1
    assert len(r.json()["feeds"]) == 1
    assert len(r.json()["rooms"]) == 1
    assert r.json()["feeds"][0]["name"] == "welcome"


async def test_get_server_requires_auth(client):
    r = await client.get("/api/v1/server")
    assert r.status_code in (401, 422)


async def test_update_server_partial(client):
    h = await auth(client)
    original = await client.get("/api/v1/server", headers=h)
    original_desc = original.json()["description"]

    r = await client.patch("/api/v1/server", headers=h, json={"name": "New Name"})
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"
    assert r.json()["description"] == original_desc


async def test_update_server_empty_body(client):
    h = await auth(client)
    r = await client.patch("/api/v1/server", headers=h, json={})
    assert r.status_code == 200


async def test_layout_requires_auth(client):
    r = await client.get("/api/v1/server/layout")
    assert r.status_code in (401, 422)


async def test_update_server_icon(client):
    """Update server icon field."""
    h = await auth(client)
    r = await client.patch("/api/v1/server", headers=h, json={"icon": "icon.png"})
    assert r.status_code == 200
    assert r.json()["icon"] == "icon.png"


async def test_update_server_existing_config(client):
    """Updating server name twice updates existing config row."""
    h = await auth(client)
    await client.patch("/api/v1/server", headers=h, json={"name": "First"})
    r = await client.patch("/api/v1/server", headers=h, json={"name": "Second"})
    assert r.json()["name"] == "Second"


async def test_get_limits(client):
    """Get server limits."""
    h = await auth(client)
    r = await client.get("/api/v1/server/limits", headers=h)
    assert r.status_code == 200
    assert "message_body_max" in r.json()


async def test_update_limits(client):
    """Update a server limit."""
    h = await auth(client)
    r = await client.patch("/api/v1/server/limits", headers=h, json={"limits": {"message_body_max": 8000}})
    assert r.status_code == 200
    assert r.json()["message_body_max"] == 8000

    # Update again (existing row path)
    r = await client.patch("/api/v1/server/limits", headers=h, json={"limits": {"message_body_max": 4000}})
    assert r.status_code == 200
    assert r.json()["message_body_max"] == 4000


async def test_update_limits_invalid(client):
    """Update with unknown limit name returns 400."""
    h = await auth(client)
    r = await client.patch("/api/v1/server/limits", headers=h, json={"limits": {"nonexistent_limit": 100}})
    assert r.status_code == 400


async def test_load_limits(client):
    """load_limits loads overrides from DB."""
    from vox.limits import load_limits, limits
    from vox.db.engine import get_session_factory
    from vox.db.models import Config

    factory = get_session_factory()
    async with factory() as db:
        db.add(Config(key="limit_message_body_max", value="9999"))
        await db.commit()

    async with factory() as db:
        await load_limits(db)

    assert limits.message_body_max == 9999

    # Clean up
    from sqlalchemy import delete
    async with factory() as db:
        await db.execute(delete(Config).where(Config.key == "limit_message_body_max"))
        await db.commit()
    async with factory() as db:
        await load_limits(db)


def test_str_limit_none():
    """str_limit validator passes None through."""
    from vox.limits import str_limit

    validator = str_limit(max_attr="message_body_max")
    assert validator(None) is None


def test_int_limit_none():
    """int_limit validator passes None through."""
    from vox.limits import int_limit

    validator = int_limit(ge=0, max_attr="message_body_max")
    assert validator(None) is None


@pytest.mark.asyncio
async def test_periodic_cleanup_runs():
    """_periodic_cleanup executes cleanup logic."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from vox.api.app import _periodic_cleanup
    import asyncio

    call_count = 0

    async def fake_sleep(secs):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise asyncio.CancelledError()

    mock_factory = MagicMock()
    mock_db = AsyncMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("asyncio.sleep", side_effect=fake_sleep):
        with patch("vox.auth.service.cleanup_expired_sessions", new_callable=AsyncMock):
            try:
                await _periodic_cleanup(mock_factory)
            except asyncio.CancelledError:
                pass

    assert call_count >= 1
