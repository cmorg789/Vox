# Rate Limits

Vox uses per-endpoint rate limiting to protect the server from excessive request volume. The SDK handles rate limits automatically, but understanding the mechanism is useful for debugging and advanced usage.

## Response headers

Every API response includes rate limit headers:

| Header                  | Description                                                |
|-------------------------|------------------------------------------------------------|
| `X-RateLimit-Limit`     | Maximum number of requests allowed in the current window.  |
| `X-RateLimit-Remaining` | Number of requests remaining in the current window.        |
| `X-RateLimit-Reset`     | Unix timestamp (seconds) when the current window resets.   |
| `Retry-After`           | Seconds to wait before retrying (present on 429 responses).|

## 429 responses

When a rate limit is exceeded, the server responds with HTTP 429 and the `RATE_LIMITED` error code:

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "You are being rate limited.",
    "retry_after_ms": 2500
  }
}
```

The `retry_after_ms` field indicates the exact number of milliseconds to wait before the next request will be accepted.

## Rate limit categories

Rate limits are enforced per-endpoint category. Different API operations may have different limits based on server policy. Common categories include:

- **Message send** -- Limits on sending messages per feed per time window.
- **Auth attempts** -- Strict limits on login and registration to prevent brute force.
- **File uploads** -- Limits on upload frequency and size.
- **Gateway events** -- Limits on client-to-server gateway messages (typing, presence).
- **Search** -- Limits on search query frequency.
- **General API** -- Default limits applied to all other endpoints.

Exact limits are configured by the server operator and are not fixed by the protocol.

## Federation rate limits

Federation traffic is rate-limited on a per-peer basis. Each federated peer has its own rate limit bucket, preventing a single peer from consuming disproportionate resources.

## Client best practices

### Respect Retry-After

Always wait the full duration indicated by `Retry-After` or `retry_after_ms` before retrying. The SDK does this automatically.

### Track remaining requests

Monitor `X-RateLimit-Remaining` from response headers to anticipate limits before hitting them. The SDK's `HTTPClient` tracks this internally via `wait_if_needed()`.

### Use exponential backoff

For transient errors (500, 502, 503, 504), use exponential backoff rather than immediate retry. The SDK implements this automatically with a maximum of 3 retries.

### Avoid tight loops

Do not poll endpoints in tight loops. Use the [gateway](../sdk/gateway-client.md) for real-time updates instead of repeatedly querying the REST API.

### Batch where possible

Some API endpoints accept batch operations (for example, bulk delete messages). Prefer these over individual requests to reduce total request count.
