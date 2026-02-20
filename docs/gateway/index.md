# Gateway Overview

The Vox gateway provides a persistent WebSocket connection for real-time
communication between clients and the server. All state changes, messages,
presence updates, and voice signaling flow through the gateway.

## Connection Endpoint

```
wss://host/gateway?v=1&encoding=json&compress=zstd
```

| Parameter  | Required | Description                              |
|------------|----------|------------------------------------------|
| `v`        | Yes      | Protocol version. Currently `1`.         |
| `encoding` | Yes      | Payload encoding. Currently `json` only. |
| `compress` | No       | Compression algorithm. `zstd` or omit.   |

## Message Format

Every gateway message is a JSON object with the following structure:

```json
{
  "type": "event_name",
  "seq": 42,
  "d": { }
}
```

| Field  | Type   | Description                                                                 |
|--------|--------|-----------------------------------------------------------------------------|
| `type` | string | The event or control message name.                                          |
| `seq`  | int    | Sequence number. **Server-to-client only.** Monotonically increasing.       |
| `d`    | object | The event payload. Contents vary by `type`.                                 |

The `seq` field is present only on messages sent from the server to the client.
Clients must track the last received `seq` so they can resume a dropped
connection without missing events.

## Message Categories

Gateway messages fall into three categories:

### Control Messages

Used to establish, maintain, and resume sessions.

| Type            | Direction        | Purpose                                |
|-----------------|------------------|----------------------------------------|
| `hello`         | Server to Client | Sent immediately on connection.        |
| `heartbeat`     | Client to Server | Keeps the connection alive.            |
| `heartbeat_ack` | Server to Client | Acknowledges a heartbeat.              |
| `identify`      | Client to Server | Authenticates and starts a session.     |
| `resume`        | Client to Server | Resumes a previous session.            |
| `ready`         | Server to Client | Confirms session is established.        |

### Client-to-Server Messages

Sent by the client to update state or relay data.

| Type               | Purpose                                      |
|--------------------|----------------------------------------------|
| `voice_state_update` | Update mute, deaf, video, streaming state. |
| `presence_update`    | Set online status and activity.            |
| `typing`             | Signal typing in a feed or DM.             |
| `mls_relay`          | Relay MLS (E2EE) group key messages.       |
| `cpace_relay`        | Relay CPace device-pairing messages.       |
| `voice_codec_neg`    | Negotiate voice/video codec parameters.    |
| `stage_response`     | Accept or decline a stage invite.          |

### Server-to-Client Events

The server dispatches over 60 event types covering messages, members, server
structure, presence, voice, DMs, social graph, E2EE key management, bots, and
notifications. See the [Events Reference](events.md) for the complete list.

## Compression

When the client connects with `compress=zstd`, the server compresses
server-to-client messages using Zstandard (zstd). Client-to-server messages are
always sent uncompressed. If the `compress` query parameter is omitted, no
compression is applied in either direction.
