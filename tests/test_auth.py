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
        "password": "other",
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
