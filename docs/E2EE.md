# VoxProtocol v1: End-to-End Encryption

All DMs (1:1 and group) use MLS (Message Layer Security, RFC 9420). Server feeds and rooms remain trusted and are not E2E encrypted.

## 1. Why MLS

MLS uses epoch-based keys. Within an epoch, all group members share a symmetric key. This solves multi-device naturally -- all of a user's devices share the same MLS leaf private key and can decrypt any message in the current epoch without per-message state synchronization.

| Property | Benefit |
|---|---|
| Epoch-based keys | No per-message ratchet sync between devices |
| Same protocol for 1:1 and group | One code path to implement and audit |
| Forward secrecy at epoch boundaries | Compromised key cannot decrypt past epochs |
| Efficient add/remove | Tree-based key agreement scales to group DMs |

## 2. MLS DM Flow

Key management (prekey upload/fetch, device management, backup) uses the REST API. Real-time MLS message relay (Welcome, Commit, Proposal) uses the gateway.

```
Alice                    REST API       Gateway                   Bob (+ others)
  |                         |              |                          |
  |-- GET /keys/prekeys/bob>|              |                          |
  |<-- {prekeys: [          |              |                          |
  |      {device_id, bundle}|              |                          |
  |      ...per device      |              |                          |
  |    ]} ------------------|              |                          |
  |                         |              |                          |
  |  [Create MLS group,     |              |                          |
  |   add leaf per device,  |              |                          |
  |   create Welcome per    |              |                          |
  |   device]               |              |                          |
  |                         |              |                          |
  |-- mls_relay {commit} -------------->  |-- mls_commit ---------->|
  |-- mls_relay {welcome, bob} -------->  |-- mls_welcome --------->|
  |   (one Welcome per device)           |   (to each device)       |
  |                         |              |                          |
  |  [All devices share epoch key]       |  [Each device processes   |
  |                         |              |   its Welcome, derives   |
  |                         |              |   epoch key]             |
  |                         |              |                          |
  |-- POST /feeds/{dm}/messages -------  |                          |
  |   {body: ciphertext}    |              |                          |
  |                         |  message_create event (opaque) ------->|
```

## 3. Multi-Device: Per-Device Leaves

Each device has its own MLS leaf node with its own keypair. The server tracks which leaves belong to the same user. When a new device is added, it generates its own keypair and is added to all MLS groups the user belongs to.

```
User: alice
+-- Device: laptop  (leaf key A, leaf node 3)
+-- Device: phone   (leaf key B, leaf node 7)
+-- Device: tablet  (leaf key C, leaf node 12)
```

Adding a device is a one-time operation: the existing device issues an MLS Add+Commit for the new device's leaf to each DM group the user belongs to. From then on, both devices independently derive epoch keys from the tree -- no ongoing synchronization needed.

## 4. Device Pairing: CPace Method

The primary method when the user has an existing device. Uses CPace (draft-irtf-cfrg-cpace), a password-authenticated key exchange, to bind a user-entered short code into the key derivation. This prevents the server from performing a MITM attack.

### CPace Parameters

| Parameter | Value |
|---|---|
| Group | ristretto255 |
| Hash | SHA-512 |
| Code | 6 decimal digits |
| Key derivation | HKDF-SHA256, info="vox-cpace-session", salt=pair_id |
| Confirmation | HMAC-SHA256(sk, side \|\| pair_id) |
| Encryption | AES-256-GCM |
| Timeout | 5 minutes |

### CPace Flow

```
New Device           REST API      Gateway               Existing Device
  |                     |             |                        |
  |  [generate own MLS  |             |                        |
  |   leaf keypair]     |             |                        |
  |                     |             |                        |
  |-- POST /auth/login->|             |                        |
  |<-- {token} ---------|             |                        |
  |                     |             |                        |
  |-- POST /keys/       |             |                        |
  |   devices/pair ---->|             |                        |
  |<-- {pair_id} -------|             |                        |
  |                     |             |                        |
  |                     |  device_pair_prompt event ---------->|
  |                     |             |   {device_name,        |
  |                     |             |    ip, location,       |
  |                     |             |    pair_id}            |
  |                     |             |                        |
  |                     |             |   [existing device     |
  |                     |             |    displays 6-digit    |
  |                     |             |    code, user approves]|
  |                     |             |                        |
  |                     |  POST /keys/devices/pair/{id}/respond|
  |                     |<----- {approved: true} --------------|
  |                     |             |                        |
  |  [user enters 6-digit code]      |                        |
  |                     |             |                        |
  |  === CPace key exchange (via gateway) ===                  |
  |                     |             |                        |
  |-- cpace_relay {isi} ------------>|-- cpace_isi event ---->|
  |                     |             |                        |
  |                     |             |<-- cpace_relay {rsi} --|
  |<-- cpace_rsi event --------------|                        |
  |                     |             |                        |
  |  [both derive shared key]        |  [both derive key]     |
  |                     |             |                        |
  |-- cpace_relay {confirm} -------->|-- event -------------->|
  |<-- event -------------------------<-- cpace_relay {confirm}|
  |                     |             |                        |
  |  [verify confirmation]           |  [verify confirmation] |
  |                     |             |                        |
  |-- cpace_relay {new_device_key} ->|-- event -------------->|
  |   {encrypted new leaf pubkey}    |                        |
  |                     |             |                        |
  |                     |             |  [existing device adds |
  |                     |             |   new leaf to all MLS  |
  |                     |             |   groups via Add+Commit]
  |                     |             |                        |
  |-- POST /keys/devices ----------->|                        |
  |-- PUT /keys/prekeys ------------>|  device_list_update -->|
```

The server relays all CPace messages but cannot derive the session key because it does not know the 6-digit code displayed on the existing device. The new device's public key is sent encrypted, preventing the server from substituting a different key.

If denied, the server SHOULD flag the session and MAY lock the account for review.

## 5. Device Pairing: QR Code Method

Alternative when push is unavailable:

```
New Device                                            Existing Device
  |                                                          |
  |  [generate own MLS leaf keypair]                         |
  |  [display QR: {leaf_public_key, device_id}]              |
  |                                                          |
  |  <-------- user scans QR with existing device -------->  |
  |                                                          |
  |                              [verify key, add new leaf   |
  |                               to all MLS groups via      |
  |                               Add+Commit]                |
  |                                                          |
  |  <-------- confirmation relayed via gateway ----------   |
  |                                                          |
  |  [new device is now part of all DM groups]               |
```

## 6. Recovery: All Devices Lost

Two gates protect recovery:

| Gate | Proves | Mechanism |
|---|---|---|
| Authentication | "I am this user" | Username + password |
| Recovery passphrase | "I should have this user's keys" | Decrypts server-stored blob |

Setup (at account creation). Clients MUST use the following procedure to ensure cross-client recovery interoperability:

1. Generate 12-word recovery passphrase (BIP39 mnemonic)
2. Derive encryption key: K = Argon2id(passphrase, user_id_salt)
3. Encrypt MLS leaf private key and group state with K
4. Upload encrypted blob via `PUT /api/v1/keys/backup`
5. User stores the 12 words securely

Recovery flow:

```
New Device                REST API
  |                          |
  |-- POST /auth/login ----->|  (gate 1: proves identity)
  |<-- {token} --------------|
  |                          |
  |-- GET /keys/backup ----->|
  |<-- {encrypted_blob} -----|
  |                          |
  |  [user enters recovery   |
  |   phrase]                |
  |  [K = Argon2id(phrase,   |
  |   salt)]                 |
  |  [decrypt blob -> leaf   |
  |   key + group state]     |  (gate 2: proves key ownership)
  |                          |
  |-- POST /keys/devices --->|
  |-- PUT /keys/prekeys ---->|
```

## 7. Key Reset (no recovery possible)

If a user has lost all devices AND forgotten their recovery passphrase:

1. User authenticates and calls `POST /api/v1/keys/reset`
2. Server dispatches `key_reset_notify` to all DM contacts via gateway
3. Contacts see: "Alice's security key has changed"
4. All existing MLS group states with Alice are invalidated
5. New DM sessions must be re-established
6. Old encrypted message history is unreadable

## 8. Safety Numbers

Users can verify each other's identity keys out-of-band. Clients MUST compute safety numbers as follows:

```
fingerprint = SHA-256(sort(alice_identity_key, bob_identity_key))

Displayed as 12 groups of 5 digits:
  37281 48103 59274 10384
  92847 38291 04827 19384
  28471 93827 48291 03847

Or as a QR code encoding both identity keys.
```

Safety numbers change when a user does key reset. Contacts are warned.

## 9. Federated Key Exchange

For cross-server DMs, servers relay prekey requests transparently. Clients see the same REST endpoints and gateway events regardless of whether the recipient is local or federated. See `FEDERATION.md` for the server-to-server relay details.
