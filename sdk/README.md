# Vox Python SDK

Python client SDK for the Vox protocol.

## Install

```bash
pip install vox-sdk
```

## Quickstart

```python
import asyncio
from vox_sdk import Client

async def main():
    async with Client("https://vox.example.com") as client:
        # Login
        await client.login("alice", "password123")

        # Send a message
        msg = await client.messages.send(feed_id=1, body="Hello from the SDK!")

        # List members
        members = await client.members.list()
        print(f"{len(members.items)} members online")

asyncio.run(main())
```

## Gateway Events

```python
import asyncio
from vox_sdk import Client, GatewayClient

async def main():
    async with Client("https://vox.example.com") as client:
        await client.login("alice", "password123")

        info = await client.server.gateway_info()
        gw = GatewayClient(info.url, client.http.token)

        @gw.on("message_create")
        async def on_message(event):
            print(f"[{event.feed_id}] {event.author_id}: {event.body}")

        @gw.on("presence_update")
        async def on_presence(event):
            print(f"User {event.user_id} is now {event.status}")

        # run() auto-reconnects on recoverable errors
        await gw.run()

asyncio.run(main())
```

## Error Handling

```python
from vox_sdk import VoxHTTPError, VoxNetworkError
from vox_sdk.errors import VoxGatewayError

try:
    await client.messages.send(feed_id=1, body="hello")
except VoxHTTPError as e:
    print(f"API error: {e.status} {e.code}")
except VoxNetworkError as e:
    print(f"Network error: {e}")
```

## API Groups

The client exposes these API groups as properties:

| Property | Description |
|---|---|
| `client.auth` | Login, register, MFA, sessions |
| `client.messages` | Send, edit, delete, reactions, pins |
| `client.channels` | Feeds, rooms, categories, threads |
| `client.members` | List, get, ban, kick, update |
| `client.roles` | Create, assign, permissions |
| `client.server` | Server info, layout, limits |
| `client.users` | Profiles, friends, blocks |
| `client.invites` | Create, resolve, delete |
| `client.dms` | Open, send, close DMs |
| `client.voice` | Join, leave, mute, stage |
| `client.webhooks` | Create, execute webhooks |
| `client.bots` | Commands, interactions |
| `client.files` | Upload, download, delete |
| `client.emoji` | Emoji and stickers |
| `client.e2ee` | Prekeys, devices, MLS |
| `client.moderation` | Reports, audit log |
| `client.federation` | Cross-server federation |
| `client.search` | Message search |
| `client.sync` | Offline sync |
| `client.embeds` | URL embed resolution |

## Models

All response models are re-exported from `vox_sdk.models`:

```python
from vox_sdk.models import MessageResponse, UserResponse, FeedResponse
```
