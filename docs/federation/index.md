# Federation Overview

Vox federation allows users on different servers to communicate with each other.
Users can send DMs across server boundaries, look up remote profiles, exchange
presence, and join remote servers -- all while preserving end-to-end encryption
and server sovereignty.

## User Identity

Federated users are identified by a `user@domain` format (e.g.,
`alice@vox.example.com`). Within a single server, the local `uint32` user ID is
used for all operations. The `user@domain` address is only used when
communicating across server boundaries.

---

## DNS Records

Federation relies on DNS for service discovery, key distribution, and policy
advertisement.

### Service Discovery

```
_vox    SVCB    1 vox.example.com alpn="h2"
```

A `_vox` SVCB record points to the server that handles federation traffic for
the domain.

### Public Key

```
_voxkey    TXT    "ed25519:BASE64_PUBLIC_KEY"
```

A `_voxkey` TXT record publishes the server's Ed25519 public key. Remote servers
use this key to verify signatures on incoming federation requests.

### Policy

```
_voxpolicy    TXT    "federation=open abuse-contact=abuse@example.com"
```

A `_voxpolicy` TXT record advertises the server's federation policy and abuse
contact.

| Field           | Values                            | Description                        |
|-----------------|-----------------------------------|------------------------------------|
| `federation`    | `open`, `allowlist`, `closed`     | Who can federate with this server. |
| `abuse-contact` | email address                     | Contact for abuse reports.         |

### Allowlist

When `federation=allowlist`, the server publishes A records under `_voxallow`
for each allowed domain:

```
remotedomain.com._voxallow    A    0.0.0.0
```

The A record value is unused; the presence of the record is what matters.

---

## Transport

All server-to-server federation traffic uses **HTTPS REST**. Every request is
authenticated with Ed25519 signatures.

### Request Signing

Each outbound federation request includes two headers:

| Header             | Description                                              |
|--------------------|----------------------------------------------------------|
| `X-Vox-Origin`     | The sending server's domain.                             |
| `X-Vox-Signature`  | Ed25519 signature of the request body, base64-encoded.   |

The receiving server:

1. Reads the `X-Vox-Origin` header.
2. Looks up the `_voxkey` TXT record for that domain.
3. Verifies the `X-Vox-Signature` against the request body using the public key.
4. Rejects the request if verification fails.

---

## What Gets Federated

### Federated

- **DMs** -- End-to-end encrypted blob relay between users on different servers.
- **User profile lookup** -- Display name, avatar, and bio of remote users.
- **Presence** -- Subscription-based online status sharing.
- **Typing and read receipts** -- For DM conversations.
- **Prekey exchange** -- E2EE key material for establishing encrypted sessions.
- **Server joining** -- Remote users can join a server via the voucher system.
- **File transfer in DMs** -- Encrypted file attachments in DM conversations.

### Not Federated

- **Server feeds and rooms** -- Users must connect directly to the server that
  hosts the feeds and rooms. Federation does not proxy or replicate server-local
  content.

---

## Federated DM Flow

```
Client A          Home Server A          Home Server B          Client B
   |                    |                      |                    |
   |-- send message --->|                      |                    |
   |                    |-- sign & relay ------>|                    |
   |                    |                      |-- verify & dispatch |
   |                    |                      |--- gateway event -->|
```

1. Client A sends an E2EE-encrypted DM to their home server.
2. Home Server A signs the request and relays it to Home Server B.
3. Home Server B verifies the signature against Server A's DNS public key.
4. Home Server B dispatches the message to Client B via the gateway.

---

## Federated Server Joining

Remote users join a server using a **voucher system**. A voucher is a signed
JSON object:

```json
{
  "user_address": "alice@remote.example.com",
  "target_domain": "vox.example.com",
  "issued_at": "2026-02-19T12:00:00Z",
  "expires_at": "2026-02-19T13:00:00Z",
  "nonce": "random-unique-nonce"
}
```

### Verification Steps

1. **Signature check** -- Verify the voucher was signed by the user's home
   server using its `_voxkey` public key.
2. **Target domain** -- Confirm `target_domain` matches the receiving server.
3. **Expiry** -- Reject expired vouchers.
4. **Nonce replay** -- Reject vouchers with previously seen nonces to prevent
   replay attacks.

---

## Security Considerations

- **Reconstruct messages locally** -- Never trust sender-provided user IDs or
  display names. Always resolve them from the verified `X-Vox-Origin` domain.
- **Verify domain matches** -- Ensure the `user@domain` in the payload matches
  the `X-Vox-Origin` header.
- **Tag federated messages** -- Mark content from remote servers so clients can
  distinguish local and federated content.
- **No admin paths for federated guests** -- Remote users joining via federation
  must never gain administrative privileges.
- **Rate limit per peer** -- Apply per-peer rate limits to all federation
  endpoints to prevent abuse from a single remote server.

---

## Abuse Prevention

- **DNS verification** -- All federation requests require a valid DNS-published
  key. Servers without proper DNS records cannot federate.
- **Local blocklist** -- Servers can block specific domains. A courtesy
  notification is sent to the blocked server.
- **DNS blocklists** -- Opt-in shared blocklists published via DNS, similar to
  email DNSBLs.
- **Per-peer rate limits** -- Each remote server is independently rate-limited.
- **User-level DM controls** -- Users can restrict who can send them federated
  DMs (e.g., friends only, same server only, anyone).

---

## Error Codes

| Code               | Description                                          |
|--------------------|------------------------------------------------------|
| `FED_OK`           | Request was processed successfully.                  |
| `FED_INVALID_SIG`  | Signature verification failed.                       |
| `FED_UNKNOWN_USER` | The target user does not exist on this server.       |
| `FED_BLOCKED`      | The sending domain is blocked.                       |
| `FED_RATE_LIMITED`  | The sending server has exceeded its rate limit.      |
| `FED_POLICY_DENY`  | Federation policy does not permit this interaction.  |
| `FED_EXPIRED`      | The voucher or token has expired.                    |
| `FED_REPLAY`       | The nonce has already been used (replay detected).   |
| `FED_NOT_FOUND`    | The requested resource was not found.                |
| `FED_SERVER_FULL`  | The server is not accepting new members.             |
