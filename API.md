# VoxProtocol HTTP v1: REST API Reference

This document defines the complete REST API surface for VoxProtocol HTTP v1. For the wire protocol (WebSocket gateway, media transport, E2E encryption, federation) see `PROTOCOL HTTP.md`.

## 1. REST API Conventions

### Base URL

All REST endpoints are prefixed with `/api/v1/`. For example:

```
https://vox.example.com/api/v1/feeds
```

### Authentication

All REST endpoints (except auth endpoints and webhook execution) require authentication via the `Authorization` header:

```
Authorization: Bearer {session_token}
Authorization: Bot {bot_token}
```

### Content Type

- Request bodies: `Content-Type: application/json` (except file uploads)
- File uploads: `Content-Type: multipart/form-data`
- Responses: `Content-Type: application/json`

### Pagination

List endpoints use cursor-based pagination:

```json
GET /api/v1/members?limit=50&after=cursor_abc

{
  "items": [...],
  "cursor": "cursor_def"
}
```

- `limit`: Max items to return (default and max are endpoint-specific)
- `after`: Cursor from a previous response. Omit for the first page.
- `cursor`: Included in response if more items exist. Null/absent if this is the last page.

### Error Response Format

All errors return a JSON body:

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "You are being rate limited.",
    "retry_after_ms": 5000
  }
}
```

Fields:

| Field | Type | Description |
|---|---|---|
| `code` | string | Machine-readable error code (see Error Handling in `PROTOCOL HTTP.md`) |
| `message` | string | Human-readable description |
| `retry_after_ms` | int? | Present on rate limit errors |
| `missing_permission` | string? | Present on permission errors |

### ID Spaces

Feed IDs and DM IDs share a single uint32 field (`feed_id`). The high bit (bit 31) distinguishes them:

- Bit 31 = 0: feed ID (`0x00000000`-`0x7FFFFFFF`, ~2 billion feeds)
- Bit 31 = 1: DM ID (`0x80000000`-`0xFFFFFFFF`, ~2 billion DMs)

IDs are represented as integers in JSON. DM endpoints return a `feed_id` with bit 31 set, which is then used in message endpoints.

## 2. Authentication

### Register

```
POST /api/v1/auth/register
```

```json
// Request
{
  "username": "alice",
  "password": "correct-horse-battery-staple",
  "display_name": "Alice"  // optional
}

// Response (201 Created)
{
  "user_id": 42,
  "token": "vox_sess_abc123..."
}
```

### Login (Password)

```
POST /api/v1/auth/login
```

```json
// Request
{
  "username": "alice",
  "password": "correct-horse-battery-staple"
}

// Response (200 OK) — no 2FA
{
  "token": "vox_sess_abc123...",
  "user_id": 42,
  "display_name": "Alice",
  "roles": [1, 3]
}

// Response (200 OK) — 2FA required
{
  "mfa_required": true,
  "mfa_ticket": "mfa_ticket_xyz...",
  "available_methods": ["totp", "webauthn"]
}
```

### Login (2FA)

```
POST /api/v1/auth/login/2fa
```

```json
// Request (TOTP)
{
  "mfa_ticket": "mfa_ticket_xyz...",
  "method": "totp",
  "code": "123456"
}

// Request (WebAuthn)
{
  "mfa_ticket": "mfa_ticket_xyz...",
  "method": "webauthn",
  "assertion": { ... }  // WebAuthn assertion object
}

// Response (200 OK)
{
  "token": "vox_sess_abc123...",
  "user_id": 42,
  "display_name": "Alice",
  "roles": [1, 3]
}
```

### Login (Recovery Code)

```
POST /api/v1/auth/login/2fa
```

```json
// Request
{
  "mfa_ticket": "mfa_ticket_xyz...",
  "method": "recovery",
  "code": "XXXX-XXXX"
}
```

### Login (WebAuthn Passwordless)

```
POST /api/v1/auth/login/webauthn
```

```json
// Request
{
  "username": "alice",
  "client_data_json": "...",   // base64
  "authenticator_data": "...", // base64
  "signature": "...",          // base64
  "credential_id": "...",      // base64
  "user_handle": "..."         // base64, optional
}

// Response (200 OK)
{
  "token": "vox_sess_abc123...",
  "user_id": 42,
  "display_name": "Alice",
  "roles": [1, 3]
}
```

**Note:** 2FA challenges are only issued for password logins. Token-based session resumption and bot tokens skip 2FA since the original authentication already verified the second factor.

### 2FA Management

#### Get 2FA Status

```
GET /api/v1/auth/2fa
```

```json
// Response
{
  "totp_enabled": true,
  "webauthn_enabled": false,
  "recovery_codes_left": 6
}
```

#### Begin 2FA Setup

```
POST /api/v1/auth/2fa/setup
```

```json
// Request
{
  "method": "totp"
}

// Response (TOTP)
{
  "setup_id": "setup_abc...",
  "method": "totp",
  "totp_secret": "JBSWY3DPEHPK3PXP",
  "totp_uri": "otpauth://totp/Vox:alice?secret=JBSWY3DPEHPK3PXP&issuer=Vox"
}

// Response (WebAuthn)
{
  "setup_id": "setup_abc...",
  "method": "webauthn",
  "creation_options": { ... }  // PublicKeyCredentialCreationOptions
}
```

#### Confirm 2FA Setup

```
POST /api/v1/auth/2fa/setup/confirm
```

```json
// Request (TOTP)
{
  "setup_id": "setup_abc...",
  "code": "123456"
}

// Request (WebAuthn)
{
  "setup_id": "setup_abc...",
  "attestation": { ... },
  "credential_name": "YubiKey 5"
}

// Response
{
  "success": true,
  "recovery_codes": ["XXXX-XXXX", "YYYY-YYYY", ...]  // 8 single-use codes
}
```

**TOTP parameters:** SHA-1 hash, 6 digits, 30-second period, +/-1 window for clock skew.

**Recovery codes:** 8 single-use codes in `XXXX-XXXX` format. Stored hashed server-side (bcrypt or Argon2). Each code can be used exactly once via the recovery login flow.

#### Remove 2FA Method

```
DELETE /api/v1/auth/2fa
```

```json
// Request
{
  "method": "totp",
  "code": "123456"  // current TOTP code to verify
}
```

#### List WebAuthn Credentials

```
GET /api/v1/auth/webauthn/credentials
```

```json
// Response
{
  "credentials": [
    {
      "credential_id": "...",  // base64
      "name": "YubiKey 5",
      "registered_at": 1700000000,
      "last_used_at": 1700100000
    }
  ]
}
```

#### Delete WebAuthn Credential

```
DELETE /api/v1/auth/webauthn/credentials/{credential_id}
```

## 3. REST API Endpoints

All endpoints require authentication unless noted otherwise. Request and response bodies are JSON.

### Users

#### Get User Profile

```
GET /api/v1/users/{user_id}
```

```json
// Response
{
  "user_id": 42,
  "display_name": "Alice",
  "avatar": "https://cdn.example.com/avatars/42.webp",
  "bio": "Hello world",
  "roles": [1, 3]
}
```

#### Update Own Profile

```
PATCH /api/v1/users/@me
```

```json
// Request (all fields optional)
{
  "display_name": "Alice Updated",
  "avatar": "https://cdn.example.com/avatars/42-new.webp",
  "bio": "New bio"
}
```

#### Block User

```
PUT /api/v1/users/@me/blocks/{user_id}
```

When a user blocks another:
- All existing DMs between them are effectively closed
- Blocked user cannot open new DMs
- Blocked user cannot see blocker's presence or activity

#### Unblock User

```
DELETE /api/v1/users/@me/blocks/{user_id}
```

#### Add Friend

```
PUT /api/v1/users/@me/friends/{user_id}
```

#### Remove Friend

```
DELETE /api/v1/users/@me/friends/{user_id}
```

#### List Friends

```
GET /api/v1/users/@me/friends
```

```json
// Response
{
  "friends": [
    {"user_id": 7, "display_name": "Bob", "avatar": "..."}
  ]
}
```

### Server

#### Get Server Info

```
GET /api/v1/server
```

```json
// Response
{
  "name": "My Community",
  "icon": "https://cdn.example.com/icons/server.webp",
  "description": "A cool place",
  "member_count": 1234
}
```

#### Update Server

```
PATCH /api/v1/server
```

Requires `MANAGE_SERVER` permission.

```json
// Request (all fields optional)
{
  "name": "New Name",
  "icon": "...",
  "description": "..."
}
```

### Members

#### List Members

```
GET /api/v1/members?limit=100&after={cursor}
```

```json
// Response
{
  "items": [
    {
      "user_id": 42,
      "display_name": "Alice",
      "avatar": "...",
      "nickname": "Ali",
      "role_ids": [1, 3]
    }
  ],
  "cursor": "cursor_next..."
}
```

#### Join Server

```
POST /api/v1/members/@me/join
```

```json
// Request
{
  "invite_code": "abc123"
}
```

#### Leave Server

```
DELETE /api/v1/members/@me
```

#### Update Own Member

```
PATCH /api/v1/members/@me
```

```json
// Request
{
  "nickname": "Ali"
}
```

#### Kick Member

```
DELETE /api/v1/members/{user_id}
```

Requires `KICK_MEMBERS` permission.

```json
// Request (optional body)
{
  "reason": "Spam"
}
```

#### Ban Member

```
PUT /api/v1/bans/{user_id}
```

Requires `BAN_MEMBERS` permission.

```json
// Request
{
  "reason": "Repeated violations",
  "delete_msg_days": 7
}
```

#### Unban Member

```
DELETE /api/v1/bans/{user_id}
```

Requires `BAN_MEMBERS` permission.

#### List Bans

```
GET /api/v1/bans
```

Requires `BAN_MEMBERS` permission.

```json
// Response
{
  "bans": [
    {"user_id": 99, "display_name": "Spammer", "reason": "Spam"}
  ]
}
```

### Invites

#### Create Invite

```
POST /api/v1/invites
```

Requires `CREATE_INVITES` permission.

```json
// Request
{
  "feed_id": 5,      // optional, target feed
  "max_uses": 10,    // optional
  "max_age": 86400   // optional, seconds
}

// Response (201 Created)
{
  "code": "abc123",
  "creator_id": 42,
  "feed_id": 5,
  "max_uses": 10,
  "uses": 0,
  "expires_at": 1700086400
}
```

#### Delete Invite

```
DELETE /api/v1/invites/{code}
```

#### Resolve Invite

```
GET /api/v1/invites/{code}
```

No authentication required. Returns server info for preview before joining.

```json
// Response
{
  "code": "abc123",
  "server_name": "My Community",
  "server_icon": "...",
  "member_count": 1234
}
```

#### List Invites

```
GET /api/v1/invites
```

```json
// Response
{
  "invites": [
    {"code": "abc123", "creator_id": 42, "uses": 3, "max_uses": 10, "expires_at": 1700086400}
  ]
}
```

### Roles

#### List Roles

```
GET /api/v1/roles
```

```json
// Response
{
  "roles": [
    {"role_id": 1, "name": "Admin", "color": 16711680, "permissions": 9223372036854775807, "position": 0}
  ]
}
```

#### Create Role

```
POST /api/v1/roles
```

Requires `MANAGE_ROLES` permission.

```json
// Request
{
  "name": "Moderator",
  "color": 65280,
  "permissions": 234881024,
  "position": 2
}

// Response (201 Created)
{
  "role_id": 5,
  "name": "Moderator",
  "color": 65280,
  "permissions": 234881024,
  "position": 2
}
```

#### Update Role

```
PATCH /api/v1/roles/{role_id}
```

Requires `MANAGE_ROLES` permission.

```json
// Request (all fields optional)
{
  "name": "Senior Mod",
  "color": 255,
  "permissions": 234881024,
  "position": 1
}
```

#### Delete Role

```
DELETE /api/v1/roles/{role_id}
```

Requires `MANAGE_ROLES` permission.

#### Assign Role

```
PUT /api/v1/members/{user_id}/roles/{role_id}
```

Requires `MANAGE_ROLES` permission.

#### Revoke Role

```
DELETE /api/v1/members/{user_id}/roles/{role_id}
```

Requires `MANAGE_ROLES` permission.

### Permission Overrides

#### Set Permission Override

```
PUT /api/v1/feeds/{feed_id}/permissions/{target_type}/{target_id}
PUT /api/v1/rooms/{room_id}/permissions/{target_type}/{target_id}
```

`target_type` is `role` or `user`.

```json
// Request
{
  "allow": 3,   // permission bits to allow
  "deny": 12    // permission bits to deny
}
```

Requires `MANAGE_ROLES` permission.

#### Delete Permission Override

```
DELETE /api/v1/feeds/{feed_id}/permissions/{target_type}/{target_id}
DELETE /api/v1/rooms/{room_id}/permissions/{target_type}/{target_id}
```

### Feeds

#### List Feeds, Rooms, and Categories

```
GET /api/v1/server/layout
```

Returns the complete server hierarchy.

```json
// Response
{
  "categories": [
    {"category_id": 1, "name": "General", "position": 0}
  ],
  "feeds": [
    {"feed_id": 1, "name": "welcome", "type": "text", "category_id": 1, "topic": "Say hi!", "permission_overrides": []}
  ],
  "rooms": [
    {"room_id": 1, "name": "Lounge", "type": "voice", "category_id": 2, "permission_overrides": []}
  ]
}
```

Feed types:

| Type | Description |
|---|---|
| `text` | Standard text feed |
| `forum` | Each post is a thread |
| `announcement` | Read-only for most, push notifications |

Room types:

| Type | Description |
|---|---|
| `voice` | Persistent voice space + optional video/screen |
| `stage` | Speaker/audience model |

#### Create Feed

```
POST /api/v1/feeds
```

Requires `MANAGE_SPACES` permission.

```json
// Request
{
  "name": "announcements",
  "type": "announcement",
  "category_id": 1,  // optional
  "permission_overrides": []  // optional
}

// Response (201 Created)
{
  "feed_id": 10,
  "name": "announcements",
  "type": "announcement",
  "category_id": 1
}
```

#### Update Feed

```
PATCH /api/v1/feeds/{feed_id}
```

Requires `MANAGE_SPACES` permission.

```json
// Request (all fields optional)
{
  "name": "news",
  "topic": "Server news and updates"
}
```

#### Delete Feed

```
DELETE /api/v1/feeds/{feed_id}
```

Requires `MANAGE_SPACES` permission.

### Rooms

#### Create Room

```
POST /api/v1/rooms
```

Requires `MANAGE_SPACES` permission.

```json
// Request
{
  "name": "Gaming",
  "type": "voice",
  "category_id": 2,
  "permission_overrides": []
}

// Response (201 Created)
{
  "room_id": 5,
  "name": "Gaming",
  "type": "voice",
  "category_id": 2
}
```

#### Update Room

```
PATCH /api/v1/rooms/{room_id}
```

Requires `MANAGE_SPACES` permission.

#### Delete Room

```
DELETE /api/v1/rooms/{room_id}
```

Requires `MANAGE_SPACES` permission.

### Categories

#### Create Category

```
POST /api/v1/categories
```

Requires `MANAGE_SPACES` permission.

```json
// Request
{
  "name": "Projects",
  "position": 2
}

// Response (201 Created)
{
  "category_id": 3,
  "name": "Projects",
  "position": 2
}
```

#### Update Category

```
PATCH /api/v1/categories/{category_id}
```

Requires `MANAGE_SPACES` permission.

```json
// Request (all fields optional)
{
  "name": "Active Projects",
  "position": 1
}
```

#### Delete Category

```
DELETE /api/v1/categories/{category_id}
```

Requires `MANAGE_SPACES` permission.

### Threads

#### Create Thread

```
POST /api/v1/feeds/{feed_id}/threads
```

Requires `CREATE_THREADS` permission.

```json
// Request
{
  "parent_msg_id": 123456,
  "name": "Discussion about this"
}

// Response (201 Created)
{
  "thread_id": 7,
  "parent_feed_id": 5,
  "parent_msg_id": 123456,
  "name": "Discussion about this",
  "archived": false,
  "locked": false
}
```

#### Update Thread

```
PATCH /api/v1/threads/{thread_id}
```

```json
// Request (all fields optional)
{
  "name": "Updated name",
  "archived": true,
  "locked": false
}
```

#### Delete Thread

```
DELETE /api/v1/threads/{thread_id}
```

Requires `MANAGE_THREADS` permission.

#### Subscribe to Thread

```
PUT /api/v1/threads/{thread_id}/subscribers/@me
```

#### Unsubscribe from Thread

```
DELETE /api/v1/threads/{thread_id}/subscribers/@me
```

### Messages

#### Get Message History

```
GET /api/v1/feeds/{feed_id}/messages?limit=50&before={msg_id}
```

Requires `READ_HISTORY` permission.

```json
// Response
{
  "messages": [
    {
      "msg_id": 123456,
      "feed_id": 5,
      "author_id": 42,
      "body": "Hello everyone!",
      "timestamp": 1700000000,
      "reply_to": null,
      "mentions": [],
      "embeds": [],
      "attachments": [],
      "components": [],
      "edit_timestamp": null,
      "federated": false,
      "author_address": null
    }
  ]
}
```

#### Send Message

```
POST /api/v1/feeds/{feed_id}/messages
```

Requires `SEND_MESSAGES` permission.

```json
// Request
{
  "body": "Hello everyone!",
  "reply_to": 123455,    // optional
  "mentions": [{"user_id": 7}],  // optional
  "embeds": [],          // optional
  "attachments": [],     // optional, file_ids from upload
  "components": []       // optional, bot components
}

// Response (201 Created)
{
  "msg_id": 123456,
  "timestamp": 1700000001
}
```

The message is also delivered to all connected gateway clients via a `MESSAGE_CREATE` dispatch event.

#### Edit Message

```
PATCH /api/v1/feeds/{feed_id}/messages/{msg_id}
```

Only the author can edit their own messages.

```json
// Request
{
  "body": "Hello everyone! (edited)"
}

// Response
{
  "msg_id": 123456,
  "edit_timestamp": 1700000100
}
```

#### Delete Message

```
DELETE /api/v1/feeds/{feed_id}/messages/{msg_id}
```

Author can delete own messages. Users with `MANAGE_MESSAGES` permission can delete others'.

#### Bulk Delete Messages

```
POST /api/v1/feeds/{feed_id}/messages/bulk-delete
```

Requires `MANAGE_MESSAGES` permission.

```json
// Request
{
  "msg_ids": [123456, 123457, 123458]
}
```

#### Add/Remove Reaction

```
PUT /api/v1/feeds/{feed_id}/messages/{msg_id}/reactions/{emoji}/@me
DELETE /api/v1/feeds/{feed_id}/messages/{msg_id}/reactions/{emoji}/@me
```

Requires `ADD_REACTIONS` permission (for add).

#### Pin/Unpin Message

```
PUT /api/v1/feeds/{feed_id}/pins/{msg_id}
DELETE /api/v1/feeds/{feed_id}/pins/{msg_id}
```

#### Search Messages

```
GET /api/v1/messages/search?query=hello&feed_id=5&author_id=42
```

Query parameters:

| Param | Type | Description |
|---|---|---|
| `query` | string | Search text (required) |
| `feed_id` | uint32? | Restrict to a feed |
| `author_id` | uint32? | Restrict to an author |
| `before` | uint64? | Messages before this timestamp |
| `after` | uint64? | Messages after this timestamp |
| `has_file` | bool? | Only messages with attachments |
| `has_embed` | bool? | Only messages with embeds |
| `pinned` | bool? | Only pinned messages |

```json
// Response
{
  "results": [ /* ChatMessage objects */ ]
}
```

### Direct Messages

#### Open 1:1 DM

```
POST /api/v1/dms
```

```json
// Request
{
  "recipient_id": 7
}

// Response (200 OK or 201 Created)
{
  "dm_id": 2147483649,  // feed_id with bit 31 set
  "participant_ids": [42, 7],
  "is_group": false
}
```

#### Open Group DM

```
POST /api/v1/dms
```

```json
// Request
{
  "recipient_ids": [7, 13, 21],
  "name": "Project Team"  // optional
}

// Response (201 Created)
{
  "dm_id": 2147483650,
  "participant_ids": [42, 7, 13, 21],
  "name": "Project Team",
  "is_group": true
}
```

#### List DMs

```
GET /api/v1/dms
```

```json
// Response
{
  "dms": [
    {"dm_id": 2147483649, "participant_ids": [42, 7], "is_group": false},
    {"dm_id": 2147483650, "participant_ids": [42, 7, 13], "name": "Team", "is_group": true}
  ]
}
```

#### Close DM

```
DELETE /api/v1/dms/{dm_id}
```

Hides from DM list. Does not delete messages.

#### Update Group DM

```
PATCH /api/v1/dms/{dm_id}
```

```json
// Request (all fields optional)
{
  "name": "New Group Name",
  "icon": "..."
}
```

#### Add Recipient to Group DM

```
PUT /api/v1/dms/{dm_id}/recipients/{user_id}
```

#### Remove Recipient from Group DM

```
DELETE /api/v1/dms/{dm_id}/recipients/{user_id}
```

#### Send Read Receipt

```
POST /api/v1/dms/{dm_id}/read
```

```json
// Request
{
  "up_to_msg_id": 123456
}
```

Other participants receive a `DM_READ_NOTIFY` gateway event.

#### Get DM Settings

```
GET /api/v1/users/@me/dm-settings
```

```json
// Response
{
  "dm_permission": "everyone"  // "everyone" | "friends_only" | "mutual_servers" | "nobody"
}
```

#### Update DM Settings

```
PATCH /api/v1/users/@me/dm-settings
```

```json
// Request
{
  "dm_permission": "friends_only"
}
```

**DM messages** use the same message endpoints as feeds. Send messages to a DM via `POST /api/v1/feeds/{dm_id}/messages` using the `dm_id` as the `feed_id`. History is fetched via `GET /api/v1/feeds/{dm_id}/messages`.

### Files

#### Upload File

```
POST /api/v1/feeds/{feed_id}/files
Content-Type: multipart/form-data
```

Multipart fields:

| Field | Type | Description |
|---|---|---|
| `file` | binary | The file data |
| `name` | string | Filename |
| `mime` | string | MIME type |

```json
// Response (201 Created)
{
  "file_id": "file_abc123",
  "name": "photo.jpg",
  "size": 1048576,
  "mime": "image/jpeg",
  "url": "https://cdn.example.com/files/file_abc123/photo.jpg"
}
```

Use the `file_id` in the `attachments` array when sending a message.

#### Download File

```
GET /api/v1/files/{file_id}
```

Returns the file with appropriate `Content-Type` header. May redirect to CDN.

### Embeds

#### Resolve URL

```
POST /api/v1/embeds/resolve
```

```json
// Request
{
  "url": "https://example.com/article"
}

// Response
{
  "title": "Article Title",
  "description": "Article description...",
  "image": "https://example.com/og-image.jpg",
  "video": null
}
```

### Emoji

#### List Custom Emoji

```
GET /api/v1/emoji
```

```json
// Response
{
  "emoji": [
    {"emoji_id": 1, "name": "pepethink", "creator_id": 42}
  ]
}
```

#### Create Emoji

```
POST /api/v1/emoji
Content-Type: multipart/form-data
```

Requires `MANAGE_EMOJI` permission. Multipart fields: `name` (string), `image` (binary).

#### Delete Emoji

```
DELETE /api/v1/emoji/{emoji_id}
```

Requires `MANAGE_EMOJI` permission.

### Stickers

#### List Stickers

```
GET /api/v1/stickers
```

#### Create Sticker

```
POST /api/v1/stickers
Content-Type: multipart/form-data
```

Requires `MANAGE_EMOJI` permission. Multipart fields: `name` (string), `image` (binary).

#### Delete Sticker

```
DELETE /api/v1/stickers/{sticker_id}
```

Requires `MANAGE_EMOJI` permission.

### Webhooks

#### Create Webhook

```
POST /api/v1/feeds/{feed_id}/webhooks
```

Requires `MANAGE_WEBHOOKS` permission.

```json
// Request
{
  "name": "CI Bot",
  "avatar": "..."  // optional
}

// Response (201 Created)
{
  "webhook_id": 1,
  "feed_id": 5,
  "name": "CI Bot",
  "token": "whk_secret_token..."
}
```

#### Update Webhook

```
PATCH /api/v1/webhooks/{webhook_id}
```

Requires `MANAGE_WEBHOOKS` permission.

#### Delete Webhook

```
DELETE /api/v1/webhooks/{webhook_id}
```

Requires `MANAGE_WEBHOOKS` permission.

#### List Webhooks

```
GET /api/v1/feeds/{feed_id}/webhooks
```

#### Execute Webhook

```
POST /api/v1/webhooks/{webhook_id}/{token}
```

**No authentication required** -- the token in the URL is the secret.

```json
// Request
{
  "body": "Build #42 passed!",
  "embeds": [
    {"title": "Build Report", "description": "All tests green", "color": 65280}
  ]
}

// Response (204 No Content)
```

### Bots and Commands

#### Register Commands

```
PUT /api/v1/bots/@me/commands
```

```json
// Request
{
  "commands": [
    {
      "name": "roll",
      "description": "Roll a die",
      "params": [
        {"name": "sides", "description": "Number of sides", "required": false}
      ]
    }
  ]
}
```

#### Deregister Commands

```
DELETE /api/v1/bots/@me/commands
```

```json
// Request
{
  "command_names": ["roll"]
}
```

#### List Commands

```
GET /api/v1/commands
```

```json
// Response
{
  "commands": [
    {"name": "roll", "description": "Roll a die", "params": [...]}
  ]
}
```

#### Respond to Interaction

When using gateway bots, interactions are received as `INTERACTION_CREATE` dispatch events and responded to via:

```
POST /api/v1/interactions/{interaction_id}/response
```

```json
// Request
{
  "body": "Rolled: 17",
  "embeds": [],
  "components": [],
  "ephemeral": false
}
```

### E2E Encryption Keys

#### Upload Prekeys

```
PUT /api/v1/keys/prekeys
```

```json
// Request
{
  "identity_key": "...",      // base64
  "signed_prekey": "...",     // base64
  "one_time_prekeys": ["...", "..."]  // base64 array
}
```

#### Fetch User's Prekey Bundle

```
GET /api/v1/keys/prekeys/{user_id}
```

```json
// Response
{
  "user_id": 7,
  "identity_key": "...",
  "signed_prekey": "...",
  "one_time_prekey": "..."  // may be null if exhausted
}
```

#### Add Device

```
POST /api/v1/keys/devices
```

```json
// Request
{
  "device_id": "dev_abc123",
  "device_name": "Alice's Laptop"
}
```

#### Remove Device

```
DELETE /api/v1/keys/devices/{device_id}
```

#### Initiate Device Pairing

```
POST /api/v1/keys/devices/pair
```

```json
// Request
{
  "device_name": "Alice's Phone",
  "method": "cpace",           // "cpace" or "qr"
  "temp_public_key": "..."     // base64, QR method only
}

// Response
{
  "pair_id": "pair_xyz..."
}
```

The existing device receives a `DEVICE_PAIR_PROMPT` gateway event. CPace key exchange messages (`CPACE_ISI`, `CPACE_RSI`, `CPACE_CONFIRM`, `CPACE_LEAF_TRANSFER`) are relayed via the gateway.

#### Approve/Deny Device Pairing

```
POST /api/v1/keys/devices/pair/{pair_id}/respond
```

```json
// Request
{
  "approved": true
}
```

#### Upload Key Backup

```
PUT /api/v1/keys/backup
```

```json
// Request
{
  "encrypted_blob": "..."  // base64
}
```

#### Download Key Backup

```
GET /api/v1/keys/backup
```

```json
// Response
{
  "encrypted_blob": "..."
}
```

#### Reset Keys

```
POST /api/v1/keys/reset
```

Generates new leaf key, invalidates all DM sessions. All contacts receive a `KEY_RESET_NOTIFY` gateway event.

### Reports

#### Create Report

```
POST /api/v1/reports
```

```json
// Request
{
  "reported_user_id": 99,
  "dm_id": 2147483649,
  "messages": [
    {"msg_id": 123, "body": "offensive content", "timestamp": 1700000000}
  ],
  "reason": "harassment",
  "description": "Repeated harassment in DMs"
}

// Response (201 Created)
{
  "report_id": 1
}
```

Reason categories: `harassment`, `spam`, `illegal_content`, `threats`, `other`.

#### List Reports

```
GET /api/v1/reports?status=open&cursor={cursor}
```

Requires `VIEW_REPORTS` permission.

#### Resolve Report

```
POST /api/v1/reports/{report_id}/resolve
```

Requires `VIEW_REPORTS` permission.

```json
// Request
{
  "action": "ban"  // "dismiss" | "warn" | "kick" | "ban"
}
```

### Audit Log

#### Query Audit Log

```
GET /api/v1/audit-log?event_type=member.*&actor_id=42&limit=50
```

Requires `VIEW_AUDIT_LOG` permission.

Query parameters:

| Param | Type | Description |
|---|---|---|
| `event_type` | string? | Filter by event type pattern |
| `actor_id` | uint32? | Filter by actor |
| `target_id` | uint32? | Filter by target |
| `before` | uint64? | Entries before this timestamp |
| `after` | uint64? | Entries after this timestamp |
| `limit` | uint32? | Max entries (default 50) |
| `cursor` | string? | Pagination cursor |

```json
// Response
{
  "entries": [
    {
      "entry_id": 1001,
      "event_type": "member.kick",
      "actor_id": 42,
      "target_id": 99,
      "metadata": {"reason": "Spam"},
      "timestamp": 1700000000
    }
  ],
  "cursor": "cursor_next..."
}
```

Event types use dot-notation: `{category}.{action}` (e.g., `member.kick`, `role.assign`, `feed.delete`, `2fa.admin_reset`).

### Admin

#### Admin 2FA Reset

```
POST /api/v1/admin/2fa-reset
```

Requires `MANAGE_2FA` permission (bit 37).

```json
// Request
{
  "target_user_id": 99,
  "reason": "User locked out"
}
```

Disables all 2FA methods for the target user. Generates audit log entry (`2fa.admin_reset`). The user must re-enroll 2FA themselves.

### Voice Rooms (REST portion)

#### Join Voice Room

```
POST /api/v1/rooms/{room_id}/voice/join
```

```json
// Request
{
  "self_mute": false,
  "self_deaf": false
}

// Response
{
  "media_url": "quic://vox.example.com:4443",
  "media_token": "media_token_abc...",
  "members": [
    {"user_id": 7, "mute": false, "deaf": false, "video": false, "streaming": false}
  ]
}
```

The `media_url` and `media_token` are used to establish a separate media transport connection (see Media Transport in `PROTOCOL HTTP.md`). Voice state changes are delivered via the gateway.

#### Leave Voice Room

```
POST /api/v1/rooms/{room_id}/voice/leave
```

#### Kick from Voice

```
POST /api/v1/rooms/{room_id}/voice/kick
```

Requires `MOVE_MEMBERS` or `MUTE_MEMBERS` permission.

```json
// Request
{
  "user_id": 99
}
```

#### Move to Room

```
POST /api/v1/rooms/{room_id}/voice/move
```

Requires `MOVE_MEMBERS` permission.

```json
// Request
{
  "user_id": 99,
  "to_room_id": 6
}
```

#### Stage: Request to Speak

```
POST /api/v1/rooms/{room_id}/stage/request
```

#### Stage: Invite to Speak

```
POST /api/v1/rooms/{room_id}/stage/invite
```

Requires `STAGE_MODERATOR` permission.

```json
// Request
{
  "user_id": 99
}
```

#### Stage: Respond to Invite

```
POST /api/v1/rooms/{room_id}/stage/invite/respond
```

```json
// Request
{
  "accepted": true
}
```

#### Stage: Revoke Speaker

```
POST /api/v1/rooms/{room_id}/stage/revoke
```

Requires `STAGE_MODERATOR` permission.

```json
// Request
{
  "user_id": 99
}
```

#### Stage: Set Topic

```
PATCH /api/v1/rooms/{room_id}/stage/topic
```

```json
// Request
{
  "topic": "Q&A Session"
}
```

### Gateway Info

```
GET /api/v1/gateway
```

No authentication required.

```json
// Response
{
  "url": "wss://vox.example.com/gateway",
  "media_url": "quic://vox.example.com:4443"
}
```

### Sync

```
POST /api/v1/sync
```

Used after gateway reconnection when resume fails, to catch up on missed events.

```json
// Request
{
  "since_timestamp": 1700000000,
  "categories": ["members", "roles", "feeds", "rooms", "categories"]
}

// Response
{
  "events": [
    {"type": "member.join", "payload": {...}, "timestamp": 1700000050},
    {"type": "role.update", "payload": {...}, "timestamp": 1700000060}
  ],
  "server_timestamp": 1700000100
}
```

If `since_timestamp` is too far in the past (server-configured retention), the server returns an empty events list and the client should fall back to a full state fetch (`GET /api/v1/server/layout`, `GET /api/v1/members`, etc.).
