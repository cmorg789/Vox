# Gateway Client Reference

The `GatewayClient` provides a real-time WebSocket connection to the Vox gateway for receiving events and sending commands.

## Constructor

```python
from vox_sdk import GatewayClient

gw = GatewayClient(gateway_url, token, compress=True, protocol_version=1)
```

| Parameter          | Type   | Default | Description                                    |
|--------------------|--------|---------|------------------------------------------------|
| `gateway_url`      | `str`  | --      | WebSocket URL from `server.gateway_info()`.    |
| `token`            | `str`  | --      | Authentication token.                          |
| `compress`         | `bool` | `True`  | Enable zstd compression (server-to-client).    |
| `protocol_version` | `int`  | `1`     | Gateway protocol version.                      |

## Event registration

### Decorator

```python
@gw.on("message_create")
async def on_message(event):
    print(event.body)
```

### Programmatic

```python
async def on_message(event):
    print(event.body)

gw.add_handler("message_create", on_message)
```

### Wildcard handler

Register a handler for all events using `"*"`:

```python
@gw.on("*")
async def on_any(event):
    print(f"Event: {event}")
```

## Methods

### `run()`

Starts the gateway connection and blocks, listening for events. Automatically reconnects on disconnection using exponential backoff with jitter (see [Auto-reconnect](#auto-reconnect) below).

```python
await gw.run()
```

### `connect()`

Establishes a single gateway connection without automatic reconnection. Useful when you want manual control over the connection lifecycle.

```python
await gw.connect()
```

### `connect_in_background(timeout=30)`

Connects to the gateway in a background task and returns the `Ready` event once the session is established. The gateway continues running in the background.

```python
ready = await gw.connect_in_background(timeout=30)
print(f"Connected as session {ready.session_id}")
```

| Parameter | Type    | Default | Description                                |
|-----------|---------|---------|--------------------------------------------|
| `timeout` | `float` | `30`    | Seconds to wait for the Ready event.       |

### `close()`

Gracefully closes the gateway connection.

```python
await gw.close()
```

### `send(type, data)`

Sends a raw gateway message.

```python
await gw.send("custom_op", {"key": "value"})
```

### `send_typing(feed_id)`

Sends a typing indicator for the given feed.

```python
await gw.send_typing(feed_id=42)
```

### `update_presence(status, custom_status=None)`

Updates the current user's presence.

```python
await gw.update_presence("online", custom_status="Working on docs")
```

| Parameter       | Type            | Description                              |
|-----------------|-----------------|------------------------------------------|
| `status`        | `str`           | One of: `"online"`, `"idle"`, `"dnd"`, `"offline"`. |
| `custom_status` | `str` or `None` | Optional custom status text.             |

## Properties

| Property     | Type            | Description                                    |
|--------------|-----------------|------------------------------------------------|
| `session_id` | `str` or `None` | Current session ID, set after Ready.           |
| `last_seq`   | `int` or `None` | Last received sequence number for resumption.  |

## Auto-reconnect

The `run()` method implements automatic reconnection with the following behavior:

### Resumable close codes

When the gateway disconnects with a resumable close code, the client preserves its `session_id` and `last_seq` and sends a Resume payload on reconnect. The server replays any missed events.

### Non-resumable close codes

When the gateway disconnects with a non-resumable close code, the client resets `session_id` and `last_seq` and performs a fresh Identify handshake.

### Fatal close codes

Fatal close codes (such as authentication failure) cause `run()` to re-raise the error instead of reconnecting.

### Backoff strategy

| Parameter      | Value  |
|----------------|--------|
| Base delay     | 1s     |
| Multiplier     | 2x     |
| Jitter         | 50%    |
| Maximum delay  | 60s    |

The delay doubles on each consecutive failure and resets after a successful connection. Jitter is applied as a random value between 0% and 50% of the current delay to prevent thundering herd effects.

## Compression

When `compress=True` (the default), the client negotiates zstd compression with the server. Compressed frames are decompressed transparently on receipt.

- Compression applies to **server-to-client** messages only.
- Requires the `zstandard` package (included in the SDK's dependencies).
- If zstd is unavailable at runtime, the client falls back to uncompressed communication.
