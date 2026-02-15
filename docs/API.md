# VoxProtocol v1: REST API Reference

This document defines the complete REST API surface for VoxProtocol v1, including server-to-server federation endpoints. For the wire protocol (WebSocket gateway, media transport, E2E encryption, federation overview) see the companion docs: `PROTOCOL.md`, `GATEWAY.md`, `MEDIA.md`, `E2EE.md`, `FEDERATION.md`.

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

### ID Spaces

Feed IDs and DM IDs use separate fields:

| Field | Type | Description |
|---|---|---|
| `feed_id` | uint32 | Server feed identifier |
| `dm_id` | uint32 | Direct message conversation identifier |

In endpoints that can target either a feed or a DM (e.g., message endpoints), exactly one of `feed_id` or `dm_id` is provided. Both are full-range uint32 values.

Message IDs (`msg_id`) use snowflake uint64 values. See `PROTOCOL.md` for the snowflake bit layout and epoch definition.

## 2. Error Handling

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
| `code` | string | Machine-readable error code |
| `message` | string | Human-readable description |
| `retry_after_ms` | int? | Present on rate limit errors |
| `missing_permission` | string? | Present on permission errors |

### HTTP Status Code Mapping

| HTTP Status | Error Codes | Description |
|---|---|---|
| 400 Bad Request | `PROTOCOL_VERSION_MISMATCH`, `MESSAGE_TOO_LARGE`, `SPACE_TYPE_MISMATCH`, `GATEWAY_VERSION_MISMATCH` | Invalid request |
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
| `GATEWAY_VERSION_MISMATCH` | Client's protocol version is not supported by this server (see `min_version`/`max_version` in gateway info) |
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

## 3. Rate Limiting

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

Servers SHOULD apply rate limits per endpoint category. Specific limits are server policy.

## 4. Authentication

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

// Response (200 OK) -- no 2FA
{
  "token": "vox_sess_abc123...",
  "user_id": 42,
  "display_name": "Alice",
  "roles": [1, 3]
}

// Response (200 OK) -- 2FA required
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

## 5. REST API Endpoints

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
- Existing messages remain on blocker's client

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

#### Get Feed

```
GET /api/v1/feeds/{feed_id}
```

```json
// Response
{
  "feed_id": 5,
  "name": "general",
  "type": "text",
  "topic": "General discussion",
  "category_id": 1,
  "permission_overrides": []
}
```

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

#### Get Thread Messages

```
GET /api/v1/feeds/{feed_id}/threads/{thread_id}/messages?limit=50&before={msg_id}
```

Requires `READ_HISTORY` permission.

```json
// Response
{
  "messages": [
    {
      "msg_id": 789012,
      "thread_id": 7,
      "author_id": 42,
      "body": "Replying in the thread",
      "timestamp": 1700000100,
      "reply_to": null,
      "mentions": [],
      "embeds": [],
      "attachments": [],
      "components": [],
      "edit_timestamp": null
    }
  ]
}
```

Pagination works identically to feed message history (`limit`, `before`, `after`).

#### Send Thread Message

```
POST /api/v1/feeds/{feed_id}/threads/{thread_id}/messages
```

Requires `SEND_IN_THREADS` permission. Request and response format is identical to feed messages.

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

The message is also delivered to all connected gateway clients via a `message_create` event.

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
  "dm_id": 1,
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
  "dm_id": 2,
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
    {"dm_id": 1, "participant_ids": [42, 7], "is_group": false},
    {"dm_id": 2, "participant_ids": [42, 7, 13], "name": "Team", "is_group": true}
  ]
}
```

Group DMs have a server-configurable maximum participant count. Servers SHOULD expose this limit in the server info or capability negotiation. Exceeding the limit returns `403 FORBIDDEN`.

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

Other participants receive a `dm_read_notify` gateway event.

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

DM permission values:

| Setting | Description |
|---|---|
| `everyone` | Anyone on the server can DM |
| `friends_only` | Only users on their friend list |
| `mutual_servers` | Only users sharing a server (includes federated members) |
| `nobody` | DMs completely disabled |

If a user attempts to DM a recipient whose settings disallow it, the server returns `403 FORBIDDEN` with error code `DM_PERMISSION_DENIED`.

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

**DM messages** use dedicated DM message endpoints:

```
POST /api/v1/dms/{dm_id}/messages       // Send message
GET  /api/v1/dms/{dm_id}/messages       // Get history (same pagination as feed messages)
PATCH /api/v1/dms/{dm_id}/messages/{msg_id}  // Edit message
DELETE /api/v1/dms/{dm_id}/messages/{msg_id} // Delete message
```

Request and response formats are identical to the feed message endpoints.

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

Webhook execution SHOULD be rate-limited. Specific limits are server policy. Servers SHOULD apply per-webhook and/or per-IP rate limits to prevent abuse of unauthenticated webhook endpoints.

### Bots and Commands

#### Gateway Bots

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
  |<-- hello --------------|---------------|
  |-- identify {token} ---|-------------->|
  |<-- ready {is_bot:true}-|--------------|
  |                       |               |
  |-- PUT /bots/@me/      |               |
  |   commands ----------->|               |
  |                       |               |
  |  [receive interaction_create events]   |
  |<-- event --------------|--------------|
  |                       |               |
  |-- POST /interactions/  |               |
  |   {id}/response ------>|               |
```

#### HTTP-Only Bots

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
  |<-- message_create -----|                          |
```

HTTP-only bots register their endpoint URL and commands via REST. They cannot receive other events (messages, presence, etc.) and cannot join voice rooms.

#### Slash Command Flow

```
User                    Server                          Bot (Gateway)
  |                        |                                |
  |-- POST /feeds/{id}/   |                                |
  |   messages {"/roll 20"}|                                |
  |                        |  [parse command, route]        |
  |                        |-- interaction_create event --->|
  |                        |   {type: "slash_command",      |
  |                        |    command: "roll",            |
  |                        |    params: {sides: "20"}}     |
  |                        |                                |
  |                        |<-- POST /interactions/{id}/   |
  |<-- message_create -----|    response {body: "17"}       |
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

When a user clicks a button, the bot receives an `interaction_create` event with `type: "button"` and `component_id: "red"`.

#### Bot and Webhook Comparison

| | Gateway Bot | HTTP-Only Bot | Webhook |
|---|---|---|---|
| Connection | WebSocket | Stateless HTTP | Stateless HTTP POST |
| Receive events | Yes (all) | Interactions only | No |
| Send messages | Yes | Via interaction response | Yes |
| Slash commands | Yes | Yes | No |
| Component interactions | Yes | Yes | No |
| Voice/video | Yes | No | No |
| Use case | Interactive, real-time, voice | Simple commands | CI/CD alerts, notifications |

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

When using gateway bots, interactions are received as `interaction_create` events and responded to via:

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

#### Fetch User's Prekey Bundles

```
GET /api/v1/keys/prekeys/{user_id}
```

Returns one prekey bundle per device:

```json
// Response
{
  "user_id": 7,
  "devices": [
    {
      "device_id": "dev_abc",
      "identity_key": "...",
      "signed_prekey": "...",
      "one_time_prekey": "..."  // may be null if exhausted
    }
  ]
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

Servers enforce a maximum number of devices per user (server-configurable). Exceeding the limit returns `503 DEVICE_LIMIT_REACHED`. This limit applies globally and also bounds the number of MLS leaves per user in group DMs.

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

The existing device receives a `device_pair_prompt` gateway event. CPace key exchange messages are relayed via the gateway. See `E2EE.md` for full pairing protocol details.

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

Generates new leaf key, invalidates all DM sessions. All contacts receive a `key_reset_notify` gateway event. See `E2EE.md` for full details.

### Reports

Since the server cannot read E2EE DMs, abuse reporting is voluntary. The recipient's client decrypts selected messages and submits plaintext to the server via the reporting API.

#### Create Report

```
POST /api/v1/reports
```

```json
// Request
{
  "reported_user_id": 99,
  "dm_id": 1,
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

The `media_url` and `media_token` are used to establish a separate media transport connection (see `MEDIA.md`). Voice state changes are delivered via the gateway.

The `media_token` is short-lived (server-configurable duration). Before expiry, the server pushes a `media_token_refresh` gateway event with a replacement token. The client uses the new token transparently without reconnecting the QUIC session. See `GATEWAY.md` for the event format.

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
  "media_url": "quic://vox.example.com:4443",
  "protocol_version": 1,
  "min_version": 1,
  "max_version": 1
}
```

| Field | Type | Description |
|---|---|---|
| `url` | string | WebSocket gateway URL |
| `media_url` | string | QUIC media transport URL |
| `protocol_version` | uint32 | Server's current protocol version |
| `min_version` | uint32 | Minimum protocol version the server supports |
| `max_version` | uint32 | Maximum protocol version the server supports |

The media transport version is bound to the gateway protocol version: protocol v1 uses media transport v1. There is no independent media version negotiation.

### Sync

```
POST /api/v1/sync
```

Used after gateway reconnection when resume fails, to catch up on missed events.

```json
// Request
{
  "since_timestamp": 1700000000,
  "categories": ["members", "roles", "feeds", "rooms", "categories", "emoji", "bans", "invites"]
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

**Sync categories:**

| Category | Events Covered |
|---|---|
| `members` | member.join, member.leave, member.update, member.ban, member.unban |
| `roles` | role.create, role.update, role.delete, role.assign, role.revoke |
| `feeds` | feed.create, feed.update, feed.delete |
| `rooms` | room.create, room.update, room.delete |
| `categories` | category.create, category.update, category.delete |
| `emoji` | emoji.create, emoji.delete |
| `bans` | member.ban, member.unban |
| `invites` | invite.create, invite.delete |

Servers MUST support all listed categories. Future protocol versions may add additional categories. Servers SHOULD ignore unrecognized category names in requests.

If `since_timestamp` is too far in the past (server-configured retention), the server returns an empty events list and the client should fall back to a full state fetch (`GET /api/v1/server/layout`, `GET /api/v1/members`, etc.).

## 6. Federation (Server-to-Server)

Federation endpoints are called by remote servers, not clients. All federation requests MUST include:

| Header | Description |
|---|---|
| `X-Vox-Origin` | Sending server's domain |
| `X-Vox-Signature` | Ed25519 signature of the request body, verifiable via `_voxkey` DNS TXT record |

The receiving server MUST verify the signature against the DNS key before processing. See `FEDERATION.md` for DNS records, authentication, and security rules.

Federation error responses use the `FED_*` error codes (see `FEDERATION.md` for the full list):

```json
{
  "error": {
    "code": "FED_AUTH_FAILED",
    "message": "Signature verification failed"
  }
}
```

#### Relay DM Message

```
POST /api/v1/federation/relay/message
```

```json
// Request
{
  "from": "alice@servera.com",
  "to": "bob@serverb.com",
  "opaque_blob": "..."   // base64 E2EE ciphertext
}

// Response: 204 No Content
```

#### Relay Typing Indicator

```
POST /api/v1/federation/relay/typing
```

```json
// Request
{
  "from": "alice@servera.com",
  "to": "bob@serverb.com"
}

// Response: 204 No Content
```

#### Relay Read Receipt

```
POST /api/v1/federation/relay/read
```

```json
// Request
{
  "from": "alice@servera.com",
  "to": "bob@serverb.com",
  "up_to_msg_id": 12345
}

// Response: 204 No Content
```

#### Fetch User Prekeys

```
GET /api/v1/federation/users/{user_address}/prekeys
```

```json
// Response
{
  "user_address": "bob@serverb.com",
  "devices": [
    {
      "device_id": "dev_abc",
      "identity_key": "...",
      "signed_prekey": "...",
      "one_time_prekey": "..."
    }
  ]
}
```

#### Lookup User Profile

```
GET /api/v1/federation/users/{user_address}
```

```json
// Response
{
  "display_name": "Bob",
  "avatar_url": "...",
  "bio": "..."
}
```

#### Subscribe to Presence

```
POST /api/v1/federation/presence/subscribe
```

```json
// Request
{
  "user_address": "bob@serverb.com"
}

// Response: 204 No Content
```

Presence updates for subscribed users are pushed via `POST /api/v1/federation/presence/notify` from the home server:

```
POST /api/v1/federation/presence/notify
```

```json
// Request
{
  "user_address": "bob@serverb.com",
  "status": "online",
  "activity": {           // optional
    "type": "playing",
    "name": "Chess.com"
  }
}

// Response: 204 No Content
```

#### Join Request

```
POST /api/v1/federation/join
```

```json
// Request
{
  "user_address": "alice@servera.com",
  "invite_code": "abc123",   // optional
  "voucher": "..."            // base64 signed JSON voucher from home server
}

// Response
{
  "accepted": true,
  "federation_token": "fed_tok_...",
  "server_info": {
    "name": "My Community",
    "icon": "...",
    "description": "...",
    "member_count": 150
  }
}
```

The `federation_token` is used by the joining user to authenticate directly with the remote server via `POST /api/v1/auth/login`.

#### Block Notification

```
POST /api/v1/federation/block
```

```json
// Request
{
  "reason": "Spam"   // optional
}

// Response: 204 No Content
```

Courtesy notification sent when a server blocks a federation peer.
