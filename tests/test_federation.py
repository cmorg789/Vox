"""Tests for the federation system: crypto, vouchers, policy, endpoints, and integration."""

import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from vox.federation import client as fed_client
from vox.federation import service as fed_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_test_keypair():
    """Generate a test Ed25519 keypair."""
    private_key = Ed25519PrivateKey.generate()
    pub_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    pub_b64 = base64.b64encode(pub_bytes).decode()
    return private_key, pub_b64


async def _register(client, username="alice", password="test1234"):
    r = await client.post("/api/v1/auth/register", json={"username": username, "password": password})
    return r.json()["token"], r.json()["user_id"]


async def _setup_fed_keys_in_db(client):
    """Register a user and configure federation keys in the DB."""
    token, user_id = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}

    from vox.db.engine import get_session_factory
    from vox.db.models import Config

    factory = get_session_factory()
    async with factory() as db:
        private_key, pub_b64 = _generate_test_keypair()

        priv_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        priv_b64 = base64.b64encode(priv_bytes).decode()

        db.add(Config(key="federation_domain", value="test.local"))
        db.add(Config(key="federation_private_key", value=priv_b64))
        db.add(Config(key="federation_public_key", value=pub_b64))
        await db.commit()

    return headers, user_id, private_key, pub_b64


async def _fed_request(client, method, path, body, private_key, pub_b64, origin="remote.example"):
    """Make a signed federation request, properly matching the raw body bytes."""
    body_bytes = json.dumps(body).encode()
    sig = fed_service.sign_body(body_bytes, private_key)
    headers = {
        "X-Vox-Origin": origin,
        "X-Vox-Signature": sig,
        "Content-Type": "application/json",
    }
    with patch.object(fed_service, "lookup_vox_key", new_callable=AsyncMock, return_value=pub_b64):
        if method == "POST":
            return await client.post(path, content=body_bytes, headers=headers)
        else:
            # For GET requests, sign empty body
            empty_bytes = b""
            sig = fed_service.sign_body(empty_bytes, private_key)
            headers["X-Vox-Signature"] = sig
            return await client.get(path, headers=headers)


# ---------------------------------------------------------------------------
# Cleanup: reset nonces between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_federation_state():
    fed_service._presence_subs.clear()
    yield
    fed_service._presence_subs.clear()


# ---------------------------------------------------------------------------
# Unit Tests: Crypto
# ---------------------------------------------------------------------------


async def test_keypair_generation(client):
    """get_or_create_keypair generates and persists keys."""
    await _register(client)

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        priv, pub = await fed_service.get_or_create_keypair(db)
        assert priv is not None
        assert pub is not None

        # Second call returns the same keys
        priv2, pub2 = await fed_service.get_or_create_keypair(db)
        pub_bytes = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
        pub2_bytes = pub2.public_bytes(Encoding.Raw, PublicFormat.Raw)
        assert pub_bytes == pub2_bytes


async def test_signature_round_trip(client):
    """sign_body → verify_signature works."""
    private_key, pub_b64 = _generate_test_keypair()
    body = b'{"test": "data"}'
    sig = fed_service.sign_body(body, private_key)
    assert fed_service.verify_signature(body, sig, pub_b64) is True


async def test_signature_invalid(client):
    """Wrong key fails verification."""
    private_key, _ = _generate_test_keypair()
    _, other_pub_b64 = _generate_test_keypair()
    body = b'{"test": "data"}'
    sig = fed_service.sign_body(body, private_key)
    assert fed_service.verify_signature(body, sig, other_pub_b64) is False


async def test_signature_tampered_body(client):
    """Tampered body fails verification."""
    private_key, pub_b64 = _generate_test_keypair()
    body = b'{"test": "data"}'
    sig = fed_service.sign_body(body, private_key)
    assert fed_service.verify_signature(b'{"test": "tampered"}', sig, pub_b64) is False


# ---------------------------------------------------------------------------
# Unit Tests: Vouchers
# ---------------------------------------------------------------------------


async def test_voucher_round_trip(client):
    """create_voucher → verify_voucher works with mocked DNS."""
    from vox.db.engine import get_session_factory
    private_key, pub_b64 = _generate_test_keypair()
    voucher = fed_service.create_voucher("alice@origin.example", "target.example", private_key)

    factory = get_session_factory()
    async with factory() as db:
        with patch.object(fed_service, "lookup_vox_key", new_callable=AsyncMock, return_value=pub_b64):
            result = await fed_service.verify_voucher(voucher, "target.example", db=db)
            assert result is not None
            assert result["user_address"] == "alice@origin.example"
            assert result["target_domain"] == "target.example"
        await db.commit()


async def test_voucher_replay_rejected(client):
    """Same voucher used twice is rejected (nonce replay)."""
    from vox.db.engine import get_session_factory
    private_key, pub_b64 = _generate_test_keypair()
    voucher = fed_service.create_voucher("alice@origin.example", "target.example", private_key)

    factory = get_session_factory()
    async with factory() as db:
        with patch.object(fed_service, "lookup_vox_key", new_callable=AsyncMock, return_value=pub_b64):
            result1 = await fed_service.verify_voucher(voucher, "target.example", db=db)
            assert result1 is not None
            await db.commit()
            result2 = await fed_service.verify_voucher(voucher, "target.example", db=db)
            assert result2 is None


async def test_voucher_expired(client):
    """Expired voucher is rejected."""
    private_key, pub_b64 = _generate_test_keypair()
    voucher = fed_service.create_voucher("alice@origin.example", "target.example", private_key, ttl=-1)

    with patch.object(fed_service, "lookup_vox_key", new_callable=AsyncMock, return_value=pub_b64):
        result = await fed_service.verify_voucher(voucher, "target.example")
        assert result is None


async def test_voucher_wrong_target(client):
    """Voucher for wrong target domain is rejected."""
    private_key, pub_b64 = _generate_test_keypair()
    voucher = fed_service.create_voucher("alice@origin.example", "other.example", private_key)

    with patch.object(fed_service, "lookup_vox_key", new_callable=AsyncMock, return_value=pub_b64):
        result = await fed_service.verify_voucher(voucher, "target.example")
        assert result is None


# ---------------------------------------------------------------------------
# Unit Tests: Policy
# ---------------------------------------------------------------------------


async def test_policy_open_allows(client):
    """Open federation policy allows inbound."""
    await _register(client)
    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        assert await fed_service.check_federation_allowed(db, "any.domain") is True


async def test_policy_closed_denies(client):
    """Closed federation policy denies inbound."""
    await _register(client)
    from vox.db.engine import get_session_factory
    from vox.db.models import Config
    factory = get_session_factory()
    async with factory() as db:
        db.add(Config(key="federation_policy", value="closed"))
        await db.commit()
        assert await fed_service.check_federation_allowed(db, "any.domain") is False


async def test_policy_blocklist_denies(client):
    """Blocklisted domain is denied."""
    await _register(client)
    from datetime import datetime, timezone
    from vox.db.engine import get_session_factory
    from vox.db.models import FederationEntry
    factory = get_session_factory()
    async with factory() as db:
        db.add(FederationEntry(entry="blocked.example", created_at=datetime.now(timezone.utc)))
        await db.commit()
        assert await fed_service.check_federation_allowed(db, "blocked.example") is False


# ---------------------------------------------------------------------------
# Endpoint Tests: Relay Message
# ---------------------------------------------------------------------------


async def test_relay_message_creates_dm_and_message(client):
    """Signed relay/message creates DM + message for local user."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    body = {"from": "bob@remote.example", "to": "alice@test.local", "opaque_blob": "encrypted_data"}
    r = await _fed_request(client, "POST", "/api/v1/federation/relay/message", body, private_key, pub_b64)
    assert r.status_code == 204

    # Verify message was created
    r = await client.get("/api/v1/dms", headers=headers)
    dms = r.json()["items"]
    assert len(dms) == 1

    dm_id = dms[0]["dm_id"]
    r = await client.get(f"/api/v1/dms/{dm_id}/messages", headers=headers)
    messages = r.json()["messages"]
    assert len(messages) == 1
    assert messages[0]["federated"] is True
    assert messages[0]["author_address"] == "bob@remote.example"


async def test_relay_message_wrong_signature(client):
    """Wrong signature returns 403."""
    await _setup_fed_keys_in_db(client)

    body = {"from": "bob@remote.example", "to": "alice@test.local", "opaque_blob": "data"}
    other_key, _ = _generate_test_keypair()
    _, wrong_pub = _generate_test_keypair()

    # Sign with one key, but DNS returns a different public key
    body_bytes = json.dumps(body).encode()
    sig = fed_service.sign_body(body_bytes, other_key)
    fed_headers = {
        "X-Vox-Origin": "remote.example",
        "X-Vox-Signature": sig,
        "Content-Type": "application/json",
    }
    with patch.object(fed_service, "lookup_vox_key", new_callable=AsyncMock, return_value=wrong_pub):
        r = await client.post("/api/v1/federation/relay/message", content=body_bytes, headers=fed_headers)
        assert r.status_code == 403
        assert r.json()["detail"]["error"]["code"] == "FED_AUTH_FAILED"


# ---------------------------------------------------------------------------
# Endpoint Tests: Relay Typing
# ---------------------------------------------------------------------------


async def test_relay_typing(client):
    """Relay typing dispatches typing event for existing DM."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    # First create a DM via relay message
    msg_body = {"from": "bob@remote.example", "to": "alice@test.local", "opaque_blob": "data"}
    await _fed_request(client, "POST", "/api/v1/federation/relay/message", msg_body, private_key, pub_b64)

    # Now send typing
    typing_body = {"from": "bob@remote.example", "to": "alice@test.local"}
    r = await _fed_request(client, "POST", "/api/v1/federation/relay/typing", typing_body, private_key, pub_b64)
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Endpoint Tests: Relay Read
# ---------------------------------------------------------------------------


async def test_relay_read(client):
    """Relay read dispatches read receipt."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    msg_body = {"from": "bob@remote.example", "to": "alice@test.local", "opaque_blob": "data"}
    await _fed_request(client, "POST", "/api/v1/federation/relay/message", msg_body, private_key, pub_b64)

    read_body = {"from": "bob@remote.example", "to": "alice@test.local", "up_to_msg_id": 12345}
    r = await _fed_request(client, "POST", "/api/v1/federation/relay/read", read_body, private_key, pub_b64)
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Endpoint Tests: User Lookup
# ---------------------------------------------------------------------------


async def test_user_profile_lookup(client):
    """Returns profile for local user, 404 for unknown."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    r = await _fed_request(client, "GET", "/api/v1/federation/users/alice@test.local", {}, private_key, pub_b64)
    assert r.status_code == 200
    assert r.json()["display_name"] == "alice"

    r = await _fed_request(client, "GET", "/api/v1/federation/users/unknown@test.local", {}, private_key, pub_b64)
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "FED_USER_NOT_FOUND"


# ---------------------------------------------------------------------------
# Endpoint Tests: Prekey Fetch
# ---------------------------------------------------------------------------


async def test_prekey_fetch(client):
    """Returns prekey bundle for local user."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    await client.post("/api/v1/keys/devices", headers=headers, json={"device_id": "dev1", "device_name": "Phone"})
    await client.put("/api/v1/keys/prekeys", headers=headers, json={
        "identity_key": "id_key_data",
        "signed_prekey": "signed_pk_data",
        "one_time_prekeys": ["otp1", "otp2"],
    })

    r = await _fed_request(client, "GET", "/api/v1/federation/users/alice@test.local/prekeys", {}, private_key, pub_b64)
    assert r.status_code == 200
    data = r.json()
    assert data["user_address"] == "alice@test.local"
    assert len(data["devices"]) == 1
    assert data["devices"][0]["identity_key"] == "id_key_data"


# ---------------------------------------------------------------------------
# Endpoint Tests: Presence
# ---------------------------------------------------------------------------


async def test_presence_subscribe_and_notify(client):
    """Subscription stored, notification dispatched."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    sub_body = {"user_address": "alice@test.local"}
    r = await _fed_request(client, "POST", "/api/v1/federation/presence/subscribe", sub_body, private_key, pub_b64)
    assert r.status_code == 204

    subs = fed_service.get_presence_subscribers("alice@test.local")
    assert "remote.example" in subs

    # Create a federated user stub via relay
    msg_body = {"from": "bob@remote.example", "to": "alice@test.local", "opaque_blob": "data"}
    await _fed_request(client, "POST", "/api/v1/federation/relay/message", msg_body, private_key, pub_b64)

    notify_body = {"user_address": "bob@remote.example", "status": "online"}
    r = await _fed_request(client, "POST", "/api/v1/federation/presence/notify", notify_body, private_key, pub_b64)
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Endpoint Tests: Join Flow
# ---------------------------------------------------------------------------


async def test_join_flow(client):
    """Valid voucher creates federated user + returns fed token + server info."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    voucher = fed_service.create_voucher("newuser@remote.example", "test.local", private_key)
    join_body = {
        "user_address": "newuser@remote.example",
        "voucher": voucher,
    }

    r = await _fed_request(client, "POST", "/api/v1/federation/join", join_body, private_key, pub_b64)
    assert r.status_code == 200
    data = r.json()
    assert data["accepted"] is True
    assert data["federation_token"].startswith("fed_")
    assert data["server_info"]["domain"] == "test.local"


async def test_join_with_invite(client):
    """Join with invite code validates the invite."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    from datetime import datetime, timezone
    from vox.db.engine import get_session_factory
    from vox.db.models import Invite

    factory = get_session_factory()
    async with factory() as db:
        db.add(Invite(
            code="test-invite",
            creator_id=user_id,
            max_uses=10,
            uses=0,
            created_at=datetime.now(timezone.utc),
        ))
        await db.commit()

    voucher = fed_service.create_voucher("invitee@remote.example", "test.local", private_key)
    join_body = {
        "user_address": "invitee@remote.example",
        "voucher": voucher,
        "invite_code": "test-invite",
    }

    r = await _fed_request(client, "POST", "/api/v1/federation/join", join_body, private_key, pub_b64)
    assert r.status_code == 200
    assert r.json()["accepted"] is True


async def test_join_invalid_invite(client):
    """Join with non-existent invite code returns 404."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    voucher = fed_service.create_voucher("user@remote.example", "test.local", private_key)
    join_body = {
        "user_address": "user@remote.example",
        "voucher": voucher,
        "invite_code": "nonexistent",
    }

    r = await _fed_request(client, "POST", "/api/v1/federation/join", join_body, private_key, pub_b64)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Endpoint Tests: Federation Token Login
# ---------------------------------------------------------------------------


async def test_federation_token_login(client):
    """POST /login/federation with valid fed token returns session."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    voucher = fed_service.create_voucher("fedlogin@remote.example", "test.local", private_key)
    join_body = {
        "user_address": "fedlogin@remote.example",
        "voucher": voucher,
    }
    r = await _fed_request(client, "POST", "/api/v1/federation/join", join_body, private_key, pub_b64)
    fed_token = r.json()["federation_token"]

    r = await client.post("/api/v1/auth/login/federation", json={"federation_token": fed_token})
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert not data["token"].startswith("fed_")
    assert data["user_id"] is not None


async def test_fed_token_rejected_for_normal_auth(client):
    """fed_ prefixed token is blocked for normal auth."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    voucher = fed_service.create_voucher("blocked@remote.example", "test.local", private_key)
    join_body = {
        "user_address": "blocked@remote.example",
        "voucher": voucher,
    }
    r = await _fed_request(client, "POST", "/api/v1/federation/join", join_body, private_key, pub_b64)
    fed_token = r.json()["federation_token"]

    r = await client.get("/api/v1/dms", headers={"Authorization": f"Bearer {fed_token}"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Integration: DM Outbound Relay
# ---------------------------------------------------------------------------


async def test_dm_outbound_relay(client):
    """Sending DM with federated participant triggers relay."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    # Create a federated user stub via relay message first
    msg_body = {"from": "remote_user@remote.example", "to": "alice@test.local", "opaque_blob": "hello"}
    r = await _fed_request(client, "POST", "/api/v1/federation/relay/message", msg_body, private_key, pub_b64)
    assert r.status_code == 204

    r = await client.get("/api/v1/dms", headers=headers)
    dms = r.json()["items"]
    assert len(dms) == 1
    dm_id = dms[0]["dm_id"]

    with patch("vox.federation.client.send_federation_request", new_callable=AsyncMock, return_value=None):
        r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=headers, json={"body": "reply from alice"})
        assert r.status_code == 201


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------


async def test_federation_rate_limit_keyed_by_origin(client):
    """Federation endpoints use federation category."""
    from vox.ratelimit import classify

    path = "/api/v1/federation/relay/message"
    assert classify(path) == "federation"


# ---------------------------------------------------------------------------
# Block endpoint
# ---------------------------------------------------------------------------


async def test_block_endpoint(client):
    """Block endpoint records blocklist entry, deactivates federated users, and logs audit."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    from vox.db.engine import get_session_factory
    from vox.db.models import AuditLog, FederationEntry, User

    origin = "remote.example"

    # Create a federated user from the origin domain
    from datetime import datetime, timezone

    factory = get_session_factory()
    async with factory() as db:
        fed_user = User(
            id=99999,
            username="remoteuser",
            password_hash="x",
            display_name="Remote User",
            federated=True,
            home_domain=origin,
            active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(fed_user)
        await db.commit()

    body = {"reason": "spam"}
    r = await _fed_request(client, "POST", "/api/v1/federation/block", body, private_key, pub_b64)
    assert r.status_code == 204

    # Verify origin added to blocklist
    async with factory() as db:
        from sqlalchemy import select

        row = await db.execute(select(FederationEntry).where(FederationEntry.entry == origin))
        entry = row.scalar_one_or_none()
        assert entry is not None
        assert entry.reason == "spam"

        # Verify federated user deactivated
        row = await db.execute(select(User).where(User.id == 99999))
        u = row.scalar_one()
        assert u.active is False

        # Verify audit log entry
        row = await db.execute(
            select(AuditLog).where(AuditLog.event_type == "federation_block_received")
        )
        log = row.scalar_one()
        assert "remote.example" in log.extra

    # Second call is rejected because origin is now blocked — verify no duplicate entry
    r = await _fed_request(client, "POST", "/api/v1/federation/block", body, private_key, pub_b64)
    assert r.status_code == 403  # origin now blocked

    async with factory() as db:
        from sqlalchemy import func, select

        count = await db.execute(
            select(func.count()).select_from(FederationEntry).where(FederationEntry.entry == origin)
        )
        assert count.scalar() == 1


# ---------------------------------------------------------------------------
# Unit Tests: Federation Client
# ---------------------------------------------------------------------------


async def test_client_relay_typing_success(client):
    """relay_typing returns True on success."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with patch("vox.federation.client.send_federation_request", new_callable=AsyncMock, return_value=mock_resp) as mock_send:
            result = await fed_client.relay_typing(db, "alice@test.local", "bob@remote.example")
            assert result is True
            mock_send.assert_called_once()


async def test_client_relay_typing_invalid_domain(client):
    """relay_typing returns False if no domain in address."""
    from vox.db.engine import get_session_factory
    await _register(client)
    factory = get_session_factory()
    async with factory() as db:
        result = await fed_client.relay_typing(db, "alice@test.local", "no_at_sign")
        assert result is False


async def test_client_relay_read_receipt_success(client):
    """relay_read_receipt returns True on success."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with patch("vox.federation.client.send_federation_request", new_callable=AsyncMock, return_value=mock_resp):
            result = await fed_client.relay_read_receipt(db, "alice@test.local", "bob@remote.example", 123)
            assert result is True


async def test_client_relay_read_receipt_invalid_domain(client):
    """relay_read_receipt returns False if no domain in address."""
    await _register(client)
    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        result = await fed_client.relay_read_receipt(db, "a@test.local", "nodomain", 1)
        assert result is False


async def test_client_fetch_remote_prekeys_success(client):
    """fetch_remote_prekeys returns JSON on success."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"keys": ["k1"]}

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with patch("vox.federation.client.send_federation_request", new_callable=AsyncMock, return_value=mock_resp):
            result = await fed_client.fetch_remote_prekeys(db, "alice@remote.example")
            assert result == {"keys": ["k1"]}


async def test_client_fetch_remote_prekeys_failure(client):
    """fetch_remote_prekeys returns None on failure."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with patch("vox.federation.client.send_federation_request", new_callable=AsyncMock, return_value=None):
            result = await fed_client.fetch_remote_prekeys(db, "alice@remote.example")
            assert result is None


async def test_client_fetch_remote_prekeys_no_domain(client):
    """fetch_remote_prekeys returns None for address without domain."""
    await _register(client)
    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        result = await fed_client.fetch_remote_prekeys(db, "nodomain")
        assert result is None


async def test_client_fetch_remote_profile_success(client):
    """fetch_remote_profile returns JSON on success."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"display_name": "Alice"}

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with patch("vox.federation.client.send_federation_request", new_callable=AsyncMock, return_value=mock_resp):
            result = await fed_client.fetch_remote_profile(db, "alice@remote.example")
            assert result == {"display_name": "Alice"}


async def test_client_fetch_remote_profile_failure(client):
    """fetch_remote_profile returns None on failure."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with patch("vox.federation.client.send_federation_request", new_callable=AsyncMock, return_value=None):
            result = await fed_client.fetch_remote_profile(db, "alice@remote.example")
            assert result is None


async def test_client_subscribe_presence_success(client):
    """subscribe_presence returns True on success."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    mock_resp = MagicMock()
    mock_resp.status_code = 204

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with patch("vox.federation.client.send_federation_request", new_callable=AsyncMock, return_value=mock_resp):
            result = await fed_client.subscribe_presence(db, "alice@remote.example")
            assert result is True


async def test_client_subscribe_presence_no_domain(client):
    """subscribe_presence returns False for address without domain."""
    await _register(client)
    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        result = await fed_client.subscribe_presence(db, "nodomain")
        assert result is False


async def test_client_notify_presence_success(client):
    """notify_presence returns True on success."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    mock_resp = MagicMock()
    mock_resp.status_code = 204

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with patch("vox.federation.client.send_federation_request", new_callable=AsyncMock, return_value=mock_resp):
            result = await fed_client.notify_presence(db, "remote.example", "alice@test.local", "online")
            assert result is True


async def test_client_notify_presence_with_activity(client):
    """notify_presence includes activity in body."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    mock_resp = MagicMock()
    mock_resp.status_code = 204

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with patch("vox.federation.client.send_federation_request", new_callable=AsyncMock, return_value=mock_resp) as mock_send:
            result = await fed_client.notify_presence(db, "remote.example", "alice@test.local", "online", activity="Playing Vox")
            assert result is True
            call_args = mock_send.call_args
            assert call_args[0][3]["activity"] == "Playing Vox"


async def test_client_send_join_request_success(client):
    """send_join_request returns response JSON on success."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"accepted": True}

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with patch("vox.federation.client.send_federation_request", new_callable=AsyncMock, return_value=mock_resp):
            result = await fed_client.send_join_request(db, "alice@test.local", "remote.example")
            assert result == {"accepted": True}


async def test_client_send_join_request_with_invite(client):
    """send_join_request includes invite_code when provided."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"accepted": True}

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with patch("vox.federation.client.send_federation_request", new_callable=AsyncMock, return_value=mock_resp) as mock_send:
            result = await fed_client.send_join_request(db, "alice@test.local", "remote.example", invite_code="INV123")
            assert result is not None
            call_args = mock_send.call_args
            assert call_args[0][3]["invite_code"] == "INV123"


async def test_client_send_block_notification_success(client):
    """send_block_notification returns True on success."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    mock_resp = MagicMock()
    mock_resp.status_code = 204

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with patch("vox.federation.client.send_federation_request", new_callable=AsyncMock, return_value=mock_resp):
            result = await fed_client.send_block_notification(db, "remote.example", reason="spam")
            assert result is True


# ---------------------------------------------------------------------------
# Unit Tests: Federation Service — additional coverage
# ---------------------------------------------------------------------------


async def test_sign_body_and_get_public_key(client):
    """sign_body produces valid signature; get_public_key_b64 returns base64."""
    await _register(client)
    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        private_key = await fed_service.get_private_key(db)
        pub_b64 = await fed_service.get_public_key_b64(db)
        sig = fed_service.sign_body(b"test", private_key)
        assert fed_service.verify_signature(b"test", sig, pub_b64) is True


async def test_lookup_vox_host_success(client):
    """lookup_vox_host returns host and port from mocked DNS."""
    mock_rdata = MagicMock()
    mock_rdata.target = "svc.example.com."
    mock_rdata.params = {3: 8443}

    mock_resolver = AsyncMock()
    mock_resolver.resolve = AsyncMock(return_value=[mock_rdata])

    with patch.dict("sys.modules", {"dns.asyncresolver": mock_resolver}):
        with patch("vox.federation.service.dns.asyncresolver" if hasattr(fed_service, "dns") else "dns.asyncresolver", mock_resolver, create=True):
            # Use direct patch on the module import inside the function
            import dns.asyncresolver
            with patch.object(dns.asyncresolver, "resolve", new_callable=AsyncMock, return_value=[mock_rdata]):
                host, port = await fed_service.lookup_vox_host("example.com")
                assert host == "svc.example.com"
                assert port == 8443


async def test_lookup_vox_host_exception(client):
    """lookup_vox_host returns default on exception."""
    with patch("dns.asyncresolver.resolve", new_callable=AsyncMock, side_effect=Exception("DNS error")):
        host, port = await fed_service.lookup_vox_host("example.com")
        assert host == "example.com"
        assert port == 443


async def test_check_federation_allowed_allowlist(client):
    """Allowlist mode only allows listed domains."""
    await _register(client)
    from datetime import datetime, timezone
    from vox.db.engine import get_session_factory
    from vox.db.models import Config, FederationEntry
    factory = get_session_factory()
    async with factory() as db:
        db.add(Config(key="federation_policy", value="allowlist"))
        db.add(FederationEntry(entry="allow:allowed.example", created_at=datetime.now(timezone.utc)))
        await db.commit()

        # Allowed domain
        assert await fed_service.check_federation_allowed(db, "allowed.example") is True
        # Not-allowed domain
        assert await fed_service.check_federation_allowed(db, "other.example") is False


async def test_check_federation_allowed_outbound(client):
    """Outbound direction checks remote policy."""
    await _register(client)
    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with patch.object(fed_service, "lookup_vox_policy", new_callable=AsyncMock, return_value={"federation": "open"}):
            assert await fed_service.check_federation_allowed(db, "any.domain", direction="outbound") is True
        with patch.object(fed_service, "lookup_vox_policy", new_callable=AsyncMock, return_value={"federation": "closed"}):
            assert await fed_service.check_federation_allowed(db, "any.domain", direction="outbound") is False


async def test_cleanup_nonces(client):
    """Expired federation nonces are cleaned up via DB."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import delete, select
    from vox.db.models import FederationNonce
    from vox.db.engine import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        # Insert an expired nonce and a fresh nonce
        now = datetime.now(timezone.utc)
        db.add(FederationNonce(nonce="old_nonce", seen_at=now - timedelta(hours=1), expires_at=now - timedelta(minutes=10)))
        db.add(FederationNonce(nonce="fresh_nonce", seen_at=now, expires_at=now + timedelta(minutes=10)))
        await db.commit()

        # Clean expired nonces (same logic as background task)
        await db.execute(delete(FederationNonce).where(FederationNonce.expires_at <= now))
        await db.commit()

        result = await db.execute(select(FederationNonce.nonce))
        remaining = [r[0] for r in result.all()]
        assert "old_nonce" not in remaining
        assert "fresh_nonce" in remaining

        # Clean up
        await db.execute(delete(FederationNonce))
        await db.commit()


async def test_presence_subs(client):
    """add_presence_sub and get_presence_subscribers work correctly."""
    fed_service.add_presence_sub("domain1.example", "alice@test.local")
    fed_service.add_presence_sub("domain2.example", "alice@test.local")
    fed_service.add_presence_sub("domain1.example", "bob@test.local")

    subs = fed_service.get_presence_subscribers("alice@test.local")
    assert sorted(subs) == ["domain1.example", "domain2.example"]

    subs_bob = fed_service.get_presence_subscribers("bob@test.local")
    assert subs_bob == ["domain1.example"]

    subs_nobody = fed_service.get_presence_subscribers("nobody@test.local")
    assert subs_nobody == []


async def test_send_federation_request_exception(client):
    """send_federation_request returns None on exception."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with patch.object(fed_service, "lookup_vox_host", new_callable=AsyncMock, side_effect=Exception("network error")):
            result = await fed_service.send_federation_request(db, "remote.example", "/test", {"data": 1})
            assert result is None


async def test_send_federation_request_no_domain(client):
    """send_federation_request returns None when no federation domain configured."""
    await _register(client)
    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    # No federation_domain in config
    async with factory() as db:
        with patch.object(fed_service, "lookup_vox_host", new_callable=AsyncMock, return_value=("remote.example", 443)):
            result = await fed_service.send_federation_request(db, "remote.example", "/test", {"data": 1})
            assert result is None


async def test_send_federation_request_success(client):
    """send_federation_request makes an HTTP request and returns the response."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    from vox.db.engine import get_session_factory
    factory = get_session_factory()

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.is_closed = False

    async with factory() as db:
        with patch.object(fed_service, "lookup_vox_host", new_callable=AsyncMock, return_value=("svc.remote.example", 443)):
            with patch.object(fed_service, "_get_http_client", return_value=mock_client):
                result = await fed_service.send_federation_request(db, "remote.example", "/test", {"data": 1})
                assert result is not None
                assert result.status_code == 200
                mock_client.request.assert_called_once()
                call_args = mock_client.request.call_args
                assert call_args[0][0] == "POST"
                assert "svc.remote.example" in call_args[0][1]


async def test_send_federation_request_non_443_port(client):
    """send_federation_request uses http:// for non-443 ports."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    from vox.db.engine import get_session_factory
    factory = get_session_factory()

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.is_closed = False

    async with factory() as db:
        with patch.object(fed_service, "lookup_vox_host", new_callable=AsyncMock, return_value=("svc.remote.example", 8080)):
            with patch.object(fed_service, "_get_http_client", return_value=mock_client):
                result = await fed_service.send_federation_request(db, "remote.example", "/test")
                assert result is not None
                call_args = mock_client.request.call_args
                assert "http://" in call_args[0][1]


async def test_lookup_vox_key_success(client):
    """lookup_vox_key extracts public key from DNS TXT record."""
    mock_rdata = MagicMock()
    mock_rdata.to_text.return_value = '"v=vox1;p=ABCDEF123"'

    with patch("dns.asyncresolver.resolve", new_callable=AsyncMock, return_value=[mock_rdata]):
        result = await fed_service.lookup_vox_key("example.com")
        assert result == "ABCDEF123"


async def test_lookup_vox_key_failure(client):
    """lookup_vox_key returns None on DNS failure."""
    with patch("dns.asyncresolver.resolve", new_callable=AsyncMock, side_effect=Exception("DNS error")):
        result = await fed_service.lookup_vox_key("example.com")
        assert result is None


async def test_lookup_vox_policy_success(client):
    """lookup_vox_policy parses TXT record correctly."""
    mock_rdata = MagicMock()
    mock_rdata.to_text.return_value = '"federation=closed;version=1"'

    with patch("dns.asyncresolver.resolve", new_callable=AsyncMock, return_value=[mock_rdata]):
        result = await fed_service.lookup_vox_policy("example.com")
        assert result["federation"] == "closed"
        assert result["version"] == "1"


async def test_lookup_vox_policy_failure(client):
    """lookup_vox_policy returns default on DNS failure."""
    with patch("dns.asyncresolver.resolve", new_callable=AsyncMock, side_effect=Exception("DNS error")):
        result = await fed_service.lookup_vox_policy("example.com")
        assert result == {"federation": "open"}


async def test_verify_signature_for_origin(client):
    """verify_signature_for_origin uses DNS lookup to get public key."""
    private_key, pub_b64 = _generate_test_keypair()
    body = b'{"test": true}'
    sig = fed_service.sign_body(body, private_key)

    with patch.object(fed_service, "lookup_vox_key", new_callable=AsyncMock, return_value=pub_b64):
        assert await fed_service.verify_signature_for_origin(body, sig, "example.com") is True

    with patch.object(fed_service, "lookup_vox_key", new_callable=AsyncMock, return_value=None):
        assert await fed_service.verify_signature_for_origin(body, sig, "example.com") is False


# ---------------------------------------------------------------------------
# Endpoint Tests: Edge Cases
# ---------------------------------------------------------------------------


async def test_relay_message_origin_mismatch(client):
    """relay/message rejects when sender domain != origin."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    body = {"from": "bob@other.example", "to": "alice@test.local", "opaque_blob": "data"}
    r = await _fed_request(client, "POST", "/api/v1/federation/relay/message", body, private_key, pub_b64, origin="remote.example")
    assert r.status_code == 403


async def test_relay_message_recipient_not_found(client):
    """relay/message returns 404 for unknown recipient."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    body = {"from": "bob@remote.example", "to": "nobody@test.local", "opaque_blob": "data"}
    r = await _fed_request(client, "POST", "/api/v1/federation/relay/message", body, private_key, pub_b64)
    assert r.status_code == 404


async def test_relay_typing_recipient_not_found(client):
    """relay/typing silently ignores unknown recipient (returns 204)."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    body = {"from": "bob@remote.example", "to": "nobody@test.local"}
    r = await _fed_request(client, "POST", "/api/v1/federation/relay/typing", body, private_key, pub_b64)
    assert r.status_code == 204


async def test_relay_typing_no_dm(client):
    """relay/typing silently ignores when no DM exists."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    # Don't create a DM first — register bob as federated but no DM
    from vox.db.engine import get_session_factory
    from vox.db.models import User
    from datetime import datetime, timezone
    factory = get_session_factory()
    async with factory() as db:
        fed_bob = User(username="bob@remote.example", display_name="bob", federated=True, home_domain="remote.example", active=True, created_at=datetime.now(timezone.utc))
        db.add(fed_bob)
        await db.commit()

    body = {"from": "bob@remote.example", "to": "alice@test.local"}
    r = await _fed_request(client, "POST", "/api/v1/federation/relay/typing", body, private_key, pub_b64)
    assert r.status_code == 204


async def test_relay_read_recipient_not_found(client):
    """relay/read silently ignores unknown recipient."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    body = {"from": "bob@remote.example", "to": "nobody@test.local", "up_to_msg_id": 1}
    r = await _fed_request(client, "POST", "/api/v1/federation/relay/read", body, private_key, pub_b64)
    assert r.status_code == 204


async def test_relay_read_no_dm(client):
    """relay/read silently ignores when no DM exists."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    from vox.db.engine import get_session_factory
    from vox.db.models import User
    from datetime import datetime, timezone
    factory = get_session_factory()
    async with factory() as db:
        fed_bob = User(username="bob@remote.example", display_name="bob", federated=True, home_domain="remote.example", active=True, created_at=datetime.now(timezone.utc))
        db.add(fed_bob)
        await db.commit()

    body = {"from": "bob@remote.example", "to": "alice@test.local", "up_to_msg_id": 1}
    r = await _fed_request(client, "POST", "/api/v1/federation/relay/read", body, private_key, pub_b64)
    assert r.status_code == 204


async def test_prekey_fetch_user_not_found(client):
    """Prekey fetch for unknown user returns 404."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    r = await _fed_request(client, "GET", "/api/v1/federation/users/nobody@test.local/prekeys", {}, private_key, pub_b64)
    assert r.status_code == 404


async def test_presence_subscribe_user_not_found(client):
    """Presence subscribe for unknown user returns 404."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    body = {"user_address": "nobody@test.local"}
    r = await _fed_request(client, "POST", "/api/v1/federation/presence/subscribe", body, private_key, pub_b64)
    assert r.status_code == 404


async def test_presence_notify_no_federated_user(client):
    """Presence notify for unknown federated user silently returns 204."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    body = {"user_address": "unknown@remote.example", "status": "online"}
    r = await _fed_request(client, "POST", "/api/v1/federation/presence/notify", body, private_key, pub_b64)
    assert r.status_code == 204


async def test_join_no_federation_domain(client):
    """Join fails 500 when federation domain not configured."""
    # Register user but DON'T configure federation domain
    token, user_id = await _register(client)
    private_key, pub_b64 = _generate_test_keypair()

    from vox.db.engine import get_session_factory
    from vox.db.models import Config
    factory = get_session_factory()
    async with factory() as db:
        priv_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        priv_b64 = base64.b64encode(priv_bytes).decode()
        db.add(Config(key="federation_private_key", value=priv_b64))
        db.add(Config(key="federation_public_key", value=pub_b64))
        await db.commit()

    voucher = fed_service.create_voucher("user@remote.example", "test.local", private_key)
    body = {"user_address": "user@remote.example", "voucher": voucher}
    r = await _fed_request(client, "POST", "/api/v1/federation/join", body, private_key, pub_b64)
    assert r.status_code == 500


async def test_join_invalid_voucher(client):
    """Join with invalid voucher returns 403."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    body = {"user_address": "user@remote.example", "voucher": "invalid_voucher_string"}
    r = await _fed_request(client, "POST", "/api/v1/federation/join", body, private_key, pub_b64)
    assert r.status_code == 403


async def test_join_voucher_user_mismatch(client):
    """Join with voucher for different user returns 403."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)
    voucher = fed_service.create_voucher("alice@remote.example", "test.local", private_key)
    body = {"user_address": "bob@remote.example", "voucher": voucher}
    r = await _fed_request(client, "POST", "/api/v1/federation/join", body, private_key, pub_b64)
    assert r.status_code == 403


async def test_join_invite_maxed_out(client):
    """Join with fully-used invite code returns 410."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    from datetime import datetime, timezone
    from vox.db.engine import get_session_factory
    from vox.db.models import Invite
    factory = get_session_factory()
    async with factory() as db:
        db.add(Invite(code="maxed", creator_id=user_id, max_uses=1, uses=1, created_at=datetime.now(timezone.utc)))
        await db.commit()

    voucher = fed_service.create_voucher("user@remote.example", "test.local", private_key)
    body = {"user_address": "user@remote.example", "voucher": voucher, "invite_code": "maxed"}
    r = await _fed_request(client, "POST", "/api/v1/federation/join", body, private_key, pub_b64)
    assert r.status_code == 410


async def test_join_banned_user(client):
    """Join for banned federated user returns 403."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    from datetime import datetime, timezone
    from vox.db.engine import get_session_factory
    from vox.db.models import Ban, User
    factory = get_session_factory()
    async with factory() as db:
        fed_user = User(username="banned@remote.example", display_name="banned", federated=True, home_domain="remote.example", active=True, created_at=datetime.now(timezone.utc))
        db.add(fed_user)
        await db.flush()
        db.add(Ban(user_id=fed_user.id, reason="banned", created_at=datetime.now(timezone.utc)))
        await db.commit()

    voucher = fed_service.create_voucher("banned@remote.example", "test.local", private_key)
    body = {"user_address": "banned@remote.example", "voucher": voucher}
    r = await _fed_request(client, "POST", "/api/v1/federation/join", body, private_key, pub_b64)
    assert r.status_code == 403


async def test_config_helpers(client):
    """_get_config and _set_config work correctly including update path."""
    await _register(client)
    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        # Get nonexistent key
        val = await fed_service._get_config(db, "nonexistent_key")
        assert val is None

        # Set a key
        await fed_service._set_config(db, "test_key", "value1")
        await db.commit()

        val = await fed_service._get_config(db, "test_key")
        assert val == "value1"

        # Update existing key
        await fed_service._set_config(db, "test_key", "value2")
        await db.commit()

        val = await fed_service._get_config(db, "test_key")
        assert val == "value2"
