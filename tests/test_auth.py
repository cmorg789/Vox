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
    assert r.json()["detail"]["error"]["code"] == "AUTH_FAILED"


async def test_setup_token_rejected_for_auth(client):
    """setup_totp_ prefixed tokens must not work for authenticated endpoints."""
    r = await client.get(
        "/api/v1/auth/2fa",
        headers={"Authorization": "Bearer setup_totp_fake"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "AUTH_FAILED"


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
    assert r.json()["detail"]["error"]["code"] == "2FA_ALREADY_ENABLED"


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
    assert r.status_code == 200
    data = r.json()
    assert data["mfa_required"] is True
    assert "totp" in data["available_methods"]
    mfa_ticket = data["mfa_ticket"]

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
    mfa_ticket = r.json()["mfa_ticket"]

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
    mfa_ticket = r.json()["mfa_ticket"]

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
    mfa_ticket = r.json()["mfa_ticket"]
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
    mfa_ticket = r.json()["mfa_ticket"]
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
    mfa_ticket = r.json()["mfa_ticket"]
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
    assert "mfa_required" not in r.json()
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
    assert r.json()["detail"]["error"]["code"] == "WEBAUTHN_CREDENTIAL_NOT_FOUND"


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
    assert verify_totp(secret, code) is True
    assert verify_totp(secret, "000000") is False


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
    mfa_ticket = r.json()["mfa_ticket"]

    r = await client.post("/api/v1/auth/login/2fa", json={
        "mfa_ticket": mfa_ticket,
        "method": "carrier_pigeon",
        "code": "123456",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["message"] == "Unsupported 2FA method."


async def test_confirm_2fa_setup_invalid_prefix(client):
    """confirm_2fa_setup with invalid setup_id prefix returns error."""
    token, _ = await _register_and_get_token(client)

    r = await client.post(
        "/api/v1/auth/2fa/setup/confirm",
        json={"setup_id": "invalid_prefix_xyz", "code": "123456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "2FA_SETUP_EXPIRED"


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
    assert r.status_code == 200
    data = r.json()
    assert data["mfa_required"] is True
    assert "webauthn" in data["available_methods"]
    assert "totp" not in data["available_methods"]


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
    mfa_ticket = r.json()["mfa_ticket"]

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
    mfa_ticket = r.json()["mfa_ticket"]

    r = await client.post("/api/v1/auth/login/2fa", json={
        "mfa_ticket": mfa_ticket,
        "method": "recovery",
    })
    assert r.status_code == 400


# --- WebAuthn mock tests ---


async def test_webauthn_registration_options(client):
    """generate_webauthn_registration returns challenge_id and options."""
    from vox.auth.mfa import generate_webauthn_registration
    from vox.db.models import WebAuthnChallenge
    from sqlalchemy import select

    token, user_id = await _register_and_get_token(client)

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
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

    from vox.db.engine import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        with _pytest.raises(HTTPException) as exc_info:
            await generate_webauthn_authentication(db, user_id)
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["error"]["code"] == "WEBAUTHN_CREDENTIAL_NOT_FOUND"


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
    """_get_webauthn_config returns defaults or configured values."""
    from vox.auth.mfa import _get_webauthn_config
    from vox.db.models import Config

    token, user_id = await _register_and_get_token(client)
    from vox.db.engine import get_session_factory
    factory = get_session_factory()

    # Default values
    async with factory() as db:
        rp_id, origin = await _get_webauthn_config(db)
        assert rp_id == "localhost"
        assert origin == "http://localhost:8000"

    # Custom values
    async with factory() as db:
        db.add(Config(key="webauthn_rp_id", value="vox.example.com"))
        db.add(Config(key="webauthn_origin", value="https://vox.example.com"))
        await db.commit()
        rp_id, origin = await _get_webauthn_config(db)
        assert rp_id == "vox.example.com"
        assert origin == "https://vox.example.com"


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
    mfa_ticket = r.json()["mfa_ticket"]

    r = await client.post("/api/v1/auth/login/2fa", json={
        "mfa_ticket": mfa_ticket,
        "method": "webauthn",
    })
    assert r.status_code == 400


async def test_webauthn_setup_flow(client):
    """WebAuthn setup returns creation_options with challenge_id."""
    token, user_id = await _register_and_get_token(client)

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
