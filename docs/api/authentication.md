# Authentication

All endpoints in this section live under `/api/v1/auth/`.

---

## POST /auth/register

Create a new user account. No authentication required.

**Request**

```json
{
  "username": "alice",
  "password": "hunter2!Strong",
  "display_name": "Alice"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `username` | `string` | yes | Unique username (3-32 chars, alphanumeric + underscores) |
| `password` | `string` | yes | Password (minimum 8 characters) |
| `display_name` | `string` | no | Display name shown to other users |

**Response `201 Created`**

```json
{
  "user_id": 10001,
  "token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 400 | `INVALID_BODY` | Validation failure (e.g. password too short) |
| 409 | `USERNAME_TAKEN` | Username already registered |

---

## POST /auth/login

Log in with username and password. No authentication required.

**Request**

```json
{
  "username": "alice",
  "password": "hunter2!Strong"
}
```

**Response `200 OK` -- no MFA**

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user_id": 10001,
  "display_name": "Alice",
  "roles": ["admin"]
}
```

**Response `200 OK` -- MFA required**

```json
{
  "mfa_required": true,
  "mfa_ticket": "tkt_abc123",
  "available_methods": ["totp", "webauthn", "recovery"]
}
```

When `mfa_required` is `true`, the client must complete a second-factor
challenge via [POST /auth/login/2fa](#post-authlogin2fa) before receiving a
session token.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 401 | `UNAUTHORIZED` | Invalid username or password |

---

## POST /auth/login/2fa

Complete a multi-factor authentication challenge. No authentication required;
the `mfa_ticket` from the login response is used instead.

**Request -- TOTP**

```json
{
  "mfa_ticket": "tkt_abc123",
  "method": "totp",
  "code": "482901"
}
```

**Request -- Recovery code**

```json
{
  "mfa_ticket": "tkt_abc123",
  "method": "recovery",
  "code": "ABCD-1234-EFGH"
}
```

**Request -- WebAuthn**

```json
{
  "mfa_ticket": "tkt_abc123",
  "method": "webauthn",
  "assertion": {
    "client_data_json": "base64...",
    "authenticator_data": "base64...",
    "signature": "base64...",
    "credential_id": "base64..."
  }
}
```

**Response `200 OK`**

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user_id": 10001,
  "display_name": "Alice",
  "roles": ["admin"]
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 400 | `INVALID_BODY` | Missing or malformed fields |
| 401 | `UNAUTHORIZED` | Invalid ticket, code, or assertion |

---

## POST /auth/login/webauthn/challenge

Request a WebAuthn authentication challenge. No authentication required.

**Request**

```json
{
  "username": "alice"
}
```

**Response `200 OK`**

```json
{
  "challenge_id": "chall_abc123",
  "challenge": "base64-encoded-challenge",
  "credential_ids": [
    "base64-credential-id-1",
    "base64-credential-id-2"
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `challenge_id` | `string` | Unique ID for this challenge. Must be passed to the login endpoint. |
| `challenge` | `string` | Base64-encoded WebAuthn challenge. |
| `credential_ids` | `string[]` | Base64-encoded credential IDs registered for this user. |

**Errors**

| Status | Code | Condition |
|---|---|---|
| 400 | `WEBAUTHN_NOT_CONFIGURED` | WebAuthn is not configured on this server |

---

## POST /auth/login/webauthn

Authenticate directly with a WebAuthn assertion (passwordless flow). No
authentication required. The `challenge_id` must be obtained from a prior call
to [POST /auth/login/webauthn/challenge](#post-authloginwebauthnchallenges).

**Request**

```json
{
  "username": "alice",
  "challenge_id": "chall_abc123",
  "client_data_json": "base64...",
  "authenticator_data": "base64...",
  "signature": "base64...",
  "credential_id": "base64..."
}
```

**Response `200 OK`**

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user_id": 10001,
  "display_name": "Alice",
  "roles": ["admin"]
}
```

**Errors**

| Status | Code | Condition |
|---|---|---|
| 400 | `WEBAUTHN_NOT_CONFIGURED` | WebAuthn is not configured on this server |
| 401 | `UNAUTHORIZED` | Assertion verification failed |

---

## POST /auth/logout

Invalidate the current session token. Requires authentication.

**Response `204 No Content`**

No body.

---

## GET /auth/2fa

Retrieve the caller's current two-factor authentication status. Requires
authentication.

**Response `200 OK`**

```json
{
  "totp_enabled": true,
  "webauthn_enabled": false,
  "recovery_codes_left": 8
}
```

---

## POST /auth/2fa/setup

Begin setting up a new two-factor method. Requires authentication.

**Request -- TOTP**

```json
{
  "method": "totp"
}
```

**Response `200 OK` -- TOTP**

```json
{
  "setup_id": "setup_xyz789",
  "totp_secret": "JBSWY3DPEHPK3PXP"
}
```

The client should display the `totp_secret` as a QR code for the user's
authenticator app.

**Request -- WebAuthn**

```json
{
  "method": "webauthn"
}
```

**Response `200 OK` -- WebAuthn**

```json
{
  "setup_id": "setup_xyz789",
  "creation_options": {
    "rp": { "name": "Vox", "id": "vox.example.com" },
    "user": { "id": "base64...", "name": "alice", "displayName": "Alice" },
    "challenge": "base64...",
    "pubKeyCredParams": [
      { "type": "public-key", "alg": -7 }
    ],
    "timeout": 60000,
    "attestation": "none"
  }
}
```

---

## POST /auth/2fa/setup/confirm

Confirm a pending two-factor setup with a verification code or attestation.
Requires authentication.

**Request -- TOTP**

```json
{
  "setup_id": "setup_xyz789",
  "code": "482901"
}
```

**Request -- WebAuthn**

```json
{
  "setup_id": "setup_xyz789",
  "attestation": {
    "client_data_json": "base64...",
    "attestation_object": "base64..."
  }
}
```

**Response `200 OK`**

```json
{
  "success": true,
  "recovery_codes": [
    "ABCD-1234-EFGH",
    "IJKL-5678-MNOP",
    "QRST-9012-UVWX",
    "YZAB-3456-CDEF",
    "GHIJ-7890-KLMN",
    "OPQR-1234-STUV",
    "WXYZ-5678-ABCD",
    "EFGH-9012-IJKL"
  ]
}
```

Recovery codes are shown **only once**. The client must prompt the user to save
them.

---

## DELETE /auth/2fa

Disable a two-factor method. Requires authentication and a valid verification
code for the method being removed.

**Request**

```json
{
  "method": "totp",
  "code": "482901"
}
```

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 401 | `UNAUTHORIZED` | Verification code is invalid |

---

## GET /auth/webauthn/credentials

List the caller's registered WebAuthn credentials. Requires authentication.

**Response `200 OK`**

```json
{
  "credentials": [
    {
      "credential_id": "base64...",
      "name": "YubiKey 5",
      "created_at": "2025-06-15T10:30:00Z",
      "last_used_at": "2025-12-01T08:15:00Z"
    }
  ]
}
```

---

## DELETE /auth/webauthn/credentials/{credential_id}

Remove a registered WebAuthn credential. Requires authentication.

**Response `204 No Content`**

No body.

**Errors**

| Status | Code | Condition |
|---|---|---|
| 404 | `NOT_FOUND` | Credential does not exist or does not belong to the caller |
