# Error Codes

All API errors follow a consistent JSON response format. This page lists every error code, its HTTP status, and when it occurs.

## Response format

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "You do not have permission to perform this action.",
    "retry_after_ms": null,
    "missing_permission": "manage_messages"
  }
}
```

| Field                | Type            | Description                                         |
|----------------------|-----------------|-----------------------------------------------------|
| `code`               | `string`        | Machine-readable error code.                        |
| `message`            | `string`        | Human-readable description.                         |
| `retry_after_ms`     | `int` or `null` | Milliseconds to wait before retrying (rate limits). |
| `missing_permission` | `string` or `null` | The permission required (for FORBIDDEN errors).  |

## Error codes by HTTP status

### 400 Bad Request

| Code                         | Description                                              |
|------------------------------|----------------------------------------------------------|
| `PROTOCOL_VERSION_MISMATCH`  | Client protocol version is not supported by the server.  |
| `MESSAGE_TOO_LARGE`          | Message body exceeds the maximum allowed size.           |
| `EMPTY_MESSAGE`              | Message must have a body or attachments.                 |
| `WEBAUTHN_NOT_CONFIGURED`    | WebAuthn is not configured on this server.               |
| `PIN_LIMIT_REACHED`          | Maximum number of pinned messages reached for this feed. |
| `NO_CERT_PINNING`            | TLS certificate pinning is not configured.               |

### 401 Unauthorized

| Code                  | Description                                            |
|-----------------------|--------------------------------------------------------|
| `AUTH_FAILED`         | Invalid username or password.                          |
| `AUTH_EXPIRED`        | Authentication token has expired.                      |
| `2FA_REQUIRED`        | Two-factor authentication is required to proceed.      |
| `2FA_INVALID_CODE`    | The provided 2FA code is incorrect.                    |
| `2FA_MAX_ATTEMPTS`    | Too many failed 2FA attempts. Session locked.          |
| `WEBAUTHN_FAILED`     | WebAuthn assertion verification failed.                |
| `WEBHOOK_TOKEN_INVALID`  | The webhook token does not match.                   |

### 403 Forbidden

| Code                   | Description                                           |
|------------------------|-------------------------------------------------------|
| `FORBIDDEN`            | Insufficient permissions. Check `missing_permission`. |
| `MISSING_PERMISSIONS`  | Missing a specific permission.                        |
| `BANNED`               | The user is banned from this space.                   |
| `ROLE_HIERARCHY`       | Cannot modify a role equal to or above your own.      |
| `DM_PERMISSION_DENIED` | The recipient does not allow DMs from you.            |
| `USER_BLOCKED`         | The target user has blocked you.                      |
| `FED_BLOCKED`          | Federation is blocked for this peer.                  |
| `FED_POLICY_DENIED`    | Federation denied by the local server's policy.       |

### 404 Not Found

| Code                          | Description                              |
|-------------------------------|------------------------------------------|
| `NOT_FOUND`                   | Generic resource not found.              |
| `USER_NOT_FOUND`              | No user exists with this ID.             |
| `SPACE_NOT_FOUND`             | No space exists with this ID.            |
| `MESSAGE_NOT_FOUND`           | No message exists with this ID.          |
| `REPORT_NOT_FOUND`            | No report exists with this ID.           |
| `INVITE_NOT_FOUND`            | No invite exists with this code.         |
| `CMD_NOT_FOUND`               | No command registered with this name.    |
| `WEBHOOK_NOT_FOUND`           | No webhook exists with this ID.          |
| `KEY_BACKUP_NOT_FOUND`        | No E2EE key backup found.               |
| `WEBAUTHN_CREDENTIAL_NOT_FOUND` | No WebAuthn credential with this ID.  |
| `INTERACTION_NOT_FOUND`       | No interaction exists with this ID.      |
| `SESSION_NOT_FOUND`           | No session exists with this ID.          |

### 409 Conflict

| Code                    | Description                                        |
|-------------------------|----------------------------------------------------|
| `ALREADY_IN_VOICE`      | User is already connected to a voice channel.      |
| `CMD_ALREADY_REGISTERED`| A command with this name is already registered.    |
| `2FA_ALREADY_ENABLED`   | Two-factor authentication is already enabled.      |

### 410 Gone

| Code                 | Description                                          |
|----------------------|------------------------------------------------------|
| `INVITE_EXPIRED`     | This invite has expired or been revoked.             |
| `2FA_SETUP_EXPIRED`  | The 2FA setup session has expired. Start over.       |

### 413 Content Too Large

| Code            | Description                                |
|-----------------|--------------------------------------------|
| `FILE_TOO_LARGE`| Uploaded file exceeds the maximum size.    |

### 422 Unprocessable Entity

| Code                     | Description                                      |
|--------------------------|--------------------------------------------------|
| `INVITE_INVALID`         | The invite code is malformed or invalid.         |
| `2FA_NOT_ENABLED`        | The specified 2FA method is not enabled.         |
| `2FA_RECOVERY_EXHAUSTED` | All recovery codes have been used.               |
| `VALIDATION_ERROR`       | Request body validation failed.                  |

### 429 Too Many Requests

| Code                | Description                                                     |
|---------------------|-----------------------------------------------------------------|
| `RATE_LIMITED`       | Rate limit exceeded. Retry after `retry_after_ms` milliseconds.|
| `AUTH_RATE_LIMITED`  | Too many authentication failures from this IP.                 |

### 500 Internal Server Error

| Code           | Description                        |
|----------------|------------------------------------|
| `UNKNOWN_ERROR`| An unexpected server error occurred.|

### 502 Bad Gateway

| Code                     | Description                                      |
|--------------------------|--------------------------------------------------|
| `FED_UNAVAILABLE`        | The federated peer server is unreachable.        |

### 503 Service Unavailable

| Code                 | Description                                          |
|----------------------|------------------------------------------------------|
| `SERVER_FULL`        | The server has reached its maximum capacity.         |
| `ROOM_FULL`          | The voice room has reached its maximum capacity.     |
| `PREKEY_EXHAUSTED`   | No pre-keys available for this device (E2EE).        |
| `DEVICE_LIMIT_REACHED`| Maximum number of devices reached for this account. |

## Gateway error codes

The following error codes are delivered as WebSocket close codes, not HTTP responses:

| Code | Name | Description |
|------|------|-------------|
| 4011 | `VERSION_MISMATCH` | Gateway protocol version is not supported. |
| 4012 | `SERVER_FULL` | Server has reached maximum gateway connections. |

See [GATEWAY.md](../GATEWAY.md) for the full close codes table.

## Gateway in-band error codes

The gateway may send `{"type": "error", "d": {...}}` messages for non-fatal errors:

| Code | Description |
|------|-------------|
| `MISSING_ROOM_ID` | `room_id` is required for voice_codec_neg or stage_response. |
| `PAYLOAD_TOO_LARGE` | Relay payload exceeds size limit. |
| `INVALID_STATUS` | Invalid presence status value. |
| `MISSING_PERMISSIONS` | User lacks required permission for voice state change. |

## Federation error codes

Federation responses between peers use a separate set of status codes:

| Code              | Description                                    |
|-------------------|------------------------------------------------|
| `FED_OK`          | Request succeeded.                             |
| `FED_BLOCKED`     | Federation blocked by peer.                    |
| `FED_POLICY_DENIED` | Federation denied by the local server's policy. |
| `FED_INVALID`     | Invalid federation request format.             |
| `FED_NONCE_REUSE` | Nonce has already been used (replay detected). |
| `FED_EXPIRED`           | Federation request timestamp is too old.             |
| `FED_MISSING_TIMESTAMP` | Required `X-Vox-Timestamp` header is missing.        |
| `FED_TIMESTAMP_EXPIRED` | `X-Vox-Timestamp` value is older than 300 seconds.   |
| `FED_AUTH_FAILED`       | Federation authentication failed.                    |
| `FED_USER_NOT_FOUND`    | Federated user not found on remote server.           |
| `FED_NOT_CONFIGURED`    | Federation is not configured on this server.         |
| `FED_UNAVAILABLE`       | The federated peer server is unreachable.            |
| `FED_UNKNOWN`           | Unknown federation error.                            |
| `FED_SERVER_FULL`       | The federated peer server is at capacity.            |
