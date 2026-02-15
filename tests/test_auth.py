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
    assert data["roles"] == []


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
