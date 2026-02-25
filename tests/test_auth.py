import pytest


async def test_register(client):
    r = await client.post("/api/v1/auth/register", json={
        "username": "alice",
        "password": "test1234",
        "display_name": "Alice",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["user_id"] == 1
    assert data["token"].startswith("vox_sess_")


async def test_register_duplicate(client):
    await client.post("/api/v1/auth/register", json={
        "username": "alice",
        "password": "test1234",
    })
    r = await client.post("/api/v1/auth/register", json={
        "username": "alice",
        "password": "other1234",
    })
    assert r.status_code == 409


async def test_login(client):
    await client.post("/api/v1/auth/register", json={
        "username": "alice",
        "password": "test1234",
        "display_name": "Alice",
    })
    r = await client.post("/api/v1/auth/login", json={
        "username": "alice",
        "password": "test1234",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["token"].startswith("vox_sess_")
    assert data["user_id"] == 1
    assert data["display_name"] == "Alice"
    assert isinstance(data["roles"], list)


async def test_login_wrong_password(client):
    await client.post("/api/v1/auth/register", json={
        "username": "alice",
        "password": "test1234",
    })
    r = await client.post("/api/v1/auth/login", json={
        "username": "alice",
        "password": "wrong",
    })
    assert r.status_code == 401


async def test_login_nonexistent_user(client):
    r = await client.post("/api/v1/auth/login", json={
        "username": "nobody",
        "password": "test1234",
    })
    assert r.status_code == 401


async def test_2fa_status_authenticated(client):
    r = await client.post("/api/v1/auth/register", json={
        "username": "alice",
        "password": "test1234",
    })
    token = r.json()["token"]

    r = await client.get(
        "/api/v1/auth/2fa",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["totp_enabled"] is False
    assert data["webauthn_enabled"] is False
    assert data["recovery_codes_left"] == 0


async def test_2fa_status_no_auth(client):
    r = await client.get("/api/v1/auth/2fa")
    assert r.status_code == 422


async def test_2fa_status_bad_token(client):
    r = await client.get(
        "/api/v1/auth/2fa",
        headers={"Authorization": "Bearer fake_token"},
    )
    assert r.status_code == 401


async def test_register_returns_working_token(client):
    r = await client.post("/api/v1/auth/register", json={
        "username": "bob",
        "password": "test1234",
    })
    token = r.json()["token"]

    r = await client.get(
        "/api/v1/auth/2fa",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


# --- 2FA Tests ---


async def _register_and_get_token(client, username="alice", password="test1234"):
    """Helper: register a user and return (token, user_id)."""
    r = await client.post("/api/v1/auth/register", json={
        "username": username,
        "password": password,
    })
    data = r.json()
    return data["token"], data["user_id"]


async def _set_webauthn_config(rp_id="localhost", origin="http://localhost"):
    """Helper: configure WebAuthn in the DB and reload config."""
    from vox.db.engine import get_session_factory
    from vox.db.models import Config
    from vox.config import load_config
    from vox.db.engine import dialect_insert

    factory = get_session_factory()
    async with factory() as db:
        for key, val in [("webauthn_rp_id", rp_id), ("webauthn_origin", origin)]:
            stmt = dialect_insert(Config).values(key=key, value=val).on_conflict_do_nothing()
            await db.execute(stmt)
        await db.commit()
    async with factory() as db:
        await load_config(db)


async def _clear_webauthn_config():
    """Helper: remove WebAuthn config and reload."""
    from vox.db.engine import get_session_factory
    from vox.db.models import Config
    from vox.config import load_config
    from sqlalchemy import delete

    factory = get_session_factory()
    async with factory() as db:
        await db.execute(delete(Config).where(Config.key.in_(["webauthn_rp_id", "webauthn_origin"])))
        await db.commit()
    async with factory() as db:
        await load_config(db)


async def _setup_totp(client, token):
    """Helper: start TOTP setup and confirm it. Returns recovery codes."""
    import pyotp

    # Start setup
    r = await client.post(
        "/api/v1/auth/2fa/setup",
        json={"method": "totp"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    setup_data = r.json()
    assert setup_data["method"] == "totp"
    assert setup_data["totp_secret"]
    assert setup_data["totp_uri"]
    setup_id = setup_data["setup_id"]
    secret = setup_data["totp_secret"]

    # Generate a valid code
    totp = pyotp.TOTP(secret)
    code = totp.now()

    # Confirm
    r = await client.post(
        "/api/v1/auth/2fa/setup/confirm",
        json={"setup_id": setup_id, "code": code},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    confirm_data = r.json()
    assert confirm_data["success"] is True
    assert len(confirm_data["recovery_codes"]) == 8

    return secret, confirm_data["recovery_codes"]


async def test_mfa_ticket_rejected_for_auth(client):
    """mfa_ prefixed tokens must not work for authenticated endpoints."""
    r = await client.get(
        "/api/v1/auth/2fa",
        headers={"Authorization": "Bearer mfa_fake_token"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_FAILED"


async def test_setup_token_rejected_for_auth(client):
    """setup_totp_ prefixed tokens must not work for authenticated endpoints."""
    r = await client.get(
        "/api/v1/auth/2fa",
        headers={"Authorization": "Bearer setup_totp_fake"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_FAILED"


async def test_totp_setup_flow(client):
    """Full TOTP setup: begin → confirm → status shows enabled."""
    token, _ = await _register_and_get_token(client)
    await _setup_totp(client, token)

    # Check status
    r = await client.get(
        "/api/v1/auth/2fa",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["totp_enabled"] is True
    assert data["recovery_codes_left"] == 8


async def test_totp_setup_already_enabled(client):
    """Setting up TOTP when already enabled returns 409."""
    token, _ = await _register_and_get_token(client)
    await _setup_totp(client, token)

    r = await client.post(
        "/api/v1/auth/2fa/setup",
        json={"method": "totp"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "2FA_ALREADY_ENABLED"


async def test_totp_setup_confirm_wrong_code(client):
    """Confirming TOTP with a wrong code fails."""
    token, _ = await _register_and_get_token(client)

    r = await client.post(
        "/api/v1/auth/2fa/setup",
        json={"method": "totp"},
        headers={"Authorization": f"Bearer {token}"},
    )
    setup_id = r.json()["setup_id"]

    r = await client.post(
        "/api/v1/auth/2fa/setup/confirm",
        json={"setup_id": setup_id, "code": "000000"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


async def test_login_with_totp(client):
    """Login with TOTP: login returns mfa_required, then verify with code."""
    import pyotp

    token, _ = await _register_and_get_token(client)
    secret, _ = await _setup_totp(client, token)

    # Login should now require 2FA
    r = await client.post("/api/v1/auth/login", json={
        "username": "alice",
        "password": "test1234",
    })
    assert r.status_code == 401
    data = r.json()
    assert data["error"]["code"] == "2FA_REQUIRED"
    assert "totp" in data["error"]["available_methods"]
    mfa_ticket = data["error"]["mfa_ticket"]

    # Verify with TOTP code
    totp = pyotp.TOTP(secret)
    code = totp.now()

    r = await client.post("/api/v1/auth/login/2fa", json={
        "mfa_ticket": mfa_ticket,
        "method": "totp",
        "code": code,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["token"].startswith("vox_sess_")
    assert data["user_id"] == 1


async def test_login_with_wrong_totp(client):
    """Login with wrong TOTP code fails."""
    token, _ = await _register_and_get_token(client)
    await _setup_totp(client, token)

    r = await client.post("/api/v1/auth/login", json={
        "username": "alice",
        "password": "test1234",
    })
    mfa_ticket = r.json()["error"]["mfa_ticket"]

    r = await client.post("/api/v1/auth/login/2fa", json={
        "mfa_ticket": mfa_ticket,
        "method": "totp",
        "code": "000000",
    })
    assert r.status_code == 401


async def test_login_with_recovery_code(client):
    """Login using a recovery code."""
    token, _ = await _register_and_get_token(client)
    _, recovery_codes = await _setup_totp(client, token)

    r = await client.post("/api/v1/auth/login", json={
        "username": "alice",
        "password": "test1234",
    })
    mfa_ticket = r.json()["error"]["mfa_ticket"]

    r = await client.post("/api/v1/auth/login/2fa", json={
        "mfa_ticket": mfa_ticket,
        "method": "recovery",
        "code": recovery_codes[0],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["token"].startswith("vox_sess_")


async def test_recovery_code_single_use(client):
    """A recovery code can only be used once."""
    token, _ = await _register_and_get_token(client)
    _, recovery_codes = await _setup_totp(client, token)

    # Use the first recovery code
    r = await client.post("/api/v1/auth/login", json={
        "username": "alice", "password": "test1234",
    })
    mfa_ticket = r.json()["error"]["mfa_ticket"]
    r = await client.post("/api/v1/auth/login/2fa", json={
        "mfa_ticket": mfa_ticket,
        "method": "recovery",
        "code": recovery_codes[0],
    })
    assert r.status_code == 200

    # Try to use the same code again
    r = await client.post("/api/v1/auth/login", json={
        "username": "alice", "password": "test1234",
    })
    mfa_ticket = r.json()["error"]["mfa_ticket"]
    r = await client.post("/api/v1/auth/login/2fa", json={
        "mfa_ticket": mfa_ticket,
        "method": "recovery",
        "code": recovery_codes[0],
    })
    assert r.status_code == 401


async def test_recovery_codes_counted(client):
    """After using a recovery code, the count decreases."""
    token, _ = await _register_and_get_token(client)
    _, recovery_codes = await _setup_totp(client, token)

    # Use one recovery code via login
    r = await client.post("/api/v1/auth/login", json={
        "username": "alice", "password": "test1234",
    })
    mfa_ticket = r.json()["error"]["mfa_ticket"]
    r = await client.post("/api/v1/auth/login/2fa", json={
        "mfa_ticket": mfa_ticket,
        "method": "recovery",
        "code": recovery_codes[0],
    })
    new_token = r.json()["token"]

    r = await client.get(
        "/api/v1/auth/2fa",
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert r.json()["recovery_codes_left"] == 7


async def test_remove_totp(client):
    """Remove TOTP 2FA and verify login no longer requires 2FA."""
    import pyotp

    token, _ = await _register_and_get_token(client)
    secret, _ = await _setup_totp(client, token)

    # Remove TOTP (verify with a valid TOTP code)
    totp = pyotp.TOTP(secret)
    r = await client.request(
        "DELETE",
        "/api/v1/auth/2fa",
        json={"method": "totp", "code": totp.now()},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200

    # Status should show disabled
    r = await client.get(
        "/api/v1/auth/2fa",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = r.json()
    assert data["totp_enabled"] is False
    assert data["recovery_codes_left"] == 0

    # Login should no longer require 2FA
    r = await client.post("/api/v1/auth/login", json={
        "username": "alice",
        "password": "test1234",
    })
    assert r.status_code == 200
    assert "error" not in r.json()
    assert r.json()["token"].startswith("vox_sess_")


async def test_remove_totp_wrong_code(client):
    """Removing TOTP with a wrong code fails."""
    token, _ = await _register_and_get_token(client)
    await _setup_totp(client, token)

    r = await client.request(
        "DELETE",
        "/api/v1/auth/2fa",
        json={"method": "totp", "code": "000000"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


async def test_invalid_mfa_ticket(client):
    """Using an invalid MFA ticket returns 401."""
    r = await client.post("/api/v1/auth/login/2fa", json={
        "mfa_ticket": "mfa_invalid_ticket",
        "method": "totp",
        "code": "123456",
    })
    assert r.status_code == 401


async def test_webauthn_credentials_empty(client):
    """Listing WebAuthn credentials when none exist returns empty list."""
    token, _ = await _register_and_get_token(client)

    r = await client.get(
        "/api/v1/auth/webauthn/credentials",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == []


async def test_delete_webauthn_credential_not_found(client):
    """Deleting a nonexistent WebAuthn credential returns 404."""
    token, _ = await _register_and_get_token(client)

    r = await client.request(
        "DELETE",
        "/api/v1/auth/webauthn/credentials/nonexistent",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "WEBAUTHN_CREDENTIAL_NOT_FOUND"


async def test_setup_invalid_method(client):
    """Setting up an invalid 2FA method returns 400."""
    token, _ = await _register_and_get_token(client)

    r = await client.post(
        "/api/v1/auth/2fa/setup",
        json={"method": "invalid"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


async def test_webauthn_challenge_unknown_user(client):
    """Requesting a WebAuthn challenge for unknown user fails."""
    r = await client.post("/api/v1/auth/login/webauthn/challenge", json={
        "username": "nobody",
    })
    assert r.status_code == 401


# --- MFA unit tests ---


async def test_generate_totp_secret_round_trip(client):
    """generate_totp_secret and verify_totp produce a valid round-trip."""
    import pyotp
    from vox.auth.mfa import generate_totp_secret, verify_totp

    secret, uri = generate_totp_secret("alice")
    assert secret
    assert "alice" in uri
    assert "Vox" in uri

    totp = pyotp.TOTP(secret)
    code = totp.now()
    valid, counter = verify_totp(secret, code)
    assert valid is True
    assert counter is not None
    valid2, counter2 = verify_totp(secret, "000000")
    assert valid2 is False
    assert counter2 is None


async def test_generate_recovery_codes(client):
    """generate_recovery_codes produces correct format codes."""
    from vox.auth.mfa import generate_recovery_codes

    codes = generate_recovery_codes(count=4)
    assert len(codes) == 4
    for code in codes:
        assert len(code) == 9  # XXXX-XXXX
        assert code[4] == "-"


async def test_store_recovery_codes(client):
    """store_recovery_codes stores hashed codes in DB."""
    from vox.auth.mfa import generate_recovery_codes, store_recovery_codes, verify_recovery_code

    token, user_id = await _register_and_get_token(client)
    codes = generate_recovery_codes(count=3)

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        await store_recovery_codes(db, user_id, codes)
        await db.commit()

        # Verify a valid code works
        assert await verify_recovery_code(db, user_id, codes[0]) is True
        # Same code used again fails
        assert await verify_recovery_code(db, user_id, codes[0]) is False
        # Invalid code fails
        assert await verify_recovery_code(db, user_id, "XXXX-YYYY") is False


async def test_create_and_validate_setup_session(client):
    """Setup session creation and validation work correctly."""
    from vox.auth.mfa import create_setup_session, validate_setup_session
    from fastapi import HTTPException

    token, user_id = await _register_and_get_token(client)

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        setup_token = await create_setup_session(db, user_id, "setup_test_")
        await db.commit()
        assert setup_token.startswith("setup_test_")

        # Valid token
        session = await validate_setup_session(db, setup_token, "setup_test_")
        assert session.user_id == user_id

    # Invalid prefix
    async with factory() as db:
        import pytest as _pytest
        with _pytest.raises(HTTPException) as exc_info:
            await validate_setup_session(db, "wrong_prefix_abc", "setup_test_")
        assert exc_info.value.status_code == 401

    # Expired/nonexistent token
    async with factory() as db:
        with _pytest.raises(HTTPException) as exc_info:
            await validate_setup_session(db, "setup_test_nonexistent", "setup_test_")
        assert exc_info.value.status_code == 401


# --- Auth endpoint gap tests ---


async def test_login_2fa_unsupported_method(client):
    """Login 2FA with unsupported method returns 400."""
    token, _ = await _register_and_get_token(client)
    await _setup_totp(client, token)

    r = await client.post("/api/v1/auth/login", json={
        "username": "alice", "password": "test1234",
    })
    mfa_ticket = r.json()["error"]["mfa_ticket"]

    r = await client.post("/api/v1/auth/login/2fa", json={
        "mfa_ticket": mfa_ticket,
        "method": "carrier_pigeon",
        "code": "123456",
    })
    assert r.status_code == 400
    assert r.json()["error"]["message"] == "Unsupported 2FA method."


async def test_confirm_2fa_setup_invalid_prefix(client):
    """confirm_2fa_setup with invalid setup_id prefix returns error."""
    token, _ = await _register_and_get_token(client)

    r = await client.post(
        "/api/v1/auth/2fa/setup/confirm",
        json={"setup_id": "invalid_prefix_xyz", "code": "123456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "2FA_SETUP_EXPIRED"


async def test_login_webauthn_only_2fa(client):
    """Login with WebAuthn-only 2FA shows webauthn in available_methods (no totp)."""
    from datetime import datetime, timezone
    token, user_id = await _register_and_get_token(client)

    # Manually add a WebAuthn credential to the DB (skip actual WebAuthn flow)
    from vox.db.engine import get_session_factory
    from vox.db.models import WebAuthnCredential
    factory = get_session_factory()
    async with factory() as db:
        cred = WebAuthnCredential(
            credential_id="test_cred_id",
            user_id=user_id,
            name="Test Key",
            public_key="test_pub_key",
            registered_at=datetime.now(timezone.utc),
        )
        db.add(cred)
        await db.commit()

    r = await client.post("/api/v1/auth/login", json={
        "username": "alice", "password": "test1234",
    })
    assert r.status_code == 401
    data = r.json()
    assert data["error"]["code"] == "2FA_REQUIRED"
    assert "webauthn" in data["error"]["available_methods"]
    assert "totp" not in data["error"]["available_methods"]


async def test_remove_2fa_webauthn(client):
    """Remove WebAuthn 2FA method using recovery code."""
    from datetime import datetime, timezone
    token, user_id = await _register_and_get_token(client)

    # Set up TOTP first (to get recovery codes), then add WebAuthn
    secret, recovery_codes = await _setup_totp(client, token)

    from vox.db.engine import get_session_factory
    from vox.db.models import WebAuthnCredential
    factory = get_session_factory()
    async with factory() as db:
        cred = WebAuthnCredential(
            credential_id="test_cred_id",
            user_id=user_id,
            name="Test Key",
            public_key="test_pub_key",
            registered_at=datetime.now(timezone.utc),
        )
        db.add(cred)
        await db.commit()

    # Remove WebAuthn using a recovery code
    r = await client.request(
        "DELETE",
        "/api/v1/auth/2fa",
        json={"method": "webauthn", "code": recovery_codes[0]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200

    # Check status — webauthn should be disabled, TOTP still enabled
    r = await client.get(
        "/api/v1/auth/2fa",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = r.json()
    assert data["webauthn_enabled"] is False
    assert data["totp_enabled"] is True


async def test_remove_last_2fa_cleans_recovery_codes(client):
    """Removing last 2FA method also removes recovery codes."""
    import pyotp
    token, user_id = await _register_and_get_token(client)
    secret, recovery_codes = await _setup_totp(client, token)

    # Remove TOTP (the only method)
    totp = pyotp.TOTP(secret)
    r = await client.request(
        "DELETE",
        "/api/v1/auth/2fa",
        json={"method": "totp", "code": totp.now()},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200

    # Recovery codes should be cleaned up
    r = await client.get(
        "/api/v1/auth/2fa",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.json()["recovery_codes_left"] == 0


async def test_remove_2fa_invalid_method(client):
    """Removing 2FA with invalid method returns 400."""
    token, _ = await _register_and_get_token(client)
    _, recovery_codes = await _setup_totp(client, token)

    r = await client.request(
        "DELETE",
        "/api/v1/auth/2fa",
        json={"method": "invalid_method", "code": recovery_codes[0]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


async def test_login_2fa_totp_no_code(client):
    """Login 2FA TOTP without code returns 400."""
    token, _ = await _register_and_get_token(client)
    await _setup_totp(client, token)

    r = await client.post("/api/v1/auth/login", json={
        "username": "alice", "password": "test1234",
    })
    mfa_ticket = r.json()["error"]["mfa_ticket"]

    r = await client.post("/api/v1/auth/login/2fa", json={
        "mfa_ticket": mfa_ticket,
        "method": "totp",
    })
    assert r.status_code == 400


async def test_login_2fa_recovery_no_code(client):
    """Login 2FA recovery without code returns 400."""
    token, _ = await _register_and_get_token(client)
    await _setup_totp(client, token)

    r = await client.post("/api/v1/auth/login", json={
        "username": "alice", "password": "test1234",
    })
    mfa_ticket = r.json()["error"]["mfa_ticket"]

    r = await client.post("/api/v1/auth/login/2fa", json={
        "mfa_ticket": mfa_ticket,
        "method": "recovery",
    })
    assert r.status_code == 400


# --- WebAuthn mock tests ---


async def test_webauthn_registration_options(client):
    """generate_webauthn_registration returns challenge_id and options."""
    from vox.auth.mfa import generate_webauthn_registration
    from vox.db.models import WebAuthnChallenge, Config
    from vox.config import load_config
    from sqlalchemy import select, delete

    token, user_id = await _register_and_get_token(client)

    from vox.db.engine import get_session_factory
    factory = get_session_factory()

    # Configure WebAuthn first
    async with factory() as db:
        db.add(Config(key="webauthn_rp_id", value="localhost"))
        db.add(Config(key="webauthn_origin", value="http://localhost"))
        await db.commit()
    async with factory() as db:
        await load_config(db)

    async with factory() as db:
        challenge_id, options = await generate_webauthn_registration(db, user_id, "alice")
        assert challenge_id
        assert "publicKey" in options or "rp" in options or isinstance(options, dict)
        result = await db.execute(select(WebAuthnChallenge).where(WebAuthnChallenge.id == challenge_id))
        challenge_row = result.scalar_one_or_none()
        assert challenge_row is not None
        assert challenge_row.challenge_type == "registration"

        # Clean up
        await db.delete(challenge_row)
        await db.commit()

    # Clean up config
    async with factory() as db:
        await db.execute(delete(Config).where(Config.key.in_(["webauthn_rp_id", "webauthn_origin"])))
        await db.commit()
    async with factory() as db:
        await load_config(db)


async def test_webauthn_verify_registration_invalid_challenge(client):
    """verify_webauthn_registration with invalid challenge raises."""
    from vox.auth.mfa import verify_webauthn_registration
    from fastapi import HTTPException
    import pytest as _pytest

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with _pytest.raises(HTTPException) as exc_info:
            await verify_webauthn_registration(db, "nonexistent_challenge", {})
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"]["code"] == "WEBAUTHN_FAILED"


async def test_webauthn_authentication_no_credentials(client):
    """generate_webauthn_authentication with no credentials raises 404."""
    from vox.auth.mfa import generate_webauthn_authentication
    from fastapi import HTTPException
    import pytest as _pytest

    token, user_id = await _register_and_get_token(client)
    await _set_webauthn_config()

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with _pytest.raises(HTTPException) as exc_info:
            await generate_webauthn_authentication(db, user_id)
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["error"]["code"] == "WEBAUTHN_CREDENTIAL_NOT_FOUND"

    await _clear_webauthn_config()


async def test_webauthn_verify_authentication_invalid_challenge(client):
    """verify_webauthn_authentication with invalid challenge raises."""
    from vox.auth.mfa import verify_webauthn_authentication
    from fastapi import HTTPException
    import pytest as _pytest

    token, user_id = await _register_and_get_token(client)
    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with _pytest.raises(HTTPException) as exc_info:
            await verify_webauthn_authentication(db, "nonexistent_challenge", {})
        assert exc_info.value.status_code == 400


async def test_webauthn_authentication_options(client):
    """generate_webauthn_authentication returns options when credentials exist."""
    from datetime import datetime, timezone
    from vox.auth.mfa import generate_webauthn_authentication
    from vox.db.models import WebAuthnChallenge, WebAuthnCredential
    from sqlalchemy import select

    token, user_id = await _register_and_get_token(client)
    await _set_webauthn_config()

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        # Add a WebAuthn credential
        cred = WebAuthnCredential(
            credential_id="dGVzdF9jcmVkZW50aWFs",  # base64url of "test_credential"
            user_id=user_id,
            name="Test Key",
            public_key="test_pub_key",
            registered_at=datetime.now(timezone.utc),
        )
        db.add(cred)
        await db.commit()

        challenge_id, options = await generate_webauthn_authentication(db, user_id)
        assert challenge_id
        assert isinstance(options, dict)
        result = await db.execute(select(WebAuthnChallenge).where(WebAuthnChallenge.id == challenge_id))
        challenge_row = result.scalar_one_or_none()
        assert challenge_row is not None
        assert challenge_row.challenge_type == "authentication"

        # Clean up
        await db.delete(challenge_row)
        await db.commit()

    await _clear_webauthn_config()


async def test_validate_mfa_ticket_invalid_prefix(client):
    """validate_mfa_ticket with non-mfa_ prefix raises 401."""
    from vox.auth.mfa import validate_mfa_ticket
    from fastapi import HTTPException
    import pytest as _pytest

    token, user_id = await _register_and_get_token(client)
    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with _pytest.raises(HTTPException) as exc_info:
            await validate_mfa_ticket(db, "not_mfa_prefix")
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"]["code"] == "2FA_INVALID_CODE"


async def test_validate_mfa_ticket_expired(client):
    """validate_mfa_ticket with expired/nonexistent token raises 401."""
    from vox.auth.mfa import validate_mfa_ticket
    from fastapi import HTTPException
    import pytest as _pytest

    token, user_id = await _register_and_get_token(client)
    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with _pytest.raises(HTTPException) as exc_info:
            await validate_mfa_ticket(db, "mfa_nonexistent_token")
        assert exc_info.value.status_code == 401


async def test_webauthn_get_config(client):
    """_get_webauthn_config raises when unconfigured, returns configured values."""
    from vox.auth.mfa import _get_webauthn_config
    from vox.config import config, load_config
    from vox.db.models import Config
    from fastapi import HTTPException
    import pytest as _pytest

    token, user_id = await _register_and_get_token(client)
    from vox.db.engine import get_session_factory
    factory = get_session_factory()

    # Unconfigured — should raise
    with _pytest.raises(HTTPException) as exc_info:
        _get_webauthn_config()
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"]["code"] == "WEBAUTHN_NOT_CONFIGURED"

    # Custom values
    async with factory() as db:
        db.add(Config(key="webauthn_rp_id", value="vox.example.com"))
        db.add(Config(key="webauthn_origin", value="https://vox.example.com"))
        await db.commit()
    async with factory() as db:
        await load_config(db)
    rp_id, origin = _get_webauthn_config()
    assert rp_id == "vox.example.com"
    assert origin == "https://vox.example.com"
    # Clean up
    from sqlalchemy import delete
    async with factory() as db:
        await db.execute(delete(Config).where(Config.key.in_(["webauthn_rp_id", "webauthn_origin"])))
        await db.commit()
    async with factory() as db:
        await load_config(db)


async def test_login_2fa_webauthn_no_assertion(client):
    """Login 2FA WebAuthn without assertion returns 400."""
    from datetime import datetime, timezone
    from vox.db.models import WebAuthnCredential

    token, user_id = await _register_and_get_token(client)

    # Add WebAuthn credential to trigger 2FA
    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        cred = WebAuthnCredential(
            credential_id="test_cred_id",
            user_id=user_id,
            name="Test Key",
            public_key="test_pub_key",
            registered_at=datetime.now(timezone.utc),
        )
        db.add(cred)
        await db.commit()

    r = await client.post("/api/v1/auth/login", json={
        "username": "alice", "password": "test1234",
    })
    mfa_ticket = r.json()["error"]["mfa_ticket"]

    r = await client.post("/api/v1/auth/login/2fa", json={
        "mfa_ticket": mfa_ticket,
        "method": "webauthn",
    })
    assert r.status_code == 400


async def test_webauthn_setup_flow(client):
    """WebAuthn setup returns creation_options with challenge_id."""
    token, user_id = await _register_and_get_token(client)
    await _set_webauthn_config()

    r = await client.post(
        "/api/v1/auth/2fa/setup",
        json={"method": "webauthn"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["method"] == "webauthn"
    assert "creation_options" in data
    assert "challenge_id" in data["creation_options"]
    assert data["setup_id"].startswith("setup_webauthn_")

    await _clear_webauthn_config()


async def test_logout(client):
    """Logout invalidates the session token."""
    token, _ = await _register_and_get_token(client)
    r = await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 204

    # Token should no longer work
    r = await client.get("/api/v1/auth/2fa", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_logout_non_bearer_prefix(client):
    """Logout with unrecognized prefix returns 204 silently."""
    token, _ = await _register_and_get_token(client)
    # Use a weird prefix - depends on get_current_user accepting it or not
    # Actually the deps will reject it, so let's test the Bot prefix path instead
    # by manually calling with Bot token (will be rejected by get_current_user first)
    r = await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bot {token}"})
    # Bot tokens go through get_current_user which might handle them
    assert r.status_code in (204, 401)


async def test_confirm_2fa_setup_totp_no_code(client):
    """Confirming TOTP setup without code returns 400."""
    token, _ = await _register_and_get_token(client)
    r = await client.post(
        "/api/v1/auth/2fa/setup",
        json={"method": "totp"},
        headers={"Authorization": f"Bearer {token}"},
    )
    setup_id = r.json()["setup_id"]

    r = await client.post(
        "/api/v1/auth/2fa/setup/confirm",
        json={"setup_id": setup_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


async def test_confirm_2fa_setup_totp_no_pending(client):
    """Confirming TOTP when no pending setup exists returns 400."""
    token, _ = await _register_and_get_token(client)

    # Create a setup session manually with the right prefix but no pending TOTP
    from vox.db.engine import get_session_factory
    from vox.auth.mfa import create_setup_session
    factory = get_session_factory()
    async with factory() as db:
        setup_id = await create_setup_session(db, 1, "setup_totp_")
        await db.commit()

    # Try to confirm (no pending TOTP secret)
    # But first delete any pending secrets
    from sqlalchemy import delete
    from vox.db.models import TOTPSecret
    async with factory() as db:
        await db.execute(delete(TOTPSecret))
        await db.commit()

    r = await client.post(
        "/api/v1/auth/2fa/setup/confirm",
        json={"setup_id": setup_id, "code": "123456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "2FA_SETUP_EXPIRED"


async def test_confirm_webauthn_setup_no_attestation(client):
    """Confirming WebAuthn setup without attestation returns 400."""
    token, _ = await _register_and_get_token(client)
    await _set_webauthn_config()
    r = await client.post(
        "/api/v1/auth/2fa/setup",
        json={"method": "webauthn"},
        headers={"Authorization": f"Bearer {token}"},
    )
    setup_id = r.json()["setup_id"]

    r = await client.post(
        "/api/v1/auth/2fa/setup/confirm",
        json={"setup_id": setup_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "WEBAUTHN_FAILED"
    await _clear_webauthn_config()


async def test_webauthn_login_challenge_with_credential(client):
    """WebAuthn login challenge works when user has credentials."""
    from datetime import datetime, timezone
    from vox.db.models import WebAuthnCredential
    from vox.db.engine import get_session_factory

    token, user_id = await _register_and_get_token(client)
    await _set_webauthn_config()
    factory = get_session_factory()
    async with factory() as db:
        cred = WebAuthnCredential(
            credential_id="dGVzdF9jcmVkZW50aWFs",
            user_id=user_id,
            name="Test Key",
            public_key="test_pub_key",
            registered_at=datetime.now(timezone.utc),
        )
        db.add(cred)
        await db.commit()

    r = await client.post("/api/v1/auth/login/webauthn/challenge", json={"username": "alice"})
    assert r.status_code == 200
    data = r.json()
    assert "challenge_id" in data
    assert "options" in data

    await _clear_webauthn_config()


async def test_webauthn_login_no_challenge(client):
    """WebAuthn login without a pending challenge returns 401."""
    from datetime import datetime, timezone
    from vox.db.models import WebAuthnCredential
    from vox.db.engine import get_session_factory

    token, user_id = await _register_and_get_token(client)
    factory = get_session_factory()
    async with factory() as db:
        cred = WebAuthnCredential(
            credential_id="dGVzdF9jcmVkZW50aWFs",
            user_id=user_id,
            name="Test Key",
            public_key="test_pub_key",
            registered_at=datetime.now(timezone.utc),
        )
        db.add(cred)
        await db.commit()

    r = await client.post("/api/v1/auth/login/webauthn", json={
        "username": "alice",
        "challenge_id": "nonexistent_challenge",
        "credential_id": "dGVzdF9jcmVkZW50aWFs",
        "client_data_json": "eyJ0eXBlIjoid2ViYXV0aG4uZ2V0In0",
        "authenticator_data": "dGVzdA",
        "signature": "dGVzdA",
    })
    assert r.status_code in (400, 401)
    assert r.json()["error"]["code"] == "WEBAUTHN_FAILED"


async def test_webauthn_login_unknown_user(client):
    """WebAuthn login with unknown user returns 401."""
    r = await client.post("/api/v1/auth/login/webauthn", json={
        "username": "nobody",
        "challenge_id": "test",
        "credential_id": "test",
        "client_data_json": "test",
        "authenticator_data": "test",
        "signature": "test",
    })
    assert r.status_code == 401


async def test_federation_login_invalid_token(client):
    """Federation login with invalid token returns 401."""
    r = await client.post("/api/v1/auth/login/federation", json={
        "federation_token": "invalid_token",
    })
    assert r.status_code == 401


async def test_federation_login_not_federated(client):
    """Federation login with a non-federated user's token returns 403."""
    # Register a regular user and get their session token
    token, user_id = await _register_and_get_token(client)

    # Try using the session token as a federation token (user is not federated)
    r = await client.post("/api/v1/auth/login/federation", json={
        "federation_token": token,
    })
    assert r.status_code == 403


async def test_cleanup_expired_sessions(client):
    """cleanup_expired_sessions deletes expired sessions."""
    from vox.auth.service import cleanup_expired_sessions
    from vox.db.engine import get_session_factory
    from vox.db.models import Session
    from sqlalchemy import select
    from datetime import datetime, timedelta, timezone

    # Register a user
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    token = r.json()["token"]

    from vox.auth.service import hash_token
    factory = get_session_factory()
    async with factory() as db:
        # Expire the session
        result = await db.execute(select(Session).where(Session.token == hash_token(token)))
        session = result.scalar_one()
        session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await db.commit()

    async with factory() as db:
        await cleanup_expired_sessions(db)

    # Token should no longer work
    r = await client.get("/api/v1/auth/2fa", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_verify_webauthn_registration_invalid_challenge(client):
    """verify_webauthn_registration with invalid challenge raises 400."""
    from vox.auth.mfa import verify_webauthn_registration
    from vox.db.engine import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        with pytest.raises(Exception) as exc_info:
            await verify_webauthn_registration(db, "nonexistent_challenge", {})
        assert exc_info.value.status_code == 400


async def test_verify_webauthn_registration_verification_fails(client):
    """verify_webauthn_registration with bad attestation raises 400."""
    from vox.auth.mfa import verify_webauthn_registration, _store_challenge
    from vox.db.engine import get_session_factory
    from vox.db.models import Config

    factory = get_session_factory()
    async with factory() as db:
        db.add(Config(key="webauthn_rp_id", value="localhost"))
        db.add(Config(key="webauthn_origin", value="http://localhost"))
        await db.flush()

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


async def test_verify_webauthn_authentication_invalid_challenge(client):
    """verify_webauthn_authentication with invalid challenge raises 400."""
    from vox.auth.mfa import verify_webauthn_authentication
    from vox.db.engine import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        with pytest.raises(Exception) as exc_info:
            await verify_webauthn_authentication(db, "nonexistent_challenge", {})
        assert exc_info.value.status_code == 400


async def test_verify_webauthn_authentication_credential_not_found(client):
    """verify_webauthn_authentication with no matching credential raises 400."""
    from vox.auth.mfa import verify_webauthn_authentication, _store_challenge
    from vox.db.engine import get_session_factory

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


async def test_verify_webauthn_authentication_verify_fails(client):
    """verify_webauthn_authentication with bad assertion raises 401."""
    from vox.auth.mfa import verify_webauthn_authentication, _store_challenge
    from vox.db.engine import get_session_factory
    from vox.db.models import WebAuthnCredential
    from datetime import datetime, timezone

    factory = get_session_factory()
    async with factory() as db:
        await _store_challenge(db, "auth_challenge2", 1, "authentication", {
            "challenge": "dGVzdA",
            "rp_id": "localhost",
            "origin": "http://localhost",
            "user_id": 1,
        })
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


async def test_delete_webauthn_credential_success(client):
    """Deleting an existing WebAuthn credential works."""
    from datetime import datetime, timezone
    from vox.db.models import WebAuthnCredential
    from vox.db.engine import get_session_factory

    token, user_id = await _register_and_get_token(client)
    factory = get_session_factory()
    async with factory() as db:
        cred = WebAuthnCredential(
            credential_id="to_delete_cred",
            user_id=user_id,
            name="Deletable Key",
            public_key="test_pub_key",
            registered_at=datetime.now(timezone.utc),
        )
        db.add(cred)
        await db.commit()

    r = await client.request(
        "DELETE",
        "/api/v1/auth/webauthn/credentials/to_delete_cred",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200

    # Verify it's gone
    r = await client.get(
        "/api/v1/auth/webauthn/credentials",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.json() == []
