# VoxProtocol HTTP v1: Hybrid REST + WebSocket + Media Protocol

## 1. Design Philosophy

- **One server = one community.** No multi-guild abstraction. You connect to a server, that server IS the community.
- **Trusted server for feeds and rooms.** Server feeds and rooms are not E2E encrypted -- the server can moderate, search, and index.
- **E2EE for DMs.** All direct messages (1:1 and group) use MLS with a per-user shared key. The server relays opaque blobs it cannot read.
- **Federated.** Servers communicate via DNS discovery, mTLS, and signed message relay. Users are identified as `user@domain`. Cross-server DMs, presence, and server joining are fully supported.
- **Hybrid transport.** Standard HTTPS for all CRUD operations, WebSocket for real-time events, QUIC datagrams for media. Each layer uses the transport best suited to its traffic pattern.
- **Developer-friendly.** Standard HTTP/JSON means any language with an HTTP client can build a bot or integration.
- **Progressive complexity.** HTTP-only bots are possible for simple use cases. Add WebSocket for real-time. Add media transport only if you need voice/video.

## 2. Definitions

| Term | Definition |
|---|---|
| **Announcement** | A read-only feed for broadcasts and notifications. |
| **Attachment** | A file uploaded alongside a message. |
| **Bot** | A programmatic client. Gateway bots connect via WebSocket and receive real-time events. HTTP-only bots receive interactions via webhook callback. Both can send messages and register commands via REST. |
| **Category** | An organizational grouping of feeds and rooms within a server. |
| **DM** | A direct message between users (1:1 or group). E2E encrypted. Exists outside the server hierarchy. |
| **Embed** | A rich content preview generated from a URL. |
| **Epoch** | An MLS key generation. All messages within an epoch share the same group key. Epoch changes on membership add/remove. |
| **Federation** | Server-to-server communication enabling cross-server DMs, presence, and server joining. Uses DNS discovery and signed message relay. |
| **Feed** | A persistent text and media space within a server. Variants: forum, announcement. |
| **Forum** | A feed variant where every top-level post creates a thread. |
| **Gateway** | The WebSocket connection (`wss://`) that delivers real-time events (messages, presence, typing, voice signaling, MLS relay). |
| **Home Server** | The server where a user's account lives. Identified by the domain in their address (e.g., `example.com` in `alice@example.com`). |
| **Interaction** | A user action (slash command, button click, menu selection) routed to a bot for handling. |
| **Invite** | A code or link granting access to a server. |
| **Leaf Key** | A user's MLS private key, shared across all their devices. Used to participate in MLS groups. |
| **Member** | A user within a server. |
| **Recovery Passphrase** | A 12-word mnemonic used to recover E2EE keys when all devices are lost. |
| **REST API** | The HTTPS JSON API (`/api/v1/`) for all CRUD operations, authentication, history, search, and file management. |
| **Role** | A named permission group within a server. |
| **Room** | A real-time voice and video space within a server. Variant: stage. |
| **Server** | The infrastructure node and the community it hosts. One server = one community. |
| **Session** | An authenticated connection from a client to a server. |
| **SFU** | Selective Forwarding Unit -- the server's role in voice, forwarding media without mixing. |
| **Slash Command** | A bot-registered command invoked by users with a `/` prefix. Parsed and routed by the server. |
| **Stage** | A room variant with a speaker/audience model. |
| **Thread** | A sub-conversation branching off a message in a feed. |
| **Webhook** | A stateless HTTP endpoint for posting messages to a feed. Cannot receive events or join voice rooms. |

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Client                               │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   REST API   │  │   Gateway    │  │  Media Transport  │  │
│  │  HTTPS JSON  │  │  WebSocket   │  │  QUIC    │  │
│  │  /api/v1/*   │  │  wss://      │  │  UDP datagrams    │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │             │
└─────────┼─────────────────┼────────────────────┼─────────────┘
          │                 │                    │
          ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                        Server                               │
└─────────────────────────────────────────────────────────────┘
```

### Layer Summary

| Layer | Transport | Encoding | Purpose |
|---|---|---|---|
| **REST API** | HTTPS (`/api/v1/`) | JSON | All CRUD, auth, history, search, file upload, management |
| **Gateway** | WebSocket (`wss://`) | JSON | Real-time events, presence, typing, voice signaling, MLS relay |
| **Media** | QUIC datagrams | Binary | Voice/video/screen share |

### When to Use Each Layer

| Operation | Layer | Reason |
|---|---|---|
| Create/read/update/delete resources | REST | Standard request/response |
| Authentication and login | REST | One-time operation |
| Message history and search | REST | Paginated query |
| File upload/download | REST | Multipart HTTP, resumable |
| Receive new messages in real time | Gateway | Server pushes events as they happen |
| Presence and typing indicators | Gateway | High frequency, low latency |
| Voice/video signaling | Gateway | Real-time state changes |
| MLS key exchange relay | Gateway | Real-time relay between devices |
| Voice/video/screen media | Media | Ultra-low latency, unreliable delivery OK |

> **REST API Reference:** See `API.md` for the complete REST API endpoint documentation (authentication, CRUD operations, file management, etc.).

## 4. WebSocket Gateway Protocol

The gateway provides real-time event delivery over a persistent WebSocket connection.

### Connection

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

### Message Format

All gateway messages are JSON objects with the following structure:

```json
{
  "op": 0,       // opcode (integer)
  "t": "EVENT",  // event name (string, only for op 0 DISPATCH)
  "s": 42,       // sequence number (integer, only for op 0 DISPATCH)
  "d": { ... }   // event data (object)
}
```

### Opcodes

| Opcode | Name | Direction | Description |
|---|---|---|---|
| 0 | DISPATCH | Server → Client | Real-time event with sequence number |
| 1 | HEARTBEAT | Bidirectional | Keepalive ping |
| 2 | IDENTIFY | Client → Server | Authenticate after connecting |
| 3 | RESUME | Client → Server | Resume a dropped connection |
| 4 | HELLO | Server → Client | Sent immediately on connect |
| 5 | HEARTBEAT_ACK | Server → Client | Acknowledges heartbeat |
| 6 | VOICE_STATE_UPDATE | Client → Server | Update own voice state (mute/deaf/video) |
| 7 | PRESENCE_UPDATE | Client → Server | Update own presence status |
| 8 | TYPING | Client → Server | Typing indicator |
| 9 | MLS_RELAY | Bidirectional | MLS messages (Welcome, Commit, Proposal) |
| 10 | CPACE_RELAY | Bidirectional | CPace device pairing messages |
| 11 | VOICE_CODEC_NEG | Bidirectional | Codec and SVC layer negotiation |
| 12 | STAGE_RESPONSE | Client → Server | Accept/decline stage request or invite |

### Connection Flow

```
Client                                   Gateway
  |                                         |
  |-- WebSocket connect ------------------->|
  |                                         |
  |<-- op 4 HELLO {                        |
  |      heartbeat_interval: 45000          |
  |    } -----------------------------------|
  |                                         |
  |-- op 2 IDENTIFY {                      |
  |      token: "vox_sess_abc...",          |
  |      capabilities: ["voice", "e2ee"]   |
  |    } ---------------------------------->|
  |                                         |
  |<-- op 0 DISPATCH t=READY {             |
  |      session_id: "sess_123",            |
  |      user_id: 42,                       |
  |      server_name: "My Community",       |
  |      server_icon: "...",                |
  |      capabilities: ["voice", "e2ee",   |
  |        "federation", "bots"]            |
  |    } -----------------------------------|
  |                                         |
  |  [begin heartbeat loop]                 |
  |  [receive dispatch events]              |
```

### IDENTIFY Payload

```json
{
  "op": 2,
  "d": {
    "token": "vox_sess_abc123...",
    "capabilities": ["voice", "video", "e2ee", "compress.zstd"]
  }
}
```

Capabilities:

| Capability | Description |
|---|---|
| `voice` | Client supports voice rooms |
| `video` | Client supports video in voice rooms |
| `e2ee` | Client supports end-to-end encryption |
| `federation` | Client supports federation features |
| `bots` | Client is a bot |
| `compress.zstd` | Client supports zstd payload compression |

### READY Event

Dispatched after successful IDENTIFY:

```json
{
  "op": 0,
  "t": "READY",
  "s": 1,
  "d": {
    "session_id": "sess_123",
    "user_id": 42,
    "display_name": "Alice",
    "server_name": "My Community",
    "server_icon": "...",
    "server_time": 1700000000,
    "capabilities": ["voice", "e2ee", "federation", "bots", "webhooks", "2fa"]
  }
}
```

### Heartbeat

The server sends a `heartbeat_interval` in HELLO (milliseconds). The client MUST send a heartbeat at this interval:

```json
// Client sends
{"op": 1, "d": null}

// Server responds
{"op": 5, "d": null}
```

If the client misses two consecutive heartbeat ACKs, it should reconnect. If the server does not receive a heartbeat within `heartbeat_interval * 1.5`, it may close the connection.

### Resume

When the WebSocket drops unexpectedly, the client can resume to avoid missing events:

```json
{
  "op": 3,
  "d": {
    "token": "vox_sess_abc123...",
    "session_id": "sess_123",
    "last_sequence": 42
  }
}
```

If the session is still valid, the server replays all events since `last_sequence` and continues normally. If the session has expired, the server sends close code 4009 (SESSION_EXPIRED) and the client must re-IDENTIFY and use `POST /api/v1/sync` to catch up.

### Client-to-Server Opcodes

#### Voice State Update (op 6)

```json
{
  "op": 6,
  "d": {
    "self_mute": true,
    "self_deaf": false,
    "video": false,
    "streaming": false
  }
}
```

#### Presence Update (op 7)

```json
{
  "op": 7,
  "d": {
    "status": "online",             // "online" | "idle" | "dnd" | "invisible"
    "custom_status": {              // optional
      "text": "Playing chess",
      "emoji": "♟️",
      "expiry": 1700003600
    },
    "activity": {                   // optional
      "type": "playing",            // "playing" | "streaming" | "listening"
      "name": "Chess.com",
      "detail": "Rapid 10+0"
    }
  }
}
```

#### Typing (op 8)

```json
{
  "op": 8,
  "d": {
    "feed_id": 5
  }
}
```

Typing is timeout-based: there is no explicit stop message. Clients SHOULD re-send typing every ~8 seconds while the user continues typing. Recipients SHOULD expire typing indicators after ~10 seconds.

#### MLS Relay (op 9)

Used to relay MLS Welcome, Commit, and Proposal messages for E2EE DM sessions:

```json
{
  "op": 9,
  "d": {
    "type": "welcome",    // "welcome" | "commit" | "proposal"
    "data": "..."          // base64 MLS message
  }
}
```

#### CPace Relay (op 10)

Used during device pairing:

```json
{
  "op": 10,
  "d": {
    "type": "isi",         // "isi" | "rsi" | "confirm" | "leaf_transfer"
    "pair_id": "pair_xyz",
    "data": "..."          // base64
  }
}
```

#### Voice Codec Negotiation (op 11)

```json
{
  "op": 11,
  "d": {
    "codec": "opus",       // "opus" | "av1" | "av1_screen"
    "spatial_layers": 3,
    "temporal_layers": 2,
    "target_bitrates": [150000, 500000, 2000000],
    "dependency_templates": [...]
  }
}
```

#### Stage Response (op 12)

Accept or decline a stage request or invite:

```json
{
  "op": 12,
  "d": {
    "room_id": 5,
    "type": "request_ack",    // "request_ack" | "invite_ack"
    "approved": true           // or "accepted": true for invite_ack
  }
}
```

### Dispatch Events

All dispatch events use opcode 0 with an event name (`t`) and sequence number (`s`). The `d` field contains event-specific data.

#### Message Events

| Event | Description | Key Fields |
|---|---|---|
| `MESSAGE_CREATE` | New message sent | Full ChatMessage object |
| `MESSAGE_UPDATE` | Message edited | `msg_id`, `body`, `edit_timestamp` |
| `MESSAGE_DELETE` | Message deleted | `msg_id`, `feed_id` |
| `MESSAGE_BULK_DELETE` | Bulk delete | `feed_id`, `msg_ids[]` |
| `MESSAGE_REACTION_ADD` | Reaction added | `msg_id`, `user_id`, `emoji` |
| `MESSAGE_REACTION_REMOVE` | Reaction removed | `msg_id`, `user_id`, `emoji` |
| `MESSAGE_PIN_UPDATE` | Pin changed | `msg_id`, `feed_id`, `pinned` |

#### Member Events

| Event | Description | Key Fields |
|---|---|---|
| `MEMBER_JOIN` | User joined server | Member object |
| `MEMBER_LEAVE` | User left | `user_id` |
| `MEMBER_UPDATE` | Nickname changed | `user_id`, `nickname` |
| `MEMBER_BAN` | User banned | `user_id` |
| `MEMBER_UNBAN` | User unbanned | `user_id` |

#### Server Structure Events

| Event | Description | Key Fields |
|---|---|---|
| `FEED_CREATE` | Feed created | FeedInfo object |
| `FEED_UPDATE` | Feed modified | `feed_id` + changed fields |
| `FEED_DELETE` | Feed deleted | `feed_id` |
| `ROOM_CREATE` | Room created | RoomInfo object |
| `ROOM_UPDATE` | Room modified | `room_id` + changed fields |
| `ROOM_DELETE` | Room deleted | `room_id` |
| `CATEGORY_CREATE` | Category created | CategoryInfo object |
| `CATEGORY_UPDATE` | Category modified | `category_id` + changed fields |
| `CATEGORY_DELETE` | Category deleted | `category_id` |
| `THREAD_CREATE` | Thread created | ThreadInfo object |
| `THREAD_UPDATE` | Thread modified | `thread_id` + changed fields |
| `THREAD_DELETE` | Thread deleted | `thread_id` |
| `ROLE_CREATE` | Role created | Role object |
| `ROLE_UPDATE` | Role modified | `role_id` + changed fields |
| `ROLE_DELETE` | Role deleted | `role_id` |
| `SERVER_UPDATE` | Server settings changed | Changed fields |
| `INVITE_CREATE` | Invite created | Invite object |
| `INVITE_DELETE` | Invite deleted | `code` |

#### Presence Events

| Event | Description | Key Fields |
|---|---|---|
| `PRESENCE_UPDATE` | User presence changed | `user_id`, `status`, `activity?` |
| `TYPING_START` | User started typing | `user_id`, `feed_id` |

#### Voice Events

| Event | Description | Key Fields |
|---|---|---|
| `VOICE_STATE_UPDATE` | Voice state changed | `room_id`, `members[]` |
| `VOICE_CODEC_NEGOTIATION` | Codec negotiation | Codec parameters |
| `STAGE_REQUEST` | User requested to speak | `room_id`, `user_id` |
| `STAGE_INVITE` | User invited to speak | `room_id`, `user_id` |
| `STAGE_REVOKE` | Speaker revoked | `room_id`, `user_id` |
| `STAGE_TOPIC_UPDATE` | Stage topic changed | `room_id`, `topic` |

#### DM Events

| Event | Description | Key Fields |
|---|---|---|
| `DM_CREATE` | New DM opened | DmInfo object |
| `DM_UPDATE` | Group DM updated | `dm_id` + changed fields |
| `DM_RECIPIENT_ADD` | User added to group DM | `dm_id`, `user_id` |
| `DM_RECIPIENT_REMOVE` | User removed from group DM | `dm_id`, `user_id` |
| `DM_READ_NOTIFY` | Read receipt | `dm_id`, `user_id`, `up_to_msg_id` |

#### E2E Encryption Events

| Event | Description | Key Fields |
|---|---|---|
| `MLS_WELCOME` | MLS Welcome message | `data` (base64) |
| `MLS_COMMIT` | MLS Commit message | `data` (base64) |
| `MLS_PROPOSAL` | MLS Proposal message | `data` (base64) |
| `DEVICE_LIST_UPDATE` | Device list changed | `devices[]` |
| `DEVICE_PAIR_PROMPT` | Pairing request | `device_name`, `ip`, `location`, `pair_id` |
| `CPACE_ISI` | CPace initiator share | `pair_id`, `data` |
| `CPACE_RSI` | CPace responder share | `pair_id`, `data` |
| `CPACE_CONFIRM` | CPace confirmation | `pair_id`, `data` |
| `CPACE_LEAF_TRANSFER` | Encrypted leaf key | `pair_id`, `data`, `nonce` |
| `KEY_RESET_NOTIFY` | User's key changed | `user_id` |

#### Bot Events

| Event | Description | Key Fields |
|---|---|---|
| `INTERACTION_CREATE` | User triggered interaction | Interaction object |

### Gateway Close Codes

| Code | Name | Description | Reconnect? |
|---|---|---|---|
| 4000 | UNKNOWN_ERROR | Unknown error | Yes (resume) |
| 4001 | UNKNOWN_OPCODE | Invalid opcode sent | No |
| 4002 | DECODE_ERROR | Invalid payload | No |
| 4003 | NOT_AUTHENTICATED | Sent payload before IDENTIFY | No |
| 4004 | AUTH_FAILED | Invalid token in IDENTIFY | No |
| 4005 | ALREADY_AUTHENTICATED | Sent IDENTIFY twice | No |
| 4006 | RATE_LIMITED | Sending too fast | Yes (after delay) |
| 4007 | SESSION_TIMEOUT | Server hasn't received heartbeat | Yes (resume) |
| 4008 | SERVER_RESTART | Server is restarting | Yes (resume) |
| 4009 | SESSION_EXPIRED | Session too old to resume | Yes (re-IDENTIFY) |

### Compression

When connecting with `compress=zstd`, the server compresses each WebSocket message with zstd before sending. The client must decompress before parsing JSON. Client-to-server messages are not compressed.

## 5. Media Transport

Media frames (voice, video, screen share) use a dedicated binary transport over QUIC datagrams or WebRTC, separate from the REST and gateway connections. Media requires ultra-low latency unreliable delivery that HTTP and WebSocket cannot provide.

### Connecting to Media

After joining a voice room via `POST /api/v1/rooms/{room_id}/voice/join`, the response includes:

```json
{
  "media_url": "quic://vox.example.com:4443",
  "media_token": "media_token_abc..."
}
```

The client opens a separate QUIC connection (or WebRTC session) to the media endpoint and authenticates with the media token. Media frames are then sent/received as QUIC datagrams.

### Media Frame Header

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Version (8)  |  Type (8)     |  Codec ID (8) |   Flags (8)   |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Room ID (32)                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       User ID (32)                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Sequence (32)                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Timestamp RTP (32)                         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Spatial ID (4)| Temporal ID(4)| DTX (1)|    Reserved (7)      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|       Dependency Descriptor (variable, 0-32 bytes)         ..|
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Payload (variable)                        ..|
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

Fixed media header: 22 bytes + dependency descriptor
```

Flags: `[KEYFRAME, END_OF_FRAME, FEC, MARKER, HAS_DEP_DESC, RSV, RSV, RSV]` -- 3 reserved bits

- **MARKER**: last packet of a video frame
- **HAS_DEP_DESC**: dependency descriptor is present (always true for video/screen, false for audio)

### Media Types

| Type | Value | Description |
|---|---|---|
| AUDIO | 0x00 | Audio frame |
| VIDEO | 0x01 | Video frame |
| SCREEN | 0x02 | Screen share frame |
| FEC | 0x03 | Forward error correction (reserved) |
| RTCP_FB | 0x04 | TWCC feedback report |

### Codec IDs

| ID | Codec | Use |
|---|---|---|
| 0x00 | None | Reserved (unset) |
| 0x01 | Opus | Voice |
| 0x02 | AV1 | Video |
| 0x03 | AV1 screen profile | Screen share |
| 0x04-0xFF | [reserved] | |

### Scalable Video Coding (SVC)

Video and screen share use AV1 SVC (Scalable Video Coding). The sender encodes a single stream with embedded spatial and temporal layers. The SFU strips layers based on each receiver's available bandwidth.

#### Layer Structure

| Layer Type | IDs | Purpose |
|---|---|---|
| Spatial | S0, S1, S2 | Resolution tiers (e.g., 180p, 360p, 720p) |
| Temporal | T0, T1 | Frame rate tiers (e.g., 15fps base, 30fps full) |

Example configuration for video (actual values are negotiated via the VOICE_CODEC_NEG gateway opcode):

```
S2 (720p)  ─── T0 (15fps) ─── T1 (30fps)     ~2 Mbps total
S1 (360p)  ─── T0 (15fps) ─── T1 (30fps)     ~500 kbps total
S0 (180p)  ─── T0 (15fps) ─── T1 (30fps)     ~150 kbps total
```

Example configuration for screen share:

```
S1 (1080p) ─── T0 (5fps)  ─── T1 (15fps)     ~4 Mbps total
S0 (540p)  ─── T0 (5fps)  ─── T1 (15fps)     ~1 Mbps total
```

#### Dependency Descriptor

The Dependency Descriptor is a codec-agnostic metadata structure attached to video/screen media packets. It describes the layer dependency graph so the SFU can strip layers without parsing the AV1 bitstream.

Fields:
- `start_of_frame`: is this the first packet of a frame
- `end_of_frame`: is this the last packet of a frame
- `template_id`: references a pre-negotiated frame dependency template
- `frame_number`: frame counter within the stream
- `frame_dependencies`: which previous frames this frame depends on
- `decode_target_indications`: which quality targets this frame contributes to
- `chain_diffs`: chain-based dependency signaling for efficient layer switching

The dependency descriptor is negotiated during VOICE_CODEC_NEG (gateway opcode 11) and sent on every video/screen packet when the HAS_DEP_DESC flag is set.

#### SFU Layer Forwarding

The SFU reads the dependency descriptor (not the AV1 bitstream) to make forwarding decisions:

```
Sender                          SFU                         Receivers
  |                               |                            |
  |== S0+S1+S2 video stream ====>|                            |
  |   (all layers, ~2.5 Mbps)    |                            |
  |                               |  [read dependency desc]    |
  |                               |  [check receiver bandwidth]|
  |                               |                            |
  |                               |== S0+S1+S2 ==> Receiver A (good bw)
  |                               |== S0+S1    ==> Receiver B (medium bw)
  |                               |== S0       ==> Receiver C (poor bw)
```

The SFU never decodes or re-encodes video. It only reads metadata and drops packets whose spatial/temporal ID exceeds the target for a given receiver.

#### Layer Switching

When a receiver's bandwidth changes, the SFU can:
- **Drop to lower spatial layer**: requires waiting for a keyframe on the lower layer, or using chain-based switching if the dependency structure allows it
- **Drop temporal layers**: can happen immediately (temporal layers are independently decodable)
- **Add higher layers**: immediate if packets are available

### DTX (Discontinuous Transmission)

Opus supports DTX -- sending no packets during silence. In a room with 10 people where 2 are speaking, the other 8 send no audio packets. The DTX flag in the media header signals that the sender is in DTX mode. Receivers should generate comfort noise locally during DTX periods to avoid perceived dead silence.

### Voice Room Flow

```
User A              REST API        Gateway            SFU (Media)         User B, C
  |                    |               |                   |                   |
  |-- POST /rooms/     |               |                   |                   |
  |   {id}/voice/join->|               |                   |                   |
  |<-- {media_url,     |               |                   |                   |
  |     media_token,   |               |                   |                   |
  |     members[]} ----|               |                   |                   |
  |                    |               |                   |                   |
  |                    |  VOICE_STATE_UPDATE (A joined) -->|                   |
  |                    |               |---dispatch------->|                   |
  |                    |               |---dispatch--------|------------------>|
  |                    |               |                   |                   |
  |== QUIC connect to media_url =====>|==================>|                   |
  |                    |               |                   |                   |
  |-- op 11 VOICE_CODEC_NEG --------->|                   |                   |
  |<-- op 11 VOICE_CODEC_NEG ---------|                   |                   |
  |                    |               |                   |                   |
  |== MEDIA_AUDIO =======================================>|== forward ======>|
  |== MEDIA_VIDEO (S0+S1+S2) ============================>|== S0+S1+S2 => B  |
  |                    |               |                   |== S0 =======> C   |
  |                    |               |                   |                   |
  |-- POST /rooms/     |               |                   |                   |
  |   {id}/voice/leave>|               |                   |                   |
  |                    |  VOICE_STATE_UPDATE (A left) ---->|                   |
```

### Congestion Control (TWCC)

VoxProtocol uses Transport-Wide Congestion Control. Instead of aggregate statistics, receivers report per-packet arrival times. Both the SFU and senders run bandwidth estimation independently.

#### Feedback Flow

```
Sender =============> SFU =============> Receiver
  |                    |                    |
  |  (sends all SVC    |  (forwards layers  |
  |   layers)          |   per receiver)    |
  |                    |                    |
  |<-- MEDIA_RTCP_FB --|<-- MEDIA_RTCP_FB --|
  |   (uplink TWCC)    |  (downlink TWCC)   |
  |                    |                    |
  | [sender runs GCC,  | [SFU runs GCC per  |
  |  adjusts encoder]  |  receiver, adjusts |
  |                    |  layer forwarding] |
```

**Downlink path (Receiver → SFU):** Receiver sends TWCC reports about packets received from the SFU. The SFU runs a bandwidth estimator per receiver and adjusts which SVC layers to forward.

**Uplink path (SFU → Sender):** The SFU sends TWCC reports about packets received from the sender. The sender runs its own bandwidth estimator and adjusts encoder quality (bitrate, resolution, frame rate) if uplink is constrained.

#### TWCC Report Format

Sent via MEDIA_RTCP_FB:

| Field | Size | Description |
|---|---|---|
| base_sequence | 32 bits | First packet sequence number in this report |
| packet_count | 32 bits | Number of packets covered |
| reference_time | 32 bits | Base receive time (64ms resolution) |
| packet_statuses | variable | Bitmap: received / not received / received-with-delta for each packet |
| recv_deltas | variable | Inter-arrival time deltas for received packets (250us or 1ms resolution) |

This is modeled on the IETF RTCP Transport-Wide CC feedback format. The sender/SFU uses inter-arrival deltas to detect congestion (increasing delays = congestion, stable = clear).

#### Bandwidth Estimation

Implementations use TWCC reports to perform bandwidth estimation and adjust encoding/forwarding accordingly. The choice of algorithm is implementation-defined. One common approach is GCC (Google Congestion Control), which uses inter-arrival delay variation to detect congestion and adjusts bitrate via an AIMD (additive increase, multiplicative decrease) scheme.

#### SFU Layer Selection

The SFU maps estimated bandwidth per receiver to SVC layers. The specific thresholds are implementation-defined. Example mapping:

```
Estimated BW    Forwarded Layers          Approx Quality
> 2 Mbps        S2+T1 (720p/30fps)        Full
> 800 kbps      S1+T1 (360p/30fps)        Medium
> 300 kbps      S1+T0 (360p/15fps)        Medium-Low
> 150 kbps      S0+T1 (180p/30fps)        Low
< 150 kbps      S0+T0 (180p/15fps)        Minimum
```

Layer switches happen at dependency descriptor chain boundaries to avoid decoding artifacts.

#### Additional Feedback Signals

Beyond TWCC, MEDIA_RTCP_FB also carries:

| Signal | Purpose |
|---|---|
| NACK | Request retransmission of specific sequence numbers (video only, selective) |
| PLI (Picture Loss Indication) | Request new keyframe from sender |

## 6. Server Hierarchy

```
Server (the machine IS the community)
+-- Settings (name, icon, description, max_members)
+-- Roles[]
+-- Custom Emoji[]
+-- Members[]
|
+-- Category: "General"
|   +-- #welcome        (text feed, read-only)
|   +-- #general        (text feed)
|   +-- #off-topic      (text feed)
|
+-- Category: "Voice"
|   +-- Lounge           (voice room)
|   +-- Gaming           (voice room)
|   +-- Town Hall        (stage room)
|
+-- Category: "Projects"
|   +-- #frontend       (text feed)
|   +-- #bugs           (forum feed)
|
+-- [uncategorized feeds/rooms]
```

## 7. Permissions

64-bit bitfield:

```
Bit  Permission               Scope
---  ---------------------    -----
 0   VIEW_SPACE               Feed/Room
 1   SEND_MESSAGES            Feed
 2   SEND_EMBEDS              Feed
 3   ATTACH_FILES             Feed
 4   ADD_REACTIONS            Feed
 5   READ_HISTORY             Feed/Room
 6   MENTION_EVERYONE         Feed
 7   USE_EXTERNAL_EMOJI       Feed
 8   CONNECT                  Room
 9   SPEAK                    Room
10   VIDEO                    Room (webcam)
11   MUTE_MEMBERS             Room
12   DEAFEN_MEMBERS           Room
13   MOVE_MEMBERS             Room
14   PRIORITY_SPEAKER         Room
15   STREAM                   Room (screen share)
16   STAGE_MODERATOR          Room (stage)
17   CREATE_THREADS           Feed
18   MANAGE_THREADS           Feed
19   SEND_IN_THREADS          Feed

24   MANAGE_SPACES            Server
25   MANAGE_ROLES             Server
26   MANAGE_EMOJI             Server
27   MANAGE_WEBHOOKS          Server
28   MANAGE_SERVER            Server (settings, icon, name)
29   KICK_MEMBERS             Server
30   BAN_MEMBERS              Server
31   CREATE_INVITES           Server
32   CHANGE_NICKNAME          Server
33   MANAGE_NICKNAMES         Server
34   VIEW_AUDIT_LOG           Server
35   MANAGE_MESSAGES          Server (delete others messages)
36   VIEW_REPORTS             Server (can view and manage DM reports)
37   MANAGE_2FA               Server (reset user 2FA enrollment)

63   ADMINISTRATOR            Server (bypasses all)

20-23  [reserved for future user-level permissions -- must be 0]
38-62  [reserved -- must be 0]
```

### Resolution Order

```
1. @everyone base permissions
2. OR together all of user's role permissions
3. Apply feed/room @everyone overrides (allow/deny)
4. Apply feed/room role overrides (OR allow, OR deny)
5. Apply feed/room user-specific override
6. Administrator bypasses everything
```

## 8. E2E Encryption

All DMs (1:1 and group) use MLS (Message Layer Security, RFC 9420). Server feeds and rooms remain trusted and are not E2E encrypted.

### Why MLS for Everything

MLS uses epoch-based keys. Within an epoch, all group members share a symmetric key. This solves multi-device naturally -- all of a user's devices share the same MLS leaf private key and can decrypt any message in the current epoch without per-message state synchronization.

| Property | Benefit |
|---|---|
| Epoch-based keys | No per-message ratchet sync between devices |
| Same protocol for 1:1 and group | One code path to implement and audit |
| Forward secrecy at epoch boundaries | Compromised key cannot decrypt past epochs |
| Efficient add/remove | Tree-based key agreement scales to group DMs |

### MLS DM Flow

Key management (prekey upload/fetch, device management, backup) uses the REST API. Real-time MLS message relay (Welcome, Commit, Proposal) uses the gateway.

```
Alice                    REST API       Gateway                   Bob (+ others)
  |                         |              |                          |
  |-- GET /keys/prekeys/bob>|              |                          |
  |<-- {prekey bundle} -----|              |                          |
  |                         |              |                          |
  |  [Create MLS group,     |              |                          |
  |   generate GroupInfo,   |              |                          |
  |   create Welcome for Bob]              |                          |
  |                         |              |                          |
  |-- op 9 MLS_RELAY {commit} ----------->|-- dispatch MLS_COMMIT -->|
  |-- op 9 MLS_RELAY {welcome, bob} ----->|-- dispatch MLS_WELCOME ->|
  |                         |              |                          |
  |  [Both now share epoch key]            |  [Bob processes Welcome, |
  |                         |              |   derives epoch key]     |
  |                         |              |                          |
  |-- POST /feeds/{dm}/messages --------  |                          |
  |   {body: ciphertext}    |              |                          |
  |                         |  MESSAGE_CREATE dispatch (opaque) ----->|
```

### Multi-Device: Shared Leaf Key

Each user has ONE MLS leaf key shared across all their devices. Adding a new device means transferring this key securely.

```
User
+-- MLS leaf keypair (shared)
+-- Device: laptop  (has leaf key)
+-- Device: phone   (has leaf key)
+-- Device: tablet  (has leaf key)
```

### Device Pairing: CPace Method

The primary method when the user has an existing device. Uses CPace (RFC 9497), a password-authenticated key exchange, to bind a user-entered short code into the key derivation. This prevents the server from performing a MITM attack.

**CPace Parameters:**

| Parameter | Value |
|---|---|
| Group | ristretto255 |
| Hash | SHA-512 |
| Code | 6 decimal digits |
| Key derivation | HKDF-SHA256, info="vox-cpace-session", salt=pair_id |
| Confirmation | HMAC-SHA256(sk, side \|\| pair_id) |
| Encryption | AES-256-GCM |
| Timeout | 5 minutes |

```
New Device           REST API      Gateway               Existing Device
  |                     |             |                        |
  |-- POST /auth/login->|             |                        |
  |<-- {token} ---------|             |                        |
  |                     |             |                        |
  |-- POST /keys/       |             |                        |
  |   devices/pair ---->|             |                        |
  |<-- {pair_id} -------|             |                        |
  |                     |             |                        |
  |                     |  DEVICE_PAIR_PROMPT dispatch ------->|
  |                     |             |   {device_name,        |
  |                     |             |    ip, location,       |
  |                     |             |    pair_id}            |
  |                     |             |                        |
  |                     |             |   [existing device     |
  |                     |             |    displays 6-digit    |
  |                     |             |    code, user approves]|
  |                     |             |                        |
  |                     |  POST /keys/devices/pair/{id}/respond|
  |                     |<----- {approved: true} --------------|
  |                     |             |                        |
  |  [user enters 6-digit code]      |                        |
  |                     |             |                        |
  |  === CPace key exchange (via gateway) ===                  |
  |                     |             |                        |
  |-- op 10 CPACE_RELAY {isi} ------>|-- CPACE_ISI dispatch ->|
  |                     |             |                        |
  |                     |             |<-- op 10 CPACE_RELAY --|
  |<-- CPACE_RSI dispatch ------------|     {rsi}              |
  |                     |             |                        |
  |  [both derive shared key]        |  [both derive key]     |
  |                     |             |                        |
  |-- op 10 {confirm} -------------->|-- dispatch ----------->|
  |<-- dispatch ----------------------|<-- op 10 {confirm} ---|
  |                     |             |                        |
  |  [verify confirmation]           |  [verify confirmation] |
  |                     |             |                        |
  |<-- dispatch ----------------------|<-- op 10 {leaf_transfer}|
  |   {encrypted_leaf_key, nonce}    |                        |
  |                     |             |                        |
  |  [decrypt with cpace_key]        |                        |
  |  [now has MLS leaf key]          |                        |
  |                     |             |                        |
  |-- POST /keys/devices ----------->|                        |
  |-- PUT /keys/prekeys ------------>|  DEVICE_LIST_UPDATE -->|
```

The server relays all CPace messages but cannot derive the session key because it does not know the 6-digit code displayed on the existing device.

If denied, the server SHOULD flag the session and MAY lock the account for review.

### Device Pairing: QR Code Method

Alternative when push is unavailable:

```
New Device                                            Existing Device
  |                                                          |
  |  [generate temp keypair]                                 |
  |  [display QR: {temp_public_key, device_id}]              |
  |                                                          |
  |  <-------- user scans QR with existing device -------->  |
  |                                                          |
  |                              [encrypt MLS leaf key with  |
  |                               temp_public_key]           |
  |                                                          |
  |  <-------- encrypted blob relayed via gateway --------   |
  |                                                          |
  |  [decrypt, now has MLS leaf key]                         |
```

### Recovery: All Devices Lost

Two gates protect recovery:

| Gate | Proves | Mechanism |
|---|---|---|
| Authentication | "I am this user" | Username + password |
| Recovery passphrase | "I should have this user's keys" | Decrypts server-stored blob |

Setup (at account creation). Clients MUST use the following procedure to ensure cross-client recovery interoperability:

1. Generate 12-word recovery passphrase (BIP39 mnemonic)
2. Derive encryption key: K = Argon2(passphrase, user_id_salt)
3. Encrypt MLS leaf private key with K
4. Upload encrypted blob via `PUT /api/v1/keys/backup`
5. User stores the 12 words securely

Recovery flow:

```
New Device                REST API
  |                          |
  |-- POST /auth/login ----->|  (gate 1: proves identity)
  |<-- {token} --------------|
  |                          |
  |-- GET /keys/backup ----->|
  |<-- {encrypted_blob} -----|
  |                          |
  |  [user enters recovery   |
  |   phrase]                |
  |  [K = Argon2(phrase,     |
  |   salt)]                 |
  |  [decrypt blob -> leaf   |
  |   key]                   |  (gate 2: proves key ownership)
  |                          |
  |-- POST /keys/devices --->|
  |-- PUT /keys/prekeys ---->|
```

### Key Reset (no recovery possible)

If a user has lost all devices AND forgotten their recovery passphrase:

1. User authenticates and calls `POST /api/v1/keys/reset`
2. Server dispatches `KEY_RESET_NOTIFY` to all DM contacts via gateway
3. Contacts see: "Alice's security key has changed"
4. All existing MLS group states with Alice are invalidated
5. New DM sessions must be re-established
6. Old encrypted message history is unreadable

### Safety Numbers

Users can verify each other's identity keys out-of-band. Clients MUST compute safety numbers as follows:

```
fingerprint = SHA-256(sort(alice_identity_key, bob_identity_key))

Displayed as 12 groups of 5 digits:
  37281 48103 59274 10384
  92847 38291 04827 19384
  28471 93827 48291 03847

Or as a QR code encoding both identity keys.
```

Safety numbers change when a user does KEY_RESET. Contacts are warned.

### Federated Key Exchange

For cross-server DMs, servers relay prekey requests transparently. Clients see the same REST endpoints and gateway events regardless of whether the recipient is local or federated.

## 9. Connection Lifecycle

### Full Client Startup

```
Client                  REST API         Gateway          Media (SFU)
  |                        |                |                  |
  |  1. Authenticate       |                |                  |
  |-- POST /auth/login --->|                |                  |
  |<-- {token, user_id} ---|                |                  |
  |                        |                |                  |
  |  2. Get gateway URL    |                |                  |
  |-- GET /gateway -------->|                |                  |
  |<-- {url, media_url} ---|                |                  |
  |                        |                |                  |
  |  3. Connect gateway    |                |                  |
  |-- WebSocket connect ----|--------------->|                  |
  |<-- HELLO {interval} ---|----------------|                  |
  |-- IDENTIFY {token} ----|--------------->|                  |
  |<-- READY {session_id} -|----------------|                  |
  |                        |                |                  |
  |  4. Fetch initial state|                |                  |
  |-- GET /server/layout -->|                |                  |
  |<-- {categories, feeds, rooms} -------   |                  |
  |-- GET /members -------->|                |                  |
  |                        |                |                  |
  |  5. Fetch message history (per feed)    |                  |
  |-- GET /feeds/{id}/messages ------------>|                  |
  |                        |                |                  |
  |  6. (Optional) Join voice              |                  |
  |-- POST /rooms/{id}/voice/join -------->|                  |
  |<-- {media_url, media_token, members[]} |                  |
  |-- QUIC connect to media_url ------------|----------------->|
  |                        |                |                  |
  |  [Normal operation: REST for actions, gateway for events]  |
```

### Reconnect

When the gateway connection drops:

```
Client                   Gateway
  |                         |
  |  [WebSocket dropped]    |
  |                         |
  |-- WebSocket reconnect ->|
  |<-- HELLO {interval} ----|
  |-- RESUME {              |
  |     session_id,         |
  |     last_sequence       |
  |   } ------------------>|
  |                         |
  |  [If session valid:]    |
  |<-- missed events -------|
  |<-- DISPATCH (continue) -|
  |                         |
  |  [If session expired:]  |
  |<-- close 4009 ----------|
  |                         |
  |  [Re-IDENTIFY + sync]  |
  |-- IDENTIFY {token} --->|
  |<-- READY ---------------|
  |-- POST /sync ---------->|  (REST)
  |<-- {events[]} ----------|
```

## 10. Error Handling

### HTTP Status Code Mapping

| HTTP Status | Error Codes | Description |
|---|---|---|
| 400 Bad Request | `PROTOCOL_VERSION_MISMATCH`, `MESSAGE_TOO_LARGE`, `SPACE_TYPE_MISMATCH` | Invalid request |
| 401 Unauthorized | `AUTH_FAILED`, `AUTH_EXPIRED`, `2FA_REQUIRED`, `2FA_INVALID_CODE`, `WEBAUTHN_INVALID` | Authentication issue |
| 403 Forbidden | `FORBIDDEN`, `BANNED`, `ROLE_HIERARCHY`, `DM_PERMISSION_DENIED`, `USER_BLOCKED`, `FEDERATION_DENIED` | Permission denied |
| 404 Not Found | `USER_NOT_FOUND`, `SPACE_NOT_FOUND`, `MESSAGE_NOT_FOUND`, `REPORT_NOT_FOUND`, `CMD_NOT_FOUND`, `WEBHOOK_NOT_FOUND`, `KEY_BACKUP_NOT_FOUND`, `WEBAUTHN_CREDENTIAL_NOT_FOUND` | Resource not found |
| 409 Conflict | `ALREADY_IN_VOICE`, `CMD_ALREADY_REGISTERED`, `2FA_ALREADY_ENABLED` | Conflicting state |
| 410 Gone | `INVITE_EXPIRED`, `INTERACTION_EXPIRED`, `2FA_SETUP_EXPIRED`, `DEVICE_PAIR_EXPIRED`, `CPACE_EXPIRED` | Resource expired |
| 413 Payload Too Large | `FILE_TOO_LARGE` | Request too large |
| 422 Unprocessable Entity | `INVITE_INVALID`, `WEBHOOK_TOKEN_INVALID`, `2FA_NOT_ENABLED`, `2FA_RECOVERY_EXHAUSTED`, `CPACE_FAILED` | Validation failure |
| 429 Too Many Requests | `RATE_LIMITED` | Rate limited |
| 500 Internal Server Error | `UNKNOWN_ERROR` | Server error |
| 502 Bad Gateway | `FEDERATION_UNAVAILABLE` | Upstream error |
| 503 Service Unavailable | `SERVER_FULL`, `ROOM_FULL`, `PREKEY_EXHAUSTED`, `DEVICE_LIMIT_REACHED` | Capacity limit |

### Error Code Reference

| Code | Description |
|---|---|
| `OK` | Success (not returned in error responses) |
| `UNKNOWN_ERROR` | Unknown error |
| `PROTOCOL_VERSION_MISMATCH` | Incompatible protocol version |
| `AUTH_FAILED` | Authentication failed |
| `AUTH_EXPIRED` | Session token expired |
| `RATE_LIMITED` | Rate limited (includes `retry_after_ms`) |
| `FORBIDDEN` | Insufficient permissions (includes `missing_permission`) |
| `USER_NOT_FOUND` | User does not exist |
| `SPACE_NOT_FOUND` | Feed or room does not exist |
| `MESSAGE_NOT_FOUND` | Message does not exist |
| `MESSAGE_TOO_LARGE` | Message body exceeds size limit |
| `FILE_TOO_LARGE` | File exceeds upload size limit |
| `UNSUPPORTED_CODEC` | Media codec not supported |
| `ROOM_FULL` | Voice room at capacity |
| `ALREADY_IN_VOICE` | Already connected to a voice room |
| `INVITE_EXPIRED` | Invite has expired |
| `INVITE_INVALID` | Invite code is not valid |
| `BANNED` | User is banned from this server |
| `ROLE_HIERARCHY` | Cannot act on a user with higher role |
| `SPACE_TYPE_MISMATCH` | Wrong operation for this space type |
| `SERVER_FULL` | Server at member capacity |
| `E2E_KEY_MISMATCH` | E2E key verification failed |
| `PREKEY_EXHAUSTED` | No prekeys available for user |
| `DEVICE_LIMIT_REACHED` | Maximum devices reached |
| `DM_PERMISSION_DENIED` | Recipient has restricted DMs |
| `USER_BLOCKED` | You are blocked by this user |
| `REPORT_NOT_FOUND` | Report does not exist |
| `DEVICE_PAIR_DENIED` | Pairing request was rejected |
| `DEVICE_PAIR_EXPIRED` | Pairing request timed out |
| `KEY_BACKUP_NOT_FOUND` | No recovery backup exists |
| `FEDERATION_UNAVAILABLE` | Remote server unreachable |
| `FEDERATION_DENIED` | Remote server denied federation |
| `CMD_ALREADY_REGISTERED` | Command name conflicts |
| `CMD_NOT_FOUND` | Command does not exist |
| `INTERACTION_EXPIRED` | Interaction response too slow |
| `WEBHOOK_NOT_FOUND` | Webhook does not exist |
| `WEBHOOK_TOKEN_INVALID` | Webhook token is invalid |
| `2FA_REQUIRED` | Two-factor authentication required |
| `2FA_INVALID_CODE` | 2FA code is incorrect or expired |
| `2FA_ALREADY_ENABLED` | 2FA method already enrolled |
| `2FA_NOT_ENABLED` | 2FA is not enabled |
| `2FA_SETUP_EXPIRED` | 2FA setup session expired |
| `2FA_RECOVERY_EXHAUSTED` | All recovery codes used |
| `CPACE_FAILED` | CPace key exchange failed |
| `CPACE_EXPIRED` | CPace pairing session expired |
| `WEBAUTHN_INVALID` | WebAuthn assertion verification failed |
| `WEBAUTHN_CREDENTIAL_NOT_FOUND` | WebAuthn credential ID not recognized |

## 11. Rate Limiting

When a client exceeds rate limits, the server returns:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 5
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1700000005
```

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "You are being rate limited.",
    "retry_after_ms": 5000
  }
}
```

### Rate Limit Headers

| Header | Description |
|---|---|
| `X-RateLimit-Limit` | Max requests in this window |
| `X-RateLimit-Remaining` | Requests remaining in this window |
| `X-RateLimit-Reset` | Unix timestamp when the window resets |
| `Retry-After` | Seconds to wait before retrying (on 429) |

### Per-Endpoint Categories

Servers SHOULD apply rate limits per category:

| Category | Example Limit | Endpoints |
|---|---|---|
| Auth | 5/min | `/auth/*` |
| Messages (send) | 5/5s per feed | `POST /feeds/{id}/messages` |
| Messages (history) | 30/min | `GET /feeds/{id}/messages` |
| DM open | 10/hour | `POST /dms` |
| DM messages | 30/min per DM | `POST /feeds/{dm_id}/messages` |
| Bulk operations | 5/min | `*/bulk-delete` |
| File upload | 10/min | `POST /feeds/{id}/files` |
| Search | 10/min | `GET /messages/search` |
| Gateway events | 120/min | Typing, presence updates |
| General API | 60/min | All other endpoints |

## 12. DM Moderation

### DM Permission Controls

Users control who can DM them via `GET/PATCH /api/v1/users/@me/dm-settings`:

| Setting | Value | Description |
|---|---|---|
| `everyone` | 0 | Anyone on the server can DM |
| `friends_only` | 1 | Only users on their friend list |
| `mutual_servers` | 2 | Only users sharing a server (includes federated members) |
| `nobody` | 3 | DMs completely disabled |

If a user attempts to DM a recipient whose settings disallow it, the server returns `403 FORBIDDEN` with error code `DM_PERMISSION_DENIED`.

### User Blocking

When a user blocks another:
- All existing DMs between them are effectively closed
- Blocked user cannot open new DMs
- Blocked user cannot see blocker's presence or activity
- Existing messages remain on blocker's client

Blocking is via `PUT /api/v1/users/@me/blocks/{user_id}`.

### Rate Limiting

DM-specific rate limits are applied per the table in Section 11.

### Client-Side Reporting

Since the server cannot read E2EE DMs, reporting is voluntary and initiated by the recipient:

```
Recipient              REST API                           Admin
  |                       |                                  |
  |  [selects messages]   |                                  |
  |  [client decrypts]    |                                  |
  |                       |                                  |
  |-- POST /reports ----->|  [store report]                  |
  |<-- {report_id} -------|                                  |
  |                       |                                  |
  |                       |<-- GET /reports?status=open -----|
  |                       |-- {reports[]} ------------------>|
  |                       |                                  |
  |                       |<-- POST /reports/{id}/resolve ---|
  |                       |    {action: "ban"}               |
  |                       |  [execute action]                |
```

### Metadata Monitoring

The server can observe DM patterns without breaking encryption:
- Number of DMs opened per user per time period
- Message frequency per DM
- Rapid-fire DM opening to many users (spam pattern)

Servers MAY use this metadata for abuse detection.

## 13. Federation

Federation allows servers to communicate with each other, enabling cross-server DMs, presence, and server joining.

### User Identity

Users are identified by email-style addresses:

```
alice@voxchat.example.com
  |         |
  user      server domain
```

For local operations, the short `user_id` (uint32) is used. The full `user@domain` form is used only for federation.

### DNS Records

```
; Service discovery
_vox._quic.example.com.     IN SRV  10 0 443 vox.example.com.

; Server public key
_voxkey.example.com.        IN TXT  "v=vox1; k=ed25519; p=<base64_public_key>"

; Federation policy
_voxpolicy.example.com.     IN TXT  "v=vox1; federation=open; abuse=admin@example.com"

; Allowlist entries (when federation=allowlist)
servera.com._voxallow.example.com.    IN A  127.0.0.2
```

| Record | Purpose | Email Equivalent |
|---|---|---|
| `_vox._quic` SRV | Service discovery (host + port) | MX record |
| `_voxkey` TXT | Server signing key | DKIM |
| `_voxpolicy` TXT | Federation policy and abuse contact | DMARC |
| `<domain>._voxallow` A | Allowlist entries | N/A |

### Federation Policy

| Policy | Behavior |
|---|---|
| `federation=open` | Accept federation from any server, subject to blocklists |
| `federation=allowlist` | Only federate with domains listed in `_voxallow` records |
| `federation=closed` | No federation |

### Server-to-Server Transport

Server-to-server federation continues to use QUIC for efficient binary message relay. This is internal infrastructure -- clients never interact with the federation layer directly.

Two layers of authentication:

**1. mTLS (mutual TLS):** Both servers present certificates during the QUIC handshake.

**2. DNS key signature (like DKIM):** The connecting server signs federation messages with its Ed25519 private key. The receiving server verifies via `_voxkey` DNS TXT record.

```
Server A                                          Server B
  |                                                  |
  |  [lookup _vox._quic.serverb.com SRV]             |
  |  [lookup _voxkey.serverb.com TXT]                |
  |                                                  |
  |-- QUIC connect (mTLS, both sides verify) ------->|
  |                                                  |
  |-- FED_HELLO {                                    |
  |     origin: servera.com,                         |
  |     signature: sign(payload, servera_privkey)    |
  |   } ------------------------------------------->|
  |                                                  |
  |   [Server B verifies signature against DNS key]  |
  |                                                  |
  |<-- FED_HELLO_ACK {verified: true} ---------------|
```

### What Gets Federated

| Feature | Federated | How |
|---|---|---|
| DMs (1:1 and group) | Yes | E2EE blob relay, servers cannot read content |
| User profile lookup | Yes | Server-to-server lookup |
| Presence | Yes, for contacts | Server-to-server subscription |
| Typing indicators (DMs) | Yes | Server-to-server relay |
| Read receipts (DMs) | Yes | Server-to-server relay |
| Prekey exchange (E2EE) | Yes | Server-to-server prekey fetch |
| Server joining | Yes | Federation join, then direct connection |
| File transfer (DMs) | Yes | E2EE blob relay |
| Server feeds and rooms | No | Connect directly to the server |

### Federated DM Flow

The client protocol is identical regardless of federation. The home server wraps and unwraps transparently:

```
Alice@ServerA              ServerA              ServerB              Bob@ServerB
  |                          |                     |                     |
  |-- POST /feeds/{dm}/     |                     |                     |
  |   messages {ciphertext}->|                     |                     |
  |                          |  [wrap in federation |                    |
  |                          |   envelope, sign]    |                    |
  |                          |-- FED_MSG_RELAY --->|                     |
  |                          |   {from: alice@a,   |                     |
  |                          |    to: bob@b,       |                     |
  |                          |    opaque_blob,     |                     |
  |                          |    signature}       |                     |
  |                          |                     |  [verify, dispatch] |
  |                          |                     |-- MESSAGE_CREATE -->|
  |                          |                     |   (gateway event)   |
```

### Federated Server Joining

A user on Server A joins Server B's community:

```
Alice@ServerA              ServerA              ServerB
  |                          |                     |
  |-- "join serverb.com" -->|                     |
  |                          |-- FED_JOIN_REQ {   |
  |                          |   user: alice@      |
  |                          |    servera.com,     |
  |                          |   voucher: signed   |
  |                          |    proof            |
  |                          |  } --------------->|
  |                          |                     |
  |                          |<-- FED_JOIN_RES {  |
  |                          |   accepted: true,   |
  |                          |   federation_token, |
  |                          |   server_info       |
  |                          |  } ----------------|
  |                          |                     |
  |  [Alice connects directly to ServerB via HTTP/WS/media] |
  |                                                |
  |== REST: POST /auth/login {federation_token} ==>|
  |<== {token, user_id} ==========================|
  |== WebSocket: IDENTIFY ========================>|
  |<== READY =====================================|
```

Alice authenticates with her home server, which vouches for her identity. She then connects directly to Server B using the standard HTTP/WS/media model. Her identity remains `alice@servera.com`.

### HTTP Federation (Alternative)

As an alternative to QUIC-based server-to-server communication, servers MAY implement federation over HTTPS REST endpoints. This can simplify deployment at the cost of some efficiency. The federation messages and authentication remain the same -- only the transport changes.

### Security: Message Reconstruction

The receiving server MUST reconstruct local messages from validated federation data. Never blindly unwrap.

| Rule | Reason |
|---|---|
| Never trust sender-provided IDs | Server generates its own msg_id, timestamp, feed assignment |
| Verify domain matches connection | `from: alice@evil.com` must arrive on a verified `evil.com` connection |
| Tag all federated messages | Local code can distinguish federated vs local |
| Do not parse E2EE blobs | Server cannot and should not interpret encrypted content |
| Federated guests cannot access admin paths | No role management, no server settings |
| Rate limit per federation peer | Even verified servers get throttled |

### Abuse Prevention

#### 1. DNS Verification

Server signatures verified against DNS public keys. No valid signature = no federation.

#### 2. Local Blocklist

Server admin maintains a blocklist of domains. Sends `FED_BLOCK_NOTIFY` courtesy notification.

#### 3. DNS Blocklists (opt-in)

```
Incoming federation from sketchyserver.net:
  DNS query: sketchyserver.net.voxblock.community.org  A?
  -> 127.0.0.2 = blocked
  -> NXDOMAIN = not listed, proceed
```

#### 4. Rate Limiting Per Peer

| Limit | Example | Description |
|---|---|---|
| Max DM relays/hour/peer | 100 | Caps message relay from a single domain |
| Max presence subs/peer | 500 | Caps presence subscriptions |
| Max join requests/hour/peer | 20 | Caps join requests |

#### 5. User-Level Controls

Existing DM permission settings apply to federated users. Users can block specific remote users (`alice@evil.com`).

### Federation Error Codes

| Code | Description |
|---|---|
| `FED_OK` | Success |
| `FED_UNKNOWN_ERROR` | Unknown error |
| `FED_AUTH_FAILED` | Signature verification failed |
| `FED_DNS_KEY_MISMATCH` | DNS key does not match signature |
| `FED_POLICY_DENIED` | Remote server's policy denies federation |
| `FED_NOT_ON_ALLOWLIST` | Domain not on allowlist |
| `FED_BLOCKED` | Domain is on blocklist |
| `FED_RATE_LIMITED` | Rate limited (includes retry_after_ms) |
| `FED_USER_NOT_FOUND` | Remote user does not exist |
| `FED_INVITE_INVALID` | Invite code invalid or expired |
| `FED_INVITE_EXPIRED` | Invite code expired |
| `FED_SERVER_FULL` | Remote server at capacity |

## 14. Bots and Webhooks

### Gateway Bots

Gateway bots connect via WebSocket and participate in real-time events. They authenticate with a bot token via REST, then connect to the gateway:

```
Bot                    REST API        Gateway
  |                       |               |
  |-- POST /auth/login -->|               |
  |   {bot_token}         |               |
  |<-- {token} -----------|               |
  |                       |               |
  |-- GET /gateway ------->|               |
  |<-- {url} -------------|               |
  |                       |               |
  |-- WebSocket connect ---|-------------->|
  |<-- HELLO --------------|---------------|
  |-- IDENTIFY {token} ---|-------------->|
  |<-- READY {is_bot:true}-|--------------|
  |                       |               |
  |-- PUT /bots/@me/      |               |
  |   commands ----------->|               |
  |                       |               |
  |  [receive INTERACTION_CREATE events]   |
  |<-- dispatch -----------|--------------|
  |                       |               |
  |-- POST /interactions/  |               |
  |   {id}/response ------>|               |
```

#### Slash Command Flow

```
User                    Server                          Bot (Gateway)
  |                        |                                |
  |-- POST /feeds/{id}/   |                                |
  |   messages {"/roll 20"}|                                |
  |                        |  [parse command, route]        |
  |                        |-- INTERACTION_CREATE dispatch->|
  |                        |   {type: "slash_command",      |
  |                        |    command: "roll",            |
  |                        |    params: {sides: "20"}}     |
  |                        |                                |
  |                        |<-- POST /interactions/{id}/   |
  |<-- MESSAGE_CREATE -----|    response {body: "17"}       |
```

The `/roll` input is intercepted by the server and never posted as a regular message.

#### Component Interactions (Buttons and Menus)

Bots can attach interactive components to messages:

```json
// Send message with components
POST /api/v1/feeds/{feed_id}/messages
{
  "body": "Pick a color",
  "components": [
    {"type": "button", "id": "red", "label": "Red"},
    {"type": "button", "id": "blue", "label": "Blue"}
  ]
}
```

When a user clicks a button, the bot receives an `INTERACTION_CREATE` with `type: "button"` and `component_id: "red"`.

#### Voice Room Participation

Bots join voice rooms using the same protocol as clients:

```
Bot                     REST API        Gateway          SFU
  |                        |               |               |
  |-- POST /rooms/{id}/   |               |               |
  |   voice/join --------->|               |               |
  |<-- {media_url, token} -|               |               |
  |                        |               |               |
  |== QUIC connect to SFU ===============================|
  |== MEDIA_AUDIO ======================================>|== forward ==>
```

Use cases: music playback, recording, AI voice, speech-to-text, real-time translation, soundboards.

### HTTP-Only Bots

For simpler bots that don't need real-time events, register an interaction endpoint URL. The server POSTs interactions directly to the bot's HTTP server:

```
User                    Server                   Bot HTTP Server
  |                        |                          |
  |-- "/roll 20" --------->|                          |
  |                        |-- POST https://bot.      |
  |                        |   example.com/interact   |
  |                        |   {type: "slash_command", |
  |                        |    command: "roll",       |
  |                        |    params: {sides: "20"}} |
  |                        |                          |
  |                        |<-- {body: "Rolled: 17"} -|
  |<-- MESSAGE_CREATE -----|                          |
```

HTTP-only bots register their endpoint URL and commands via REST. They cannot receive other events (messages, presence, etc.) and cannot join voice rooms.

### Bot and Webhook Comparison

| | Gateway Bot | HTTP-Only Bot | Webhook |
|---|---|---|---|
| Connection | WebSocket | Stateless HTTP | Stateless HTTP POST |
| Receive events | Yes (all) | Interactions only | No |
| Send messages | Yes | Via interaction response | Yes |
| Slash commands | Yes | Yes | No |
| Component interactions | Yes | Yes | No |
| Voice/video | Yes | No | No |
| Use case | Interactive, real-time, voice | Simple commands | CI/CD alerts, notifications |

#### Webhook Flow

```
External Service                 Server                      Feed
  |                                |                           |
  |-- POST /api/v1/webhooks/      |                           |
  |   {id}/{token}                |                           |
  |   {body, embeds?} ----------->|                           |
  |                                |-- MESSAGE_CREATE -------->|
  |<-- 204 No Content ------------|   (gateway dispatch)      |
```

## 15. Audit Logging

The audit log records administrative actions for accountability. Queried via `GET /api/v1/audit-log` (requires `VIEW_AUDIT_LOG` permission).

### Convention

Event types use dot-notation: `{category}.{action}`:

```
member.kick              {target_id, reason?}
role.assign              {role_id, target_id}
feed.delete              {feed_id, name}
message.bulk_delete      {feed_id, count}
invite.use               {code, target_id}
federation.block         {domain, reason?}
2fa.admin_reset          {target_user_id, reason?}
```

The `metadata` map on each entry carries event-specific key-value pairs. Message content should not be stored in the audit log -- only IDs, names, and changes.

## 16. Priority and QoS

Priority and QoS are primarily relevant to the media transport layer, where different traffic types compete for bandwidth:

| Priority | Traffic |
|---|---|
| 0 (highest) | Voice audio |
| 1 | Video |
| 2 | Screen share |

For the REST API and gateway, standard HTTP/2 prioritization and WebSocket message ordering apply. The server may apply rate limiting (Section 11) to manage load across REST endpoints.
