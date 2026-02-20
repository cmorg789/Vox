# Two-Factor Authentication

Vox supports two-factor authentication (2FA) as a second layer of protection on user
accounts. 2FA is only required during **password-based logins**. Token-based session
resumption and bot tokens skip 2FA.

## Methods

### TOTP (Time-Based One-Time Password)

Standard TOTP as defined in RFC 6238:

| Parameter | Value |
|-----------|-------|
| Algorithm | SHA-1 |
| Digits | 6 |
| Period | 30 seconds |
| Window | +/- 1 period (accepts codes from the previous, current, or next period) |
| Replay prevention | Each TOTP counter value can only be used once (`last_used_counter` tracked in DB) |

Users register TOTP by scanning a QR code or manually entering the shared secret into
their authenticator app.

TOTP codes are protected against replay attacks. The server tracks the counter value
of the last successfully used code. Any code with a counter less than or equal to the
previously used counter is rejected, even if it falls within the valid time window.

### WebAuthn (FIDO2 / U2F)

WebAuthn supports hardware security keys (e.g., YubiKey) and platform biometrics
(e.g., Touch ID, Windows Hello).

- Registration creates a credential bound to the Vox origin.
- Authentication uses the challenge-response flow defined by the WebAuthn specification.
- Challenges are stored in the database (`WebAuthnChallenge` model) with a short TTL.

### Recovery Codes

Recovery codes are a fallback for when the user has lost access to their TOTP app and
WebAuthn devices.

| Property | Value |
|----------|-------|
| Count | 8 codes |
| Format | `XXXX-XXXX` (alphanumeric) |
| Usage | Single-use; each code is invalidated after one successful authentication |
| Storage | Hashed with Argon2 (server never stores plaintext) |

Users should store recovery codes in a safe offline location. Once all codes are used,
the user must generate a new set.

## Login Flow with 2FA

```
Client                              Server
  |                                    |
  |-- POST /auth/login (credentials) ->|
  |<- 401 {mfa_required, mfa_ticket} --|
  |                                    |
  |-- POST /auth/mfa (ticket + code) ->|
  |<- 200 {session_token} -------------|
```

1. The client submits username and password to `POST /auth/login`.
2. If the password is correct and the account has 2FA enabled, the server returns
   HTTP 401 with `mfa_required: true` and an `mfa_ticket`.
3. The client prompts the user for their 2FA code (TOTP, WebAuthn, or recovery code)
   and submits it to `POST /auth/mfa` along with the `mfa_ticket`.
4. If the code is valid, the server returns a full session token.

The `mfa_ticket` is short-lived and single-use. It binds the 2FA step to the specific
password authentication that preceded it.

## Brute-Force Protection

Failed 2FA attempts are tracked per session in the database (`mfa_fail_count` on the
session record). After exceeding the maximum number of attempts, the server returns
`2FA_MAX_ATTEMPTS` and the session is locked. This counter persists across server
restarts and multiple workers, unlike an in-memory approach.

## When 2FA Applies

| Authentication Method | 2FA Required |
|----------------------|--------------|
| Password login | Yes |
| Session token resumption | No |
| Bot token | No |

2FA is intentionally not required for session token resumption because the session token
itself represents a previously authenticated session. Requiring 2FA on every API call
would be impractical.

## Admin 2FA Reset

Administrators with the `MANAGE_2FA` permission can reset another user's 2FA in cases
where the user has lost access to all second factors:

```
POST /admin/2fa-reset
```

```json
{
  "user_id": "target user ID"
}
```

This action:

- Disables all 2FA methods on the target account.
- Invalidates all existing recovery codes.
- Generates an **audit log entry** recording the administrator who performed the reset,
  the target user, and a timestamp.

The user can then log in with only their password and re-enroll in 2FA.
