# Emoji, Stickers, and Embeds

Endpoints for managing custom emoji, stickers, and resolving URL embeds.

All endpoints are under `/api/v1/` and require a Bearer token.

---

## List Emoji

Retrieve custom emoji with cursor pagination.

```
GET /emoji
```

### Query Parameters

| Parameter | Type   | Default | Description                    |
|-----------|--------|---------|--------------------------------|
| `limit`   | int    | `50`    | Number of emoji to return      |
| `cursor`  | string | —       | Pagination cursor              |

### Response `200 OK`

```json
{
  "emoji": [
    {
      "emoji_id": "600000000000001",
      "name": "vox_wave",
      "url": "https://cdn.vox.example/emoji/600000000000001.png",
      "creator_id": "100000000000042",
      "created_at": "2026-02-10T08:00:00Z"
    },
    {
      "emoji_id": "600000000000002",
      "name": "vox_thumbsup",
      "url": "https://cdn.vox.example/emoji/600000000000002.png",
      "creator_id": "100000000000099",
      "created_at": "2026-02-11T14:30:00Z"
    }
  ],
  "cursor": "600000000000002"
}
```

---

## Create Emoji

```
POST /emoji
```

**Required Permission:** `MANAGE_EMOJI`

**Content-Type:** `multipart/form-data`

### Form Fields

| Field   | Type   | Required | Description                    |
|---------|--------|----------|--------------------------------|
| `name`  | string | Yes      | Emoji name (alphanumeric and underscores) |
| `image` | binary | Yes      | Image file (PNG, GIF, or WebP) |

### Response `201 Created`

```json
{
  "emoji_id": "600000000000003",
  "name": "vox_rocket",
  "url": "https://cdn.vox.example/emoji/600000000000003.png",
  "creator_id": "100000000000042",
  "created_at": "2026-02-19T12:00:00Z"
}
```

---

## Delete Emoji

```
DELETE /emoji/{emoji_id}
```

**Required Permission:** `MANAGE_EMOJI`

### Response `204 No Content`

---

## List Stickers

Retrieve custom stickers with cursor pagination.

```
GET /stickers
```

### Query Parameters

| Parameter | Type   | Default | Description                      |
|-----------|--------|---------|----------------------------------|
| `limit`   | int    | `50`    | Number of stickers to return     |
| `cursor`  | string | —       | Pagination cursor                |

### Response `200 OK`

```json
{
  "stickers": [
    {
      "sticker_id": "650000000000001",
      "name": "happy_vox",
      "url": "https://cdn.vox.example/stickers/650000000000001.png",
      "creator_id": "100000000000042",
      "created_at": "2026-02-12T10:00:00Z"
    }
  ],
  "cursor": "650000000000001"
}
```

---

## Create Sticker

```
POST /stickers
```

**Required Permission:** `MANAGE_EMOJI`

**Content-Type:** `multipart/form-data`

### Form Fields

| Field   | Type   | Required | Description                    |
|---------|--------|----------|--------------------------------|
| `name`  | string | Yes      | Sticker name                   |
| `image` | binary | Yes      | Image file (PNG, APNG, or Lottie JSON) |

### Response `201 Created`

```json
{
  "sticker_id": "650000000000002",
  "name": "cool_vox",
  "url": "https://cdn.vox.example/stickers/650000000000002.png",
  "creator_id": "100000000000042",
  "created_at": "2026-02-19T12:00:00Z"
}
```

---

## Delete Sticker

```
DELETE /stickers/{sticker_id}
```

**Required Permission:** `MANAGE_EMOJI`

### Response `204 No Content`

---

## Resolve Embed

Fetch Open Graph / oEmbed metadata for a URL. Used by clients to generate link previews.

```
POST /embeds/resolve
```

### Request Body

```json
{
  "url": "https://example.com/article/interesting-post"
}
```

### Response `200 OK`

```json
{
  "title": "An Interesting Post",
  "description": "This article covers the latest developments in...",
  "image": "https://example.com/og-image.jpg",
  "video": null
}
```

| Field         | Type        | Description                              |
|---------------|-------------|------------------------------------------|
| `title`       | string      | Page title from metadata                 |
| `description` | string      | Page description from metadata           |
| `image`       | string/null | Preview image URL                        |
| `video`       | string/null | Embeddable video URL                     |

---

## Error Responses

| Status | Description                                      |
|--------|--------------------------------------------------|
| `400`  | Invalid request body, name, or image format      |
| `403`  | Missing `MANAGE_EMOJI` permission                |
| `404`  | Emoji or sticker not found                       |
| `413`  | Image exceeds maximum allowed size               |
| `429`  | Rate limited                                     |
