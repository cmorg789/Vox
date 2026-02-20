# Threads

Thread endpoints for creating, managing, and messaging within threads attached to feed messages.

All endpoints are under `/api/v1/` and require a Bearer token.

---

## Create Thread

Create a new thread from an existing message in a feed.

```
POST /feeds/{feed_id}/threads
```

**Required Permission:** `CREATE_THREADS`

### Request Body

```json
{
  "parent_msg_id": "419870123456789",
  "name": "Design discussion"
}
```

| Field            | Type   | Required | Description                          |
|------------------|--------|----------|--------------------------------------|
| `parent_msg_id`  | string | Yes      | ID of the message to thread from     |
| `name`           | string | Yes      | Display name for the thread          |

### Response `201 Created`

```json
{
  "thread_id": "700000000000001",
  "feed_id": "300000000000001",
  "parent_msg_id": "419870123456789",
  "name": "Design discussion",
  "archived": false,
  "locked": false,
  "created_at": "2026-02-19T12:00:00Z",
  "creator_id": "100000000000042"
}
```

---

## Update Thread

```
PATCH /threads/{thread_id}
```

### Request Body

All fields are optional.

```json
{
  "name": "Design discussion (resolved)",
  "archived": true,
  "locked": false
}
```

| Field      | Type    | Description                                 |
|------------|---------|---------------------------------------------|
| `name`     | string  | New display name for the thread             |
| `archived` | boolean | Archive the thread (hides from active list) |
| `locked`   | boolean | Prevent new messages in the thread          |

### Response `200 OK`

```json
{
  "thread_id": "700000000000001",
  "feed_id": "300000000000001",
  "parent_msg_id": "419870123456789",
  "name": "Design discussion (resolved)",
  "archived": true,
  "locked": false,
  "created_at": "2026-02-19T12:00:00Z",
  "creator_id": "100000000000042"
}
```

---

## Delete Thread

```
DELETE /threads/{thread_id}
```

**Required Permission:** `MANAGE_THREADS`

### Response `204 No Content`

---

## List Thread Messages

Retrieve messages within a thread. Uses the same cursor pagination as feed messages.

```
GET /feeds/{feed_id}/threads/{thread_id}/messages
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
      "msg_id": "419870123456900",
      "feed_id": "300000000000001",
      "author_id": "100000000000042",
      "body": "I think we should go with option A",
      "timestamp": "2026-02-19T12:10:00Z",
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

## Send Thread Message

```
POST /feeds/{feed_id}/threads/{thread_id}/messages
```

**Required Permission:** `SEND_IN_THREADS`

### Request Body

```json
{
  "body": "Good point, let's proceed with that."
}
```

The request body accepts the same fields as [Send Message](messages.md#send-message): `body`, `reply_to`, `mentions`, `embeds`, `attachments`, `components`.

### Response `201 Created`

```json
{
  "msg_id": "419870123456901",
  "timestamp": "2026-02-19T12:11:00Z"
}
```

---

## Subscribe to Thread

Add yourself to a thread's subscriber list to receive notifications for new messages.

```
PUT /feeds/{feed_id}/threads/{thread_id}/subscribers
```

### Response `204 No Content`

---

## Unsubscribe from Thread

Remove yourself from a thread's subscriber list.

```
DELETE /feeds/{feed_id}/threads/{thread_id}/subscribers
```

### Response `204 No Content`

---

## Error Responses

| Status | Description                                      |
|--------|--------------------------------------------------|
| `400`  | Invalid request body or parameters               |
| `403`  | Missing required permission or thread is locked   |
| `404`  | Feed, thread, or message not found               |
| `429`  | Rate limited                                     |
