# Users

All endpoints in this section require authentication unless otherwise noted.

---

## GET /users/{user_id}

Retrieve a user's public profile.

**Response `200 OK`**

```json
{
  "user_id": 10001,
  "username": "alice",
  "display_name": "Alice",
  "avatar": "https://cdn.vox.example.com/avatars/10001/abc123.webp",
  "bio": "Building things.",
  "created_at": "2025-01-10T14:22:00Z"
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 404 | `NOT_FOUND` | User does not exist |

---

## GET /users/{user_id}/presence

Retrieve a user's current presence status.

**Response `200 OK`**

```json
{
  "user_id": 10001,
  "status": "online",
  "custom_status": "Hacking on Vox",
  "last_seen_at": "2025-12-20T18:45:00Z"
}
```

`status` is one of `online`, `idle`, `dnd`, or `offline`.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 404 | `NOT_FOUND` | User does not exist |

---

## PATCH /users/@me

Update the authenticated user's profile. All fields are optional; only
provided fields are changed.

**Request**

```json
{
  "display_name": "Alice B.",
  "avatar": "base64-encoded-image-data",
  "bio": "Building cool things."
}
```

| Field | Type | Description |
|---|---|---|
| `display_name` | `string` | New display name (1-64 characters) |
| `avatar` | `string` | Base64-encoded image (JPEG, PNG, or WebP; max 4 MB) |
| `bio` | `string` | Short biography (max 256 characters) |

**Response `200 OK`**

```json
{
  "user_id": 10001,
  "username": "alice",
  "display_name": "Alice B.",
  "avatar": "https://cdn.vox.example.com/avatars/10001/def456.webp",
  "bio": "Building cool things.",
  "created_at": "2025-01-10T14:22:00Z"
}
```

---

## PUT /users/@me/blocks/{user_id}

Block a user. Blocking has the following effects:

- Any existing DM channel between the two users is closed.
- The blocked user cannot open a new DM with the caller.
- The blocked user's presence is hidden from the caller.

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 404 | `NOT_FOUND` | Target user does not exist |

---

## DELETE /users/@me/blocks/{user_id}

Unblock a user.

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 404 | `NOT_FOUND` | Target user does not exist or was not blocked |

---

## PUT /users/@me/friends/{user_id}

Send or accept a friend request. If the target user has already sent a request
to the caller, this endpoint accepts it and the friendship is established
immediately.

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 404 | `NOT_FOUND` | Target user does not exist |

---

## DELETE /users/@me/friends/{user_id}

Remove a friend or cancel an outgoing friend request.

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 404 | `NOT_FOUND` | Target user does not exist or is not a friend |

---

## GET /users/@me/friends

List the authenticated user's friends. Results are paginated.

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
      "user_id": 10002,
      "username": "bob",
      "display_name": "Bob",
      "status": "online",
      "since": "2025-03-15T09:00:00Z"
    },
    {
      "user_id": 10003,
      "username": "carol",
      "display_name": "Carol",
      "status": "offline",
      "since": "2025-06-01T12:00:00Z"
    }
  ],
  "cursor": "eyJpZCI6MTAwMDN9"
}
```
