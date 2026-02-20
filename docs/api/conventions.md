# API Conventions

## Base URL

All endpoints are prefixed with:

```
/api/v1/
```

A full URL therefore looks like `https://vox.example.com/api/v1/feeds`.

---

## Authentication

Attach one of the following headers to every authenticated request:

| Header | Format | Usage |
|---|---|---|
| `Authorization` | `Bearer {token}` | Regular user sessions |
| `Authorization` | `Bot {bot_token}` | Bot accounts |

Endpoints that do not require authentication (e.g. registration, login) are
marked explicitly.

---

## Content Types

| Scenario | Content-Type |
|---|---|
| Standard requests | `application/json` |
| File / avatar uploads | `multipart/form-data` |

Responses are always `application/json` unless the endpoint streams binary data.

---

## ID Spaces

| ID | Type | Notes |
|---|---|---|
| `user_id` | `uint64` | Unique per user |
| `feed_id` | `uint32` | Channel for text / forum / announcement content |
| `dm_id` | `uint32` | Direct-message channel |
| `room_id` | `uint32` | Voice or stage room |
| `role_id` | `uint32` | Role within the server |
| `msg_id` | `uint64` | Snowflake -- encodes creation timestamp |
| `category_id` | `uint32` | Grouping container for feeds and rooms |

Snowflake IDs are returned as JSON integers.  They embed a millisecond
timestamp, a worker identifier, and a sequence counter.

---

## Pagination

List endpoints use **cursor-based** pagination with the following query
parameters:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | `integer` | 50 | Number of items to return (max 100) |
| `after` | `string` | — | Return items after this cursor value |

Responses include a `cursor` field when more results are available:

```json
{
  "items": [ ... ],
  "cursor": "eyJpZCI6MTIzNH0"
}
```

Pass the returned `cursor` as the `after` parameter in the next request.  When
`cursor` is `null` or absent, you have reached the end of the list.

---

## Error Response Format

All errors follow a consistent envelope:

```json
{
  "error": {
    "code": "MISSING_PERMISSIONS",
    "message": "You do not have the MANAGE_SPACES permission.",
    "retry_after_ms": null
  }
}
```

| Field | Type | Description |
|---|---|---|
| `code` | `string` | Machine-readable error code |
| `message` | `string` | Human-readable explanation |
| `retry_after_ms` | `integer?` | Present only on rate-limit errors; milliseconds to wait |

### HTTP Status Codes

| Status | Meaning |
|---|---|
| `200 OK` | Success with response body |
| `201 Created` | Resource created |
| `204 No Content` | Success with no response body |
| `400 Bad Request` | Malformed or invalid request body |
| `401 Unauthorized` | Missing or invalid authentication |
| `403 Forbidden` | Valid auth but insufficient permissions |
| `404 Not Found` | Resource does not exist |
| `409 Conflict` | Resource already exists (e.g. duplicate username) |
| `413 Payload Too Large` | Upload exceeds size limit |
| `429 Too Many Requests` | Rate limited -- see `retry_after_ms` |
| `500 Internal Server Error` | Unexpected server failure |

### Error Codes

| Code | Typical Status | Description |
|---|---|---|
| `INVALID_BODY` | 400 | Request body failed validation |
| `MISSING_FIELD` | 400 | A required field is absent |
| `UNAUTHORIZED` | 401 | Token missing or expired |
| `MFA_REQUIRED` | 401 | Login needs a second factor |
| `MISSING_PERMISSIONS` | 403 | Caller lacks a required permission |
| `NOT_FOUND` | 404 | The requested resource does not exist |
| `USERNAME_TAKEN` | 409 | Registration conflict |
| `RATE_LIMITED` | 429 | Too many requests |

---

## Rate Limit Headers

Every response includes rate-limit information:

| Header | Description |
|---|---|
| `X-RateLimit-Limit` | Maximum requests allowed in the current window |
| `X-RateLimit-Remaining` | Requests remaining in the current window |
| `X-RateLimit-Reset` | Unix epoch seconds when the window resets |
| `Retry-After` | Seconds to wait (present only on 429 responses) |

When you receive a `429` response, wait for `retry_after_ms` milliseconds
(from the JSON body) or `Retry-After` seconds (from the header) before
retrying.
