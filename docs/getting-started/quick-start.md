---
title: Quick Start
description: Register, create a feed, send messages, and connect to the real-time gateway.
---

# Quick Start

This tutorial walks through the core Vox workflow: registering a user, logging in, creating a feed, sending messages, and connecting to the WebSocket gateway for real-time events.

!!! note "Prerequisites"
    Make sure you have a Vox server running locally on `http://localhost:8000`. See [Installation](installation.md) for setup instructions.

---

## 1. Register a User

=== "curl"

    ```bash
    curl -X POST http://localhost:8000/api/auth/register \
         -H "Content-Type: application/json" \
         -d '{
           "username": "alice",
           "password": "a-strong-password"
         }'
    ```

    Response:

    ```json
    {
      "id": "123456789012345678",
      "username": "alice"
    }
    ```

=== "Python SDK"

    ```python
    from vox_sdk import Client

    client = Client("http://localhost:8000")
    user = client.register("alice", "a-strong-password")
    print(user.id, user.username)
    ```

---

## 2. Log In

=== "curl"

    ```bash
    curl -X POST http://localhost:8000/api/auth/login \
         -H "Content-Type: application/json" \
         -d '{
           "username": "alice",
           "password": "a-strong-password"
         }'
    ```

    Response:

    ```json
    {
      "token": "eyJhbGciOiJIUzI1NiIs..."
    }
    ```

    Save the token for subsequent requests:

    ```bash
    export TOKEN="eyJhbGciOiJIUzI1NiIs..."
    ```

=== "Python SDK"

    ```python
    client.login("alice", "a-strong-password")
    # The client stores the session token automatically
    ```

---

## 3. Create a Feed

Feeds are channels within your server where messages are posted.

=== "curl"

    ```bash
    curl -X POST http://localhost:8000/api/feeds \
         -H "Authorization: Bearer $TOKEN" \
         -H "Content-Type: application/json" \
         -d '{
           "name": "general",
           "kind": "text"
         }'
    ```

    Response:

    ```json
    {
      "id": "234567890123456789",
      "name": "general",
      "kind": "text"
    }
    ```

=== "Python SDK"

    ```python
    feed = client.create_feed("general", kind="text")
    print(feed.id, feed.name)
    ```

---

## 4. Send a Message

=== "curl"

    ```bash
    curl -X POST http://localhost:8000/api/feeds/234567890123456789/messages \
         -H "Authorization: Bearer $TOKEN" \
         -H "Content-Type: application/json" \
         -d '{
           "body": "Hello, Vox!"
         }'
    ```

    Response:

    ```json
    {
      "id": "345678901234567890",
      "feed_id": "234567890123456789",
      "author_id": "123456789012345678",
      "body": "Hello, Vox!",
      "created_at": "2026-02-19T12:00:00Z"
    }
    ```

=== "Python SDK"

    ```python
    message = client.send_message(feed.id, "Hello, Vox!")
    print(message.id, message.body)
    ```

---

## 5. Fetch Messages

=== "curl"

    ```bash
    curl http://localhost:8000/api/feeds/234567890123456789/messages \
         -H "Authorization: Bearer $TOKEN"
    ```

    Response:

    ```json
    [
      {
        "id": "345678901234567890",
        "feed_id": "234567890123456789",
        "author_id": "123456789012345678",
        "body": "Hello, Vox!",
        "created_at": "2026-02-19T12:00:00Z"
      }
    ]
    ```

=== "Python SDK"

    ```python
    messages = client.get_messages(feed.id)
    for msg in messages:
        print(f"{msg.author_id}: {msg.body}")
    ```

---

## 6. Connect to the Gateway

The WebSocket gateway provides real-time event delivery. Connect to receive events as they happen.

=== "curl (websocat)"

    ```bash
    websocat "ws://localhost:8000/gateway?token=$TOKEN"
    ```

    You will receive JSON events as they occur:

    ```json
    {"op": "hello", "d": {"heartbeat_interval": 30000}}
    ```

    Send a heartbeat to keep the connection alive:

    ```json
    {"op": "heartbeat"}
    ```

=== "Python SDK"

    ```python
    import asyncio
    from vox_sdk import Client

    async def main():
        client = Client("http://localhost:8000")
        client.login("alice", "a-strong-password")

        @client.on("message_create")
        async def on_message(event):
            print(f"New message: {event.body}")

        await client.connect()

    asyncio.run(main())
    ```

---

## Gateway Events

Once connected, the gateway delivers events in real time. Common events include:

| Event | Description |
|---|---|
| `message_create` | A new message was posted |
| `message_update` | A message was edited |
| `message_delete` | A message was deleted |
| `presence_update` | A user's online status changed |
| `typing_start` | A user started typing in a feed |

---

## Next Steps

You now have a working Vox server with a user, a feed, and real-time event delivery. From here you can:

- **[Configure your server](configuration.md)** -- Customize limits, enable federation, and set up media transport.
- Set up **WebAuthn** for passwordless authentication.
- Enable **federation** to connect with other Vox servers.
- Create **bots and webhooks** for automation.
