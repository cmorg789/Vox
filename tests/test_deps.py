"""Tests for auth dependency edge cases in vox.api.deps."""


async def test_missing_auth_header(client):
    r = await client.get("/api/v1/server")
    assert r.status_code == 422


async def test_invalid_auth_scheme(client):
    r = await client.get("/api/v1/server", headers={"Authorization": "Basic abc123"})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "AUTH_FAILED"


async def test_restricted_token_mfa(client):
    r = await client.get("/api/v1/server", headers={"Authorization": "Bearer mfa_sometoken"})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "AUTH_FAILED"


async def test_restricted_token_setup_totp(client):
    r = await client.get("/api/v1/server", headers={"Authorization": "Bearer setup_totp_sometoken"})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "AUTH_FAILED"


async def test_restricted_token_setup_webauthn(client):
    r = await client.get("/api/v1/server", headers={"Authorization": "Bearer setup_webauthn_sometoken"})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "AUTH_FAILED"


async def test_restricted_token_fed(client):
    r = await client.get("/api/v1/server", headers={"Authorization": "Bearer fed_sometoken"})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "AUTH_FAILED"


async def test_expired_token(client):
    r = await client.get("/api/v1/server", headers={"Authorization": "Bearer garbage_token_that_doesnt_exist"})
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "AUTH_EXPIRED"
