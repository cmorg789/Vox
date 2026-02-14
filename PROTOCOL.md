# VoxProtocol v1: QUIC-Based Community Server Protocol

## 1. Design Philosophy

- **One server = one community.** No multi-guild abstraction. You connect to a server, that server IS the community.
- **Trusted server for feeds and rooms.** Server feeds and rooms are not E2E encrypted -- the server can moderate, search, and index.
- **E2EE for DMs.** All direct messages (1:1 and group) use MLS with a per-user shared key. The server relays opaque blobs it cannot read.
- **Federated.** Servers communicate via DNS discovery, mTLS, and signed message relay. Users are identified as `user@domain`. Cross-server DMs, presence, and server joining are fully supported.
- **QUIC-native.** Streams for reliable data, datagrams for media, built-in TLS 1.3 for transport security.

## 2. Definitions

| Term | Definition |
|---|---|
| **Announcement** | A read-only feed for broadcasts and notifications. |
| **Attachment** | A file uploaded alongside a message. |
| **Bot** | A programmatic client that connects via the full QUIC protocol. Can send messages, register commands, respond to interactions, and join voice rooms. |
| **Category** | An organizational grouping of feeds and rooms within a server. |
| **DM** | A direct message between users (1:1 or group). E2E encrypted. Exists outside the server hierarchy. |
| **Embed** | A rich content preview generated from a URL. |
| **Epoch** | An MLS key generation. All messages within an epoch share the same group key. Epoch changes on membership add/remove. |
| **Federation** | Server-to-server communication enabling cross-server DMs, presence, and server joining. Uses DNS discovery and signed message relay. |
| **Feed** | A persistent text and media space within a server. Variants: forum, announcement. |
| **Forum** | A feed variant where every top-level post creates a thread. |
| **Home Server** | The server where a user's account lives. Identified by the domain in their address (e.g., `example.com` in `alice@example.com`). |
| **Interaction** | A user action (slash command, button click, menu selection) routed to a bot for handling. |
| **Invite** | A code or link granting access to a server. |
| **Leaf Key** | A user's MLS private key, shared across all their devices. Used to participate in MLS groups. |
| **Member** | A user within a server. |
| **Recovery Passphrase** | A 12-word mnemonic used to recover E2EE keys when all devices are lost. |
| **Role** | A named permission group within a server. |
| **Room** | A real-time voice and video space within a server. Variant: stage. |
| **Server** | The infrastructure node and the community it hosts. One server = one community. |
| **Session** | An authenticated connection from a client to a server. |
| **SFU** | Selective Forwarding Unit -- the server's role in voice, forwarding media without mixing. |
| **Slash Command** | A bot-registered command invoked by users with a `/` prefix. Parsed and routed by the server. |
| **Stage** | A room variant with a speaker/audience model. |
| **Thread** | A sub-conversation branching off a message in a feed. |
| **Webhook** | A stateless HTTP endpoint for posting messages to a feed. Cannot receive events or join voice rooms. |

## 3. Why QUIC

- **Multiplexed streams** -- voice, video, text, file transfer without head-of-line blocking
- **0-RTT connection resumption** -- fast reconnects
- **Built-in TLS 1.3** -- transport encryption by default
- **Connection migration** -- seamless WiFi to cellular handoff
- **Per-stream flow control** -- prioritize voice over file transfers
- **Unreliable datagrams** (RFC 9221) -- low-latency media

## 4. Connection Architecture

```
+------------------------------------------------------+
|                    QUIC Connection                    |
|                                                      |
|  Stream 0 (bidi)     -- Control Channel (reliable)   |
|  Stream 2 (bidi)     -- Auth                         |
|  Stream 4+ (bidi)    -- Text / Signaling (reliable)  |
|  Stream N  (uni)     -- File Transfer (reliable)     |
|  DATAGRAM frames     -- Voice/Video (unreliable)     |
|                                                      |
+------------------------------------------------------+
```

### Stream Allocation

| Stream ID Range | Direction | Purpose |
|---|---|---|
| 0 | Bidirectional | Control (HELLO/HELLO_ACK, presence, typing, sync) |
| 2 | Bidirectional | Auth handshake (AUTH, AUTH_CHALLENGE, AUTH_OK) |
| 4-1023 | Bidirectional | Text messaging (one per feed/DM) |
| 1024-2047 | Bidirectional | Voice/stage room signaling |
| 2048+ | Unidirectional | File transfers (one per file) |
| DATAGRAM | N/A | Voice and video media frames |

## 5. Frame Format

All protocol messages use a common envelope with versioning and reserved padding:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Version (8)  | Min Compat (8)|           Type (16)            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                     Sequence Number (32)                       |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                      Timestamp (64)                           |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                   Payload Length (32)                          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   Flags (8)   |Hdr Ext Len (8)|        Reserved (16)          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|              Header Extensions (variable, 0-255 bytes)      ..|
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                   Payload (variable)                        ..|
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

Fixed header: 24 bytes + 0-255 bytes extensions
```

### Fields

| Field | Bits | Description |
|---|---|---|
| **Version** | 8 | Protocol version (current: `0x01`) |
| **Min Compatible** | 8 | Oldest version sender supports. Disconnect if peer version < this |
| **Type** | 16 | Message type (see Section 7). 65,536 possible types |
| **Sequence Number** | 32 | Per-stream monotonic counter |
| **Timestamp** | 64 | Microsecond Unix epoch |
| **Payload Length** | 32 | Payload size in bytes |
| **Flags** | 8 | `[COMPRESSED, RSV, RSV, RSV, RSV, RSV, RSV, RSV]` -- 7 reserved bits. Priority is determined by message type (see Section 15) |
| **Header Ext Len** | 8 | Bytes of header extensions (0 = none) |
| **Reserved** | 16 | MUST be `0x0000`. Future versions may assign meaning |
| **Header Extensions** | 0-255 bytes | TLV-encoded. Unknown extensions skipped via ExtLen |

### Version Negotiation

```
Client: Version=0x01, MinCompat=0x01
Server: Version=0x01, MinCompat=0x01   <- OK

Client: Version=0x01, MinCompat=0x01
Server: Version=0x02, MinCompat=0x02   <- FAIL: client 0x01 < server min 0x02
  -> ERROR(PROTOCOL_VERSION_MISMATCH), disconnect
```

### Header Extension TLV

```
+--------------+--------------+-----------------+
|  ExtType (8) |  ExtLen (8)  |  ExtData (var)  |
+--------------+--------------+-----------------+

0x00        NOP / alignment padding
0x01        Trace ID (16 bytes)
0x02-0xEF   Reserved for future standard use
0xF0-0xFF   Application-specific / experimental
```

### Compression

When the `COMPRESSED` flag is set in the frame header, the payload is compressed. The compression algorithm is negotiated during the HELLO handshake via capabilities (e.g., `compress.zstd`). If no compression capability was negotiated, the COMPRESSED flag MUST NOT be set.

### Response Convention

Every mutating request has a typed response message. On success, the server sends the corresponding `*_ACK` or `*_RES` message. On failure, the server sends `ERROR` (0x0008) with an appropriate error code. Clients SHOULD treat the absence of either within a reasonable timeout as a connection-level failure.

### ID Spaces

Feed IDs and DM IDs share a single uint32 field (`feed_id`). The high bit (bit 31) distinguishes them:

- Bit 31 = 0: feed ID (`0x00000000`-`0x7FFFFFFF`, ~2 billion feeds)
- Bit 31 = 1: DM ID (`0x80000000`-`0xFFFFFFFF`, ~2 billion DMs)

`DM_OPEN` and `DM_OPEN_GROUP` return a `feed_id` with bit 31 set. Subsequent `MSG_SEND`, `TYPING_START`, and other feed-scoped messages use this ID directly. The server distinguishes feed vs DM with a single bit check.

## 6. Payload Serialization

All message payloads use Protocol Buffers (proto3) for serialization.

### Why Protobuf

| Property | Benefit |
|---|---|
| Compact binary encoding | Small payloads on the wire |
| Schema evolution | Add fields without breaking old clients (aligns with protocol versioning) |
| Field numbers | Unknown fields are skipped, not rejected |
| Code generation | First-class support for Rust, Go, C++, TypeScript, Python, and more |
| Widely deployed | Battle-tested at scale, well-documented, mature tooling |

### Encoding Rules

- All payloads in the `Payload` section of the protocol frame are proto3-encoded messages
- The `Type` field in the frame header determines which proto message to decode
- Unknown fields MUST be preserved when forwarding (future compatibility)
- Default values (zero, empty string, false) are not sent on the wire (proto3 behavior)

### Message Definitions

Each message type in Section 7 maps to a proto message. 
Full `.proto` definitions for all message types are maintained in `vox.proto` alongside this specification.

### Media Frames

Media frames sent via QUIC DATAGRAM do NOT use protobuf or the Section 5 frame envelope. They use only the fixed binary media header defined in Section 8, followed by raw codec payload. This avoids the overhead of both protobuf encoding and the 24-byte frame envelope on high-frequency media packets.

## 7. Message Types

Type is a 16-bit field. Each category is allocated a 256-slot block (`0xNN00-0xNNFF`), grouped by conceptual layer.

### Type Allocation Map

| Range | Layer | Category |
|---|---|---|
| `0x0000-0x00FF` | Infrastructure | Control |
| `0x0100-0x01FF` | Infrastructure | User, Profile, and Relationships |
| `0x0200-0x02FF` | Server Structure | Membership and Invites |
| `0x0300-0x03FF` | Server Structure | Roles and Permissions |
| `0x0400-0x04FF` | Server Structure | Feed and Room Management |
| `0x0500-0x05FF` | Server Structure | Categories and Threads |
| `0x0600-0x06FF` | Communication | Presence and Status |
| `0x0700-0x07FF` | Communication | Text Messaging |
| `0x0800-0x08FF` | Communication | Direct Messages |
| `0x0900-0x09FF` | Communication | Voice Rooms and Stages |
| `0x0A00-0x0AFF` | Communication | Media (DATAGRAM) |
| `0x0B00-0x0BFF` | Communication | File Transfer |
| `0x0C00-0x0CFF` | Rich Content | Embeds and Custom Content |
| `0x0D00-0x0DFF` | Rich Content | Bots and Webhooks |
| `0x0E00-0x0EFF` | Security | E2E Encryption |
| `0x0F00-0x0FFF` | Security | Moderation and Audit |
| `0x1000-0x10FF` | Federation | Federation |
| `0x1100-0xFFFF` | | [reserved for future categories] |

### 0x0000-0x00FF: Control

```
0x0000  HELLO              - Handshake {version, min_compat, capabilities}
0x0001  HELLO_ACK          - Server response {version, min_compat, caps, server_name, server_icon, server_time}
0x0002  AUTH               - {method: AuthMethod enum (token|password|bot_token|federation_token|webauthn), credentials}
0x0003  AUTH_CHALLENGE     - Server challenge (e.g. SRP step)
0x0004  AUTH_OK            - {user_id, session_id, display_name, roles[], is_bot}
0x0005  PING               - App-level health check
0x0006  PONG               - Health check response
0x0007  GOODBYE            - Graceful disconnect
0x0008  ERROR              - {code, reason}
0x0009  SYNC_REQ           - Reconnect catch-up  {since_timestamp, categories: members|roles|feeds|rooms|categories}
0x000A  SYNC_RES           - Sync delta response  {events[], server_timestamp}
0x000B  AUTH_2FA_STATUS_REQ        - Query own 2FA enrollment state
0x000C  AUTH_2FA_STATUS_RES        - {totp_enabled, webauthn_enabled, recovery_codes_left}
0x000D  AUTH_2FA_SETUP_REQ         - Begin 2FA enrollment  {method}
0x000E  AUTH_2FA_SETUP_RES         - Setup details  {method, setup_id, totp_secret?, totp_uri?, webauthn_creation_options?}
0x000F  AUTH_2FA_SETUP_CONFIRM     - Confirm enrollment  {setup_id, totp_code?, webauthn_attestation?, credential_name?}
0x0010  AUTH_2FA_SETUP_CONFIRM_RES - Confirm result  {success, recovery_codes[]}
0x0011  AUTH_2FA_REMOVE            - Remove 2FA method  {method, totp_code?, webauthn_assertion?}
0x0012  AUTH_2FA_REMOVE_RES        - Remove result  {success}
0x0013  AUTH_WEBAUTHN_CRED_LIST_REQ - List own WebAuthn credentials
0x0014  AUTH_WEBAUTHN_CRED_LIST_RES - {credentials[]: {credential_id, name, registered_at, last_used_at?}}
0x0015  AUTH_WEBAUTHN_CRED_DELETE   - Delete a WebAuthn credential  {credential_id}
0x0016  AUTH_2FA_RESPOND           - 2FA challenge response (during login)  {method, totp_code?, webauthn_assertion?}
0x0017  AUTH_2FA_RECOVERY_USE      - Use recovery code (during login)  {recovery_code}
0x0018-0x00FF  [reserved]
```

**PING/PONG vs QUIC keep-alive:** QUIC has built-in keep-alive at the transport level, which prevents NAT/firewall timeouts and detects dead connections. Application-level PING/PONG serves a different purpose: measuring round-trip latency visible to the application and detecting application-level hangs (e.g., a frozen server event loop where the OS TCP/QUIC stack still ACKs packets). These are optional — implementations may omit them if they don't need app-level latency metrics.

**Capabilities:** HELLO and HELLO_ACK carry a list of capability strings. The server advertises what it supports; the client advertises what it can use. Both sides operate on the intersection.

| Capability | Description |
|---|---|
| `voice` | Voice rooms supported |
| `video` | Video in voice rooms supported |
| `e2ee` | End-to-end encryption supported |
| `federation` | Federation with remote servers enabled |
| `bots` | Bot connections and slash commands supported |
| `webhooks` | Webhook endpoints supported |
| `file_transfer` | File upload/download supported |
| `compress.zstd` | Zstandard payload compression supported |
| `2fa` | Two-factor authentication supported (TOTP and/or WebAuthn) |
| `webauthn` | Passwordless WebAuthn/Passkey login supported |

### 0x0100-0x01FF: User, Profile, and Relationships

```
0x0100  USER_GET           - {user_id}
0x0101  USER_GET_RES       - {user_id, display_name, avatar, bio, roles[]}
0x0102  USER_UPDATE        - Update own profile {display_name?, avatar?, bio?}
0x0103  USER_BLOCK         - {target_user_id}
0x0104  USER_UNBLOCK       - {target_user_id}
0x0105  FRIEND_ADD         - {target_user_id}
0x0106  FRIEND_REMOVE      - {target_user_id}
0x0107  FRIEND_LIST_REQ    - List friends
0x0108  FRIEND_LIST_RES    - {friends[]}
0x0109  REGISTER           - {username, password, display_name?}
0x010A  REGISTER_RES       - {user_id, session_id}
0x010B-0x01FF  [reserved]
```

### 0x0200-0x02FF: Membership and Invites

```
0x0200  MEMBER_JOIN        - User joins server (via invite)
0x0201  MEMBER_LEAVE       - User leaves
0x0202  MEMBER_KICK        - {user_id, reason?}
0x0203  MEMBER_BAN         - {user_id, reason?, delete_msg_days?}
0x0204  MEMBER_UNBAN       - {user_id}
0x0205  MEMBER_UPDATE      - {nickname?}
0x0206  MEMBER_LIST_REQ    - {cursor?}
0x0207  MEMBER_LIST_RES    - {members[], cursor?}
0x0208  BAN_LIST_REQ       - Request ban list
0x0209  BAN_LIST_RES       - {bans[]}
0x020A  INVITE_CREATE      - {feed_id?, max_uses?, max_age?}
0x020B  INVITE_DELETE      - {code}
0x020C  INVITE_RESOLVE     - Resolve code -> server info (pre-join)
0x020D  INVITE_LIST_REQ    - List active invites
0x020E  INVITE_LIST_RES    - {invites[]}
0x020F-0x02FF  [reserved]
```

### 0x0300-0x03FF: Roles and Permissions

```
0x0300  ROLE_CREATE        - {name, color, permissions_bitfield, position}
0x0301  ROLE_UPDATE        - {role_id, name?, color?, permissions?, position?}
0x0302  ROLE_DELETE         - {role_id}
0x0303  ROLE_ASSIGN        - {user_id, role_id}
0x0304  ROLE_REVOKE        - {user_id, role_id}
0x0305  ROLE_LIST          - List all roles
0x0306  ROLE_LIST_RES      - {roles[]}
0x0307  PERM_OVERRIDE_SET  - {target_space_id, target: role|user, target_id, allow, deny}
0x0308  PERM_OVERRIDE_DEL  - Remove override
0x0309-0x03FF  [reserved]
```

### 0x0400-0x04FF: Feed and Room Management

```
0x0400  FEED_CREATE        - {category_id?, name, type, permission_overrides[]}
0x0401  FEED_UPDATE        - {feed_id, name?, topic?, settings?}
0x0402  FEED_DELETE         - {feed_id}
0x0403  ROOM_CREATE        - {category_id?, name, type, permission_overrides[]}
0x0404  ROOM_UPDATE        - {room_id, name?, settings?}
0x0405  ROOM_DELETE         - {room_id}
0x0406  FEED_ROOM_LIST     - Fetch all feeds, rooms, and categories
0x0407  FEED_ROOM_LIST_RES - {categories[], feeds[], rooms[]}
0x0408-0x04FF  [reserved]
```

### 0x0500-0x05FF: Categories and Threads

```
0x0500  CATEGORY_CREATE    - {name, position}
0x0501  CATEGORY_UPDATE    - {category_id, name?, position?}
0x0502  CATEGORY_DELETE    - {category_id}
0x0503  THREAD_CREATE      - {parent_feed_id, parent_msg_id, name}
0x0504  THREAD_UPDATE      - {thread_id, name?, archived?, locked?}
0x0505  THREAD_DELETE      - {thread_id}
0x0506  THREAD_JOIN        - Subscribe to thread
0x0507  THREAD_LEAVE       - Unsubscribe
0x0508-0x05FF  [reserved]
```

Feed types:

| Type | Value | Description |
|---|---|---|
| TEXT | 0 | Standard text feed |
| FORUM | 1 | Each post is a thread |
| ANNOUNCEMENT | 2 | Read-only for most, push notifications |

Room types:

| Type | Value | Description |
|---|---|---|
| VOICE | 0 | Persistent voice space + optional video/screen |
| STAGE | 1 | Speaker/audience model |

### 0x0600-0x06FF: Presence and Status

```
0x0600  PRESENCE_UPDATE    - {status: online|idle|dnd|invisible}
0x0601  PRESENCE_NOTIFY    - Server broadcast {user_id, status, activity?}
0x0602  TYPING_START       - {feed_id}
0x0603  CUSTOM_STATUS      - {text, emoji, expiry}
0x0604  ACTIVITY_UPDATE    - {type: playing|streaming|listening, name, detail?}
0x0605-0x06FF  [reserved]
```

Typing is timeout-based: there is no explicit stop message. Clients SHOULD re-send `TYPING_START` periodically while the user continues typing. Recipients SHOULD treat `TYPING_START` as transient and expire it locally.

### 0x0700-0x07FF: Text Messaging

```
0x0700  MSG_SEND           - {feed_id, body, reply_to?, mentions[], embeds[]}
0x0701  MSG_ACK            - Server assigns {msg_id, timestamp}
0x0702  MSG_DELIVER        - Server -> recipients
0x0703  MSG_EDIT           - {msg_id, new_body}
0x0704  MSG_DELETE         - {msg_id}
0x0705  MSG_REACTION       - {msg_id, emoji, action: add|remove}
0x0706  MSG_PIN            - {msg_id, action: pin|unpin}
0x0707  MSG_HISTORY_REQ    - {feed_id, before_seq, limit}
0x0708  MSG_HISTORY_RES    - {messages[]}
0x0709  MSG_BULK_DELETE    - {feed_id, msg_ids[]}  (moderator)
0x070A  MSG_SEARCH_REQ     - {query, feed_id?, author_id?, filters}
0x070B  MSG_SEARCH_RES     - {results[]}
0x070C  MSG_EDIT_ACK       - Server confirms edit  {msg_id, timestamp}
0x070D  MSG_DELETE_ACK     - Server confirms delete  {msg_id}
0x070E-0x07FF  [reserved]
```

### 0x0800-0x08FF: Direct Messages

DMs are private conversations between users. They support read receipts and E2E encryption (see Section 13).

```
0x0800  DM_OPEN            - 1:1 DM  {recipient_id}
0x0801  DM_OPEN_GROUP      - Group DM  {recipient_ids[], name?}  (max is server-configured)
0x0802  DM_CLOSE           - Hide DM from list  {dm_id}
0x0803  DM_LIST_REQ        - List open DMs
0x0804  DM_LIST_RES        - {dms[]}
0x0805  DM_ADD_RECIPIENT   - Add user to group DM  {dm_id, user_id}
0x0806  DM_REMOVE_RECIPIENT - Remove user / leave group DM  {dm_id, user_id}
0x0807  DM_UPDATE          - Rename group DM, change icon  {dm_id, name?, icon?}
0x0808  DM_READ            - Read receipt  {dm_id, up_to_msg_id}
0x0809  DM_READ_NOTIFY     - Server -> other DM participants  {dm_id, user_id, up_to_msg_id}
0x080A  DM_SETTINGS_GET    - Get own DM permission settings
0x080B  DM_SETTINGS_RES    - {dm_permission: everyone|friends_only|mutual_servers|nobody}
0x080C  DM_SETTINGS_UPDATE - Update DM permissions  {dm_permission}
0x080D-0x08FF  [reserved]
```

### 0x0900-0x09FF: Voice Rooms and Stages

```
0x0900  VOICE_JOIN         - {room_id, self_mute, self_deaf}
0x0901  VOICE_LEAVE        - {room_id}
0x0902  VOICE_STATE        - {user_id, mute, deaf, video, streaming}
0x0903  VOICE_KICK         - Disconnect user from room (moderator)
0x0904  VOICE_MOVE         - Move user to another room (moderator)
0x0905  VOICE_CODEC_NEG    - Codec, bitrate, and SVC layer negotiation  {codec, spatial_layers, temporal_layers, target_bitrates[], dependency_templates[]}
0x0906  STAGE_REQUEST      - Request to speak
0x0907  STAGE_REQUEST_ACK  - Server acknowledges request  {approved}
0x0908  STAGE_INVITE       - Invite audience member to speak  {user_id}
0x0909  STAGE_INVITE_ACK   - User accepts/declines invite  {accepted}
0x090A  STAGE_REVOKE       - Move speaker to audience  {user_id}
0x090B  STAGE_REVOKE_ACK   - Confirms revocation
0x090C  STAGE_TOPIC        - Set stage topic  {topic}
0x090D-0x09FF  [reserved]
```

### 0x0A00-0x0AFF: Media (DATAGRAM -- unreliable)

```
0x0A00  MEDIA_AUDIO        - Audio frame
0x0A01  MEDIA_VIDEO        - Video frame
0x0A02  MEDIA_SCREEN       - Screen share frame
0x0A03  MEDIA_FEC          - Forward error correction  [reserved, not yet specified]
0x0A04  MEDIA_RTCP_FB      - TWCC feedback report  {base_seq, packet_status[], recv_deltas[], reference_time}
0x0A05-0x0AFF  [reserved]
```

### 0x0B00-0x0BFF: File Transfer

```
0x0B00  FILE_UPLOAD        - {file_id, feed_id, name, size, mime, sha256}
0x0B01  FILE_UPLOAD_ACK    - Server accepts upload  {file_id}  (or ERROR on rejection)
0x0B02  FILE_DATA          - {file_id, offset, data}
0x0B03  FILE_COMPLETE      - Upload done, checksum verified
0x0B04  FILE_CANCEL        - Abort
0x0B05  FILE_RESUME        - Resume {file_id, from_offset}
0x0B06  FILE_PROGRESS      - Server -> client: progress update  {file_id, bytes_received}
0x0B07-0x0BFF  [reserved]
```

### 0x0C00-0x0CFF: Embeds and Custom Content

```
0x0C00  EMBED_RESOLVE_REQ  - Server resolves URL -> preview
0x0C01  EMBED_RESOLVE_RES  - {title, description, image?, video?}
0x0C02  EMOJI_LIST         - List custom emoji
0x0C03  EMOJI_LIST_RES     - {emoji[]}
0x0C04  EMOJI_CREATE       - {name, image_data}
0x0C05  EMOJI_DELETE       - {emoji_id}
0x0C06  STICKER_LIST       - List server stickers
0x0C07  STICKER_LIST_RES   - {stickers[]}
0x0C08  STICKER_CREATE     - Upload sticker
0x0C09  STICKER_DELETE     - Delete sticker
0x0C0A-0x0CFF  [reserved]
```

### 0x0D00-0x0DFF: Bots and Webhooks

Bots are full protocol participants -- they connect via QUIC, authenticate with a bot token, and use the same message types as regular clients. They can join voice rooms, send messages, and respond to interactions. Command registration and interaction routing are the only bot-specific protocol features.

Webhooks are stateless HTTP endpoints for fire-and-forget message posting (CI/CD alerts, notifications). They cannot receive events or join voice rooms.

```
0x0D00  WEBHOOK_CREATE     - {feed_id, name, avatar?}
0x0D01  WEBHOOK_UPDATE     - {webhook_id, name?, avatar?}
0x0D02  WEBHOOK_DELETE     - {webhook_id}
0x0D03  WEBHOOK_EXECUTE    - Post message via webhook  {webhook_id, body, embeds?}
0x0D04  INTERACTION        - Server -> bot: slash command / button / menu  {type, command?, component_id?, user_id, feed_id, params?}
0x0D05  INTERACTION_RESP   - Bot -> server: response  {body?, embeds?, components?}
0x0D06  CMD_REGISTER       - Bot registers slash commands  {commands[]}
0x0D07  CMD_DEREGISTER     - Bot removes commands  {command_names[]}
0x0D08  CMD_LIST           - List registered commands for server
0x0D09  CMD_LIST_RES       - {commands[]}
0x0D0A-0x0DFF  [reserved]
```

### 0x0E00-0x0EFF: E2E Encryption (DMs only)

All DMs (1:1 and group) use MLS (Message Layer Security, RFC 9420) with a per-user shared key. Each user has one MLS leaf key shared across all their devices. This means senders encrypt once per recipient, not once per device.

```
0x0E00  KEY_PREKEY_UPLOAD      - Upload signed prekeys to server  {identity_key, signed_prekey, one_time_prekeys[]}
0x0E01  KEY_PREKEY_REQ         - Request a user's prekey bundle  {user_id}
0x0E02  KEY_PREKEY_RES         - Prekey bundle response  {user_id, identity_key, signed_prekey, one_time_prekey?}
0x0E03  KEY_MLS_WELCOME        - MLS Welcome message (invites user into group)
0x0E04  KEY_MLS_COMMIT         - MLS Commit (add/remove/update triggers epoch change)
0x0E05  KEY_MLS_PROPOSAL       - MLS Proposal (suggest add/remove/update)
0x0E06  KEY_DEVICE_ADD         - Register new device  {device_id, device_name}
0x0E07  KEY_DEVICE_REMOVE      - Remove device  {device_id}
0x0E08  KEY_DEVICE_LIST_NOTIFY - Server notifies all devices of device list change  {devices[]}
0x0E09  KEY_DEVICE_PAIR_REQ    - New device requests pairing  {device_name, method: cpace|qr, temp_public_key? (QR only)}
0x0E0A  KEY_DEVICE_PAIR_PROMPT - Server -> existing device  {device_name, ip, location, pair_id}
0x0E0B  KEY_DEVICE_PAIR_RES    - Existing device approves/denies  {pair_id, approved}
0x0E0C  KEY_BACKUP_UPLOAD      - Store passphrase-encrypted key blob on server
0x0E0D  KEY_BACKUP_DOWNLOAD    - Retrieve encrypted key blob (after auth)
0x0E0E  KEY_BACKUP_DOWNLOAD_RES - Encrypted key blob response  {encrypted_blob}
0x0E0F  KEY_RESET              - Generate new leaf key, invalidate all DM sessions
0x0E10  KEY_RESET_NOTIFY       - Server -> contacts: user's key has changed
0x0E11  KEY_CPACE_ISI          - CPace initiator share  {pair_id, isi_data (Ya = g^ya)}
0x0E12  KEY_CPACE_RSI          - CPace responder share  {pair_id, rsi_data (Yb = g^yb)}
0x0E13  KEY_CPACE_CONFIRM      - CPace key confirmation  {pair_id, confirm (HMAC)}
0x0E14  KEY_CPACE_LEAF_TRANSFER - Encrypted leaf key via CPace session  {pair_id, encrypted_leaf_key, nonce}
0x0E15-0x0EFF  [reserved]
```

### 0x0F00-0x0FFF: Moderation and Audit

```
0x0F00  REPORT_CREATE      - {reported_user_id, dm_id, messages[], reason, description?}
0x0F01  REPORT_ACK         - Server confirms report received  {report_id}
0x0F02  REPORT_LIST_REQ    - Admin: list reports  {status?, cursor?}
0x0F03  REPORT_LIST_RES    - {reports[], cursor?}
0x0F04  REPORT_RESOLVE     - Admin: resolve report  {report_id, action: dismiss|warn|kick|ban}
0x0F05  AUDIT_LOG_REQ      - Admin: query audit log  {event_type?, actor_id?, target_id?, before?, after?, limit?}
0x0F06  AUDIT_LOG_RES      - {entries[], cursor?}
0x0F07  AUTH_2FA_ADMIN_RESET     - Admin resets user's 2FA (requires MANAGE_2FA)  {target_user_id, reason?}
0x0F08  AUTH_2FA_ADMIN_RESET_RES - Admin reset result  {success}
0x0F09-0x0FFF  [reserved]
```

### 0x1000-0x10FF: Federation (server-to-server)

These messages are used exclusively for server-to-server communication. Clients never send or receive FED_ messages. The client protocol is identical regardless of whether the recipient is local or federated.

```
0x1000  FED_HELLO           - Server-to-server handshake  {origin_domain, signature, capabilities}
0x1001  FED_HELLO_ACK       - Federation handshake response  {verified, capabilities}
0x1002  FED_PREKEY_REQ      - Fetch remote user's prekey bundle  {user@domain}
0x1003  FED_PREKEY_RES      - Prekey bundle response
0x1004  FED_MSG_RELAY       - Relay E2EE DM blob  {from_user@domain, to_user@domain, opaque_blob}
0x1005  FED_PRESENCE_SUB    - Subscribe to remote user presence  {user@domain}
0x1006  FED_PRESENCE_NOTIFY - Remote user presence update  {user@domain, status, activity?}
0x1007  FED_USER_LOOKUP     - Fetch remote user profile  {user@domain}
0x1008  FED_USER_LOOKUP_RES - Profile response  {display_name, avatar_url, bio}
0x1009  FED_JOIN_REQ        - User wants to join remote server  {user@domain, invite_code?}
0x100A  FED_JOIN_RES        - Join response  {federation_token, server_info}
0x100B  FED_TYPING          - Relay typing indicator for DMs  {from_user@domain, to_user@domain}
0x100C  FED_DM_READ         - Relay read receipt for DMs  {from_user@domain, to_user@domain, up_to_msg_id}
0x100D  FED_BLOCK_NOTIFY    - Courtesy notification that a server has been blocked  {reason?}
0x100E  FED_ERROR           - Federation-specific error  {code, reason}
0x100F-0x10FF  [reserved]
```

### 0x1100-0xFFFF: Unallocated

The `0x1100-0xFFFF` range is available for future categories, providing space for up to 238 additional 256-slot blocks.

## 8. Media Frame (DATAGRAM)

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

Example configuration for video (actual values are negotiated via `VOICE_CODEC_NEG`):

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

The dependency descriptor is negotiated during `VOICE_CODEC_NEG` (0x0905) and sent on every video/screen packet when the HAS_DEP_DESC flag is set.

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
User A                        Server (SFU)                User B, C
  |                               |                          |
  +-- VOICE_JOIN(room) ---------->|                          |
  |<-- VOICE_STATE(members[]) ---|-- VOICE_STATE(A joined)->|
  |                               |                          |
  |-- VOICE_CODEC_NEG ----------->|   [negotiate SVC layers] |
  |<-- VOICE_CODEC_NEG -----------|                          |
  |                               |                          |
  |== MEDIA_AUDIO ===============>|== forward to B, C ======>|
  |== MEDIA_VIDEO (S0+S1+S2) ===>|== S0+S1+S2 => B (good bw)|
  |                               |== S0 =======> C (low bw) |
  |                               |                          |
  |-- VOICE_LEAVE(room) -------->|-- VOICE_STATE(A left) -->|
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

Sent via `MEDIA_RTCP_FB` (0x0A04):

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

Beyond TWCC, `MEDIA_RTCP_FB` also carries:

| Signal | Purpose |
|---|---|
| NACK | Request retransmission of specific sequence numbers (video only, selective) |
| PLI (Picture Loss Indication) | Request new keyframe from sender |

## 9. Server Hierarchy

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

## 10. Permissions

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
2. OR together all of user's role .
3. Apply feed/room @everyone overrides (allow/deny)
4. Apply feed/room role overrides (OR allow, OR deny)
5. Apply feed/room user-specific override
6. Administrator bypasses everything
```

## 11. File Transfer

```
Sender                          Server                     Feed
  |                               |                          |
  +-- FILE_UPLOAD {feed, meta} -->|                          |
  |<-- FILE_UPLOAD_ACK {file_id} -|  (or ERROR if rejected)  |
  |== open uni stream ===========>|                          |
  |-- FILE_DATA (chunk 0) ------>|  [store to disk/CDN]     |
  |-- FILE_DATA (chunk 1) ------>|                          |
  |-- FILE_COMPLETE ------------>|                          |
  |                               +-- MSG_DELIVER {          |
  |<-- MSG_ACK ------------------|    attachment: {url,     ->
  |                               |    name, size, mime}}    |
```

- Files upload to server, get stored, served back as attachment URLs
- `FILE_RESUME` for interrupted uploads
- If a file exceeds the server's configured limits, the server returns `ERROR(FILE_TOO_LARGE)`

## 12. Presence

Everyone connected to the server sees presence for all other members -- the server broadcasts automatically.

```
Client                                Server
  |                                      |
  |-- PRESENCE_UPDATE {online} -------->|
  |                                      +-- PRESENCE_NOTIFY {user, online} -> all
  |                                      |
  |  [idle timeout]                       |
  |                                      +-- PRESENCE_NOTIFY {user, idle} -> all
  |                                      |
  |-- TYPING_START {feed_id} ---------->|
  |                                      +-- TYPING_START {user, feed_id} -> viewers
```

| State | Meaning |
|---|---|
| online | Active |
| idle | Idle (e.g., >5 min) |
| dnd | Do not disturb |
| invisible | Hidden but connected |
| offline | Disconnected |

## 13. E2E Encryption

All DMs (1:1 and group) use MLS (Message Layer Security, RFC 9420). Server feeds and rooms remain trusted and are not E2E encrypted.

### Why MLS for Everything

MLS uses epoch-based keys. Within an epoch, all group members share a symmetric key. This solves multi-device naturally -- all of a user's devices share the same MLS leaf private key and can decrypt any message in the current epoch without per-message state synchronization.

| Property | Benefit |
|---|---|
| Epoch-based keys | No per-message ratchet sync between devices |
| Same protocol for 1:1 and group | One code path to implement and audit |
| Forward secrecy at epoch boundaries | Compromised key cannot decrypt past epochs |
| Efficient add/remove | Tree-based key agreement scales to group DMs |

### MLS DM Flow (1:1 and group, same protocol)

```
Alice                            Server                    Bob (+ others)
  |                                |                              |
  |-- KEY_PREKEY_REQ(bob) -------->|                              |
  |<-- KEY_PREKEY_RES -------------|                              |
  |                                |                              |
  |  [Create MLS group,            |                              |
  |   generate GroupInfo,          |                              |
  |   create Welcome for Bob]      |                              |
  |                                |                              |
  |-- KEY_MLS_COMMIT ------------->|-- relay to all ------------->|
  |-- KEY_MLS_WELCOME(bob) ------->|-- relay to bob ------------->|
  |                                |                              |
  |  [Both now share epoch key]    |   [Bob processes Welcome,   |
  |                                |    derives epoch key]        |
  |                                |                              |
  |-- MSG_SEND {e2e, ciphertext} ->|-- relay (opaque blob) ----->|
  |                                |                              |
  |  [Epoch changes on member add/remove, not per message]        |
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

The primary method when the user has an existing device. Uses CPace (RFC 9497), a password-authenticated key exchange, to bind a user-entered short code into the key derivation. This prevents the server from performing a MITM attack — the server relays the CPace messages but cannot derive the session key without knowing the code.

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
New Device                       Server                   Existing Device
  |                                |                              |
  |-- AUTH {user, password} ------>|                              |
  |<-- AUTH_OK --------------------|                              |
  |   (with 2FA if enabled)        |                              |
  |                                |                              |
  |-- KEY_DEVICE_PAIR_REQ {       |                              |
  |     device_name,               |                              |
  |     method: cpace              |                              |
  |   } -------------------------->|                              |
  |                                |-- KEY_DEVICE_PAIR_PROMPT --->|
  |                                |   {device_name,              |
  |                                |    ip, location, pair_id}    |
  |                                |                              |
  |                                |   [existing device displays  |
  |                                |    6-digit code, user        |
  |                                |    approves pairing]         |
  |                                |                              |
  |                                |<-- KEY_DEVICE_PAIR_RES ------|
  |                                |    {pair_id, approved: true} |
  |<-- relay approval -------------|                              |
  |                                |                              |
  |  [user enters 6-digit code     |                              |
  |   on new device]               |                              |
  |                                |                              |
  |  === CPace key exchange (code-bound) ===                      |
  |                                |                              |
  |-- KEY_CPACE_ISI {pair_id,     |                              |
  |     isi_data: Ya=g^ya} ------>|-- relay ------------------>  |
  |                                |                              |
  |                                |<-- KEY_CPACE_RSI {pair_id,  |
  |  <-- relay --------------------|     rsi_data: Yb=g^yb} -----|
  |                                |                              |
  |  [both sides derive shared     |  [both sides derive shared  |
  |   key from CPace + code]       |   key from CPace + code]    |
  |                                |                              |
  |-- KEY_CPACE_CONFIRM ---------->|-- relay ------------------>  |
  |                                |<-- KEY_CPACE_CONFIRM --------|
  |  <-- relay --------------------|                              |
  |                                |                              |
  |  [verify mutual confirmation]  |  [verify mutual confirmation]|
  |                                |                              |
  |                                |<-- KEY_CPACE_LEAF_TRANSFER --|
  |  <-- relay --------------------|   {encrypted_leaf_key, nonce}|
  |                                |   (AES-256-GCM with          |
  |  [decrypt with cpace_key]      |    cpace-derived key)        |
  |  [now has MLS leaf key]        |                              |
  |                                |                              |
  |-- KEY_DEVICE_ADD ------------->|-- KEY_DEVICE_LIST_NOTIFY --->|
  |-- KEY_PREKEY_UPLOAD ---------->|                              |
```

The server relays all CPace messages but cannot derive the session key because it does not know the 6-digit code displayed on the existing device. If the server swaps CPace shares, the derived keys won't match and confirmation will fail.

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
  |  <-------- encrypted blob relayed via server --------    |
  |                                                          |
  |  [decrypt, now has MLS leaf key]                         |
```

### Authentication Security

#### Auth with 2FA

When a user has 2FA enabled, the server issues an AUTH_CHALLENGE after receiving valid credentials. The client must respond with a valid second factor before receiving AUTH_OK.

```
Client                                          Server
  |                                                |
  |-- AUTH {method, credentials} ----------------->|
  |                                                |  [credentials valid,
  |                                                |   2FA enabled]
  |<-- AUTH_CHALLENGE {                            |
  |      type: 2fa_required,                       |
  |      available_methods: [totp, webauthn],      |
  |      relying_party_id?                         |
  |   } ------------------------------------------|
  |                                                |
  |-- AUTH_2FA_RESPOND {                           |
  |     method: totp,                              |
  |     totp_code: "123456"                        |
  |   } ----------------------------------------->|
  |                                                |
  |<-- AUTH_OK {user_id, session_id, ...} ---------|
```

If the 2FA response is invalid, the server returns `ERROR(2FA_INVALID_CODE)`. Recovery codes can be used via `AUTH_2FA_RECOVERY_USE` as an alternative.

**Note:** 2FA challenges are only issued for `AUTH_METHOD_PASSWORD` logins. `AUTH_METHOD_TOKEN` (session resumption) and `AUTH_METHOD_BOT_TOKEN` skip 2FA since the original authentication already verified the second factor.

#### Passwordless WebAuthn Login

Users with a registered WebAuthn credential can authenticate without a password:

```
Client                                          Server
  |                                                |
  |-- AUTH {method: webauthn,                      |
  |     credentials: WebAuthnLoginAssertion {      |
  |       username, client_data_json,              |
  |       authenticator_data, signature,           |
  |       credential_id, user_handle?              |
  |     }                                          |
  |   } ----------------------------------------->|
  |                                                |
  |<-- AUTH_OK {user_id, session_id, ...} ---------|
```

If the assertion is invalid, the server returns `ERROR(WEBAUTHN_INVALID)`. If the credential ID is not found, the server returns `ERROR(WEBAUTHN_CREDENTIAL_NOT_FOUND)`.

#### 2FA Setup: TOTP

```
Client                                          Server
  |                                                |
  |-- AUTH_2FA_SETUP_REQ {method: totp} ---------->|
  |                                                |
  |<-- AUTH_2FA_SETUP_RES {                        |
  |      method: totp,                             |
  |      setup_id,                                 |
  |      totp_secret (Base32),                     |
  |      totp_uri (otpauth://)                     |
  |   } ------------------------------------------|
  |                                                |
  |  [user scans QR / enters secret in            |
  |   authenticator app, gets a code]              |
  |                                                |
  |-- AUTH_2FA_SETUP_CONFIRM {                     |
  |     setup_id,                                  |
  |     totp_code: "123456"                        |
  |   } ----------------------------------------->|
  |                                                |
  |<-- AUTH_2FA_SETUP_CONFIRM_RES {                |
  |      success: true,                            |
  |      recovery_codes: ["XXXX-XXXX", ...]        |
  |   } ------------------------------------------|
```

**TOTP parameters:** SHA-1 hash, 6 digits, 30-second period, +/-1 window for clock skew.

#### 2FA Setup: WebAuthn

```
Client                                          Server
  |                                                |
  |-- AUTH_2FA_SETUP_REQ {method: webauthn} ------>|
  |                                                |
  |<-- AUTH_2FA_SETUP_RES {                        |
  |      method: webauthn,                         |
  |      setup_id,                                 |
  |      webauthn_creation_options (JSON)           |
  |   } ------------------------------------------|
  |                                                |
  |  [browser/platform creates credential]         |
  |                                                |
  |-- AUTH_2FA_SETUP_CONFIRM {                     |
  |     setup_id,                                  |
  |     webauthn_attestation,                      |
  |     credential_name: "YubiKey 5"               |
  |   } ----------------------------------------->|
  |                                                |
  |<-- AUTH_2FA_SETUP_CONFIRM_RES {                |
  |      success: true,                            |
  |      recovery_codes: ["XXXX-XXXX", ...]        |
  |   } ------------------------------------------|
```

#### Recovery Codes

On successful 2FA setup, the server returns 8 single-use recovery codes in the format `XXXX-XXXX`. These are stored hashed server-side (bcrypt or Argon2). Each code can be used exactly once via `AUTH_2FA_RECOVERY_USE` as a substitute for a 2FA response during authentication.

#### Admin 2FA Reset

Server admins with `MANAGE_2FA` permission (bit 37) can reset a user's 2FA via `AUTH_2FA_ADMIN_RESET`. This disables all 2FA methods for the target user and generates an audit log entry (`2fa.admin_reset`). The user must re-enroll 2FA themselves afterward.

```
Admin Client                                    Server
  |                                                |
  |-- AUTH_2FA_ADMIN_RESET {                       |
  |     target_user_id: 42,                        |
  |     reason: "User locked out"                  |
  |   } ----------------------------------------->|
  |                                                |  [verify MANAGE_MEMBERS perm,
  |                                                |   disable all 2FA for user 42,
  |                                                |   write audit log entry]
  |<-- AUTH_2FA_ADMIN_RESET_RES {success: true} ---|
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
4. Upload encrypted blob via KEY_BACKUP_UPLOAD
5. User stores the 12 words securely

Recovery flow:

```
New Device                       Server
  |                                |
  |-- AUTH {user, password} ------>|  (gate 1: proves identity)
  |<-- AUTH_OK --------------------|
  |                                |
  |-- KEY_BACKUP_DOWNLOAD -------->|
  |<-- {encrypted_blob} -----------|
  |                                |
  |  [user enters recovery phrase] |
  |  [K = Argon2(phrase, salt)]    |
  |  [decrypt blob -> leaf key]    |  (gate 2: proves key ownership)
  |                                |
  |-- KEY_DEVICE_ADD ------------->|
  |-- KEY_PREKEY_UPLOAD ---------->|
```

### Key Reset (no recovery possible)

If a user has lost all devices AND forgotten their recovery passphrase:

1. User authenticates and triggers KEY_RESET
2. Server generates KEY_RESET_NOTIFY to all DM contacts
3. Contacts see: "Alice's security key has changed"
4. All existing MLS group states with Alice are invalidated
5. New DM sessions must be re-established
6. Old encrypted message history is unreadable

### Safety Numbers

Users can verify each other's identity keys out-of-band. Clients MUST compute safety numbers as follows to ensure consistent verification across implementations:

```
fingerprint = SHA-256(sort(alice_identity_key, bob_identity_key))

Displayed as 12 groups of 5 digits:
  37281 48103 59274 10384
  92847 38291 04827 19384
  28471 93827 48291 03847

Or as a QR code encoding both identity keys.
```

Safety numbers change when a user does KEY_RESET. Contacts are warned.

### Federated Key Exchange (server-to-server)

For cross-server DMs, servers relay prekey requests transparently:

```
Server X                          Server Y
  |                                  |
  |-- FED_PREKEY_REQ {user_id} ---->|
  |<-- FED_PREKEY_RES {bundle} -----|
  |                                  |
  |-- FED_MSG_RELAY {               |
  |     from, to, opaque_blob      |
  |   } --------------------------->|
```

Clients see the same KEY_PREKEY_REQ/RES and MSG_SEND/DELIVER regardless of whether the recipient is local or federated.

## 14. Connection Lifecycle

```
Client                                          Server
  |                                                |
  |-- QUIC handshake (0-RTT if resuming) -------->|
  |-- [Stream 0] HELLO {v=1, min=1, caps} ------>|
  |<-- HELLO_ACK {v=1, min=1, caps, name, icon,  |
  |     time} ------------------------------------|
  |-- [Stream 2] AUTH {token} ------------------>|
  |                                                |
  |  [if 2FA enabled:]                             |
  |<-- AUTH_CHALLENGE {type: 2fa_required,         |
  |     available_methods} -----------------------|
  |-- AUTH_2FA_RESPOND {method, code/assertion} ->|
  |                                                |
  |<-- AUTH_OK {user_id, session_id,              |
  |     display_name, roles[], is_bot} ----------|
  |                                                |
  |-- PRESENCE_UPDATE {online} ------------------>|
  |-- FEED_ROOM_LIST ---------------------------->|
  |<-- FEED_ROOM_LIST_RES {categories[], feeds[], rooms[]} |
  |-- MSG_HISTORY_REQ (per feed as needed) ------>|
  |<-- PRESENCE_NOTIFY x N (who is online) -------|
  |                                                |
  |  ... normal operation ...                      |
  |                                                |
  |-- GOODBYE ----------------------------------->|
  |-- QUIC CONNECTION_CLOSE --------------------->|
```

**Passwordless WebAuthn variant:** The client sends `AUTH {method: webauthn, credentials: WebAuthnLoginAssertion}` in place of token/password auth. If valid, the server responds directly with `AUTH_OK` — no separate challenge step is needed since the assertion itself is the proof of identity.

### Reconnection Sync

When a client reconnects after being offline, it uses `SYNC_REQ` to fetch state deltas instead of re-fetching everything:

```
Client                                          Server
  |                                                |
  |-- QUIC handshake (0-RTT resumption) -------->|
  |-- HELLO / AUTH (as above) ------------------>|
  |<-- AUTH_OK ----------------------------------|
  |                                                |
  |-- SYNC_REQ {                                  |
  |     since_timestamp: <last known>,            |
  |     categories: [MEMBERS, ROLES, FEEDS]       |
  |   } ---------------------------------------->|
  |<-- SYNC_RES {                                 |
  |     events: [                                  |
  |       {type: "member.join", ...},              |
  |       {type: "role.update", ...},              |
  |       {type: "feed.create", ...}               |
  |     ],                                         |
  |     server_timestamp                           |
  |   } ------------------------------------------|
  |                                                |
  |-- MSG_HISTORY_REQ (per feed as needed) ------>|
  |                                                |
```

If `since_timestamp` is too far in the past (server-configured retention), the server returns a `SYNC_RES` with an empty events list and the client falls back to full state fetch (`FEED_ROOM_LIST`, `MEMBER_LIST_REQ`, etc.).

## 15. Priority and QoS

| Priority | Traffic |
|---|---|
| 0 (highest) | Room signaling (VOICE_JOIN, etc.) |
| 1 | Voice audio datagrams |
| 2 | Video datagrams |
| 3 | Control (presence, typing) |
| 4 | Text messages |
| 5 | Screen share |
| 6 | Embed resolution / thumbnails |
| 7 (lowest) | File uploads |

## 16. Error Codes

```
0x0000  OK
0x0001  UNKNOWN_ERROR
0x0002  PROTOCOL_VERSION_MISMATCH
0x0003  AUTH_FAILED
0x0004  AUTH_EXPIRED
0x0005  RATE_LIMITED              {retry_after_ms}
0x0006  FORBIDDEN                 {missing_permission}
0x0007  USER_NOT_FOUND
0x0008  SPACE_NOT_FOUND
0x0009  MESSAGE_NOT_FOUND
0x000A  MESSAGE_TOO_LARGE
0x000B  FILE_TOO_LARGE
0x000C  UNSUPPORTED_CODEC
0x000D  ROOM_FULL
0x000E  ALREADY_IN_VOICE
0x000F  INVITE_EXPIRED
0x0010  INVITE_INVALID
0x0011  BANNED
0x0012  ROLE_HIERARCHY            {cannot act on higher role}
0x0013  SPACE_TYPE_MISMATCH
0x0014  SERVER_FULL
0x0015  E2E_KEY_MISMATCH
0x0016  PREKEY_EXHAUSTED
0x0017  DEVICE_LIMIT_REACHED
0x0018  DM_PERMISSION_DENIED      {recipient has restricted DMs}
0x0019  USER_BLOCKED              {you are blocked by this user}
0x001A  REPORT_NOT_FOUND
0x001B  DEVICE_PAIR_DENIED        {pairing request was rejected}
0x001C  DEVICE_PAIR_EXPIRED       {pairing request timed out}
0x001D  KEY_BACKUP_NOT_FOUND      {no recovery backup exists}
0x001E  FEDERATION_UNAVAILABLE    {remote server unreachable or federation closed}
0x001F  FEDERATION_DENIED         {remote server denied federation}
0x0020  CMD_ALREADY_REGISTERED    {command name conflicts with existing registration}
0x0021  CMD_NOT_FOUND             {command does not exist}
0x0022  INTERACTION_EXPIRED       {interaction response took too long}
0x0023  WEBHOOK_NOT_FOUND         {webhook does not exist}
0x0024  WEBHOOK_TOKEN_INVALID     {webhook token is invalid}
0x0025  2FA_REQUIRED              {two-factor authentication required}
0x0026  2FA_INVALID_CODE          {2FA code is incorrect or expired}
0x0027  2FA_ALREADY_ENABLED       {2FA method is already enrolled}
0x0028  2FA_NOT_ENABLED           {2FA is not enabled for this account}
0x0029  2FA_SETUP_EXPIRED         {2FA setup session has expired}
0x002A  2FA_RECOVERY_EXHAUSTED    {all recovery codes have been used}
0x002B  CPACE_FAILED              {CPace key exchange failed (confirmation mismatch)}
0x002C  CPACE_EXPIRED             {CPace pairing session has expired}
0x002D  WEBAUTHN_INVALID          {WebAuthn assertion verification failed}
0x002E  WEBAUTHN_CREDENTIAL_NOT_FOUND  {WebAuthn credential ID not recognized}
0x002F-0x00FF  [reserved]
```

## 17. DM Moderation

Moderation uses a layered approach that balances privacy with user safety: permission controls, blocking, rate limiting, voluntary reporting, and metadata monitoring.

### DM Permission Controls

Users control who can DM them. Settings are stored server-side per user and enforced by the server when a `DM_OPEN` or `DM_OPEN_GROUP` is received.

| Setting | Value | Description |
|---|---|---|
| `EVERYONE` | 0 | Anyone on the server can DM |
| `FRIENDS_ONLY` | 1 | Only users on their friend list |
| `MUTUAL_SERVERS` | 2 | Only users sharing a server (includes federated members) |
| `NOBODY` | 3 | DMs completely disabled |

Clients fetch and update settings via `DM_SETTINGS_GET` (0x080A) / `DM_SETTINGS_UPDATE` (0x080C). Server responds with `DM_SETTINGS_RES` (0x080B). If a user attempts to DM a recipient whose settings disallow it, the server returns `ERROR(DM_PERMISSION_DENIED)`.

### User Blocking

When a user blocks another:

- All existing DMs between them are effectively closed
- Blocked user cannot open new DMs
- Blocked user cannot see blocker's presence or activity
- Existing messages remain on blocker's client (they can delete locally)

If the blocked user attempts to open a DM or send a message, the server returns `ERROR(USER_BLOCKED)`.

### Rate Limiting

Servers SHOULD rate-limit DM operations and return `ERROR(RATE_LIMITED)` with `retry_after_ms` when limits are exceeded. Example categories and values:

| Limit | Example | Description |
|---|---|---|
| Max new DM conversations per hour | 10 | Caps DM_OPEN / DM_OPEN_GROUP |
| Max messages per DM per minute | 30 | Per-DM send rate |
| Max total DM messages per hour | 200 | Across all DMs |
| New account cooldown period | varies | Stricter limits for new accounts |

### Client-Side Reporting

Since the server cannot read E2EE DMs, reporting is voluntary and initiated by the recipient. This preserves E2EE -- only the recipient can choose to reveal content.

**Report flow:**

1. Recipient selects messages to report in their client
2. Client decrypts and forwards plaintext + metadata to server via `REPORT_CREATE` (0x0F00)
3. Server stores the report and responds with `REPORT_ACK` (0x0F01) containing a `report_id`
4. Admins with `VIEW_REPORTS` permission query reports via `REPORT_LIST_REQ` (0x0F02)
5. Admins resolve reports via `REPORT_RESOLVE` (0x0F04) with an action

**REPORT_CREATE payload:**

| Field | Type | Description |
|---|---|---|
| reporter_id | user_id | Reporting user |
| reported_user_id | user_id | User being reported |
| dm_id | dm_id | DM containing the messages |
| messages[] | array | Decrypted message content + timestamps |
| reason | enum | Reason category |
| description | string? | Optional free-text description |

**Reason categories:**

| Category | Description |
|---|---|
| `harassment` | Targeted harassment or bullying |
| `spam` | Unsolicited bulk messages |
| `illegal_content` | Content that violates law |
| `threats` | Threats of violence or harm |
| `other` | Other reason (use description) |

**Resolve actions:**

| Action | Effect |
|---|---|
| `dismiss` | Close report, no action taken |
| `warn` | Send warning to reported user |
| `kick` | Kick reported user from server |
| `ban` | Ban reported user from server |

```
Recipient                       Server                          Admin
  |                               |                               |
  |  [selects messages to report] |                               |
  |  [client decrypts content]    |                               |
  |                               |                               |
  |-- REPORT_CREATE {             |                               |
  |     reported_user_id,         |                               |
  |     dm_id,                    |                               |
  |     messages[],               |                               |
  |     reason,                   |                               |
  |     description?              |                               |
  |   } ------------------------->|  [store report]               |
  |<-- REPORT_ACK {report_id} ---|                               |
  |                               |                               |
  |                               |<-- REPORT_LIST_REQ {status?} -|
  |                               |-- REPORT_LIST_RES {reports[]} >|
  |                               |                               |
  |                               |<-- REPORT_RESOLVE {           |
  |                               |     report_id,                |
  |                               |     action: dismiss|warn|     |
  |                               |             kick|ban          |
  |                               |   } --------------------------|
  |                               |  [execute action]             |
```

### Metadata Monitoring

The server can observe DM patterns without breaking encryption. No message content is accessed.

**Observable metadata:**

- Number of DMs opened per user per time period
- Message frequency per DM
- Rapid-fire DM opening to many users (spam pattern)

Servers MAY use this metadata for abuse detection. Admins with `VIEW_REPORTS` permission can see metadata reports but never message content.

## 18. Federation

Federation allows servers to communicate with each other, enabling cross-server DMs, presence, and server joining. The design follows email's model: DNS for discovery and authentication, domain-based identity, and layered abuse prevention.

### User Identity

Users are identified by email-style addresses:

```
alice@voxchat.example.com
  |         |
  user      server domain
```

For local operations (messages within the server), the short user_id (uint32) is used. The full `user@domain` form is used only for federation.

### DNS Records

Servers publish DNS records for discovery, authentication, and policy:

```
; Service discovery -- where to connect (like email MX records)
_vox._quic.example.com.     IN SRV  10 0 443 vox.example.com.

; Server public key -- for verifying signatures (like DKIM)
_voxkey.example.com.        IN TXT  "v=vox1; k=ed25519; p=<base64_public_key>"

; Federation policy -- open, allowlist, or closed (like DMARC)
_voxpolicy.example.com.     IN TXT  "v=vox1; federation=open; abuse=admin@example.com"

; Allowlist entries -- one record per allowed domain (when federation=allowlist)
servera.com._voxallow.example.com.    IN A  127.0.0.2
trusted.org._voxallow.example.com.    IN A  127.0.0.2
```

| Record | Purpose | Email Equivalent |
|---|---|---|
| `_vox._quic` SRV | Service discovery (host + port) | MX record |
| `_voxkey` TXT | Server signing key | DKIM |
| `_voxpolicy` TXT | Federation policy and abuse contact | DMARC |
| `<domain>._voxallow` A | Allowlist entries | N/A |

### Federation Policy

Published via `_voxpolicy` DNS TXT record:

| Policy | Behavior |
|---|---|
| `federation=open` | Accept federation from any server, subject to blocklists |
| `federation=allowlist` | Only federate with domains listed in `_voxallow` records |
| `federation=closed` | No federation |

### Server-to-Server Authentication

Two layers of authentication:

**1. mTLS (mutual TLS):** Both servers present certificates during the QUIC handshake. This verifies domain ownership at the transport level.

**2. DNS key signature (like DKIM):** The connecting server signs federation messages with its Ed25519 private key. The receiving server looks up the public key via `_voxkey` DNS TXT record and verifies the signature. This proves messages came from the domain's actual Vox server.

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
  |   [Server B looks up _voxkey.servera.com TXT]    |
  |   [Verifies signature against DNS public key]    |
  |                                                  |
  |<-- FED_HELLO_ACK {verified: true} ---------------|
  |                                                  |
  |  [Federation session established]                |
```

### What Gets Federated

| Feature | Federated | How |
|---|---|---|
| DMs (1:1 and group) | Yes | E2EE blob relay via FED_MSG_RELAY, servers cannot read content |
| User profile lookup | Yes | FED_USER_LOOKUP / FED_USER_LOOKUP_RES |
| Presence | Yes, for contacts | FED_PRESENCE_SUB / FED_PRESENCE_NOTIFY |
| Typing indicators (DMs) | Yes | FED_TYPING relay |
| Read receipts (DMs) | Yes | FED_DM_READ relay |
| Prekey exchange (E2EE) | Yes | FED_PREKEY_REQ / FED_PREKEY_RES |
| Server joining | Yes | FED_JOIN_REQ, then direct QUIC connection |
| File transfer (DMs) | Yes | E2EE blob relay |
| Server feeds and rooms | No | Connect directly to the server |

### Federated DM Flow

The client protocol is identical regardless of federation. The home server wraps and unwraps transparently:

```
Alice@ServerA              ServerA              ServerB              Bob@ServerB
  |                          |                     |                     |
  |-- MSG_SEND {             |                     |                     |
  |     dm_id, ciphertext    |                     |                     |
  |   } ------------------->|                     |                     |
  |                          |  [wrap in FED       |                     |
  |                          |   envelope, sign]   |                     |
  |                          |                     |                     |
  |                          |-- FED_MSG_RELAY {   |                     |
  |                          |   from: alice@a.com,|                     |
  |                          |   to: bob@b.com,    |                     |
  |                          |   opaque_blob,      |                     |
  |                          |   signature         |                     |
  |                          |  } --------------->|                     |
  |                          |                     |  [verify sig]       |
  |                          |                     |  [reconstruct       |
  |                          |                     |   local msg]        |
  |                          |                     |                     |
  |                          |                     |-- MSG_DELIVER {    |
  |                          |                     |   author: alice@   |
  |                          |                     |    a.com,          |
  |                          |                     |   ciphertext,      |
  |                          |                     |   federated: true  |
  |                          |                     |  } --------------->|
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
  |  [Alice connects directly to ServerB]          |
  |                                                |
  |======= direct QUIC connection ================>|
  |-- AUTH {federation_token} -------------------->|
  |<-- AUTH_OK {guest_user_id, roles[]} ----------|
```

Alice authenticates with her home server, which vouches for her identity. She then connects directly to Server B for real-time participation. Her identity remains `alice@servera.com`.

### Security: Message Reconstruction

The receiving server MUST reconstruct local messages from validated federation data. Never blindly unwrap.

**Rules:**

| Rule | Reason |
|---|---|
| Never trust sender-provided IDs | Server generates its own msg_id, timestamp, feed assignment |
| Verify domain matches connection | `from: alice@evil.com` must arrive on a verified `evil.com` connection |
| Tag all federated messages | Local code can distinguish federated vs local and restrict accordingly |
| Do not parse E2EE blobs | Server cannot and should not interpret encrypted content |
| Federated guests cannot access admin paths | No role management, no feed/room management, no server settings |
| Rate limit per federation peer | Even verified servers get throttled |

### Abuse Prevention

Layered approach following email's model:

#### 1. DNS Verification (prevents spoofing)

Server signatures are verified against DNS public keys. No valid signature = no federation. Prevents impersonation.

#### 2. Local Blocklist (admin-managed)

Server admin maintains a blocklist of domains. All federation from blocked domains is rejected at connection time.

When a server is blocked, a courtesy `FED_BLOCK_NOTIFY` is sent to inform the remote server.

#### 3. DNS Blocklists (community-maintained, opt-in)

Shared blocklists using DNS lookups, like email's DNSBL (Spamhaus, etc.):

```
Incoming federation from sketchyserver.net:

  DNS query: sketchyserver.net.voxblock.community.org  A?
  -> 127.0.0.2 = blocked, reject connection
  -> NXDOMAIN = not listed, proceed
```

#### 4. Rate Limiting Per Peer

Servers SHOULD rate-limit federation operations per remote domain and return `FED_ERROR(FED_RATE_LIMITED)` when limits are exceeded. Example categories and values:

| Limit | Example | Description |
|---|---|---|
| Max new DM relays per hour per peer | 100 | Caps FED_MSG_RELAY from a single domain |
| Max presence subscriptions per peer | 500 | Caps FED_PRESENCE_SUB from a single domain |
| Max join requests per hour per peer | 20 | Caps FED_JOIN_REQ from a single domain |

#### 5. User-Level Controls

Existing DM permission settings apply to federated users:
- Users can restrict DMs to friends only (blocks unsolicited federated DMs)
- Users can block specific remote users (`alice@evil.com`)
- These controls are enforced by the local server before relaying

### Federation Error Codes

Sent via `FED_ERROR` (0x100E):

```
0xF000  FED_OK
0xF001  FED_UNKNOWN_ERROR
0xF002  FED_AUTH_FAILED              Signature verification failed
0xF003  FED_DNS_KEY_MISMATCH         DNS key does not match signature
0xF004  FED_POLICY_DENIED            Remote server's policy denies federation
0xF005  FED_NOT_ON_ALLOWLIST         Your domain is not on the allowlist
0xF006  FED_BLOCKED                  Your domain is on the blocklist
0xF007  FED_RATE_LIMITED             {retry_after_ms}
0xF008  FED_USER_NOT_FOUND           Remote user does not exist
0xF009  FED_INVITE_INVALID           Invite code is invalid or expired
0xF00A  FED_INVITE_EXPIRED           Invite code has expired
0xF00B  FED_SERVER_FULL              Remote server is at capacity
0xF00C-0xF0FF  [reserved]
```

## 19. Bots and Webhooks

### Bots

Bot permissions are handled through the existing role system -- the server admin assigns roles to the bot like any other member. This is a server configuration concern, not a protocol-level feature.

#### Bot Authentication

```
Bot                              Server
  |                                |
  |-- QUIC connect --------------->|
  |-- HELLO {v=1, caps} --------->|
  |<-- HELLO_ACK ------------------|
  |-- AUTH {method: bot_token,     |
  |    token: "bot.xxx.yyy"} ---->|
  |<-- AUTH_OK {user_id,           |
  |    session_id, roles[],        |
  |    is_bot: true} --------------|
  |                                |
  |-- CMD_REGISTER {commands} --->|   [register slash commands]
  |-- PRESENCE_UPDATE {online} -->|
  |                                |
```

#### Slash Command Flow

Bots register commands on connect. The server intercepts matching user input and routes it as an `INTERACTION`:

```
User                          Server                         Bot
  |                              |                             |
  |-- MSG_SEND {feed_id,        |                             |
  |    "/roll 20"} ------------>|                             |
  |                              |  [match to bot's "roll"    |
  |                              |   command, parse params]    |
  |                              |                             |
  |                              |-- INTERACTION {            |
  |                              |    type: SLASH_COMMAND,     |
  |                              |    command: "roll",         |
  |                              |    user_id, feed_id,        |
  |                              |    params: {sides: "20"}   |
  |                              |  } ----------------------->|
  |                              |                             |
  |                              |<-- INTERACTION_RESP {      |
  |<-- MSG_DELIVER {             |    body: "Rolled: 17"      |
  |    "Rolled: 17"} -----------|  } <-----------------------|
```

The `/roll` input is intercepted by the server and never posted as a regular message. Other users see only the bot's response.

#### Component Interactions (Buttons and Menus)

Bots can attach interactive components to messages. When a user clicks, the server routes it back:

```
Bot                           Server                         User
  |                              |                             |
  |-- MSG_SEND {                |                             |
  |    body: "Pick a color",    |-- MSG_DELIVER ------------->|
  |    components: [             |   [rendered with buttons]   |
  |      {type: BUTTON,          |                             |
  |       id: "red",             |                             |
  |       label: "Red"},         |                             |
  |      {type: BUTTON,          |                             |
  |       id: "blue",            |                             |
  |       label: "Blue"}         |                             |
  |    ]} --------------------->|                             |
  |                              |                             |
  |                              |   [user clicks "Red"]       |
  |                              |<-- INTERACTION {           |
  |<-- INTERACTION {             |    type: BUTTON,            |
  |    type: BUTTON,             |    component_id: "red"     |
  |    component_id: "red",      |  } <-----------------------|
  |    user_id                   |                             |
  |  } <------------------------|                             |
  |                              |                             |
  |-- INTERACTION_RESP {        |                             |
  |    body: "You picked Red!", |-- MSG_DELIVER ------------->|
  |    ephemeral: true           |   [only visible to user]   |
  |  } ----------------------->|                             |
```

#### Voice Room Participation

Bots join voice rooms using the same protocol as clients:

```
Music Bot                      Server (SFU)              Users in Room
  |                               |                          |
  |-- VOICE_JOIN(room) --------->|                          |
  |<-- VOICE_STATE(members[]) --|-- VOICE_STATE(bot joined)>|
  |-- VOICE_CODEC_NEG --------->|                          |
  |                               |                          |
  |  [decode audio source,        |                          |
  |   encode to Opus,             |                          |
  |   send as MEDIA_AUDIO]       |                          |
  |                               |                          |
  |== MEDIA_AUDIO ===============>|== forward to users ====>|
  |                               |                          |
  |  [can also receive audio]     |                          |
  |<=============================|== MEDIA_AUDIO from users |
```

Use cases: music playback, recording, AI voice, speech-to-text, real-time translation, soundboards.

### Webhooks

| | Bot (QUIC) | Webhook (HTTP) |
|---|---|---|
| Connection | Persistent QUIC | Stateless HTTP POST |
| Receive events | Yes | No |
| Send messages | Yes | Yes |
| Slash commands | Yes | No |
| Component interactions | Yes | No |
| Voice/video rooms | Yes | No |
| Use case | Interactive, real-time, voice | CI/CD alerts, notifications |

#### Webhook Flow

```
External Service                 Server                      Feed
  |                                |                           |
  |-- POST /webhook/{id}/{token}  |                           |
  |   {body, embeds?} ----------->|                           |
  |                                |-- MSG_DELIVER {          |
  |<-- 200 OK --------------------|    author: webhook_name,  ->
  |                                |    body, embeds}          |
```

## 20. Audit Logging

The protocol defines the audit log entry format (`AuditLogEntry` in Section 6) and the query interface (`AUDIT_LOG_REQ` / `AUDIT_LOG_RES`). What gets logged, how long it's retained, and which events are enabled are server implementation decisions.

### Convention

Event types use dot-notation: `{category}.{action}`. The `event_type` field is a freeform string -- servers can define any events that make sense for their community. A few examples:

```
member.kick              {target_id, reason?}
role.assign              {role_id, target_id}
feed.delete              {feed_id, name}
message.bulk_delete      {feed_id, count}
invite.use               {code, target_id}
federation.block         {domain, reason?}
```

The `metadata` map on each entry carries event-specific key-value pairs (the `{...}` above). Servers choose what to include. Message content should not be stored in the audit log -- only IDs, names, and changes.

### Querying

Admins with `VIEW_AUDIT_LOG` permission query logs via `AUDIT_LOG_REQ` (0x0F05). Supports filtering by event type, actor, target, and time range. Results are paginated via cursor.

```
Admin Client                     Server
  |                                |
  |-- AUDIT_LOG_REQ {             |
  |     event_type: "member.*",   |
  |     after: <24h ago>,         |
  |     limit: 50                 |
  |   } ------------------------->|
  |                                |
  |<-- AUDIT_LOG_RES {            |
  |     entries: [...],            |
  |     cursor: "next_page_xyz"   |
  |   } --------------------------|
  |                                |
  |-- AUDIT_LOG_REQ {             |
  |     cursor: "next_page_xyz"   |   [next page]
  |   } ------------------------->|
  |<-- AUDIT_LOG_RES {...} -------|
```
