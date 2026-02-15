# VoxProtocol v1: Protocol Overview

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
| **Leaf Key** | A device's MLS private key. Each device has its own leaf in the MLS ratchet tree. |
| **Member** | A user within a server. |
| **Recovery Passphrase** | A 12-word mnemonic used to recover E2EE keys when all devices are lost. |
| **REST API** | The HTTPS JSON API (`/api/v1/`) for all CRUD operations, authentication, history, search, and file management. |
| **Role** | A named permission group within a server. |
| **Room** | A real-time voice and video space within a server. Variant: stage. |
| **Server** | The infrastructure node and the community it hosts. One server = one community. |
| **Session** | An authenticated connection from a client to a server. |
| **SFU** | Selective Forwarding Unit -- the server's role in voice, forwarding media without mixing. |
| **Slash Command** | A bot-registered command invoked by users with a `/` prefix. Parsed and routed by the server. |
| **Space** | Collective term for feeds and rooms. Any content area within the server hierarchy. |
| **Stage** | A room variant with a speaker/audience model. |
| **Thread** | A sub-conversation branching off a message in a feed. |
| **Webhook** | A stateless HTTP endpoint for posting messages to a feed. Cannot receive events or join voice rooms. |

## 3. Architecture Overview

```
+-------------------------------------------------------------+
|                        Client                                |
|                                                              |
|  +--------------+  +--------------+  +------------------+   |
|  |   REST API   |  |   Gateway    |  |  Media Transport  |  |
|  |  HTTPS JSON  |  |  WebSocket   |  |  QUIC datagrams   |  |
|  |  /api/v1/*   |  |  wss://      |  |  UDP datagrams    |  |
|  +------+-------+  +------+-------+  +--------+---------+   |
|         |                 |                    |              |
+---------+-----------------+--------------------+--------------+
          |                 |                    |
          v                 v                    v
+-------------------------------------------------------------+
|                        Server                                |
+-------------------------------------------------------------+
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

### Documentation Map

| Document | Covers |
|---|---|
| `API.md` | Complete REST API endpoint reference, error codes, rate limits |
| `GATEWAY.md` | WebSocket gateway protocol, message types, events |
| `MEDIA.md` | QUIC media transport, binary frame format, SVC, congestion control |
| `E2EE.md` | MLS encryption for DMs, device pairing, key recovery |
| `FEDERATION.md` | Server-to-server communication, DNS discovery, federated flows |

## 4. Server Hierarchy

A server contains the following entity types:

| Entity | Contains | Notes |
|---|---|---|
| **Server** | Settings, Roles[], Custom Emoji[], Members[], Categories[], Feeds[], Rooms[] | Top-level; one server = one community |
| **Category** | Feeds[], Rooms[] | Organizational grouping; feeds/rooms may also be uncategorized |
| **Feed** | Messages, Threads | Variants: text (default), forum, announcement |
| **Room** | Voice/video participants | Variants: voice (default), stage |
| **Thread** | Messages | Branches off a message in a feed |

## 5. IDs

### Snowflake IDs

Message IDs (`msg_id`) use snowflake uint64 values. A snowflake embeds a timestamp, enabling time-based ordering and cursor pagination by ID. Other entity IDs (`user_id`, `feed_id`, `dm_id`, `room_id`, `thread_id`, `role_id`, etc.) use uint32.

```
 63        22 21    12 11         0
+----------+---------+------------+
| timestamp | worker | sequence   |
| (42 bits) | (10 b) | (12 bits)  |
+----------+---------+------------+
```

| Field | Bits | Description |
|---|---|---|
| `timestamp` | 42 | Milliseconds since Vox epoch (2025-01-01T00:00:00Z). Covers ~139 years. |
| `worker` | 10 | Server/process identifier. Allows up to 1024 concurrent ID generators. |
| `sequence` | 12 | Per-worker sequence counter. Allows 4096 IDs per millisecond per worker. |

Snowflakes are represented as uint64 in JSON. Clients can extract the approximate creation time from any snowflake:

```
timestamp_ms = (snowflake >> 22) + VOX_EPOCH
```

Where `VOX_EPOCH = 1735689600000` (2025-01-01T00:00:00Z in Unix milliseconds).

### Feed and DM IDs

Feed IDs and DM IDs use separate fields (`feed_id` and `dm_id`, both uint32). In endpoints that operate on either type (e.g., message endpoints), only one field is provided:

| Field | Type | Description |
|---|---|---|
| `feed_id` | uint32? | Present when targeting a server feed |
| `dm_id` | uint32? | Present when targeting a DM conversation |

Exactly one of `feed_id` or `dm_id` MUST be present in any request or event that references a message container.

### Thread IDs

Thread IDs (`thread_id`) are uint32 values scoped to the parent feed. They are unique within a feed but not globally unique. Endpoints that reference threads always include the parent `feed_id`.

## 6. Message Body Format

Message bodies use a subset of Markdown for formatting with a mention syntax for referencing users and roles.

### Supported Markdown

| Syntax | Renders As |
|---|---|
| `*italic*` or `_italic_` | *italic* |
| `**bold**` | **bold** |
| `~~strikethrough~~` | ~~strikethrough~~ |
| `` `inline code` `` | `inline code` |
| ` ```code block``` ` | Code block (with optional language hint) |
| `> quote` | Blockquote |
| `[text](url)` | Hyperlink |
| `||spoiler||` | Spoiler (hidden until clicked) |

### Mention Syntax

| Syntax | Targets |
|---|---|
| `<@user_id>` | User mention |
| `<@&role_id>` | Role mention |
| `<@everyone>` | Everyone in the feed |

Mentions are parsed by clients for display and notification purposes. The `mentions` array in the message object provides the resolved mention targets for convenience.

Servers do not validate or transform Markdown. Message bodies are stored and relayed as-is. Rendering is a client responsibility.

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

## 8. Connection Lifecycle

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
  |<-- {url, media_url,   |                |                  |
  |     protocol_version,  |                |                  |
  |     min_version,       |                |                  |
  |     max_version} ------|                |                  |
  |                        |                |                  |
  |  3. Connect gateway    |                |                  |
  |-- WebSocket connect ----|--------------->|                  |
  |<-- hello {interval} ---|----------------|                  |
  |-- identify {token} ----|--------------->|                  |
  |<-- ready {session_id} -|----------------|                  |
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
  |<-- hello {interval} ----|
  |-- resume {              |
  |     session_id,         |
  |     last_seq            |
  |   } ------------------>|
  |                         |
  |  [If session valid:]    |
  |<-- missed events -------|
  |<-- (continue) ----------|
  |                         |
  |  [If session expired:]  |
  |<-- close 4009 ----------|
  |                         |
  |  [If replay buffer      |
  |   exhausted:]           |
  |<-- close 4010 ----------|
  |                         |
  |  [Re-identify + sync]   |
  |-- identify {token} ---->|
  |<-- ready ---------------|
  |-- POST /sync ---------->|  (REST)
  |<-- {events[]} ----------|
```

Close code 4009 (SESSION_EXPIRED) requires full re-authentication. Close code 4010 (REPLAY_EXHAUSTED) means the session is valid but the replay buffer cannot cover the gap -- the client re-identifies with its existing token (no re-login) and calls `/sync` to catch up.
