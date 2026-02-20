# Search, Sync, and Gateway Info

Endpoints for message search, state synchronization after reconnection, and gateway discovery.

All endpoints are under `/api/v1/` and require a Bearer token unless noted otherwise.

---

## Search Messages

Full-text search across messages the authenticated user has access to.

```
GET /messages/search
```

### Query Parameters

| Parameter   | Type    | Required | Description                              |
|-------------|---------|----------|------------------------------------------|
| `query`     | string  | Yes      | Search query string                      |
| `feed_id`   | string  | No       | Restrict results to a specific feed      |
| `author_id` | string  | No       | Restrict results to a specific author    |
| `before`    | string  | No       | Messages before this timestamp           |
| `after`     | string  | No       | Messages after this timestamp            |
| `has_file`  | boolean | No       | Only messages with file attachments      |
| `has_embed` | boolean | No       | Only messages with embeds                |
| `pinned`    | boolean | No       | Only pinned messages                     |
| `limit`     | int     | No       | Number of results (default 25, max 100)  |
| `cursor`    | string  | No       | Pagination cursor                        |

### Example Request

```
GET /api/v1/messages/search?query=hello&feed_id=300000000000001&author_id=100000000000042&has_file=true&limit=10
```

### Response `200 OK`

```json
{
  "messages": [
    {
      "msg_id": "419870123456789",
      "feed_id": "300000000000001",
      "author_id": "100000000000042",
      "body": "Hello everyone, here is the file you requested.",
      "timestamp": "2026-02-19T10:00:00Z",
      "reply_to": null,
      "mentions": [],
      "embeds": [],
      "attachments": [
        {
          "file_id": "500000000000001",
          "name": "report.pdf",
          "size": 1048576,
          "mime": "application/pdf",
          "url": "https://cdn.vox.example/files/500000000000001"
        }
      ],
      "components": [],
      "edit_timestamp": null,
      "federated": false,
      "author_address": "alice@vox.example"
    }
  ],
  "cursor": "419870123456789",
  "total_results": 1
}
```

---

## Sync State

Fetch events that occurred since a given timestamp. Used after a failed gateway resume to catch up on missed state changes without a full state refetch.

```
POST /sync
```

### Request Body

```json
{
  "since_timestamp": "2026-02-19T11:00:00Z",
  "categories": ["members", "roles", "feeds", "emoji"]
}
```

| Field             | Type     | Required | Description                                |
|-------------------|----------|----------|--------------------------------------------|
| `since_timestamp` | string   | Yes      | ISO 8601 timestamp to sync from            |
| `categories`      | string[] | Yes      | Categories of state to sync                |

### Available Categories

| Category     | Description                          |
|--------------|--------------------------------------|
| `members`    | Member joins, leaves, updates        |
| `roles`      | Role creates, updates, deletes       |
| `feeds`      | Feed creates, updates, deletes       |
| `rooms`      | Voice room creates, updates, deletes |
| `categories` | Category creates, updates, deletes   |
| `emoji`      | Emoji creates, deletes               |
| `bans`       | Ban and unban events                 |
| `invites`    | Invite creates, deletes              |

### Response `200 OK`

```json
{
  "events": [
    {
      "event_type": "member.join",
      "data": {
        "user_id": "100000000000150",
        "username": "new_user",
        "joined_at": "2026-02-19T11:30:00Z"
      },
      "timestamp": "2026-02-19T11:30:00Z"
    },
    {
      "event_type": "role.update",
      "data": {
        "role_id": "200000000000005",
        "name": "Moderator",
        "permissions": 2147483647
      },
      "timestamp": "2026-02-19T11:45:00Z"
    },
    {
      "event_type": "emoji.create",
      "data": {
        "emoji_id": "600000000000010",
        "name": "new_emoji",
        "url": "https://cdn.vox.example/emoji/600000000000010.png"
      },
      "timestamp": "2026-02-19T11:50:00Z"
    }
  ],
  "server_timestamp": "2026-02-19T12:00:00Z"
}
```

If `since_timestamp` is too old (beyond the server's event retention window), the response returns an empty events array. The client should fall back to a full state fetch.

```json
{
  "events": [],
  "server_timestamp": "2026-02-19T12:00:00Z"
}
```

---

## Gateway Info

Retrieve the gateway WebSocket URL and media server URL. **No authentication required.**

```
GET /gateway
```

### Response `200 OK`

```json
{
  "url": "wss://gateway.vox.example/v1",
  "media_url": "wss://media.vox.example/v1",
  "protocol_version": 3,
  "min_version": 1,
  "max_version": 3
}
```

| Field              | Type   | Description                                    |
|--------------------|--------|------------------------------------------------|
| `url`              | string | WebSocket URL for the main gateway             |
| `media_url`        | string | WebSocket URL for the media/voice server       |
| `protocol_version` | int    | Current recommended protocol version           |
| `min_version`      | int    | Minimum supported protocol version             |
| `max_version`      | int    | Maximum supported protocol version             |

Clients should connect to the `url` using a protocol version between `min_version` and `max_version`. Using `protocol_version` is recommended for the best experience.

---

## Error Responses

| Status | Description                                      |
|--------|--------------------------------------------------|
| `400`  | Invalid request body or missing `query` parameter|
| `403`  | Missing permission to search in specified feed   |
| `429`  | Rate limited                                     |
