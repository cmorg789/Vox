# Server

All endpoints in this section require authentication. Endpoints that modify
server settings require the `MANAGE_SERVER` permission.

---

## GET /server

Retrieve public server metadata.

**Response `200 OK`**

```json
{
  "name": "Vox Community",
  "icon": "https://cdn.vox.example.com/icons/server/abc123.webp",
  "description": "The official Vox community server.",
  "member_count": 4827
}
```

---

## PATCH /server

Update server metadata. Requires `MANAGE_SERVER`.

**Request**

```json
{
  "name": "Vox HQ",
  "icon": "base64-encoded-image-data",
  "description": "Official headquarters for Vox development."
}
```

| Field | Type | Description |
|---|---|---|
| `name` | `string` | Server name (1-64 characters) |
| `icon` | `string` | Base64-encoded image (JPEG, PNG, or WebP; max 4 MB) |
| `description` | `string` | Server description (max 512 characters) |

All fields are optional; only provided fields are changed.

**Response `200 OK`**

```json
{
  "name": "Vox HQ",
  "icon": "https://cdn.vox.example.com/icons/server/def456.webp",
  "description": "Official headquarters for Vox development.",
  "member_count": 4827
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SERVER` |

---

## GET /server/limits

Retrieve the current server-wide limits. Requires `MANAGE_SERVER`.

**Response `200 OK`**

```json
{
  "max_members": 10000,
  "max_feeds": 200,
  "max_rooms": 100,
  "max_categories": 50,
  "max_roles": 100,
  "max_message_length": 4000,
  "max_attachment_size_mb": 50,
  "max_reactions_per_message": 20
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SERVER` |

---

## PATCH /server/limits

Update server-wide limits. Changes are written to the database and
**hot-reloaded** -- no restart is required. Requires `MANAGE_SERVER`.

**Request**

```json
{
  "max_message_length": 8000,
  "max_attachment_size_mb": 100
}
```

All fields are optional; only provided fields are changed.

**Response `200 OK`**

Returns the full limits object with updated values:

```json
{
  "max_members": 10000,
  "max_feeds": 200,
  "max_rooms": 100,
  "max_categories": 50,
  "max_roles": 100,
  "max_message_length": 8000,
  "max_attachment_size_mb": 100,
  "max_reactions_per_message": 20
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 400 | `INVALID_BODY` | Value out of allowed range |
| 403 | `MISSING_PERMISSIONS` | Caller lacks `MANAGE_SERVER` |

---

## GET /server/layout

Retrieve the full server layout: categories, feeds, and rooms in display
order.

**Response `200 OK`**

```json
{
  "categories": [
    {
      "category_id": 1,
      "name": "General",
      "position": 0
    },
    {
      "category_id": 2,
      "name": "Development",
      "position": 1
    }
  ],
  "feeds": [
    {
      "feed_id": 100,
      "name": "general",
      "type": "text",
      "category_id": 1,
      "position": 0,
      "topic": "General discussion"
    },
    {
      "feed_id": 101,
      "name": "announcements",
      "type": "announcement",
      "category_id": 1,
      "position": 1,
      "topic": "Official announcements"
    },
    {
      "feed_id": 102,
      "name": "help",
      "type": "forum",
      "category_id": 2,
      "position": 0,
      "topic": "Ask questions and get help"
    }
  ],
  "rooms": [
    {
      "room_id": 200,
      "name": "Voice Lounge",
      "type": "voice",
      "category_id": 1,
      "position": 0,
      "user_limit": 0
    },
    {
      "room_id": 201,
      "name": "Town Hall",
      "type": "stage",
      "category_id": 2,
      "position": 0,
      "user_limit": 500
    }
  ]
}
```

### Feed Types

| Type | Description |
|---|---|
| `text` | Standard text channel for messages |
| `forum` | Thread-based discussion channel |
| `announcement` | Broadcast channel; only permitted roles can post |

### Room Types

| Type | Description |
|---|---|
| `voice` | Real-time voice channel; all participants can speak |
| `stage` | Moderated audio channel; speakers are managed by hosts |
