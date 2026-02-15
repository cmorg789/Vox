# VoxProtocol v1: Federation

Federation allows servers to communicate with each other, enabling cross-server DMs, presence, and server joining.

## 1. User Identity

Users are identified by email-style addresses:

```
alice@voxchat.example.com
  |         |
  user      server domain
```

For local operations, the short `user_id` (uint32) is used. The full `user@domain` form is used only for federation.

## 2. DNS Records

```
; Service discovery (RFC 9460 SVCB)
_vox.example.com.           IN SVCB  1 vox.example.com. alpn="vox1" port=443

; Server public key
_voxkey.example.com.        IN TXT  "v=vox1; k=ed25519; p=<base64_public_key>"

; Federation policy
_voxpolicy.example.com.     IN TXT  "v=vox1; federation=open; abuse=admin@example.com"

; Allowlist entries (when federation=allowlist)
servera.com._voxallow.example.com.    IN A  127.0.0.2
```

| Record | Purpose | Email Equivalent |
|---|---|---|
| `_vox` SVCB | Service discovery (host, port, ALPN) | MX record |
| `_voxkey` TXT | Server signing key | DKIM |
| `_voxpolicy` TXT | Federation policy and abuse contact | DMARC |
| `<domain>._voxallow` A | Allowlist entries | N/A |

## 3. Federation Policy

| Policy | Behavior |
|---|---|
| `federation=open` | Accept federation from any server, subject to blocklists |
| `federation=allowlist` | Only federate with domains listed in `_voxallow` records |
| `federation=closed` | No federation |

## 4. Server-to-Server Transport

Federation uses HTTPS REST between servers. Each federation request is signed with the sending server's Ed25519 private key. The receiving server verifies the signature against the `_voxkey` DNS TXT record. This is internal infrastructure -- clients never interact with the federation layer directly.

Two layers of authentication:

**1. TLS:** Standard HTTPS with certificate verification.

**2. DNS key signature (like DKIM):** Each federation request includes an `X-Vox-Origin` header (sending domain) and an `X-Vox-Signature` header (Ed25519 signature over the request body). The receiving server verifies the signature against the `_voxkey` DNS TXT record for that domain.

```
Server A                                          Server B
  |                                                  |
  |  [lookup _vox.serverb.com SVCB]                   |
  |  [lookup _voxkey.serverb.com TXT]                |
  |                                                  |
  |-- POST https://serverb.com/api/v1/federation/    |
  |   relay/message                                  |
  |   Headers:                                       |
  |     X-Vox-Origin: servera.com                    |
  |     X-Vox-Signature: sign(body, privkey)         |
  |   Body: {from, to, opaque_blob}                  |
  |   ------------------------------------------------>|
  |                                                  |
  |   [Server B verifies signature against DNS key]  |
  |                                                  |
  |<-- 200 OK --------------------------------------|
```

> **Federation API endpoints:** See `API.md` (Federation section) for the complete server-to-server REST endpoint reference.

## 5. What Gets Federated

| Feature | Federated | How |
|---|---|---|
| DMs (1:1 and group) | Yes | E2EE blob relay, servers cannot read content |
| User profile lookup | Yes | Server-to-server lookup |
| Presence | Yes, for contacts | Server-to-server subscription |
| Typing indicators (DMs) | Yes | Server-to-server relay |
| Read receipts (DMs) | Yes | Server-to-server relay |
| Prekey exchange (E2EE) | Yes | Server-to-server prekey fetch |
| Server joining | Yes | Federation join, then direct connection |
| File transfer (DMs) | Yes | E2EE blob relay |
| Server feeds and rooms | No | Connect directly to the server |

## 6. Federated DM Flow

The client protocol is identical regardless of federation. The home server wraps and unwraps transparently:

```
Alice@ServerA              ServerA              ServerB              Bob@ServerB
  |                          |                     |                     |
  |-- POST /feeds/{dm}/     |                     |                     |
  |   messages {ciphertext}->|                     |                     |
  |                          |  [sign, POST to     |                     |
  |                          |   ServerB federation |                    |
  |                          |   relay endpoint]    |                    |
  |                          |-- POST /federation/ |                     |
  |                          |   relay/message --->|                     |
  |                          |   {from: alice@a,   |                     |
  |                          |    to: bob@b,       |                     |
  |                          |    opaque_blob}     |                     |
  |                          |                     |  [verify, dispatch] |
  |                          |                     |-- message_create -->|
  |                          |                     |   (gateway event)   |
```

## 7. Federated Server Joining

A user on Server A joins Server B's community:

```
Alice@ServerA              ServerA              ServerB
  |                          |                     |
  |-- "join serverb.com" -->|                     |
  |                          |-- POST /federation/ |
  |                          |   join {            |
  |                          |   user: alice@      |
  |                          |    servera.com,     |
  |                          |   voucher: signed   |
  |                          |    proof            |
  |                          |  } --------------->|
  |                          |                     |
  |                          |<-- 200 {            |
  |                          |   accepted: true,   |
  |                          |   federation_token, |
  |                          |   server_info       |
  |                          |  } ----------------|
  |                          |                     |
  |  [Alice connects directly to ServerB via HTTP/WS/media] |
  |                                                |
  |== REST: POST /auth/login {federation_token} ==>|
  |<== {token, user_id} ==========================|
  |== WebSocket: identify ========================>|
  |<== ready =====================================|
```

Alice authenticates with her home server, which vouches for her identity. She then connects directly to Server B using the standard HTTP/WS/media model. Her identity remains `alice@servera.com`.

### Voucher Format

The `voucher` is a base64-encoded signed JSON payload issued by the user's home server. The receiving server verifies the signature against the home server's `_voxkey` DNS TXT record.

```json
// Voucher payload (before base64 encoding)
{
  "user_address": "alice@servera.com",
  "target_domain": "serverb.com",
  "issued_at": 1700000000,
  "expires_at": 1700000300,
  "nonce": "random_unique_string"
}
```

The voucher is transmitted as:

```
base64(json_payload) + "." + base64(ed25519_signature)
```

| Field | Type | Description |
|---|---|---|
| `user_address` | string | Full `user@domain` of the joining user |
| `target_domain` | string | Domain of the server being joined. Receiving server MUST reject vouchers not addressed to its own domain. |
| `issued_at` | uint64 | Unix timestamp of issuance |
| `expires_at` | uint64 | Unix timestamp of expiry. Receiving server MUST reject expired vouchers. Recommended TTL: 5 minutes. |
| `nonce` | string | Unique per-voucher string to prevent replay attacks. Receiving server SHOULD track seen nonces within the expiry window. |

Verification steps:
1. Base64-decode the payload and signature
2. Verify the Ed25519 signature against the `_voxkey` DNS record for the user's home domain
3. Verify `target_domain` matches the receiving server's domain
4. Verify `expires_at` has not passed
5. Verify `nonce` has not been seen before

## 8. Security: Message Reconstruction

The receiving server MUST reconstruct local messages from validated federation data. Never blindly unwrap.

| Rule | Reason |
|---|---|
| Never trust sender-provided IDs | Server generates its own msg_id, timestamp, feed assignment |
| Verify domain matches connection | `from: alice@evil.com` must arrive on a verified `evil.com` connection |
| Tag all federated messages | Local code can distinguish federated vs local |
| Do not parse E2EE blobs | Server cannot and should not interpret encrypted content |
| Federated guests cannot access admin paths | No role management, no server settings |
| Rate limit per federation peer | Even verified servers get throttled |

## 9. Abuse Prevention

### DNS Verification

Server signatures verified against DNS public keys. No valid signature = no federation.

### Local Blocklist

Server admin maintains a blocklist of domains. Sends a courtesy block notification to the peer via `POST /api/v1/federation/block`.

### DNS Blocklists (opt-in)

```
Incoming federation from sketchyserver.net:
  DNS query: sketchyserver.net.voxblock.community.org  A?
  -> 127.0.0.2 = blocked
  -> NXDOMAIN = not listed, proceed
```

### Rate Limiting Per Peer

| Limit | Example | Description |
|---|---|---|
| Max DM relays/hour/peer | 100 | Caps message relay from a single domain |
| Max presence subs/peer | 500 | Caps presence subscriptions |
| Max join requests/hour/peer | 20 | Caps join requests |

### User-Level Controls

Existing DM permission settings apply to federated users. Users can block specific remote users (`alice@evil.com`).

## 10. Federation Error Codes

| Code | Description |
|---|---|
| `FED_OK` | Success |
| `FED_UNKNOWN_ERROR` | Unknown error |
| `FED_AUTH_FAILED` | Signature verification failed |
| `FED_DNS_KEY_MISMATCH` | DNS key does not match signature |
| `FED_POLICY_DENIED` | Remote server's policy denies federation |
| `FED_NOT_ON_ALLOWLIST` | Domain not on allowlist |
| `FED_BLOCKED` | Domain is on blocklist |
| `FED_RATE_LIMITED` | Rate limited (includes retry_after_ms) |
| `FED_USER_NOT_FOUND` | Remote user does not exist |
| `FED_INVITE_INVALID` | Invite code invalid or expired |
| `FED_INVITE_EXPIRED` | Invite code expired |
| `FED_SERVER_FULL` | Remote server at capacity |
