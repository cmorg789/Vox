async def auth(client, username="admin"):
    r = await client.post("/api/v1/auth/register", json={"username": username, "password": "test1234"})
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user_id"]


async def test_create_and_list_reports(client):
    h_admin, _ = await auth(client, "admin")
    _, uid_bob = await auth(client, "bob")

    r = await client.post("/api/v1/reports", headers=h_admin, json={
        "reported_user_id": uid_bob,
        "reason": "harassment",
        "description": "Being rude",
    })
    assert r.status_code == 201
    assert r.json()["report_id"] == 1

    r = await client.get("/api/v1/reports", headers=h_admin)
    assert len(r.json()["items"]) == 1
    assert r.json()["items"][0]["reason"] == "harassment"


async def test_resolve_report(client):
    h, _ = await auth(client)
    _, uid = await auth(client, "spammer")

    await client.post("/api/v1/reports", headers=h, json={"reported_user_id": uid, "reason": "spam"})

    r = await client.post("/api/v1/reports/1/resolve", headers=h, json={"action": "ban"})
    assert r.status_code == 204

    r = await client.get("/api/v1/reports?status=resolved", headers=h)
    assert len(r.json()["items"]) == 1


async def test_filter_reports_by_status(client):
    h, _ = await auth(client)
    _, uid = await auth(client, "user2")

    await client.post("/api/v1/reports", headers=h, json={"reported_user_id": uid, "reason": "spam"})

    r = await client.get("/api/v1/reports?status=open", headers=h)
    assert len(r.json()["items"]) == 1

    r = await client.get("/api/v1/reports?status=resolved", headers=h)
    assert len(r.json()["items"]) == 0


async def test_audit_log(client):
    h, _ = await auth(client)
    _, uid = await auth(client, "target")

    # Admin 2FA reset creates an audit log entry
    await client.post("/api/v1/admin/2fa-reset", headers=h, json={"target_user_id": uid, "reason": "Locked out"})

    r = await client.get("/api/v1/audit-log", headers=h)
    assert r.status_code == 200
    assert len(r.json()["entries"]) == 1
    assert r.json()["entries"][0]["event_type"] == "2fa.admin_reset"


async def test_audit_log_filter_by_event_type(client):
    h, _ = await auth(client)
    _, uid = await auth(client, "target")

    await client.post("/api/v1/admin/2fa-reset", headers=h, json={"target_user_id": uid, "reason": "test"})

    r = await client.get("/api/v1/audit-log?event_type=2fa.*", headers=h)
    assert len(r.json()["entries"]) == 1

    r = await client.get("/api/v1/audit-log?event_type=member.*", headers=h)
    assert len(r.json()["entries"]) == 0


async def test_reports_pagination(client):
    h, _ = await auth(client)
    _, uid = await auth(client, "bob")
    await client.post("/api/v1/reports", headers=h, json={"reported_user_id": uid, "reason": "spam"})
    await client.post("/api/v1/reports", headers=h, json={"reported_user_id": uid, "reason": "spam2"})

    r = await client.get("/api/v1/reports?after=1", headers=h)
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["report_id"] > 1


async def test_resolve_report_not_found(client):
    h, _ = await auth(client)
    r = await client.post("/api/v1/reports/99999/resolve", headers=h, json={"action": "ban"})
    assert r.status_code == 404


async def test_audit_log_filter_by_actor_and_target(client):
    h, admin_uid = await auth(client)
    _, uid = await auth(client, "target")
    await client.post("/api/v1/admin/2fa-reset", headers=h, json={"target_user_id": uid, "reason": "test"})

    r = await client.get(f"/api/v1/audit-log?actor_id={admin_uid}", headers=h)
    assert len(r.json()["entries"]) >= 1

    r = await client.get(f"/api/v1/audit-log?target_id={uid}", headers=h)
    assert len(r.json()["entries"]) >= 1

    r = await client.get("/api/v1/audit-log?after=0", headers=h)
    assert r.status_code == 200
