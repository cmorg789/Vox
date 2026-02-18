async def auth(client, username="alice"):
    r = await client.post("/api/v1/auth/register", json={"username": username, "password": "test1234", "display_name": username.title()})
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user_id"]


async def test_list_members(client):
    h, _ = await auth(client)
    r = await client.get("/api/v1/members", headers=h)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1
    assert r.json()["items"][0]["display_name"] == "Alice"


async def test_update_member_nickname(client):
    h, uid = await auth(client)
    r = await client.patch(f"/api/v1/members/{uid}", headers=h, json={"nickname": "Ali"})
    assert r.status_code == 200
    assert r.json()["nickname"] == "Ali"


async def test_kick_member(client):
    h_admin, _ = await auth(client, "admin")
    _, uid_bob = await auth(client, "bob")

    r = await client.delete(f"/api/v1/members/{uid_bob}", headers=h_admin)
    assert r.status_code == 204


async def test_ban_and_unban(client):
    h_admin, _ = await auth(client, "admin")
    _, uid_bob = await auth(client, "bob")

    # Ban
    r = await client.put(f"/api/v1/bans/{uid_bob}", headers=h_admin, json={"reason": "Spam"})
    assert r.status_code == 200
    assert r.json()["reason"] == "Spam"

    # List bans
    r = await client.get("/api/v1/bans", headers=h_admin)
    assert len(r.json()["items"]) == 1

    # Unban
    r = await client.delete(f"/api/v1/bans/{uid_bob}", headers=h_admin)
    assert r.status_code == 204

    r = await client.get("/api/v1/bans", headers=h_admin)
    assert len(r.json()["items"]) == 0


async def test_list_members_pagination(client):
    h, _ = await auth(client, "alice")
    await auth(client, "bob")
    r = await client.get("/api/v1/members?after=1", headers=h)
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["user_id"] > 1


async def test_join_max_uses_invite(client):
    h, uid = await auth(client, "alice")

    from vox.db.engine import get_session_factory
    from vox.db.models import Invite
    from datetime import datetime, timezone
    factory = get_session_factory()
    async with factory() as db:
        db.add(Invite(code="maxed", creator_id=uid, max_uses=1, uses=1, created_at=datetime.now(timezone.utc)))
        await db.commit()

    await auth(client, "bob")
    h_bob = (await client.post("/api/v1/auth/login", json={"username": "bob", "password": "test1234"})).json()
    h2 = {"Authorization": f"Bearer {h_bob['token']}"}
    r = await client.post("/api/v1/members/join", headers=h2, json={"invite_code": "maxed"})
    assert r.status_code == 422


async def test_join_banned_user(client):
    h_admin, admin_uid = await auth(client, "admin")
    _, uid_bob = await auth(client, "bob")

    # Create invite
    from vox.db.engine import get_session_factory
    from vox.db.models import Invite
    from datetime import datetime, timezone
    factory = get_session_factory()
    async with factory() as db:
        db.add(Invite(code="valid", creator_id=admin_uid, max_uses=10, uses=0, created_at=datetime.now(timezone.utc)))
        await db.commit()

    # Ban bob
    await client.put(f"/api/v1/bans/{uid_bob}", headers=h_admin, json={"reason": "bad"})

    reg = await client.post('/api/v1/auth/register', json={'username': 'charlie', 'password': 'test1234'})
    charlie_token = reg.json()['token']
    charlie_uid = reg.json()['user_id']
    h_bob = {"Authorization": f"Bearer {charlie_token}"}
    # Actually use bob's token - but bob is banned and inactive so can't log in easily
    # Instead test with admin banning charlie then charlie trying to join
    await client.put(f"/api/v1/bans/{charlie_uid}", headers=h_admin, json={"reason": "bad"})
    r = await client.post("/api/v1/members/join", headers=h_bob, json={"invite_code": "valid"})
    assert r.status_code == 403


async def test_leave_server(client):
    h, uid = await auth(client, "alice")
    r = await client.delete(f"/api/v1/members/{uid}", headers=h)
    assert r.status_code == 204


async def test_kick_member_not_found(client):
    h, _ = await auth(client, "admin")
    r = await client.delete("/api/v1/members/99999", headers=h)
    assert r.status_code == 404


async def test_ban_member_not_found(client):
    h, _ = await auth(client, "admin")
    r = await client.put("/api/v1/bans/99999", headers=h, json={"reason": "ghost"})
    assert r.status_code == 404


async def test_join_invalid_invite(client):
    """Joining with a non-existent invite code returns 422."""
    h, _ = await auth(client, "alice")
    r = await client.post("/api/v1/members/join", headers=h, json={"invite_code": "nonexistent"})
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "INVITE_INVALID"


async def test_join_expired_invite(client):
    """Joining with an expired invite returns 410."""
    h, uid = await auth(client, "alice")

    from vox.db.engine import get_session_factory
    from vox.db.models import Invite
    from datetime import datetime, timedelta, timezone
    factory = get_session_factory()
    async with factory() as db:
        # Store a tz-aware datetime matching the format the code uses for comparison
        db.add(Invite(
            code="expired",
            creator_id=uid,
            expires_at=datetime(2020, 1, 1),
            created_at=datetime(2019, 1, 1),
        ))
        await db.commit()

    from unittest.mock import patch
    with patch("vox.api.members.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2025, 1, 1)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        r = await client.post("/api/v1/members/join", headers=h, json={"invite_code": "expired"})
    assert r.status_code == 410
    assert r.json()["detail"]["error"]["code"] == "INVITE_EXPIRED"


async def test_list_bans_pagination(client):
    """Ban list pagination with after cursor."""
    h, _ = await auth(client, "admin")
    _, uid_bob = await auth(client, "bob")
    await client.put(f"/api/v1/bans/{uid_bob}", headers=h, json={"reason": "test"})

    r = await client.get(f"/api/v1/bans?after={uid_bob}", headers=h)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 0


async def test_unban_reactivates_user(client):
    """Unbanning a user reactivates them and they become accessible again."""
    h_admin, _ = await auth(client, "admin")
    h_bob, uid_bob = await auth(client, "bob")

    # Ban bob
    r = await client.put(f"/api/v1/bans/{uid_bob}", headers=h_admin, json={"reason": "Spam"})
    assert r.status_code == 200

    # Verify bob is banned
    r = await client.get("/api/v1/bans", headers=h_admin)
    ban_ids = [b["user_id"] for b in r.json()["items"]]
    assert uid_bob in ban_ids

    # Unban bob
    r = await client.delete(f"/api/v1/bans/{uid_bob}", headers=h_admin)
    assert r.status_code == 204

    # Verify bob is accessible
    r = await client.get(f"/api/v1/users/{uid_bob}", headers=h_admin)
    assert r.status_code == 200
    assert r.json()["user_id"] == uid_bob


async def test_unban_not_banned_returns_404(client):
    """Unbanning a user that was never banned returns 404."""
    h_admin, _ = await auth(client, "admin")
    _, uid_bob = await auth(client, "bob")

    r = await client.delete(f"/api/v1/bans/{uid_bob}", headers=h_admin)
    assert r.status_code == 404


async def test_invalid_user_id_returns_400(client):
    """Non-numeric user_id returns 400."""
    h, _ = await auth(client)
    r = await client.delete("/api/v1/members/notanumber", headers=h)
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "INVALID_USER_ID"
