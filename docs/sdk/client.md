# HTTP Client Reference

## Client

```python
from vox_sdk import Client

client = Client(base_url, token=None, timeout=30.0)
```

| Parameter  | Type            | Default | Description                          |
|------------|-----------------|---------|--------------------------------------|
| `base_url` | `str`           | --      | Base URL of the Vox server.          |
| `token`    | `str` or `None` | `None`  | Optional pre-existing auth token.    |
| `timeout`  | `float`         | `30.0`  | Request timeout in seconds.          |

### Async context manager

`Client` implements the async context manager protocol. Use `async with` to ensure the underlying HTTP session is properly closed.

```python
async with Client("https://vox.example.com") as client:
    await client.login("alice", "password123")
    # ...
```

### Authentication

#### `login(username, password)`

Convenience method that calls the auth API to obtain a token and stores it on the client for subsequent requests.

```python
await client.login("alice", "password123")
```

After login, all API calls automatically include the `Authorization: Bearer <token>` header.

If you already have a token (for example, from a bot account), pass it directly to the constructor:

```python
client = Client("https://vox.example.com", token="bot-token-here")
```

## API groups

All API groups are available as lazy-loaded properties on the `Client` instance. Each group is instantiated on first access and cached for the lifetime of the client.

| Property       | Description                                      |
|----------------|--------------------------------------------------|
| `auth`         | Authentication, registration, sessions, 2FA.     |
| `messages`     | Send, edit, delete, pin, and search messages.     |
| `channels`     | Create, update, delete, and list feeds/channels.  |
| `members`      | List, update, kick, and ban members.              |
| `roles`        | Create, update, delete, and reorder roles.        |
| `server`       | Server info, settings, gateway info.              |
| `users`        | User profiles, relationships, presence.           |
| `invites`      | Create, list, and revoke invites.                 |
| `voice`        | Join, leave, and manage voice channels.           |
| `dms`          | Direct message conversations.                     |
| `webhooks`     | Create and manage webhooks.                       |
| `bots`         | Register, update, and manage bot accounts.        |
| `e2ee`         | End-to-end encryption key management.             |
| `moderation`   | Reports, audit log, moderation actions.           |
| `files`        | Upload and manage file attachments.               |
| `federation`   | Federation peer management and status.            |
| `search`       | Full-text message and user search.                |
| `emoji`        | Custom emoji management.                          |
| `sync`         | Client state synchronization.                     |
| `embeds`       | Link embed and preview management.                |

## HTTPClient internals

The `Client` wraps an internal `HTTPClient` that handles the low-level HTTP communication.

### Transport

- Built on **httpx.AsyncClient** for fully async HTTP/1.1 and HTTP/2 support.
- Automatic `Authorization: Bearer <token>` header injection on all authenticated requests.

### Rate limit handling

The client tracks rate limit state from response headers and automatically avoids hitting limits.

- **`wait_if_needed()`** -- Called before each request. If the current endpoint's rate limit bucket is exhausted, the client sleeps until the reset time before proceeding.
- **Auto-retry on 429** -- When a `429 Too Many Requests` response is received, the client reads the `retry_after_ms` value from the error body and waits that duration before retrying the request.

### Server error retry

Transient server errors are retried automatically with exponential backoff:

- **Retried status codes**: 500, 502, 503, 504.
- **Maximum retries**: 3.
- **Backoff**: Exponential with base delay, doubling on each attempt.

## Response models

All API responses are deserialized into Pydantic v2 models defined in `vox_sdk.models`. Common models include:

| Model              | Description                        |
|--------------------|------------------------------------|
| `MessageResponse`  | A message with author, content, timestamps. |
| `UserResponse`     | User profile (ID, display name, avatar, etc.). |
| `FeedResponse`     | A channel/feed with metadata.      |
| `MemberResponse`   | A server member with roles and join date. |
| `RoleResponse`     | A role with permissions and color.  |
| `InviteResponse`   | An invite link with expiry info.   |
| `ServerResponse`   | Server metadata and settings.      |
| `FileResponse`     | An uploaded file with URL and metadata. |
| `WebhookResponse`  | A webhook configuration.           |
| `EmojiResponse`    | A custom emoji entry.              |

All models support standard Pydantic operations: `.model_dump()`, `.model_dump_json()`, attribute access, and type validation.
