# Channels

This section covers feeds (text channels), rooms (voice channels), categories,
roles, and permission overrides. All endpoints require authentication.
Endpoints that create, modify, or delete resources require the indicated
permission.

---

## Feeds

Feeds are text-based channels. Types: `text`, `forum`, `announcement`.

### GET /feeds

List all feeds the caller can see.

**Response `200 OK`**

```json
{
  "items": [
    {
      "feed_id": 100,
      "name": "general",
      "type": "text",
      "category_id": 1,
      "position": 0,
      "topic": "General discussion",
      "nsfw": false,
      "slowmode_seconds": 0
    },
    {
      "feed_id": 101,
      "name": "announcements",
      "type": "announcement",
      "category_id": 1,
      "position": 1,
      "topic": "Official announcements",
      "nsfw": false,
      "slowmode_seconds": 0
    }
  ]
}
```

### POST /feeds

Create a new feed. Requires `MANAGE_SPACES`.

**Request**

```json
{
  "name": "dev-chat",
  "type": "text",
  "category_id": 2,
  "topic": "Developer discussion",
  "nsfw": false,
  "slowmode_seconds": 0
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | yes | Channel name (1-64 chars, lowercase, hyphens allowed) |
| `type` | `string` | yes | One of `text`, `forum`, `announcement` |
| `category_id` | `uint32` | no | Parent category ID |
| `topic` | `string` | no | Channel topic (max 256 characters) |
| `nsfw` | `boolean` | no | Whether the feed is age-restricted (default `false`) |
| `slowmode_seconds` | `integer` | no | Seconds between messages per user (0 = disabled) |

**Response `201 Created`**

```json
{
  "feed_id": 103,
  "name": "dev-chat",
  "type": "text",
  "category_id": 2,
  "position": 1,
  "topic": "Developer discussion",
  "nsfw": false,
  "slowmode_seconds": 0
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 400 | `INVALID_BODY` | Validation failure |
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SPACES` |

### PATCH /feeds/{feed_id}

Update a feed. Requires `MANAGE_SPACES`. All fields are optional.

**Request**

```json
{
  "name": "dev-general",
  "topic": "All things development",
  "position": 2
}
```

**Response `200 OK`**

```json
{
  "feed_id": 103,
  "name": "dev-general",
  "type": "text",
  "category_id": 2,
  "position": 2,
  "topic": "All things development",
  "nsfw": false,
  "slowmode_seconds": 0
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SPACES` |
| 404 | `NOT_FOUND` | Feed does not exist |

### DELETE /feeds/{feed_id}

Delete a feed and all its messages. Requires `MANAGE_SPACES`.

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SPACES` |
| 404 | `NOT_FOUND` | Feed does not exist |

---

## Rooms

Rooms are real-time audio channels. Types: `voice`, `stage`.

### GET /rooms

List all rooms the caller can see.

**Response `200 OK`**

```json
{
  "items": [
    {
      "room_id": 200,
      "name": "Voice Lounge",
      "type": "voice",
      "category_id": 1,
      "position": 0,
      "user_limit": 0,
      "bitrate": 64000
    },
    {
      "room_id": 201,
      "name": "Town Hall",
      "type": "stage",
      "category_id": 2,
      "position": 0,
      "user_limit": 500,
      "bitrate": 96000
    }
  ]
}
```

### POST /rooms

Create a new room. Requires `MANAGE_SPACES`.

**Request**

```json
{
  "name": "Music Room",
  "type": "voice",
  "category_id": 1,
  "user_limit": 10,
  "bitrate": 128000
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | yes | Room name (1-64 characters) |
| `type` | `string` | yes | One of `voice`, `stage` |
| `category_id` | `uint32` | no | Parent category ID |
| `user_limit` | `integer` | no | Max users (0 = unlimited, default 0) |
| `bitrate` | `integer` | no | Audio bitrate in bps (default 64000) |

**Response `201 Created`**

```json
{
  "room_id": 202,
  "name": "Music Room",
  "type": "voice",
  "category_id": 1,
  "position": 1,
  "user_limit": 10,
  "bitrate": 128000
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 400 | `INVALID_BODY` | Validation failure |
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SPACES` |

### PATCH /rooms/{room_id}

Update a room. Requires `MANAGE_SPACES`. All fields are optional.

**Request**

```json
{
  "name": "Chill Music Room",
  "user_limit": 20
}
```

**Response `200 OK`**

```json
{
  "room_id": 202,
  "name": "Chill Music Room",
  "type": "voice",
  "category_id": 1,
  "position": 1,
  "user_limit": 20,
  "bitrate": 128000
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SPACES` |
| 404 | `NOT_FOUND` | Room does not exist |

### DELETE /rooms/{room_id}

Delete a room. Requires `MANAGE_SPACES`.

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SPACES` |
| 404 | `NOT_FOUND` | Room does not exist |

---

## Categories

Categories group feeds and rooms in the server layout.

### POST /categories

Create a new category. Requires `MANAGE_SPACES`.

**Request**

```json
{
  "name": "Projects"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | yes | Category name (1-64 characters) |

**Response `201 Created`**

```json
{
  "category_id": 3,
  "name": "Projects",
  "position": 2
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SPACES` |

### PATCH /categories/{category_id}

Update a category. Requires `MANAGE_SPACES`.

**Request**

```json
{
  "name": "Active Projects",
  "position": 1
}
```

**Response `200 OK`**

```json
{
  "category_id": 3,
  "name": "Active Projects",
  "position": 1
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SPACES` |
| 404 | `NOT_FOUND` | Category does not exist |

### DELETE /categories/{category_id}

Delete a category. Feeds and rooms in the category are moved to uncategorized.
Requires `MANAGE_SPACES`.

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SPACES` |
| 404 | `NOT_FOUND` | Category does not exist |

---

## Roles

### GET /roles

List all roles in the server.

**Response `200 OK`**

```json
{
  "items": [
    {
      "role_id": 1,
      "name": "Member",
      "color": "#99AAB5",
      "position": 0,
      "permissions": 104324,
      "mentionable": true,
      "hoist": false
    },
    {
      "role_id": 2,
      "name": "Moderator",
      "color": "#E74C3C",
      "position": 1,
      "permissions": 1071766,
      "mentionable": true,
      "hoist": true
    }
  ]
}
```

### POST /roles

Create a new role. Requires `MANAGE_ROLES`.

**Request**

```json
{
  "name": "Contributor",
  "color": "#2ECC71",
  "permissions": 104324,
  "mentionable": true,
  "hoist": false
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | yes | Role name (1-64 characters) |
| `color` | `string` | no | Hex color code (default `#99AAB5`) |
| `permissions` | `integer` | no | Permission bitfield (default 0) |
| `mentionable` | `boolean` | no | Whether the role can be mentioned (default `false`) |
| `hoist` | `boolean` | no | Whether the role is displayed separately in the member list (default `false`) |

**Response `201 Created`**

```json
{
  "role_id": 3,
  "name": "Contributor",
  "color": "#2ECC71",
  "position": 2,
  "permissions": 104324,
  "mentionable": true,
  "hoist": false
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_ROLES` |

### PATCH /roles/{role_id}

Update a role. Requires `MANAGE_ROLES`. All fields are optional.

**Request**

```json
{
  "name": "Active Contributor",
  "color": "#27AE60"
}
```

**Response `200 OK`**

```json
{
  "role_id": 3,
  "name": "Active Contributor",
  "color": "#27AE60",
  "position": 2,
  "permissions": 104324,
  "mentionable": true,
  "hoist": false
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_ROLES` |
| 404 | `NOT_FOUND` | Role does not exist |

### DELETE /roles/{role_id}

Delete a role. Requires `MANAGE_ROLES`.

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_ROLES` |
| 404 | `NOT_FOUND` | Role does not exist |

### PUT /members/{user_id}/roles/{role_id}

Assign a role to a member. Requires `MANAGE_ROLES`.

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_ROLES` |
| 404 | `NOT_FOUND` | Member or role does not exist |

### DELETE /members/{user_id}/roles/{role_id}

Remove a role from a member. Requires `MANAGE_ROLES`.

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_ROLES` |
| 404 | `NOT_FOUND` | Member or role does not exist |

---

## Permission Overrides

Permission overrides allow granting or denying specific permissions for a role
or user on a particular feed or room. The `target_type` is either `role` or
`user`, and `target_id` is the corresponding `role_id` or `user_id`.

### PUT /feeds/{feed_id}/permissions/{target_type}/{target_id}

Set a permission override on a feed. Requires `MANAGE_SPACES`.

**Request**

```json
{
  "allow": 2048,
  "deny": 4096
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `allow` | `integer` | yes | Permission bitfield to explicitly allow |
| `deny` | `integer` | yes | Permission bitfield to explicitly deny |

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 400 | `INVALID_BODY` | Invalid permission values |
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SPACES` |
| 404 | `NOT_FOUND` | Feed or target does not exist |

### DELETE /feeds/{feed_id}/permissions/{target_type}/{target_id}

Remove a permission override from a feed. Requires `MANAGE_SPACES`.

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SPACES` |
| 404 | `NOT_FOUND` | Feed, target, or override does not exist |

### PUT /rooms/{room_id}/permissions/{target_type}/{target_id}

Set a permission override on a room. Requires `MANAGE_SPACES`.

**Request**

```json
{
  "allow": 2048,
  "deny": 4096
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `allow` | `integer` | yes | Permission bitfield to explicitly allow |
| `deny` | `integer` | yes | Permission bitfield to explicitly deny |

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 400 | `INVALID_BODY` | Invalid permission values |
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SPACES` |
| 404 | `NOT_FOUND` | Room or target does not exist |

### DELETE /rooms/{room_id}/permissions/{target_type}/{target_id}

Remove a permission override from a room. Requires `MANAGE_SPACES`.

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SPACES` |
| 404 | `NOT_FOUND` | Room, target, or override does not exist |
