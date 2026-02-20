# Webhooks

Endpoints for creating and managing webhooks. Webhooks allow external services to post messages into a feed without a full bot or user account.

All management endpoints are under `/api/v1/` and require a Bearer token. Webhook execution does not require authentication.

---

## Create Webhook

```
POST /feeds/{feed_id}/webhooks
```

**Required Permission:** `MANAGE_WEBHOOKS`

### Request Body

```json
{
  "name": "CI Notifications",
  "avatar": "https://cdn.vox.example/avatars/ci-bot.png"
}
```

| Field    | Type   | Required | Description                    |
|----------|--------|----------|--------------------------------|
| `name`   | string | Yes      | Display name for the webhook   |
| `avatar` | string | No       | Avatar URL                     |

### Response `201 Created`

```json
{
  "webhook_id": "900000000000001",
  "feed_id": "300000000000001",
  "name": "CI Notifications",
  "avatar": "https://cdn.vox.example/avatars/ci-bot.png",
  "token": "whk_a1b2c3d4e5f6g7h8i9j0"
}
```

!!! warning
    The `token` is only returned on creation. Store it securely -- it cannot be retrieved again.

---

## Update Webhook

```
PATCH /webhooks/{webhook_id}
```

**Required Permission:** `MANAGE_WEBHOOKS`

### Request Body

```json
{
  "name": "Deploy Notifications",
  "avatar": "https://cdn.vox.example/avatars/deploy-bot.png"
}
```

### Response `200 OK`

```json
{
  "webhook_id": "900000000000001",
  "feed_id": "300000000000001",
  "name": "Deploy Notifications",
  "avatar": "https://cdn.vox.example/avatars/deploy-bot.png"
}
```

---

## Delete Webhook

```
DELETE /webhooks/{webhook_id}
```

**Required Permission:** `MANAGE_WEBHOOKS`

### Response `204 No Content`

---

## List Feed Webhooks

```
GET /feeds/{feed_id}/webhooks
```

### Response `200 OK`

```json
{
  "webhooks": [
    {
      "webhook_id": "900000000000001",
      "feed_id": "300000000000001",
      "name": "CI Notifications",
      "avatar": "https://cdn.vox.example/avatars/ci-bot.png"
    },
    {
      "webhook_id": "900000000000002",
      "feed_id": "300000000000001",
      "name": "GitHub Updates",
      "avatar": null
    }
  ]
}
```

Note that the `token` is never returned in list responses.

---

## Execute Webhook

Post a message to the feed via webhook. **No authentication required** -- the token in the URL serves as the credential.

```
POST /webhooks/{webhook_id}/{token}
```

### Request Body

```json
{
  "body": "Build #1234 passed on `main` branch.",
  "embeds": [
    {
      "title": "Build Details",
      "description": "All 847 tests passed in 3m 12s.",
      "url": "https://ci.example.com/builds/1234"
    }
  ]
}
```

| Field    | Type     | Required | Description                    |
|----------|----------|----------|--------------------------------|
| `body`   | string   | Yes      | Message content                |
| `embeds` | object[] | No       | Embed objects                  |

### Response `204 No Content`

!!! tip "Rate Limiting"
    Rate limiting is recommended on webhook execution to prevent abuse. The server enforces per-webhook rate limits. Exceeding the limit returns `429 Too Many Requests` with a `Retry-After` header.

---

## Error Responses

| Status | Description                                      |
|--------|--------------------------------------------------|
| `400`  | Invalid request body                             |
| `401`  | Invalid webhook token (execution endpoint)       |
| `403`  | Missing `MANAGE_WEBHOOKS` permission             |
| `404`  | Webhook or feed not found                        |
| `429`  | Rate limited                                     |
