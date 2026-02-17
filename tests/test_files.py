"""Tests for file upload, download, and message attachments."""

import io


async def setup(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    return h


async def test_upload_and_download(client):
    h = await setup(client)

    r = await client.post(
        "/api/v1/feeds/1/files",
        headers=h,
        files={"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "test.txt"
    assert data["size"] == 11
    assert data["mime"] == "text/plain"
    assert data["file_id"]
    assert data["url"].startswith("/api/v1/files/")

    # Download
    r = await client.get(data["url"], headers=h)
    assert r.status_code == 200
    assert r.content == b"hello world"


async def test_upload_custom_name_and_mime(client):
    h = await setup(client)

    r = await client.post(
        "/api/v1/feeds/1/files",
        headers=h,
        files={"file": ("original.bin", io.BytesIO(b"data"), "application/octet-stream")},
        data={"name": "custom.dat", "mime": "application/pdf"},
    )
    assert r.status_code == 201
    assert r.json()["name"] == "custom.dat"
    assert r.json()["mime"] == "application/pdf"


async def test_upload_too_large(client, monkeypatch):
    h = await setup(client)

    # Patch MAX_FILE_SIZE to something small for testing
    import vox.api.files as files_mod
    monkeypatch.setattr(files_mod, "MAX_FILE_SIZE", 100)

    r = await client.post(
        "/api/v1/feeds/1/files",
        headers=h,
        files={"file": ("big.bin", io.BytesIO(b"x" * 101), "application/octet-stream")},
    )
    assert r.status_code == 413
    body = r.json()
    err = body.get("error") or body.get("detail", {}).get("error", {})
    assert err["code"] == "FILE_TOO_LARGE"


async def test_download_not_found(client):
    h = await setup(client)

    r = await client.get("/api/v1/files/nonexistent", headers=h)
    assert r.status_code == 404


async def test_upload_requires_auth(client):
    r = await client.post(
        "/api/v1/feeds/1/files",
        files={"file": ("test.txt", io.BytesIO(b"data"), "text/plain")},
    )
    assert r.status_code in (401, 422)


async def test_message_with_attachments(client):
    h = await setup(client)

    # Upload a file
    r = await client.post(
        "/api/v1/feeds/1/files",
        headers=h,
        files={"file": ("pic.png", io.BytesIO(b"\x89PNG"), "image/png")},
    )
    file_id = r.json()["file_id"]

    # Send message with attachment
    r = await client.post(
        "/api/v1/feeds/1/messages",
        headers=h,
        json={"body": "Check this out!", "attachments": [file_id]},
    )
    assert r.status_code == 201
    msg_id = r.json()["msg_id"]

    # Fetch messages — attachment should be in the response
    r = await client.get("/api/v1/feeds/1/messages", headers=h)
    assert r.status_code == 200
    msgs = r.json()["messages"]
    msg = next(m for m in msgs if m["msg_id"] == msg_id)
    assert len(msg["attachments"]) == 1
    assert msg["attachments"][0]["file_id"] == file_id
    assert msg["attachments"][0]["name"] == "pic.png"


async def test_message_with_invalid_attachment(client):
    h = await setup(client)

    r = await client.post(
        "/api/v1/feeds/1/messages",
        headers=h,
        json={"body": "Bad ref", "attachments": ["nonexistent_file_id"]},
    )
    assert r.status_code == 400
    body = r.json()
    err = body.get("error") or body.get("detail", {}).get("error", {})
    assert err["code"] == "INVALID_ATTACHMENT"


async def test_dm_with_attachment(client):
    h = await setup(client)

    # Register second user
    r2 = await client.post("/api/v1/auth/register", json={"username": "bob", "password": "test1234"})
    h2 = {"Authorization": f"Bearer {r2.json()['token']}"}

    # Open DM
    r = await client.post("/api/v1/dms", headers=h, json={"recipient_id": r2.json()["user_id"]})
    dm_id = r.json()["dm_id"]

    # Upload a file
    r = await client.post(
        "/api/v1/feeds/1/files",
        headers=h,
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
    )
    file_id = r.json()["file_id"]

    # Send DM with attachment
    r = await client.post(
        f"/api/v1/dms/{dm_id}/messages",
        headers=h,
        json={"body": "Here is the doc", "attachments": [file_id]},
    )
    assert r.status_code == 201

    # Fetch DM messages
    r = await client.get(f"/api/v1/dms/{dm_id}/messages", headers=h)
    msgs = r.json()["messages"]
    assert len(msgs) == 1
    assert len(msgs[0]["attachments"]) == 1
    assert msgs[0]["attachments"][0]["file_id"] == file_id


async def test_upload_disallowed_mime(client):
    """Uploading a file with a disallowed MIME type returns 415."""
    import io

    h = await setup(client)

    r = await client.post(
        "/api/v1/feeds/1/files",
        headers=h,
        files={"file": ("evil.bin", io.BytesIO(b"malicious"), "application/x-evil")},
    )
    assert r.status_code == 415
    body = r.json()
    err = body.get("error") or body.get("detail", {}).get("error", {})
    assert err["code"] == "UNSUPPORTED_MEDIA_TYPE"
