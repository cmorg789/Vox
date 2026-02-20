# Messages

Feed message endpoints for sending, editing, deleting, reacting, and pinning messages.

All endpoints are under `/api/v1/` and require a Bearer token unless noted otherwise.

---

## List Messages

Retrieve messages from a feed with cursor-based pagination.

```
GET /feeds/{feed_id}/messages
```

**Required Permission:** `READ_HISTORY`

### Query Parameters

| Parameter | Type   | Default | Description                              |
|-----------|--------|---------|------------------------------------------|
| `limit`   | int    | `50`    | Number of messages to return (1--100)    |
| `before`  | string | —       | Message ID cursor; returns messages before this ID |

### Response `200 OK`

```json
{
  "messages": [
    {
      "msg_id": "419870123456789",
      "feed_id": "300000000000001",
      "author_id": "100000000000042",
      "body": "Hello, world!",
      "timestamp": "2026-02-19T12:00:00Z",
      "reply_to": null,
      "mentions": [],
      "embeds": [],
      "attachments": [],
      "components": [],
      "edit_timestamp": null,
      "federated": false,
      "author_address": "alice@vox.example"
    },
    {
      "msg_id": "419870123456780",
      "feed_id": "300000000000001",
      "author_id": "100000000000099",
      "body": "Check this out",
      "timestamp": "2026-02-19T11:58:30Z",
      "reply_to": "419870123456700",
      "mentions": ["100000000000042"],
      "embeds": [
        {
          "title": "Example Page",
          "description": "An example embed",
          "url": "https://example.com",
          "image": "https://example.com/thumb.png"
        }
      ],
      "attachments": [
        {
          "file_id": "500000000000001",
          "name": "screenshot.png",
          "size": 204800,
          "mime": "image/png",
          "url": "https://cdn.vox.example/files/500000000000001"
        }
      ],
      "components": [],
      "edit_timestamp": null,
      "federated": true,
      "author_address": "bob@remote.example"
    }
  ]
}
```

Messages are returned in reverse-chronological order (newest first). Pass the last `msg_id` as the `before` parameter to fetch the next page.

---

## Send Message

```
POST /feeds/{feed_id}/messages
```

**Required Permission:** `SEND_MESSAGES`

### Request Body

```json
{
  "body": "Hello everyone!",
  "reply_to": "419870123456700",
  "mentions": ["100000000000042"],
  "embeds": [],
  "attachments": ["500000000000001"],
  "components": [
    {
      "type": "button",
      "label": "Click me",
      "component_id": "btn_hello"
    }
  ]
}
```

| Field         | Type     | Required | Description                                  |
|---------------|----------|----------|----------------------------------------------|
| `body`        | string   | Yes      | Message content                              |
| `reply_to`    | string   | No       | ID of the message being replied to           |
| `mentions`    | string[] | No       | Array of user IDs mentioned in the message   |
| `embeds`      | object[] | No       | Embed objects to include                     |
| `attachments` | string[] | No       | Array of file IDs (uploaded via file endpoint)|
| `components`  | object[] | No       | Interactive components (buttons, menus)      |

### Response `201 Created`

```json
{
  "msg_id": "419870123456800",
  "timestamp": "2026-02-19T12:05:00Z"
}
```

---

## Edit Message

Edit a message you authored. Only the message author may edit.

```
PATCH /feeds/{feed_id}/messages/{msg_id}
```

**Required Permission:** Author only

### Request Body

```json
{
  "body": "Hello everyone! (edited)"
}
```

### Response `200 OK`

```json
{
  "msg_id": "419870123456800",
  "edit_timestamp": "2026-02-19T12:06:00Z"
}
```

---

## Delete Message

Delete a single message. The author may delete their own messages; otherwise `MANAGE_MESSAGES` is required.

```
DELETE /feeds/{feed_id}/messages/{msg_id}
```

**Required Permission:** Author or `MANAGE_MESSAGES`

### Response `204 No Content`

---

## Bulk Delete Messages

Delete multiple messages at once.

```
POST /feeds/{feed_id}/messages/bulk-delete
```

**Required Permission:** `MANAGE_MESSAGES`

### Request Body

```json
{
  "msg_ids": [
    "419870123456780",
    "419870123456781",
    "419870123456782"
  ]
}
```

### Response `204 No Content`

---

## Add Reaction

```
PUT /feeds/{feed_id}/messages/{msg_id}/reactions/{emoji}
```

**Required Permission:** `ADD_REACTIONS`

The `{emoji}` path parameter is a URL-encoded Unicode emoji or a custom emoji identifier (e.g., `custom:vox_wave:600000000000001`).

### Response `204 No Content`

---

## Remove Reaction

```
DELETE /feeds/{feed_id}/messages/{msg_id}/reactions/{emoji}
```

**Required Permission:** `ADD_REACTIONS`

### Response `204 No Content`

---

## Pin Message

```
PUT /feeds/{feed_id}/pins/{msg_id}
```

**Required Permission:** `MANAGE_MESSAGES`

### Response `204 No Content`

---

## Unpin Message

```
DELETE /feeds/{feed_id}/pins/{msg_id}
```

**Required Permission:** `MANAGE_MESSAGES`

### Response `204 No Content`

---

## List Pinned Messages

```
GET /feeds/{feed_id}/pins
```

### Response `200 OK`

```json
{
  "pins": [
    {
      "msg_id": "419870123456789",
      "feed_id": "300000000000001",
      "author_id": "100000000000042",
      "body": "Important announcement",
      "timestamp": "2026-02-19T12:00:00Z",
      "reply_to": null,
      "mentions": [],
      "embeds": [],
      "attachments": [],
      "components": [],
      "edit_timestamp": null,
      "federated": false,
      "author_address": "alice@vox.example"
    }
  ]
}
```

---

## Error Responses

| Status | Description                                      |
|--------|--------------------------------------------------|
| `400`  | Invalid request body or parameters               |
| `403`  | Missing required permission                      |
| `404`  | Feed or message not found                        |
| `429`  | Rate limited                                     |
