# Quickstart

This guide walks through installing the Vox SDK and using it to interact with a Vox server.

## Installation

```bash
pip install vox-sdk
```

To build the optional media bindings (AV1 codec support), you also need a Rust toolchain and maturin:

```bash
pip install maturin
```

## Basic usage

The `Client` class is an async context manager that handles connection setup and teardown. Call `login()` to authenticate, then use the API group properties to make requests.

```python
import asyncio
from vox_sdk import Client

async def main():
    async with Client("https://vox.example.com") as client:
        await client.login("alice", "password123")

        # Send a message to a feed
        msg = await client.messages.send(feed_id=1, body="Hello!")

        # List all members
        members = await client.members.list()

        for member in members:
            print(member.user.display_name)

asyncio.run(main())
```

The client automatically manages the HTTP session, attaches authentication headers, and handles rate limiting behind the scenes.

## Gateway events

The gateway client provides real-time event streaming over WebSocket. Register event handlers with the `@gw.on()` decorator and call `gw.run()` to start receiving events.

```python
import asyncio
from vox_sdk import Client, GatewayClient

async def main():
    async with Client("https://vox.example.com") as client:
        await client.login("alice", "password123")

        # Fetch the gateway URL from the server
        info = await client.server.gateway_info()
        gw = GatewayClient(info.url, client.http.token)

        @gw.on("message_create")
        async def on_message(event):
            print(f"[{event.feed_id}] {event.author_id}: {event.body}")

        await gw.run()

asyncio.run(main())
```

The `run()` method blocks and automatically reconnects on disconnection with exponential backoff. For non-blocking usage, see `connect_in_background()` in the [Gateway Client reference](gateway-client.md).

## Error handling

The SDK raises typed exceptions for API and network errors.

```python
from vox_sdk import Client, VoxHTTPError, VoxNetworkError

async def send_message(client: Client):
    try:
        await client.messages.send(feed_id=1, body="hello")
    except VoxHTTPError as e:
        print(f"API error: {e.status} {e.code}")
    except VoxNetworkError as e:
        print(f"Network error: {e}")
```

- **`VoxHTTPError`** -- Raised when the server returns a non-success HTTP status. Contains `status` (HTTP status code), `code` (Vox error code string), and `message` (human-readable description).
- **`VoxNetworkError`** -- Raised when the request fails due to a network-level issue (DNS resolution, connection refused, timeout, etc.).

See the [Error code reference](../reference/errors.md) for a complete list of error codes.

## Next steps

- [HTTP Client reference](client.md) -- Full details on the Client class, API groups, and response models.
- [Gateway Client reference](gateway-client.md) -- Event handling, reconnection behavior, and compression.
- [Error codes](../reference/errors.md) -- All error codes and their meanings.
- [Rate limits](../reference/rate-limits.md) -- How rate limiting works and best practices.
