async def setup(client):
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/feeds", headers=h, json={"name": "general", "type": "text"})
    return h


async def test_send_and_get_messages(client):
    h = await setup(client)

    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Hello!"})
    assert r.status_code == 201
    msg_id = r.json()["msg_id"]
    assert r.json()["timestamp"] > 0

    r = await client.get("/api/v1/feeds/1/messages", headers=h)
    assert r.status_code == 200
    assert len(r.json()["messages"]) == 1
    assert r.json()["messages"][0]["msg_id"] == msg_id
    assert r.json()["messages"][0]["body"] == "Hello!"


async def test_edit_message(client):
    h = await setup(client)

    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Original"})
    msg_id = r.json()["msg_id"]

    r = await client.patch(f"/api/v1/feeds/1/messages/{msg_id}", headers=h, json={"body": "Edited"})
    assert r.status_code == 200
    assert r.json()["edit_timestamp"] > 0


async def test_edit_message_not_author(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Original"})
    msg_id = r.json()["msg_id"]

    # Register second user
    r2 = await client.post("/api/v1/auth/register", json={"username": "bob", "password": "test1234"})
    h2 = {"Authorization": f"Bearer {r2.json()['token']}"}

    r = await client.patch(f"/api/v1/feeds/1/messages/{msg_id}", headers=h2, json={"body": "Hacked"})
    assert r.status_code == 403


async def test_delete_message(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Delete me"})
    msg_id = r.json()["msg_id"]

    r = await client.delete(f"/api/v1/feeds/1/messages/{msg_id}", headers=h)
    assert r.status_code == 204

    r = await client.get("/api/v1/feeds/1/messages", headers=h)
    assert len(r.json()["messages"]) == 0


async def test_bulk_delete(client):
    h = await setup(client)
    ids = []
    for i in range(3):
        r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": f"msg {i}"})
        ids.append(r.json()["msg_id"])

    r = await client.post("/api/v1/feeds/1/messages/bulk-delete", headers=h, json={"msg_ids": ids})
    assert r.status_code == 204

    r = await client.get("/api/v1/feeds/1/messages", headers=h)
    assert len(r.json()["messages"]) == 0


async def test_reactions(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "React to this"})
    msg_id = r.json()["msg_id"]

    r = await client.put(f"/api/v1/feeds/1/messages/{msg_id}/reactions/%F0%9F%91%8D", headers=h)
    assert r.status_code == 204

    r = await client.delete(f"/api/v1/feeds/1/messages/{msg_id}/reactions/%F0%9F%91%8D", headers=h)
    assert r.status_code == 204


async def test_pins(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Pin me"})
    msg_id = r.json()["msg_id"]

    r = await client.put(f"/api/v1/feeds/1/pins/{msg_id}", headers=h)
    assert r.status_code == 204

    r = await client.get("/api/v1/feeds/1/pins", headers=h)
    assert r.status_code == 200
    assert len(r.json()["messages"]) == 1

    r = await client.delete(f"/api/v1/feeds/1/pins/{msg_id}", headers=h)
    assert r.status_code == 204

    r = await client.get("/api/v1/feeds/1/pins", headers=h)
    assert len(r.json()["messages"]) == 0


async def test_thread_messages(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Parent"})
    msg_id = r.json()["msg_id"]

    r = await client.post("/api/v1/feeds/1/threads", headers=h, json={"parent_msg_id": msg_id, "name": "Thread"})
    thread_id = r.json()["thread_id"]

    r = await client.post(f"/api/v1/feeds/1/threads/{thread_id}/messages", headers=h, json={"body": "In thread"})
    assert r.status_code == 201

    r = await client.get(f"/api/v1/feeds/1/threads/{thread_id}/messages", headers=h)
    assert len(r.json()["messages"]) == 1
    assert r.json()["messages"][0]["body"] == "In thread"


async def test_get_feed_messages_before_after(client):
    h = await setup(client)
    ids = []
    for i in range(3):
        r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": f"msg{i}"})
        ids.append(r.json()["msg_id"])

    # before filter
    r = await client.get(f"/api/v1/feeds/1/messages?before={ids[2]}", headers=h)
    assert all(m["msg_id"] < ids[2] for m in r.json()["messages"])

    # after filter
    r = await client.get(f"/api/v1/feeds/1/messages?after={ids[0]}", headers=h)
    assert all(m["msg_id"] > ids[0] for m in r.json()["messages"])


async def test_get_thread_messages_before_after(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Parent"})
    msg_id = r.json()["msg_id"]
    r = await client.post("/api/v1/feeds/1/threads", headers=h, json={"parent_msg_id": msg_id, "name": "T"})
    tid = r.json()["thread_id"]

    ids = []
    for i in range(3):
        r = await client.post(f"/api/v1/feeds/1/threads/{tid}/messages", headers=h, json={"body": f"t{i}"})
        ids.append(r.json()["msg_id"])

    r = await client.get(f"/api/v1/feeds/1/threads/{tid}/messages?before={ids[2]}", headers=h)
    assert all(m["msg_id"] < ids[2] for m in r.json()["messages"])

    r = await client.get(f"/api/v1/feeds/1/threads/{tid}/messages?after={ids[0]}", headers=h)
    assert all(m["msg_id"] > ids[0] for m in r.json()["messages"])


async def test_edit_message_not_found(client):
    h = await setup(client)
    r = await client.patch("/api/v1/feeds/1/messages/99999", headers=h, json={"body": "x"})
    assert r.status_code == 404


async def test_delete_message_not_found(client):
    h = await setup(client)
    r = await client.delete("/api/v1/feeds/1/messages/99999", headers=h)
    assert r.status_code == 404


async def test_delete_message_other_user_no_permission(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "hi"})
    msg_id = r.json()["msg_id"]

    r2 = await client.post("/api/v1/auth/register", json={"username": "bob", "password": "test1234"})
    h2 = {"Authorization": f"Bearer {r2.json()['token']}"}
    r = await client.delete(f"/api/v1/feeds/1/messages/{msg_id}", headers=h2)
    assert r.status_code == 403


async def test_slash_command_http_callback_bot(client):
    """Slash command with HTTP callback bot creates response message."""
    h = await setup(client)

    from datetime import datetime, timezone
    from vox.db.engine import get_session_factory
    from vox.db.models import Bot, BotCommand, User
    factory = get_session_factory()
    async with factory() as db:
        from sqlalchemy import select
        user = (await db.execute(select(User).where(User.username == "alice"))).scalar_one()

        bot_user = User(username="testbot", display_name="Test Bot", federated=False, active=True, created_at=datetime.now(timezone.utc))
        db.add(bot_user)
        await db.flush()

        bot = Bot(user_id=bot_user.id, owner_id=user.id, interaction_url="http://localhost:9999/callback", created_at=datetime.now(timezone.utc))
        db.add(bot)
        await db.flush()

        cmd = BotCommand(bot_id=bot.id, name="ping", description="pong")
        db.add(cmd)
        await db.commit()

    from unittest.mock import AsyncMock, MagicMock, patch
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"body": "pong!"}'
    mock_resp.json.return_value = {"body": "pong!"}

    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_resp)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("vox.api.messages.httpx.AsyncClient", return_value=mock_client_instance):
        r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "/ping"})
        assert r.status_code == 201
        assert r.json().get("interaction_id") is not None

    # Verify the bot response message was created
    r = await client.get("/api/v1/feeds/1/messages", headers=h)
    msgs = r.json()["messages"]
    assert any(m["body"] == "pong!" for m in msgs)


async def test_slash_command_gateway_bot(client):
    """Slash command with gateway bot (no interaction_url) dispatches event."""
    h = await setup(client)

    from datetime import datetime, timezone
    from vox.db.engine import get_session_factory
    from vox.db.models import Bot, BotCommand, User
    factory = get_session_factory()
    async with factory() as db:
        from sqlalchemy import select
        user = (await db.execute(select(User).where(User.username == "alice"))).scalar_one()

        bot_user = User(username="gwbot", display_name="GW Bot", federated=False, active=True, created_at=datetime.now(timezone.utc))
        db.add(bot_user)
        await db.flush()

        bot = Bot(user_id=bot_user.id, owner_id=user.id, interaction_url=None, created_at=datetime.now(timezone.utc))
        db.add(bot)
        await db.flush()

        cmd = BotCommand(bot_id=bot.id, name="hello", description="greet")
        db.add(cmd)
        await db.commit()

    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "/hello world"})
    assert r.status_code == 201
    assert r.json().get("interaction_id") is not None


async def test_slash_command_positional_params(client):
    """Slash command with positional param (no =) sets True."""
    from vox.api.messages import _parse_slash_command
    result = _parse_slash_command("/test flag key=val")
    assert result is not None
    name, params = result
    assert name == "test"
    assert params["flag"] is True
    assert params["key"] == "val"


async def test_slash_command_empty_name(client):
    """Slash command with just '/' returns None."""
    from vox.api.messages import _parse_slash_command
    assert _parse_slash_command("/ ") is None


async def test_thread_message_invalid_attachment(client):
    h = await setup(client)
    r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "Parent"})
    msg_id = r.json()["msg_id"]
    r = await client.post("/api/v1/feeds/1/threads", headers=h, json={"parent_msg_id": msg_id, "name": "T"})
    tid = r.json()["thread_id"]

    r = await client.post(f"/api/v1/feeds/1/threads/{tid}/messages", headers=h, json={"body": "hi", "attachments": ["nonexistent"]})
    assert r.status_code == 400


async def test_slash_command_http_callback_error(client):
    """HTTP callback bot that raises HTTPError is silently caught."""
    h = await setup(client)

    from datetime import datetime, timezone
    from vox.db.engine import get_session_factory
    from vox.db.models import Bot, BotCommand, User
    factory = get_session_factory()
    async with factory() as db:
        from sqlalchemy import select
        user = (await db.execute(select(User).where(User.username == "alice"))).scalar_one()

        bot_user = User(username="errbot", display_name="Err Bot", federated=False, active=True, created_at=datetime.now(timezone.utc))
        db.add(bot_user)
        await db.flush()

        bot = Bot(user_id=bot_user.id, owner_id=user.id, interaction_url="http://localhost:9999/fail", created_at=datetime.now(timezone.utc))
        db.add(bot)
        await db.flush()

        cmd = BotCommand(bot_id=bot.id, name="fail", description="fails")
        db.add(cmd)
        await db.commit()

    import httpx
    from unittest.mock import AsyncMock, patch
    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(side_effect=httpx.HTTPError("connection refused"))
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("vox.api.messages.httpx.AsyncClient", return_value=mock_client_instance):
        r = await client.post("/api/v1/feeds/1/messages", headers=h, json={"body": "/fail"})
        assert r.status_code == 201
        assert r.json().get("interaction_id") is not None
