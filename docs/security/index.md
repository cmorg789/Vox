# Security

Vox takes a layered approach to security, combining end-to-end encryption for private
conversations with server-mediated access control for community spaces.

## Security Model

**Direct Messages** are end-to-end encrypted using the Messaging Layer Security (MLS)
protocol (RFC 9420). The server relays opaque ciphertext and never has access to
plaintext message content. See [End-to-End Encryption](e2ee.md) for details.

**Feeds and Rooms** use a trusted-server model. The server enforces role-based
permissions and access control. Messages are encrypted in transit (TLS/QUIC) but are
readable by the server for moderation and search.

## Authentication

- **Passwords** are hashed with Argon2id, providing resistance to GPU and
  side-channel attacks.
- **Two-Factor Authentication** supports TOTP and WebAuthn (FIDO2) as second factors,
  with single-use recovery codes as a fallback. See [Two-Factor Authentication](two-factor.md).

## Device Management

New devices are paired using the **CPace** password-authenticated key exchange, where a
short 6-digit code displayed on the existing device proves physical proximity. A QR code
method is available as an alternative. See [Device Pairing](device-pairing.md).

## Federation

Federated servers authenticate requests using **Ed25519 signatures**. Each server signs
outbound messages with its private key, and receiving servers verify signatures against
published public keys. Nonces prevent replay attacks.

## Sub-Pages

- [End-to-End Encryption](e2ee.md) -- MLS protocol, key management, multi-device, recovery
- [Device Pairing](device-pairing.md) -- CPace and QR code pairing protocols
- [Two-Factor Authentication](two-factor.md) -- TOTP, WebAuthn, recovery codes
