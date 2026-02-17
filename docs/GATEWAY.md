# VoxProtocol v1: WebSocket Gateway

The gateway provides real-time event delivery over a persistent WebSocket connection.

## 1. Connection

Connect to the gateway URL obtained from `GET /api/v1/gateway`:

```
wss://vox.example.com/gateway?v=1&encoding=json
```

Query parameters:

| Param | Default | Description |
|---|---|---|
| `v` | 1 | Protocol version |
| `encoding` | `json` | Payload encoding |
| `compress` | none | Optional: `zstd` for zstd-compressed payloads |

## 2. Message Format

All gateway messages are JSON objects with a `type` string field:

```json
{
  "type": "message_create",   // message type (string)
  "seq": 42,                  // sequence number (server->client events only)
  "d": { ... }                // payload data
}
```

- **`type`**: Identifies the message. Always present.
- **`seq`**: Monotonically increasing sequence number. Present on server-to-client events (used for resume). Absent on control messages and client-to-server messages.
- **`d`**: Payload data. Structure depends on `type`. May be `null` for types with no payload (e.g. `heartbeat`).

## 3. Message Types

### Control Messages

| Type | Direction | Description |
|---|---|---|
| `hello` | Server -> Client | Sent immediately on connect |
| `heartbeat` | Bidirectional | Keepalive ping |
| `heartbeat_ack` | Server -> Client | Acknowledges heartbeat |
| `identify` | Client -> Server | Authenticate after connecting |
| `resume` | Client -> Server | Resume a dropped connection |
| `ready` | Server -> Client | Successful authentication (carries `seq`) |

### Client-to-Server Messages

| Type | Direction | Description |
|---|---|---|
| `voice_state_update` | Client -> Server | Update own voice state (mute/deaf/video) |
| `presence_update` | Client -> Server | Update own presence status |
| `typing` | Client -> Server | Typing indicator |
| `mls_relay` | Bidirectional | MLS messages (Welcome, Commit, Proposal) |
| `cpace_relay` | Bidirectional | CPace device pairing messages |
| `voice_codec_neg` | Bidirectional | Codec and SVC layer negotiation |
| `stage_response` | Client -> Server | Accept/decline stage request or invite |

### Server-to-Client Events

All events carry a `seq` field for resume tracking.

| Type | Description |
|---|---|
| `message_create` | New message sent |
| `message_update` | Message edited |
| `message_delete` | Message deleted |
| `message_bulk_delete` | Bulk delete |
| `message_reaction_add` | Reaction added |
| `message_reaction_remove` | Reaction removed |
| `message_pin_update` | Pin changed |
| `member_join` | User joined server |
| `member_leave` | User left |
| `member_update` | Nickname changed |
| `member_ban` | User banned |
| `member_unban` | User unbanned |
| `feed_create` | Feed created |
| `feed_update` | Feed modified |
| `feed_delete` | Feed deleted |
| `room_create` | Room created |
| `room_update` | Room modified |
| `room_delete` | Room deleted |
| `category_create` | Category created |
| `category_update` | Category modified |
| `category_delete` | Category deleted |
| `thread_create` | Thread created |
| `thread_update` | Thread modified |
| `thread_delete` | Thread deleted |
| `role_create` | Role created |
| `role_update` | Role modified |
| `role_delete` | Role deleted |
| `role_assign` | Role assigned to user |
| `role_revoke` | Role removed from user |
| `server_update` | Server settings changed |
| `invite_create` | Invite created |
| `invite_delete` | Invite deleted |
| `presence_update` | User presence changed |
| `typing_start` | User started typing |
| `friend_request` | Friend added |
| `friend_remove` | Friend removed |
| `block_add` | User blocked |
| `block_remove` | User unblocked |
| `voice_state_update` | Voice state changed |
| `voice_codec_neg` | Codec negotiation |
| `stage_request` | User requested to speak |
| `stage_invite` | User invited to speak |
| `stage_invite_decline` | User declined stage invite |
| `stage_revoke` | Speaker revoked |
| `stage_topic_update` | Stage topic changed |
| `dm_create` | New DM opened |
| `dm_update` | Group DM updated |
| `dm_recipient_add` | User added to group DM |
| `dm_recipient_remove` | User removed from group DM |
| `dm_read_notify` | Read receipt |
| `mls_welcome` | MLS Welcome message |
| `mls_commit` | MLS Commit message |
| `mls_proposal` | MLS Proposal message |
| `device_list_update` | Device list changed |
| `device_pair_prompt` | Pairing request |
| `cpace_isi` | CPace initiator share |
| `cpace_rsi` | CPace responder share |
| `cpace_confirm` | CPace confirmation |
| `cpace_new_device_key` | Encrypted new device public key |
| `key_reset_notify` | User's key changed |
| `media_token_refresh` | New media token before expiry |
| `sticker_create` | Sticker created |
| `sticker_delete` | Sticker deleted |
| `emoji_create` | Custom emoji created |
| `emoji_delete` | Custom emoji deleted |
| `webhook_create` | Webhook created |
| `webhook_update` | Webhook modified |
| `webhook_delete` | Webhook deleted |
| `bot_commands_update` | Bot commands registered/updated |
| `bot_commands_delete` | Bot commands deregistered |
| `feed_subscribe` | User subscribed to feed |
| `feed_unsubscribe` | User unsubscribed from feed |
| `thread_subscribe` | User subscribed to thread |
| `thread_unsubscribe` | User unsubscribed from thread |
| `permission_override_update` | Permission override set |
| `permission_override_delete` | Permission override removed |
| `user_update` | User profile changed |
| `notification_create` | Targeted notification |
| `interaction_create` | User triggered bot interaction |

## 4. Connection Flow

```
Client                                   Gateway
  |                                         |
  |-- WebSocket connect ------------------->|
  |                                         |
  |<-- {"type": "hello", "d": {            |
  |       "heartbeat_interval": 45000       |
  |     }} --------------------------------|
  |                                         |
  |-- {"type": "identify", "d": {          |
  |       "token": "vox_sess_abc...",       |
  |       "protocol_version": 1,            |
  |       "capabilities": ["voice", "e2ee"] |
  |     }} -------------------------------->|
  |                                         |
  |<-- {"type": "ready", "seq": 1, "d": {  |
  |       "session_id": "sess_123",         |
  |       "user_id": 42,                    |
  |       "server_name": "My Community",    |
  |       "protocol_version": 1,            |
  |       "capabilities": ["voice", "e2ee", |
  |         "federation", "bots"]           |
  |     }} --------------------------------|
  |                                         |
  |  [begin heartbeat loop]                 |
  |  [receive events]                       |
```

## 5. Message Payloads

### hello

Sent by the server immediately on WebSocket connect.

```json
{
  "type": "hello",
  "d": {
    "heartbeat_interval": 45000
  }
}
```

### identify

Sent by the client to authenticate.

```json
{
  "type": "identify",
  "d": {
    "token": "vox_sess_abc123...",
    "protocol_version": 1,
    "capabilities": ["voice", "video", "e2ee", "compress.zstd"]
  }
}
```

| Field | Type | Description |
|---|---|---|
| `token` | string | Session or bot token |
| `protocol_version` | uint32 | Protocol version the client wants to use (must be within the server's min/max range from `GET /gateway`) |
| `capabilities` | string[] | Client capabilities |

If the requested version is outside the server's supported range, the server closes the connection with code 4011 (VERSION_MISMATCH).

Capabilities:

| Capability | Description |
|---|---|
| `voice` | Client supports voice rooms |
| `video` | Client supports video in voice rooms |
| `e2ee` | Client supports end-to-end encryption |
| `federation` | Client supports federation features |
| `bots` | Client is a bot |
| `compress.zstd` | Client supports zstd payload compression |

### ready

Sent by the server after successful identify.

```json
{
  "type": "ready",
  "seq": 1,
  "d": {
    "session_id": "sess_123",
    "user_id": 42,
    "display_name": "Alice",
    "server_name": "My Community",
    "server_icon": "...",
    "server_time": 1700000000,
    "protocol_version": 1,
    "capabilities": ["voice", "e2ee", "federation", "bots", "webhooks", "2fa"]
  }
}
```

The `protocol_version` in `ready` confirms the negotiated version for this session.

### heartbeat / heartbeat_ack

The server sends a `heartbeat_interval` in `hello` (milliseconds). The client MUST send a heartbeat at this interval:

```json
// Client sends
{"type": "heartbeat"}

// Server responds
{"type": "heartbeat_ack"}
```

If the client misses two consecutive heartbeat ACKs, it should reconnect. If the server does not receive a heartbeat within `heartbeat_interval * 1.5`, it may close the connection.

### resume

When the WebSocket drops unexpectedly, the client can resume to avoid missing events:

```json
{
  "type": "resume",
  "d": {
    "token": "vox_sess_abc123...",
    "session_id": "sess_123",
    "last_seq": 42
  }
}
```

If the session is still valid, the server replays all events since `last_seq` and continues normally. If the session has expired, the server sends close code 4009 (SESSION_EXPIRED) and the client must re-identify and use `POST /api/v1/sync` to catch up.

### voice_state_update (client -> server)

```json
{
  "type": "voice_state_update",
  "d": {
    "self_mute": true,
    "self_deaf": false,
    "video": false,
    "streaming": false
  }
}
```

### presence_update (client -> server)

```json
{
  "type": "presence_update",
  "d": {
    "status": "online",
    "custom_status": {
      "text": "Playing chess",
      "emoji": "...",
      "expiry": 1700003600
    },
    "activity": {
      "type": "playing",
      "name": "Chess.com",
      "detail": "Rapid 10+0"
    }
  }
}
```

Status values: `"online"`, `"idle"`, `"dnd"`, `"invisible"`.

Activity types: `"playing"`, `"streaming"`, `"listening"`.

### typing

```json
// Feed typing
{
  "type": "typing",
  "d": {
    "feed_id": 5
  }
}

// DM typing
{
  "type": "typing",
  "d": {
    "dm_id": 1
  }
}
```

Exactly one of `feed_id` or `dm_id` MUST be present. Typing is timeout-based: there is no explicit stop message. Clients SHOULD re-send typing every ~8 seconds while the user continues typing. Recipients SHOULD expire typing indicators after ~10 seconds.

### mls_relay

Used to relay MLS Welcome, Commit, and Proposal messages for E2EE DM sessions. See `E2EE.md` for full protocol details.

```json
{
  "type": "mls_relay",
  "d": {
    "mls_type": "welcome",
    "data": "..."
  }
}
```

MLS types: `"welcome"`, `"commit"`, `"proposal"`.

### cpace_relay

Used during device pairing. See `E2EE.md` for full protocol details.

```json
{
  "type": "cpace_relay",
  "d": {
    "cpace_type": "isi",
    "pair_id": "pair_xyz",
    "data": "..."
  }
}
```

CPace types: `"isi"`, `"rsi"`, `"confirm"`, `"new_device_key"`.

### voice_codec_neg

Sent once per media type. See `MEDIA.md` for codec and SVC details.

```json
{
  "type": "voice_codec_neg",
  "d": {
    "media_type": "video",
    "codec": "av1",
    "spatial_layers": 3,
    "temporal_layers": 2,
    "target_bitrates": [150000, 500000, 2000000],
    "dependency_templates": [...]
  }
}
```

Media types: `"audio"`, `"video"`, `"screen"`.

### stage_response

Accept or decline a stage request or invite:

```json
{
  "type": "stage_response",
  "d": {
    "room_id": 5,
    "response_type": "request_ack",
    "accepted": true
  }
}
```

Response types: `"request_ack"`, `"invite_ack"`. Both use the `"accepted"` field.

## 6. Event Payloads

### Message Events

Message events are used for both feed messages and DM messages. Each event contains exactly one of `feed_id` or `dm_id` to identify the message container. DM message payloads carry an `opaque_blob` field (base64 E2EE ciphertext) instead of cleartext `body`, `embeds`, and `attachments`.

| Event | Key Fields |
|---|---|
| `message_create` | Full ChatMessage object (`feed_id` or `dm_id`) |
| `message_update` | `msg_id`, `feed_id` or `dm_id`, changed fields |
| `message_delete` | `msg_id`, `feed_id` or `dm_id` |
| `message_bulk_delete` | `feed_id`, `msg_ids[]` (feed messages only) |
| `message_reaction_add` | `msg_id`, `user_id`, `emoji` |
| `message_reaction_remove` | `msg_id`, `user_id`, `emoji` |
| `message_pin_update` | `msg_id`, `feed_id`, `pinned` (feed messages only) |

### Member Events

| Event | Key Fields |
|---|---|
| `member_join` | Member object |
| `member_leave` | `user_id` |
| `member_update` | `user_id`, `nickname` |
| `member_ban` | `user_id` |
| `member_unban` | `user_id` |

### Server Structure Events

| Event | Key Fields |
|---|---|
| `feed_create` | FeedInfo object |
| `feed_update` | `feed_id` + changed fields |
| `feed_delete` | `feed_id` |
| `room_create` | RoomInfo object |
| `room_update` | `room_id` + changed fields |
| `room_delete` | `room_id` |
| `category_create` | CategoryInfo object |
| `category_update` | `category_id` + changed fields |
| `category_delete` | `category_id` |
| `thread_create` | ThreadInfo object |
| `thread_update` | `thread_id` + changed fields |
| `thread_delete` | `thread_id` |
| `role_create` | Role object |
| `role_update` | `role_id` + changed fields |
| `role_delete` | `role_id` |
| `role_assign` | `role_id`, `user_id` |
| `role_revoke` | `role_id`, `user_id` |
| `server_update` | Changed fields |
| `invite_create` | Invite object |
| `invite_delete` | `code` |
| `sticker_create` | `sticker_id`, `name`, `creator_id` |
| `sticker_delete` | `sticker_id` |
| `emoji_create` | `emoji_id`, `name`, `creator_id` |
| `emoji_delete` | `emoji_id` |
| `webhook_create` | `webhook_id`, `feed_id`, `name` |
| `webhook_update` | `webhook_id` + changed fields |
| `webhook_delete` | `webhook_id` |
| `permission_override_update` | `space_type`, `space_id`, `target_type`, `target_id`, `allow`, `deny` |
| `permission_override_delete` | `space_type`, `space_id`, `target_type`, `target_id` |
| `feed_subscribe` | `feed_id`, `user_id` |
| `feed_unsubscribe` | `feed_id`, `user_id` |
| `thread_subscribe` | `thread_id`, `user_id` |
| `thread_unsubscribe` | `thread_id`, `user_id` |
| `user_update` | `user_id` + changed fields |

### Presence Events

| Event | Key Fields |
|---|---|
| `presence_update` | `user_id`, `status`, `activity?` |
| `typing_start` | `user_id`, `feed_id` or `dm_id` |

### Voice Events

| Event | Key Fields |
|---|---|
| `voice_state_update` | `room_id`, `members[]` |
| `voice_codec_neg` | Codec parameters |
| `stage_request` | `room_id`, `user_id` |
| `stage_invite` | `room_id`, `user_id` |
| `stage_revoke` | `room_id`, `user_id` |
| `stage_invite_decline` | `room_id`, `user_id` |
| `stage_topic_update` | `room_id`, `topic` |
| `media_token_refresh` | `room_id`, `media_token` |

### DM Events

| Event | Key Fields |
|---|---|
| `dm_create` | DmInfo object |
| `dm_update` | `dm_id` + changed fields |
| `dm_recipient_add` | `dm_id`, `user_id` |
| `dm_recipient_remove` | `dm_id`, `user_id` |
| `dm_read_notify` | `dm_id`, `user_id`, `up_to_msg_id` |

### User Relationship Events

| Event | Key Fields |
|---|---|
| `friend_request` | `user_id`, `target_id` |
| `friend_remove` | `user_id`, `target_id` |
| `block_add` | `user_id`, `target_id` |
| `block_remove` | `user_id`, `target_id` |

### E2E Encryption Events

See `E2EE.md` for protocol details.

| Event | Key Fields |
|---|---|
| `mls_welcome` | `data` (base64) |
| `mls_commit` | `data` (base64) |
| `mls_proposal` | `data` (base64) |
| `device_list_update` | `devices[]` |
| `device_pair_prompt` | `device_name`, `ip`, `location`, `pair_id` |
| `cpace_isi` | `pair_id`, `data` |
| `cpace_rsi` | `pair_id`, `data` |
| `cpace_confirm` | `pair_id`, `data` |
| `cpace_new_device_key` | `pair_id`, `data`, `nonce` |
| `key_reset_notify` | `user_id` |

### Bot Events

| Event | Key Fields |
|---|---|
| `interaction_create` | Interaction object |
| `bot_commands_update` | `bot_id`, `commands[]` |
| `bot_commands_delete` | `bot_id`, `command_names[]` |

### Notification Events

| Event | Key Fields |
|---|---|
| `notification_create` | `type` (mention/reply/reaction/message), `msg_id`, `feed_id`/`dm_id`, `author_id`, `body_preview` |

## 7. Close Codes

| Code | Name | Description | Reconnect? |
|---|---|---|---|
| 4000 | UNKNOWN_ERROR | Unknown error | Yes (resume) |
| 4001 | UNKNOWN_TYPE | Unrecognized message type | No |
| 4002 | DECODE_ERROR | Invalid payload | No |
| 4003 | NOT_AUTHENTICATED | Sent payload before identify | No |
| 4004 | AUTH_FAILED | Invalid token in identify | No |
| 4005 | ALREADY_AUTHENTICATED | Sent identify twice | No |
| 4006 | RATE_LIMITED | Sending too fast | Yes (after delay) |
| 4007 | SESSION_TIMEOUT | Server hasn't received heartbeat | Yes (resume) |
| 4008 | SERVER_RESTART | Server is restarting | Yes (resume) |
| 4009 | SESSION_EXPIRED | Session too old to resume | Yes (re-identify) |
| 4010 | REPLAY_EXHAUSTED | Session valid but replay buffer cannot cover gap | Yes (re-identify + /sync) |
| 4011 | VERSION_MISMATCH | No compatible protocol version | No |

## 8. Compression

When connecting with `compress=zstd`, the server compresses each WebSocket message with zstd before sending. The client must decompress before parsing JSON. Client-to-server messages are not compressed.
