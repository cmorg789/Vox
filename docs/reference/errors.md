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
| `SPACE_TYPE_MISMATCH`        | Operation is not valid for this space type.              |
| `GATEWAY_VERSION_MISMATCH`   | Gateway protocol version is not supported.               |

### 401 Unauthorized

| Code                  | Description                                            |
|-----------------------|--------------------------------------------------------|
| `AUTH_FAILED`         | Invalid username or password.                          |
| `AUTH_EXPIRED`        | Authentication token has expired.                      |
| `2FA_REQUIRED`        | Two-factor authentication is required to proceed.      |
| `2FA_INVALID_CODE`    | The provided 2FA code is incorrect.                    |
| `WEBAUTHN_INVALID`    | WebAuthn assertion verification failed.                |

### 403 Forbidden

| Code                   | Description                                           |
|------------------------|-------------------------------------------------------|
| `FORBIDDEN`            | Insufficient permissions. Check `missing_permission`. |
| `BANNED`               | The user is banned from this space.                   |
| `ROLE_HIERARCHY`       | Cannot modify a role equal to or above your own.      |
| `DM_PERMISSION_DENIED` | The recipient does not allow DMs from you.            |
| `USER_BLOCKED`         | The target user has blocked you.                      |
| `FEDERATION_DENIED`    | Federation is not permitted with this peer.           |

### 404 Not Found

| Code                          | Description                              |
|-------------------------------|------------------------------------------|
| `USER_NOT_FOUND`              | No user exists with this ID.             |
| `SPACE_NOT_FOUND`             | No space exists with this ID.            |
| `MESSAGE_NOT_FOUND`           | No message exists with this ID.          |
| `REPORT_NOT_FOUND`            | No report exists with this ID.           |
| `CMD_NOT_FOUND`               | No command registered with this name.    |
| `WEBHOOK_NOT_FOUND`           | No webhook exists with this ID.          |
| `KEY_BACKUP_NOT_FOUND`        | No E2EE key backup found.               |
| `WEBAUTHN_CREDENTIAL_NOT_FOUND` | No WebAuthn credential with this ID.  |

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
| `INTERACTION_EXPIRED`| This interaction token has expired.                  |
| `2FA_SETUP_EXPIRED`  | The 2FA setup session has expired. Start over.       |
| `DEVICE_PAIR_EXPIRED`| The device pairing session has expired.              |
| `CPACE_EXPIRED`      | The CPace key agreement session has expired.         |

### 413 Content Too Large

| Code            | Description                                |
|-----------------|--------------------------------------------|
| `FILE_TOO_LARGE`| Uploaded file exceeds the maximum size.    |

### 422 Unprocessable Entity

| Code                     | Description                                      |
|--------------------------|--------------------------------------------------|
| `INVITE_INVALID`         | The invite code is malformed or invalid.         |
| `WEBHOOK_TOKEN_INVALID`  | The webhook token does not match.                |
| `2FA_NOT_ENABLED`        | Cannot perform this action without 2FA enabled.  |
| `2FA_RECOVERY_EXHAUSTED` | All recovery codes have been used.               |
| `CPACE_FAILED`           | CPace key agreement verification failed.         |

### 429 Too Many Requests

| Code           | Description                                                     |
|----------------|-----------------------------------------------------------------|
| `RATE_LIMITED`  | Rate limit exceeded. Retry after `retry_after_ms` milliseconds.|

### 500 Internal Server Error

| Code           | Description                        |
|----------------|------------------------------------|
| `UNKNOWN_ERROR`| An unexpected server error occurred.|

### 502 Bad Gateway

| Code                     | Description                                      |
|--------------------------|--------------------------------------------------|
| `FEDERATION_UNAVAILABLE` | The federated peer server is unreachable.        |

### 503 Service Unavailable

| Code                 | Description                                          |
|----------------------|------------------------------------------------------|
| `SERVER_FULL`        | The server has reached its maximum capacity.         |
| `ROOM_FULL`          | The voice room has reached its maximum capacity.     |
| `PREKEY_EXHAUSTED`   | No pre-keys available for this device (E2EE).        |
| `DEVICE_LIMIT_REACHED`| Maximum number of devices reached for this account. |

## Federation error codes

Federation responses between peers use a separate set of status codes:

| Code              | Description                                    |
|-------------------|------------------------------------------------|
| `FED_OK`          | Request succeeded.                             |
| `FED_DENIED`      | Federation denied by peer policy.              |
| `FED_INVALID`     | Invalid federation request format.             |
| `FED_NONCE_REUSE` | Nonce has already been used (replay detected). |
| `FED_EXPIRED`     | Federation request timestamp is too old.       |
| `FED_UNKNOWN`     | Unknown federation error.                      |
| `FED_SERVER_FULL` | The federated peer server is at capacity.      |
