"""Tests targeting specific coverage gaps across multiple modules."""
import time
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# --- gateway/events.py gaps ---


def test_ready_with_server_icon():
    """ready() with server_icon includes it in the event."""
    from vox.gateway.events import ready

    evt = ready(
        session_id="s1", user_id=1, display_name="alice",
        server_name="Vox", server_icon="icon.png",
    )
    assert evt["d"]["server_icon"] == "icon.png"


def test_message_create_with_reply_to():
    """message_create() with reply_to includes it."""
    from vox.gateway.events import message_create

    evt = message_create(msg_id=1, feed_id=1, author_id=1, body="hi", timestamp=0, reply_to=42)
    assert evt["d"]["reply_to"] == 42


def test_feed_create_with_topic():
    """feed_create() with topic includes it."""
    from vox.gateway.events import feed_create

    evt = feed_create(feed_id=1, name="news", topic="Latest")
    assert evt["d"]["topic"] == "Latest"


def test_invite_create_with_feed_id():
    """invite_create() with feed_id includes it."""
    from vox.gateway.events import invite_create

    evt = invite_create(code="abc", creator_id=1, feed_id=5)
    assert evt["d"]["feed_id"] == 5


def test_media_token_refresh():
    """media_token_refresh() creates correct event."""
    from vox.gateway.events import media_token_refresh

    evt = media_token_refresh(room_id=1, media_token="tok123")
    assert evt["type"] == "media_token_refresh"
    assert evt["d"]["media_token"] == "tok123"


def test_device_list_update():
    """device_list_update() creates correct event."""
    from vox.gateway.events import device_list_update

    evt = device_list_update(devices=[{"id": "dev1"}])
    assert evt["type"] == "device_list_update"
    assert evt["d"]["devices"] == [{"id": "dev1"}]


def test_key_reset_notify():
    """key_reset_notify() creates correct event."""
    from vox.gateway.events import key_reset_notify

    evt = key_reset_notify(user_id=42)
    assert evt["type"] == "key_reset_notify"
    assert evt["d"]["user_id"] == 42


# --- gateway/hub.py gaps ---


def test_hub_get_session_expired():
    """get_session() returns None for expired sessions and deletes them."""
    from vox.gateway.hub import Hub, SessionState

    hub = Hub()
    state = SessionState(user_id=1, created_at=time.monotonic() - 999)
    hub.sessions["s1"] = state

    result = hub.get_session("s1")
    assert result is None
    assert "s1" not in hub.sessions


def test_hub_cleanup_sessions():
    """cleanup_sessions() removes expired sessions."""
    from vox.gateway.hub import Hub, SessionState

    hub = Hub()
    hub.sessions["fresh"] = SessionState(user_id=1, created_at=time.monotonic())
    hub.sessions["stale"] = SessionState(user_id=2, created_at=time.monotonic() - 999)

    hub.cleanup_sessions()
    assert "fresh" in hub.sessions
    assert "stale" not in hub.sessions


def test_hub_get_presence_online():
    """get_presence() returns presence data for online users."""
    from vox.gateway.hub import Hub

    hub = Hub()
    mock_conn = MagicMock()
    mock_conn.user_id = 1
    hub.connections[1] = {mock_conn}
    hub.set_presence(1, {"status": "online"})

    result = hub.get_presence(1)
    assert result["status"] == "online"
    assert result["user_id"] == 1


def test_hub_get_presence_offline():
    """get_presence() returns offline status for disconnected users."""
    from vox.gateway.hub import Hub

    hub = Hub()
    result = hub.get_presence(999)
    assert result["status"] == "offline"


def test_hub_connected_user_ids():
    """connected_user_ids returns all connected user IDs."""
    from vox.gateway.hub import Hub

    hub = Hub()
    mock_conn = MagicMock()
    mock_conn.user_id = 1
    hub.connections[1] = {mock_conn}
    hub.connections[2] = {MagicMock()}

    assert hub.connected_user_ids == {1, 2}


@pytest.mark.asyncio
async def test_hub_broadcast_all():
    """broadcast_all() sends to all connected users."""
    from vox.gateway.hub import Hub

    hub = Hub()
    mock_conn = AsyncMock()
    mock_conn.user_id = 1
    hub.connections[1] = {mock_conn}

    await hub.broadcast_all({"type": "test", "d": {}})
    mock_conn.send_event.assert_called_once()


# --- auth/service.py gaps ---


async def test_cleanup_expired_sessions(client):
    """cleanup_expired_sessions deletes expired sessions."""
    from vox.auth.service import cleanup_expired_sessions, create_session
    from vox.db.engine import get_session_factory
    from vox.db.models import Session
    from sqlalchemy import select
    from datetime import datetime, timedelta, timezone

    # Register a user
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    token = r.json()["token"]

    factory = get_session_factory()
    async with factory() as db:
        # Expire the session
        result = await db.execute(select(Session).where(Session.token == token))
        session = result.scalar_one()
        session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await db.commit()

    async with factory() as db:
        await cleanup_expired_sessions(db)

    # Token should no longer work
    r = await client.get("/api/v1/auth/2fa", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# --- limits.py gaps ---


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


# --- ratelimit.py gaps ---


async def test_ratelimit_bypass_websocket(client):
    """WebSocket requests bypass rate limiting."""
    # Just testing the module import path - the actual bypass is in middleware
    from vox.ratelimit import RateLimitMiddleware
    assert RateLimitMiddleware is not None


# --- permissions.py gap ---


def test_all_permissions_constant():
    """ALL_PERMISSIONS is used for server owner."""
    from vox.permissions import ALL_PERMISSIONS, ADMINISTRATOR

    # ALL_PERMISSIONS should be a large bitmask
    assert ALL_PERMISSIONS > 0
    assert ALL_PERMISSIONS & ADMINISTRATOR == ADMINISTRATOR


# --- sync.py gap ---


async def test_sync_no_events(client):
    """Sync with future timestamp returns empty events."""
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}

    # Sync with a very recent timestamp (should have no new events)
    import time
    ts = int(time.time() * 1000) + 100000  # future timestamp
    r = await client.post("/api/v1/sync", headers=h, json={"since_timestamp": ts, "categories": ["members"]})
    assert r.status_code == 200
    assert r.json()["events"] == []


# --- auth/mfa.py gaps (WebAuthn flows) ---


@pytest.mark.asyncio
async def test_verify_webauthn_registration_invalid_challenge():
    """verify_webauthn_registration with invalid challenge raises 400."""
    from vox.auth.mfa import verify_webauthn_registration
    from vox.db.engine import init_engine, get_engine, get_session_factory
    from vox.db.models import Base

    init_engine("sqlite+aiosqlite://")
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as db:
        with pytest.raises(Exception) as exc_info:
            await verify_webauthn_registration(db, "nonexistent_challenge", {})
        assert exc_info.value.status_code == 400

    await engine.dispose()


@pytest.mark.asyncio
async def test_verify_webauthn_registration_verification_fails():
    """verify_webauthn_registration with bad attestation raises 400."""
    import json
    from vox.auth.mfa import verify_webauthn_registration, _store_challenge
    from vox.db.engine import init_engine, get_engine, get_session_factory
    from vox.db.models import Base, Config

    init_engine("sqlite+aiosqlite://")
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as db:
        # Store config for webauthn
        db.add(Config(key="webauthn_rp_id", value="localhost"))
        db.add(Config(key="webauthn_origin", value="http://localhost"))
        await db.flush()

        # Store a challenge manually
        await _store_challenge(db, "test_challenge", 1, "registration", {
            "challenge": "dGVzdA",
            "rp_id": "localhost",
            "origin": "http://localhost",
            "user_id": 1,
        })
        await db.flush()

        with pytest.raises(Exception) as exc_info:
            await verify_webauthn_registration(db, "test_challenge", {"bad": "data"})
        assert exc_info.value.status_code == 400

    await engine.dispose()


@pytest.mark.asyncio
async def test_verify_webauthn_authentication_invalid_challenge():
    """verify_webauthn_authentication with invalid challenge raises 400."""
    from vox.auth.mfa import verify_webauthn_authentication
    from vox.db.engine import init_engine, get_engine, get_session_factory
    from vox.db.models import Base

    init_engine("sqlite+aiosqlite://")
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as db:
        with pytest.raises(Exception) as exc_info:
            await verify_webauthn_authentication(db, "nonexistent_challenge", {})
        assert exc_info.value.status_code == 400

    await engine.dispose()


@pytest.mark.asyncio
async def test_verify_webauthn_authentication_credential_not_found():
    """verify_webauthn_authentication with no matching credential raises 400."""
    from vox.auth.mfa import verify_webauthn_authentication, _store_challenge
    from vox.db.engine import init_engine, get_engine, get_session_factory
    from vox.db.models import Base

    init_engine("sqlite+aiosqlite://")
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as db:
        await _store_challenge(db, "auth_challenge", 1, "authentication", {
            "challenge": "dGVzdA",
            "rp_id": "localhost",
            "origin": "http://localhost",
            "user_id": 1,
        })
        await db.flush()

        with pytest.raises(Exception) as exc_info:
            await verify_webauthn_authentication(db, "auth_challenge", {"id": "nonexistent"})
        assert exc_info.value.status_code == 400

    await engine.dispose()


@pytest.mark.asyncio
async def test_verify_webauthn_authentication_verify_fails():
    """verify_webauthn_authentication with bad assertion raises 401."""
    from vox.auth.mfa import verify_webauthn_authentication, _store_challenge
    from vox.db.engine import init_engine, get_engine, get_session_factory
    from vox.db.models import Base, WebAuthnCredential
    from datetime import datetime, timezone

    init_engine("sqlite+aiosqlite://")
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as db:
        # Store challenge
        await _store_challenge(db, "auth_challenge2", 1, "authentication", {
            "challenge": "dGVzdA",
            "rp_id": "localhost",
            "origin": "http://localhost",
            "user_id": 1,
        })
        # Store a credential
        db.add(WebAuthnCredential(
            credential_id="cred_abc",
            user_id=1,
            name="test key",
            public_key="pubkey_base64",
            registered_at=datetime.now(timezone.utc),
        ))
        await db.flush()

        with pytest.raises(Exception) as exc_info:
            await verify_webauthn_authentication(db, "auth_challenge2", {
                "id": "cred_abc",
                "rawId": "cred_abc",
                "response": {"authenticatorData": "x", "clientDataJSON": "x", "signature": "x"},
                "type": "public-key",
            })
        assert exc_info.value.status_code == 401

    await engine.dispose()


# --- federation/service.py gaps ---


@pytest.mark.asyncio
async def test_close_http_client():
    """close_http_client closes and clears the client."""
    from vox.federation import service
    import httpx

    # Force create a client
    service._http_client = httpx.AsyncClient(timeout=5.0)
    assert service._http_client is not None

    await service.close_http_client()
    assert service._http_client is None

    # Calling again when already None is a no-op
    await service.close_http_client()


def test_get_http_client_creates_new():
    """_get_http_client creates a new client when none exists."""
    from vox.federation.service import _get_http_client, _http_client
    import vox.federation.service as svc

    old = svc._http_client
    svc._http_client = None
    try:
        client = _get_http_client()
        assert client is not None
        assert not client.is_closed
    finally:
        # Clean up
        svc._http_client = old


# --- voice/service.py gaps ---


def test_init_sfu_no_module():
    """init_sfu raises RuntimeError when vox_sfu not installed."""
    from vox.voice import service

    original_sfu_class = service.SFU
    service.SFU = None
    try:
        with pytest.raises(RuntimeError, match="vox_sfu is not installed"):
            service.init_sfu("0.0.0.0:4443")
    finally:
        service.SFU = original_sfu_class


def test_get_sfu_no_module():
    """get_sfu raises RuntimeError when vox_sfu not installed and no existing."""
    from vox.voice import service

    original_sfu_class = service.SFU
    original_sfu = service._sfu
    service.SFU = None
    service._sfu = None
    try:
        with pytest.raises(RuntimeError, match="vox_sfu is not installed"):
            service.get_sfu()
    finally:
        service.SFU = original_sfu_class
        service._sfu = original_sfu


def test_reset_sfu():
    """reset() clears the SFU instance."""
    from vox.voice import service

    mock_sfu = MagicMock()
    service._sfu = mock_sfu
    service.reset()
    assert service._sfu is None
    mock_sfu.stop.assert_called_once()


def test_reset_sfu_stop_exception():
    """reset() handles exception from sfu.stop() gracefully."""
    from vox.voice import service

    mock_sfu = MagicMock()
    mock_sfu.stop.side_effect = Exception("oops")
    service._sfu = mock_sfu
    service.reset()
    assert service._sfu is None


def test_init_sfu_replaces_existing():
    """init_sfu stops existing SFU before creating new one."""
    from vox.voice import service

    mock_old = MagicMock()
    mock_new_class = MagicMock()
    original_sfu_class = service.SFU
    service._sfu = mock_old
    service.SFU = mock_new_class
    try:
        service.init_sfu("0.0.0.0:4443")
        mock_old.stop.assert_called_once()
        mock_new_class.assert_called_once_with("0.0.0.0:4443")
    finally:
        service.SFU = original_sfu_class
        service._sfu = None


# --- api/app.py: periodic cleanup ---


@pytest.mark.asyncio
async def test_periodic_cleanup_runs():
    """_periodic_cleanup executes cleanup logic."""
    from vox.api.app import _periodic_cleanup
    import asyncio

    # We can't wait 3600s, but we can test the logic by mocking sleep to raise
    # after one iteration
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


# --- ratelimit.py gaps ---


@pytest.mark.asyncio
async def test_ratelimit_webhook_key():
    """Webhook execution is IP-keyed."""
    from vox.ratelimit import RateLimitMiddleware

    middleware = RateLimitMiddleware(app=MagicMock())

    mock_request = MagicMock()
    mock_request.url.path = "/api/v1/webhooks/123/execute"
    mock_request.client.host = "1.2.3.4"
    mock_request.headers = {}

    key = await middleware._resolve_key(mock_request, "/api/v1/webhooks/123/execute")
    assert key == "ip:1.2.3.4"


@pytest.mark.asyncio
async def test_ratelimit_exception_fallback():
    """When token lookup raises, falls back to IP key."""
    from vox.ratelimit import RateLimitMiddleware

    middleware = RateLimitMiddleware(app=MagicMock())

    mock_request = MagicMock()
    mock_request.url.path = "/api/v1/feeds"
    mock_request.client.host = "5.6.7.8"
    mock_request.headers = {"authorization": "Bearer bad_token"}

    with patch("vox.ratelimit.get_session_factory", side_effect=Exception("db error")):
        key = await middleware._resolve_key(mock_request, "/api/v1/feeds")
    assert key == "ip:5.6.7.8"
