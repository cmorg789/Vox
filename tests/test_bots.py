from datetime import datetime, timezone

from vox.db.models import Bot, User
from vox.db.engine import get_session_factory
from vox import interactions


async def _setup_bot(client):
    """Create a human user, a bot user, a bot, and a feed. Return headers and bot info."""
    # Register human user
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    human_token = r.json()["token"]
    human_user_id = r.json()["user_id"]
    human_headers = {"Authorization": f"Bearer {human_token}"}

    # Create a feed
    await client.post("/api/v1/feeds", headers=human_headers, json={"name": "general", "type": "text"})

    # Register bot user account
    r = await client.post("/api/v1/auth/register", json={"username": "testbot", "password": "botpass1234"})
    bot_token = r.json()["token"]
    bot_headers = {"Authorization": f"Bearer {bot_token}"}
    bot_user_id = r.json()["user_id"]

    # Directly create Bot record in DB
    factory = get_session_factory()
    async with factory() as db:
        bot = Bot(user_id=bot_user_id, owner_id=human_user_id, created_at=datetime.now(timezone.utc))
        db.add(bot)
        await db.commit()
        bot_id = bot.id

    return human_headers, bot_headers, bot_user_id, bot_id


async def test_register_and_list_commands(client):
    human_h, bot_h, bot_uid, _ = await _setup_bot(client)

    # Register commands as bot
    r = await client.put(f"/api/v1/bots/{bot_uid}/commands", headers=bot_h, json={
        "commands": [{"name": "ping", "description": "Pong!"}]
    })
    assert r.status_code == 200

    # List commands as human
    r = await client.get("/api/v1/commands", headers=human_h)
    assert r.status_code == 200
    assert len(r.json()["commands"]) == 1
    assert r.json()["commands"][0]["name"] == "ping"


async def test_slash_command_interception(client):
    """Sending /ping in a feed should intercept and return interaction_id."""
    human_h, bot_h, bot_uid, _ = await _setup_bot(client)
    interactions.reset()

    # Register the command
    await client.put(f"/api/v1/bots/{bot_uid}/commands", headers=bot_h, json={
        "commands": [{"name": "ping", "description": "Pong!"}]
    })

    # Send slash command as human user
    r = await client.post("/api/v1/feeds/1/messages", headers=human_h, json={"body": "/ping"})
    assert r.status_code == 201
    data = r.json()
    assert data["interaction_id"] is not None
    assert data["msg_id"] == 0  # no real message created


async def test_slash_command_with_params(client):
    human_h, bot_h, bot_uid, _ = await _setup_bot(client)
    interactions.reset()

    await client.put(f"/api/v1/bots/{bot_uid}/commands", headers=bot_h, json={
        "commands": [{"name": "echo", "description": "Echo text"}]
    })

    r = await client.post("/api/v1/feeds/1/messages", headers=human_h, json={"body": "/echo text=hello"})
    assert r.status_code == 201
    interaction_id = r.json()["interaction_id"]

    # Verify the interaction was stored with params
    interaction = interactions.get(interaction_id)
    assert interaction is not None
    assert interaction.command == "echo"
    assert interaction.params == {"text": "hello"}


async def test_normal_message_not_intercepted(client):
    """A normal message should not be intercepted."""
    human_h, bot_h, _, _ = await _setup_bot(client)

    r = await client.post("/api/v1/feeds/1/messages", headers=human_h, json={"body": "hello world"})
    assert r.status_code == 201
    assert r.json().get("interaction_id") is None
    assert r.json()["msg_id"] != 0


async def test_unregistered_command_not_intercepted(client):
    """A /command that isn't registered should pass through as normal message."""
    human_h, _, _, _ = await _setup_bot(client)

    r = await client.post("/api/v1/feeds/1/messages", headers=human_h, json={"body": "/nonexistent"})
    assert r.status_code == 201
    assert r.json().get("interaction_id") is None
    assert r.json()["msg_id"] != 0


async def test_interaction_response_creates_message(client):
    """Bot responds to interaction, creating a real message."""
    human_h, bot_h, bot_uid, _ = await _setup_bot(client)
    interactions.reset()

    await client.put(f"/api/v1/bots/{bot_uid}/commands", headers=bot_h, json={
        "commands": [{"name": "ping", "description": "Pong!"}]
    })

    r = await client.post("/api/v1/feeds/1/messages", headers=human_h, json={"body": "/ping"})
    interaction_id = r.json()["interaction_id"]

    # Bot responds
    r = await client.post(
        f"/api/v1/interactions/{interaction_id}/response",
        headers=bot_h,
        json={"body": "Pong!", "ephemeral": False},
    )
    assert r.status_code == 204

    # Verify message was created in the feed
    r = await client.get("/api/v1/feeds/1/messages", headers=human_h)
    msgs = r.json()["messages"]
    assert len(msgs) == 1
    assert msgs[0]["body"] == "Pong!"
    assert msgs[0]["author_id"] == bot_uid


async def test_interaction_response_ephemeral(client):
    """Ephemeral response should not create a stored message."""
    human_h, bot_h, bot_uid, _ = await _setup_bot(client)
    interactions.reset()

    await client.put(f"/api/v1/bots/{bot_uid}/commands", headers=bot_h, json={
        "commands": [{"name": "ping", "description": "Pong!"}]
    })

    r = await client.post("/api/v1/feeds/1/messages", headers=human_h, json={"body": "/ping"})
    interaction_id = r.json()["interaction_id"]

    r = await client.post(
        f"/api/v1/interactions/{interaction_id}/response",
        headers=bot_h,
        json={"body": "Only you can see this", "ephemeral": True},
    )
    assert r.status_code == 204

    # No message should be stored
    r = await client.get("/api/v1/feeds/1/messages", headers=human_h)
    assert len(r.json()["messages"]) == 0


async def test_interaction_response_expired(client):
    """Responding to a consumed/expired interaction returns 404."""
    human_h, bot_h, _, _ = await _setup_bot(client)
    interactions.reset()

    r = await client.post(
        "/api/v1/interactions/nonexistent/response",
        headers=bot_h,
        json={"body": "hello"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "INTERACTION_NOT_FOUND"


async def test_interaction_response_wrong_bot(client):
    """A different user can't respond to another bot's interaction."""
    human_h, bot_h, bot_uid, _ = await _setup_bot(client)
    interactions.reset()

    await client.put(f"/api/v1/bots/{bot_uid}/commands", headers=bot_h, json={
        "commands": [{"name": "ping", "description": "Pong!"}]
    })

    r = await client.post("/api/v1/feeds/1/messages", headers=human_h, json={"body": "/ping"})
    interaction_id = r.json()["interaction_id"]

    # Human user tries to respond (not the bot)
    r = await client.post(
        f"/api/v1/interactions/{interaction_id}/response",
        headers=human_h,
        json={"body": "Impostor!"},
    )
    assert r.status_code == 403


async def test_interaction_consumed_once(client):
    """Interaction can only be responded to once."""
    human_h, bot_h, bot_uid, _ = await _setup_bot(client)
    interactions.reset()

    await client.put(f"/api/v1/bots/{bot_uid}/commands", headers=bot_h, json={
        "commands": [{"name": "ping", "description": "Pong!"}]
    })

    r = await client.post("/api/v1/feeds/1/messages", headers=human_h, json={"body": "/ping"})
    interaction_id = r.json()["interaction_id"]

    # First response succeeds
    r = await client.post(
        f"/api/v1/interactions/{interaction_id}/response",
        headers=bot_h,
        json={"body": "Pong!"},
    )
    assert r.status_code == 204

    # Second response fails
    r = await client.post(
        f"/api/v1/interactions/{interaction_id}/response",
        headers=bot_h,
        json={"body": "Pong again!"},
    )
    assert r.status_code == 404


async def test_component_interaction(client):
    """Component interaction creates an interaction for the bot."""
    human_h, bot_h, bot_uid, _ = await _setup_bot(client)
    interactions.reset()

    # Bot sends a message (directly as a normal message)
    r = await client.post("/api/v1/feeds/1/messages", headers=bot_h, json={"body": "Click the button!"})
    assert r.status_code == 201
    msg_id = r.json()["msg_id"]

    # Human clicks a component
    r = await client.post(
        "/api/v1/interactions/component",
        headers=human_h,
        json={"msg_id": msg_id, "component_id": "btn_1"},
    )
    assert r.status_code == 204


async def test_component_interaction_non_bot_message(client):
    """Component interaction on a non-bot message returns error."""
    human_h, _, _, _ = await _setup_bot(client)
    interactions.reset()

    # Human sends a message
    r = await client.post("/api/v1/feeds/1/messages", headers=human_h, json={"body": "Just a message"})
    msg_id = r.json()["msg_id"]

    r = await client.post(
        "/api/v1/interactions/component",
        headers=human_h,
        json={"msg_id": msg_id, "component_id": "btn_1"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "NOT_BOT_MESSAGE"


async def test_deregister_commands(client):
    _, bot_h, bot_uid, _ = await _setup_bot(client)

    await client.put(f"/api/v1/bots/{bot_uid}/commands", headers=bot_h, json={
        "commands": [{"name": "ping", "description": "Pong!"}, {"name": "echo", "description": "Echo!"}]
    })

    r = await client.request("DELETE", f"/api/v1/bots/{bot_uid}/commands", headers=bot_h, json={
        "command_names": ["ping"]
    })
    assert r.status_code == 200

    r = await client.get("/api/v1/commands", headers=bot_h)
    assert len(r.json()["commands"]) == 1
    assert r.json()["commands"][0]["name"] == "echo"


async def test_slash_command_in_dm(client):
    """Slash commands should also be intercepted in DMs."""
    human_h, bot_h, bot_uid, _ = await _setup_bot(client)
    interactions.reset()

    # Register command
    await client.put(f"/api/v1/bots/{bot_uid}/commands", headers=bot_h, json={
        "commands": [{"name": "help", "description": "Show help"}]
    })

    # Open DM with bot
    r = await client.post("/api/v1/dms", headers=human_h, json={"recipient_id": bot_uid})
    dm_id = r.json()["dm_id"]

    # Send slash command in DM
    r = await client.post(f"/api/v1/dms/{dm_id}/messages", headers=human_h, json={"body": "/help"})
    assert r.status_code == 201
    assert r.json()["interaction_id"] is not None


async def test_register_commands_not_bot(client):
    """Non-bot user cannot register commands."""
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    uid = r.json()["user_id"]
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    r = await client.put(f"/api/v1/bots/{uid}/commands", headers=h, json={
        "commands": [{"name": "test", "description": "Test"}]
    })
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "FORBIDDEN"


async def test_deregister_commands_not_bot(client):
    """Non-bot user cannot deregister commands."""
    r = await client.post("/api/v1/auth/register", json={"username": "alice", "password": "test1234"})
    uid = r.json()["user_id"]
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    r = await client.request("DELETE", f"/api/v1/bots/{uid}/commands", headers=h, json={
        "command_names": ["test"]
    })
    assert r.status_code == 403


async def test_register_duplicate_command(client):
    """Registering a command with the same name twice returns 409."""
    human_h, bot_h, bot_uid, _ = await _setup_bot(client)
    await client.put(f"/api/v1/bots/{bot_uid}/commands", headers=bot_h, json={
        "commands": [{"name": "help", "description": "Show help"}]
    })
    r = await client.put(f"/api/v1/bots/{bot_uid}/commands", headers=bot_h, json={
        "commands": [{"name": "help", "description": "Updated help"}]
    })
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "CMD_ALREADY_REGISTERED"


async def test_respond_interaction_message_not_found(client):
    """Responding to interaction with non-existent message returns 404."""
    human_h, bot_h, _, _ = await _setup_bot(client)
    r = await client.post("/api/v1/interactions/999999/response", headers=bot_h, json={
        "body": "response"
    })
    assert r.status_code == 404
