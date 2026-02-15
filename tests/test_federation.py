"""Tests for the federation system: crypto, vouchers, policy, endpoints, and integration."""

import base64
import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

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
    fed_service._seen_nonces.clear()
    fed_service._presence_subs.clear()
    yield
    fed_service._seen_nonces.clear()
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
    private_key, pub_b64 = _generate_test_keypair()
    voucher = fed_service.create_voucher("alice@origin.example", "target.example", private_key)

    with patch.object(fed_service, "lookup_vox_key", new_callable=AsyncMock, return_value=pub_b64):
        result = await fed_service.verify_voucher(voucher, "target.example")
        assert result is not None
        assert result["user_address"] == "alice@origin.example"
        assert result["target_domain"] == "target.example"


async def test_voucher_replay_rejected(client):
    """Same voucher used twice is rejected (nonce replay)."""
    private_key, pub_b64 = _generate_test_keypair()
    voucher = fed_service.create_voucher("alice@origin.example", "target.example", private_key)

    with patch.object(fed_service, "lookup_vox_key", new_callable=AsyncMock, return_value=pub_b64):
        result1 = await fed_service.verify_voucher(voucher, "target.example")
        assert result1 is not None
        result2 = await fed_service.verify_voucher(voucher, "target.example")
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
    dms = r.json()["dms"]
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
    dms = r.json()["dms"]
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
    """Block endpoint acknowledges with 204."""
    headers, user_id, private_key, pub_b64 = await _setup_fed_keys_in_db(client)

    body = {"reason": "spam"}
    r = await _fed_request(client, "POST", "/api/v1/federation/block", body, private_key, pub_b64)
    assert r.status_code == 204
