# Connection Lifecycle

This page describes the full gateway connection flow, from initial handshake
through session resumption and error handling.

## Connection Flow

### 1. Connect

Open a WebSocket connection to the gateway endpoint:

```
wss://host/gateway?v=1&encoding=json&compress=zstd
```

### 2. Receive Hello

The server immediately sends a `hello` message:

```json
{
  "type": "hello",
  "seq": 0,
  "d": {
    "heartbeat_interval": 45000
  }
}
```

### 3. Identify

The client must send an `identify` message to authenticate:

```json
{
  "type": "identify",
  "d": {
    "token": "auth-token",
    "protocol_version": 1,
    "capabilities": ["voice", "video", "e2ee", "federation", "bots", "compress.zstd"]
  }
}
```

| Field              | Type     | Description                                        |
|--------------------|----------|----------------------------------------------------|
| `token`            | string   | Authentication token.                              |
| `protocol_version` | int      | Protocol version the client supports.              |
| `capabilities`     | string[] | Features the client supports.                      |

### 4. Ready

On successful identification the server responds with `ready`:

```json
{
  "type": "ready",
  "seq": 1,
  "d": {
    "session_id": "abc123",
    "user_id": 100,
    "display_name": "alice",
    "server_name": "My Server",
    "server_icon": "https://cdn.example.com/icon.png",
    "server_time": "2026-02-19T00:00:00Z",
    "protocol_version": 1,
    "capabilities": ["voice", "video", "e2ee", "federation", "bots", "compress.zstd"]
  }
}
```

The `capabilities` array in the `ready` payload reflects the intersection of
what the client requested and what the server supports.

---

## Heartbeat

After receiving `hello`, the client must send a `heartbeat` at the interval
specified by `heartbeat_interval` (in milliseconds).

```json
{
  "type": "heartbeat",
  "d": {}
}
```

The server replies with `heartbeat_ack`:

```json
{
  "type": "heartbeat_ack",
  "seq": 5,
  "d": {}
}
```

### Timeout Rules

- **Client**: If two consecutive `heartbeat_ack` messages are missed, the client
  should close the connection and attempt to resume.
- **Server**: If no heartbeat is received within `heartbeat_interval * 1.5`, the
  server closes the connection.

---

## Resume

When a connection drops, the client can attempt to resume the session instead of
re-identifying. Send a `resume` message on the new connection (after receiving
`hello`):

```json
{
  "type": "resume",
  "d": {
    "token": "auth-token",
    "session_id": "abc123",
    "last_seq": 42
  }
}
```

| Field        | Type   | Description                                       |
|--------------|--------|---------------------------------------------------|
| `token`      | string | Authentication token.                             |
| `session_id` | string | Session ID from the original `ready` payload.     |
| `last_seq`   | int    | Last sequence number the client received.         |

On success, the server replays all events the client missed (starting from
`last_seq + 1`). If the session has expired or the replay buffer is exhausted,
the server closes the connection with code `4009` or `4010`.

---

## Close Codes

| Code | Name                  | Resumable | Description                                           |
|------|-----------------------|-----------|-------------------------------------------------------|
| 4000 | `UNKNOWN_ERROR`       | Yes       | An unknown error occurred.                            |
| 4001 | `UNKNOWN_TYPE`        | No        | Client sent an unrecognized message type.             |
| 4002 | `DECODE_ERROR`        | No        | Client sent an invalid or malformed payload.          |
| 4003 | `NOT_AUTHENTICATED`   | No        | Client sent a payload before identifying.             |
| 4004 | `AUTH_FAILED`         | No        | Authentication token is invalid or expired.           |
| 4005 | `ALREADY_AUTHENTICATED` | No     | Client sent identify/resume on an active session.     |
| 4006 | `RATE_LIMITED`        | Yes       | Too many messages. Reconnect after a delay.           |
| 4007 | `SESSION_TIMEOUT`     | Yes       | Session timed out due to missed heartbeats.           |
| 4008 | `SERVER_RESTART`      | Yes       | Server is restarting. Resume when available.          |
| 4009 | `SESSION_EXPIRED`     | No        | Session no longer exists. Re-identify.                |
| 4010 | `REPLAY_EXHAUSTED`    | No        | Replay buffer exhausted. Re-identify and call `/sync`.|
| 4011 | `VERSION_MISMATCH`    | No        | Protocol version not supported by the server.         |

For codes marked **Resumable: Yes**, the client should reconnect and send a
`resume`. For `4009` and `4010`, the client must start a fresh session with
`identify` (and call the REST `/sync` endpoint for `4010` to catch up on missed
state).

---

## Client-to-Server Payloads

### voice_state_update

Update the client's voice and video state.

```json
{
  "type": "voice_state_update",
  "d": {
    "self_mute": false,
    "self_deaf": false,
    "video": true,
    "streaming": false
  }
}
```

### presence_update

Set the client's online status and optional activity.

```json
{
  "type": "presence_update",
  "d": {
    "status": "online",
    "custom_status": "Working on docs",
    "activity": {
      "type": "playing",
      "name": "Some Game"
    }
  }
}
```

| Field           | Type   | Required | Description                              |
|-----------------|--------|----------|------------------------------------------|
| `status`        | string | Yes      | One of `online`, `idle`, `dnd`, `offline`.|
| `custom_status` | string | No       | Free-text status message.                |
| `activity`      | object | No       | Activity information.                    |

### typing

Signal that the user is typing in a feed or DM. Send either `feed_id` or
`dm_id`, not both.

```json
{
  "type": "typing",
  "d": {
    "feed_id": 500
  }
}
```

### mls_relay

Relay an MLS (Messaging Layer Security) E2EE message to the server for
distribution to the group.

```json
{
  "type": "mls_relay",
  "d": {
    "mls_type": "commit",
    "data": "base64-encoded-mls-message"
  }
}
```

### cpace_relay

Relay a CPace device-pairing message.

```json
{
  "type": "cpace_relay",
  "d": {
    "cpace_type": "isi",
    "pair_id": "device-pair-uuid",
    "data": "base64-encoded-cpace-data"
  }
}
```

### voice_codec_neg

Negotiate codec parameters for voice or video.

```json
{
  "type": "voice_codec_neg",
  "d": {
    "media_type": "video",
    "codec": "AV1",
    "spatial_layers": 3,
    "temporal_layers": 3,
    "target_bitrates": [100000, 500000, 2000000],
    "dependency_templates": ["S0T0", "S1T0", "S2T0"]
  }
}
```

### stage_response

Accept or decline an invitation to speak on a stage.

```json
{
  "type": "stage_response",
  "d": {
    "room_id": 800,
    "response_type": "accept",
    "accepted": true
  }
}
```
