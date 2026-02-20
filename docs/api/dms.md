# Direct Messages

Endpoints for one-on-one and group direct messages.

All endpoints are under `/api/v1/` and require a Bearer token.

---

## Create DM

Open a one-on-one DM or create a group DM.

```
POST /dms
```

### One-on-One DM

```json
{
  "recipient_id": "100000000000099"
}
```

### Group DM

```json
{
  "recipient_ids": [
    "100000000000099",
    "100000000000100",
    "100000000000101"
  ],
  "name": "Project team"
}
```

| Field           | Type     | Required | Description                                 |
|-----------------|----------|----------|---------------------------------------------|
| `recipient_id`  | string   | *        | User ID for a 1:1 DM                       |
| `recipient_ids` | string[] | *        | User IDs for a group DM                    |
| `name`          | string   | No       | Display name (group DMs only)               |

Provide either `recipient_id` or `recipient_ids`, not both. The maximum number of group DM participants is server-configurable.

### Response `201 Created`

```json
{
  "dm_id": "800000000000001",
  "type": "group",
  "name": "Project team",
  "icon": null,
  "owner_id": "100000000000042",
  "recipients": [
    {"user_id": "100000000000042", "username": "alice"},
    {"user_id": "100000000000099", "username": "bob"},
    {"user_id": "100000000000100", "username": "carol"},
    {"user_id": "100000000000101", "username": "dave"}
  ],
  "created_at": "2026-02-19T12:00:00Z"
}
```

For 1:1 DMs, `type` is `"direct"`, `name` and `icon` are `null`, and `owner_id` is `null`.

---

## List DMs

```
GET /dms
```

### Response `200 OK`

```json
{
  "dms": [
    {
      "dm_id": "800000000000001",
      "type": "group",
      "name": "Project team",
      "icon": null,
      "owner_id": "100000000000042",
      "recipients": [
        {"user_id": "100000000000042", "username": "alice"},
        {"user_id": "100000000000099", "username": "bob"}
      ],
      "created_at": "2026-02-19T12:00:00Z",
      "last_message_id": "419870123456800"
    },
    {
      "dm_id": "800000000000002",
      "type": "direct",
      "name": null,
      "icon": null,
      "owner_id": null,
      "recipients": [
        {"user_id": "100000000000042", "username": "alice"},
        {"user_id": "100000000000050", "username": "eve"}
      ],
      "created_at": "2026-02-18T09:00:00Z",
      "last_message_id": "419870123456750"
    }
  ]
}
```

---

## Hide DM

Hides the DM from your list. Does not delete any messages. The DM reappears if a new message is received.

```
DELETE /dms/{dm_id}
```

### Response `204 No Content`

---

## Update Group DM

Update the name or icon of a group DM. Only applicable to group DMs.

```
PATCH /dms/{dm_id}
```

### Request Body

```json
{
  "name": "Renamed project team",
  "icon": "https://cdn.vox.example/icons/team.png"
}
```

| Field  | Type   | Description                 |
|--------|--------|-----------------------------|
| `name` | string | New display name            |
| `icon` | string | New icon URL                |

### Response `200 OK`

```json
{
  "dm_id": "800000000000001",
  "type": "group",
  "name": "Renamed project team",
  "icon": "https://cdn.vox.example/icons/team.png",
  "owner_id": "100000000000042",
  "recipients": [],
  "created_at": "2026-02-19T12:00:00Z"
}
```

---

## Add Recipient to Group DM

```
PUT /dms/{dm_id}/recipients/{user_id}
```

### Response `204 No Content`

---

## Remove Recipient from Group DM

```
DELETE /dms/{dm_id}/recipients/{user_id}
```

### Response `204 No Content`

---

## Send DM Message

```
POST /dms/{dm_id}/messages
```

### Request Body

Same format as [feed messages](messages.md#send-message).

```json
{
  "body": "Hey, how's it going?",
  "reply_to": null,
  "mentions": [],
  "embeds": [],
  "attachments": [],
  "components": []
}
```

### Response `201 Created`

```json
{
  "msg_id": "419870123456810",
  "timestamp": "2026-02-19T12:15:00Z"
}
```

---

## List DM Messages

```
GET /dms/{dm_id}/messages
```

### Query Parameters

| Parameter | Type   | Default | Description                              |
|-----------|--------|---------|------------------------------------------|
| `limit`   | int    | `50`    | Number of messages to return (1--100)    |
| `before`  | string | —       | Message ID cursor                        |

### Response `200 OK`

```json
{
  "messages": [
    {
      "msg_id": "419870123456810",
      "feed_id": null,
      "author_id": "100000000000042",
      "body": "Hey, how's it going?",
      "timestamp": "2026-02-19T12:15:00Z",
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

## Edit DM Message

```
PATCH /dms/{dm_id}/messages/{msg_id}
```

Author only. Same request body as [Edit Message](messages.md#edit-message).

### Request Body

```json
{
  "body": "Hey, how's it going? (edited)"
}
```

### Response `200 OK`

```json
{
  "msg_id": "419870123456810",
  "edit_timestamp": "2026-02-19T12:16:00Z"
}
```

---

## Delete DM Message

```
DELETE /dms/{dm_id}/messages/{msg_id}
```

Author only.

### Response `204 No Content`

---

## Add Reaction to DM Message

```
PUT /dms/{dm_id}/messages/{msg_id}/reactions/{emoji}
```

### Response `204 No Content`

---

## Remove Reaction from DM Message

```
DELETE /dms/{dm_id}/messages/{msg_id}/reactions/{emoji}
```

### Response `204 No Content`

---

## Mark DM as Read

Mark all messages up to the given ID as read. Dispatches a `dm_read_notify` gateway event to other sessions.

```
POST /dms/{dm_id}/read
```

### Request Body

```json
{
  "up_to_msg_id": "419870123456810"
}
```

### Response `204 No Content`

The server dispatches a `dm_read_notify` event via the gateway to all of the user's active sessions:

```json
{
  "event": "dm_read_notify",
  "data": {
    "dm_id": "800000000000001",
    "up_to_msg_id": "419870123456810"
  }
}
```

---

## DM Privacy Settings

### Get DM Settings

```
GET /users/@me/dm-settings
```

### Response `200 OK`

```json
{
  "dm_permission": "friends_only"
}
```

### Update DM Settings

```
PATCH /users/@me/dm-settings
```

### Request Body

```json
{
  "dm_permission": "mutual_servers"
}
```

| Value            | Description                                        |
|------------------|----------------------------------------------------|
| `everyone`       | Anyone can open a DM with you                      |
| `friends_only`   | Only users on your friends list                    |
| `mutual_servers` | Only users who share a server with you             |
| `nobody`         | No one can open new DMs with you                   |

### Response `200 OK`

```json
{
  "dm_permission": "mutual_servers"
}
```

---

## Error Responses

| Status | Description                                      |
|--------|--------------------------------------------------|
| `400`  | Invalid request body or parameters               |
| `403`  | DM permission denied by recipient's settings     |
| `404`  | DM or message not found                          |
| `429`  | Rate limited                                     |
