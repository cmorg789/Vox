"""Tests for new error codes from the error-code-consistency plan."""

import pytest


async def _register(client, username="alice", password="test1234"):
    r = await client.post("/api/v1/auth/register", json={
        "username": username, "password": password,
    })
    return r.json()["token"], r.json()["user_id"]


async def _setup_totp(client, token):
    import pyotp

    r = await client.post(
        "/api/v1/auth/2fa/setup",
        json={"method": "totp"},
        headers={"Authorization": f"Bearer {token}"},
    )
    setup_data = r.json()
    setup_id = setup_data["setup_id"]
    secret = setup_data["totp_secret"]

    totp = pyotp.TOTP(secret)
    code = totp.now()

    r = await client.post(
        "/api/v1/auth/2fa/setup/confirm",
        json={"setup_id": setup_id, "code": code},
        headers={"Authorization": f"Bearer {token}"},
    )
    return secret, r.json()["recovery_codes"]


# --- MESSAGE_TOO_LARGE ---


async def test_message_too_large_feed(client):
    """Message body exceeding limit returns MESSAGE_TOO_LARGE."""
    token, _ = await _register(client)
    h = {"Authorization": f"Bearer {token}"}

    # Create a feed
    r = await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    assert r.status_code == 201
    feed_id = r.json()["feed_id"]

    # Send a message that exceeds 4000 chars
    big_body = "x" * 4001
    r = await client.post(f"/api/v1/feeds/{feed_id}/messages", headers=h, json={"body": big_body})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "MESSAGE_TOO_LARGE"


async def test_message_too_large_dm(client):
    """DM message body exceeding limit returns MESSAGE_TOO_LARGE."""
    token1, uid1 = await _register(client, "alice")
    token2, uid2 = await _register(client, "bob")
    h1 = {"Authorization": f"Bearer {token1}"}

    r = await client.post("/api/v1/dms", headers=h1, json={"recipient_id": uid2})
    dm_id = r.json()["dm_id"]

    big_body = "x" * 4001
    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=h1, json={"body": big_body})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "MESSAGE_TOO_LARGE"


async def test_message_at_limit_succeeds(client):
    """Message body exactly at the limit succeeds."""
    token, _ = await _register(client)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    feed_id = r.json()["feed_id"]

    body_at_limit = "x" * 4000
    r = await client.post(f"/api/v1/feeds/{feed_id}/messages", headers=h, json={"body": body_at_limit})
    assert r.status_code == 201


# --- 2FA_REQUIRED ---


async def test_2fa_required_returns_401(client):
    """Login with 2FA enabled returns 401 with error envelope."""
    token, _ = await _register(client)
    await _setup_totp(client, token)

    r = await client.post("/api/v1/auth/login", json={
        "username": "alice", "password": "test1234",
    })
    assert r.status_code == 401
    data = r.json()
    assert data["error"]["code"] == "2FA_REQUIRED"
    assert data["error"]["message"] == "Two-factor authentication required."
    assert "mfa_ticket" in data["error"]
    assert "totp" in data["error"]["available_methods"]


# --- 2FA_NOT_ENABLED ---


async def test_2fa_not_enabled_totp(client):
    """Removing TOTP when not enabled returns 422."""
    token, _ = await _register(client)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.request("DELETE", "/api/v1/auth/2fa", headers=h, json={
        "method": "totp", "code": "123456",
    })
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "2FA_NOT_ENABLED"


async def test_2fa_not_enabled_webauthn(client):
    """Removing WebAuthn when not enabled returns 422."""
    token, _ = await _register(client)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.request("DELETE", "/api/v1/auth/2fa", headers=h, json={
        "method": "webauthn", "assertion": {"challenge_id": "test"},
    })
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "2FA_NOT_ENABLED"


# --- 2FA_RECOVERY_EXHAUSTED ---


async def test_2fa_recovery_exhausted(client):
    """Using recovery after all codes are used returns 422."""
    from vox.ratelimit import reset as ratelimit_reset
    token, uid = await _register(client)
    _, recovery_codes = await _setup_totp(client, token)

    # Use all recovery codes
    for code in recovery_codes:
        ratelimit_reset()  # avoid hitting auth rate limit
        r = await client.post("/api/v1/auth/login", json={
            "username": "alice", "password": "test1234",
        })
        mfa_ticket = r.json()["error"]["mfa_ticket"]
        r = await client.post("/api/v1/auth/login/2fa", json={
            "mfa_ticket": mfa_ticket, "method": "recovery", "code": code,
        })
        assert r.status_code == 200

    # Now try to use recovery again
    r = await client.post("/api/v1/auth/login", json={
        "username": "alice", "password": "test1234",
    })
    mfa_ticket = r.json()["error"]["mfa_ticket"]
    r = await client.post("/api/v1/auth/login/2fa", json={
        "mfa_ticket": mfa_ticket, "method": "recovery", "code": "XXXX-XXXX",
    })
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "2FA_RECOVERY_EXHAUSTED"


# --- AUTH_RATE_LIMITED ---


async def test_auth_rate_limited(client):
    """Exhausting auth bucket returns AUTH_RATE_LIMITED code."""
    from vox.ratelimit import CATEGORIES
    max_tokens = CATEGORIES["auth"][0]

    for _ in range(max_tokens):
        await client.post("/api/v1/auth/login", json={"username": "nobody", "password": "nope"})

    r = await client.post("/api/v1/auth/login", json={"username": "nobody", "password": "nope"})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "AUTH_RATE_LIMITED"


# --- CMD_NOT_FOUND ---


async def _setup_bot(client):
    token, uid = await _register(client, "human")
    h = {"Authorization": f"Bearer {token}"}

    from vox.db.engine import get_session_factory
    from vox.db.models import Bot, User
    from datetime import datetime, timezone
    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as db:
        # Create bot user
        bot_user = User(username="testbot", federated=False, active=True, created_at=datetime.now(timezone.utc))
        db.add(bot_user)
        await db.flush()
        bot = Bot(user_id=bot_user.id, owner_id=uid, created_at=datetime.now(timezone.utc))
        db.add(bot)
        await db.flush()

        # Create a session for the bot user
        from vox.auth.service import create_session
        bot_token = await create_session(db, bot_user.id)
        await db.commit()

    bot_h = {"Authorization": f"Bearer {bot_token}"}
    return h, bot_h, bot_user.id


async def test_cmd_not_found(client):
    """Deregistering a nonexistent command returns CMD_NOT_FOUND."""
    h, bot_h, bot_uid = await _setup_bot(client)

    r = await client.request("DELETE", f"/api/v1/bots/{bot_uid}/commands", headers=bot_h, json={
        "command_names": ["nonexistent"],
    })
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "CMD_NOT_FOUND"


# --- CMD_ALREADY_REGISTERED ---


async def test_cmd_already_registered(client):
    """Registering a duplicate command returns CMD_ALREADY_REGISTERED."""
    h, bot_h, bot_uid = await _setup_bot(client)

    r = await client.put(f"/api/v1/bots/{bot_uid}/commands", headers=bot_h, json={
        "commands": [{"name": "help", "description": "Show help"}]
    })
    assert r.status_code == 200

    r = await client.put(f"/api/v1/bots/{bot_uid}/commands", headers=bot_h, json={
        "commands": [{"name": "help", "description": "Updated help"}]
    })
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "CMD_ALREADY_REGISTERED"


# --- ROOM_FULL ---


async def test_room_full(client):
    """Joining a voice room at capacity returns ROOM_FULL."""
    token1, uid1 = await _register(client, "alice")
    token2, uid2 = await _register(client, "bob")
    h1 = {"Authorization": f"Bearer {token1}"}
    h2 = {"Authorization": f"Bearer {token2}"}

    # Create a room with max_members=1
    r = await client.post("/api/v1/rooms", headers=h1, json={"name": "tiny", "type": "voice"})
    assert r.status_code == 201
    room_id = r.json()["room_id"]

    # Set max_members=1 in DB
    from vox.db.engine import get_session_factory
    from vox.db.models import Room
    from sqlalchemy import select
    factory = get_session_factory()
    async with factory() as db:
        room = (await db.execute(select(Room).where(Room.id == room_id))).scalar_one()
        room.max_members = 1
        await db.commit()

    # Alice joins
    r = await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h1, json={})
    assert r.status_code == 200

    # Bob tries to join — should be ROOM_FULL
    r = await client.post(f"/api/v1/rooms/{room_id}/voice/join", headers=h2, json={})
    assert r.status_code == 503
    assert r.json()["detail"]["error"]["code"] == "ROOM_FULL"


# --- PREKEY_EXHAUSTED ---


async def test_prekey_exhausted_warning(client):
    """Fetching prekeys with no OTPs sets prekey_warning."""
    token, uid = await _register(client)
    h = {"Authorization": f"Bearer {token}"}

    # Add a device with prekeys but no OTPs
    r = await client.post("/api/v1/keys/devices", headers=h, json={
        "device_id": "dev1", "device_name": "Phone",
    })
    assert r.status_code == 201

    await client.put("/api/v1/keys/prekeys/dev1", headers=h, json={
        "identity_key": "aWRlbnRpdHk=",
        "signed_prekey": "c2lnbmVk",
        "one_time_prekeys": [],
    })

    # Fetch prekeys — should have warning
    r = await client.get(f"/api/v1/keys/prekeys/{uid}", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["prekey_warning"] == "PREKEY_EXHAUSTED"


async def test_prekey_no_warning_with_otps(client):
    """Fetching prekeys with OTPs available has no warning."""
    token, uid = await _register(client)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post("/api/v1/keys/devices", headers=h, json={
        "device_id": "dev1", "device_name": "Phone",
    })
    assert r.status_code == 201

    await client.put("/api/v1/keys/prekeys/dev1", headers=h, json={
        "identity_key": "aWRlbnRpdHk=",
        "signed_prekey": "c2lnbmVk",
        "one_time_prekeys": ["b3RwMQ==", "b3RwMg=="],
    })

    # Fetch prekeys — first fetch consumes one OTP, but one remains
    r = await client.get(f"/api/v1/keys/prekeys/{uid}", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["prekey_warning"] is None
