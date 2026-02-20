# Members

All endpoints in this section require authentication. Moderation endpoints
require the indicated permission.

---

## GET /members

List server members. Results are paginated.

**Query Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | `integer` | 50 | Max items to return (max 100) |
| `after` | `string` | — | Cursor from previous response |

**Response `200 OK`**

```json
{
  "items": [
    {
      "user_id": 10001,
      "username": "alice",
      "display_name": "Alice",
      "nickname": "Ali",
      "avatar": "https://cdn.vox.example.com/avatars/10001/abc123.webp",
      "roles": [1, 3],
      "joined_at": "2025-01-10T14:22:00Z"
    },
    {
      "user_id": 10002,
      "username": "bob",
      "display_name": "Bob",
      "nickname": null,
      "avatar": "https://cdn.vox.example.com/avatars/10002/def456.webp",
      "roles": [1],
      "joined_at": "2025-02-05T09:30:00Z"
    }
  ],
  "cursor": "eyJpZCI6MTAwMDJ9"
}
```

---

## POST /members/@me/join

Join the server using an invite code.

**Request**

```json
{
  "invite_code": "vox-abc123"
}
```

**Response `200 OK`**

```json
{
  "user_id": 10005,
  "username": "eve",
  "display_name": "Eve",
  "nickname": null,
  "roles": [],
  "joined_at": "2025-12-20T18:45:00Z"
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 400 | `INVALID_BODY` | Missing or malformed invite code |
| 404 | `NOT_FOUND` | Invite code is invalid or expired |
| 403 | `MISSING_PERMISSIONS` | User is banned from the server |

---

## DELETE /members/@me

Leave the server.

**Response `204 No Content`**

No body.

---

## PATCH /members/@me

Update the authenticated user's server-specific nickname.

**Request**

```json
{
  "nickname": "Ali"
}
```

| Field | Type | Description |
|---|---|---|
| `nickname` | `string?` | Server nickname (1-64 chars). Set to `null` to clear. |

**Response `200 OK`**

```json
{
  "user_id": 10001,
  "username": "alice",
  "display_name": "Alice",
  "nickname": "Ali",
  "roles": [1, 3],
  "joined_at": "2025-01-10T14:22:00Z"
}
```

---

## DELETE /members/{user_id}

Kick a member from the server. Requires `KICK_MEMBERS`.

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `KICK_MEMBERS` |
| 404 | `NOT_FOUND` | Target user is not a member |

---

## PUT /bans/{user_id}

Ban a member from the server. Requires `BAN_MEMBERS`.

**Request**

```json
{
  "reason": "Repeated rule violations",
  "delete_msg_days": 7
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | `string` | no | Audit-log reason for the ban (max 512 characters) |
| `delete_msg_days` | `integer` | no | Delete the user's messages from the last N days (0-14, default 0) |

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `BAN_MEMBERS` |
| 404 | `NOT_FOUND` | Target user does not exist |

---

## DELETE /bans/{user_id}

Unban a user. Requires `BAN_MEMBERS`.

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `BAN_MEMBERS` |
| 404 | `NOT_FOUND` | User is not banned |

---

## GET /bans

List server bans. Requires `BAN_MEMBERS`. Results are paginated.

**Query Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | `integer` | 50 | Max items to return (max 100) |
| `after` | `string` | — | Cursor from previous response |

**Response `200 OK`**

```json
{
  "items": [
    {
      "user_id": 10099,
      "username": "mallory",
      "reason": "Repeated rule violations",
      "banned_at": "2025-11-01T15:00:00Z",
      "banned_by": 10001
    }
  ],
  "cursor": null
}
```
