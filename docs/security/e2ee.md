# End-to-End Encryption

Vox uses the **Messaging Layer Security (MLS)** protocol (RFC 9420) for end-to-end
encrypted direct messages. The server relays opaque ciphertext and never has access to
plaintext content.

## Why MLS

MLS was chosen over the Signal protocol (Double Ratchet) for several reasons:

- **Epoch-based keys.** MLS derives encryption keys per epoch rather than per message.
  This eliminates the need for per-message ratchet synchronization, which simplifies
  multi-device support and reduces out-of-order message failures.
- **Unified protocol.** The same MLS protocol handles both 1:1 and group conversations.
  There is no separate group protocol layered on top.
- **Forward secrecy at epoch boundaries.** Compromising a key only exposes messages
  within the current epoch. An epoch advances on any membership change (add, remove,
  update).
- **Tree-based key agreement.** MLS uses a ratchet tree for key agreement, giving
  `O(log n)` cost for group operations rather than `O(n)`.

## DM Flow

### 1. Fetch Prekeys

The sending client fetches the recipient's prekey bundle via REST:

```
GET /keys/prekeys/{user_id}
```

The response includes one entry per device:

```json
{
  "devices": [
    {
      "device_id": "device_abc",
      "identity_key": "...",
      "signed_prekey": "...",
      "one_time_prekey": "..."
    }
  ]
}
```

### 2. Create MLS Group

The sender creates a new MLS group with one leaf node per recipient device (and one for
the sender's own device). Each leaf contains the device's identity key.

### 3. Send Welcome and Commit

The sender transmits the MLS **Welcome** message (containing the group secrets) and the
initial **Commit** to each recipient device via the gateway. The server relays these as
opaque blobs.

### 4. Send Messages

Subsequent messages are MLS application messages sent as `opaque_blob` fields. The
server stores and forwards the blob without inspecting its contents.

## Multi-Device Support

Each device has its own MLS leaf node with its own keypair. A user with three devices
has three leaves in every DM group they participate in.

**Adding a new device:** The existing device issues an MLS `Add` proposal followed by a
`Commit` to every DM group the user is part of. The new device receives `Welcome`
messages for each group and can decrypt future messages. Past messages remain
inaccessible to the new device unless restored from backup.

See [Device Pairing](device-pairing.md) for the pairing protocol.

## Recovery

Recovery handles the case where a user has lost access to **all** of their devices.

### Two Gates

Recovery requires passing two independent gates:

1. **Authentication** -- the user proves their identity with username and password.
2. **Recovery passphrase** -- a 12-word BIP39 mnemonic generated during setup.

Neither gate alone is sufficient. The server cannot decrypt the backup (it does not know
the passphrase), and the passphrase alone is useless without authentication.

### Setup

1. Generate a 12-word BIP39 mnemonic and display it to the user.
2. Derive a symmetric key: `K = Argon2id(passphrase, user_id_salt)`.
3. Encrypt the device's MLS leaf private key and all group state with `K`.
4. Upload the encrypted blob:

```
PUT /keys/backup
```

```json
{
  "encrypted_blob": "..."
}
```

### Restore

1. Authenticate with username and password.
2. Fetch the backup:

```
GET /keys/backup
```

3. Enter the recovery passphrase.
4. Derive `K` and decrypt the leaf key and group state.
5. Register a new device and resume participation in all groups.

### Key Reset (No Recovery Passphrase)

If the user has lost both their devices and their recovery passphrase, they can perform
a key reset:

```
POST /keys/reset
```

This has significant consequences:

- A `key_reset_notify` event is sent to all of the user's contacts.
- All MLS groups the user participates in are invalidated.
- Old message history becomes permanently unreadable.
- The user starts fresh with new keys.

## Safety Numbers

Safety numbers allow two users to verify that no man-in-the-middle attack has occurred.

**Computation:**

```
SHA-256(sort(alice_identity_key, bob_identity_key))
```

The keys are sorted lexicographically before hashing to ensure both parties compute the
same value. The resulting hash is displayed as **12 groups of 5 decimal digits** (60
digits total).

Safety numbers change when either party performs a key reset. Clients should alert users
when a contact's safety number changes.

## Federated Key Exchange

Key exchange with users on federated servers works transparently. Prekey fetches and MLS
messages are relayed through the federation layer. The local server forwards requests to
the remote server, which returns prekey bundles in the same format. MLS Welcome/Commit
messages are relayed as opaque blobs.

## REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `PUT` | `/keys/prekeys` | Upload identity key, signed prekey, and one-time prekeys |
| `GET` | `/keys/prekeys/{user_id}` | Fetch prekey bundle for all of a user's devices |
| `POST` | `/keys/devices` | Register a new device |
| `DELETE` | `/keys/devices/{device_id}` | Remove a device |
| `PUT` | `/keys/backup` | Upload encrypted key backup |
| `GET` | `/keys/backup` | Download encrypted key backup |
| `POST` | `/keys/reset` | Reset all keys (destroys history) |

### Request/Response Bodies

**PUT /keys/prekeys**

```json
{
  "identity_key": "base64-encoded Ed25519 public key",
  "signed_prekey": "base64-encoded signed prekey",
  "one_time_prekeys": [
    "base64-encoded one-time prekey",
    "..."
  ]
}
```

**POST /keys/devices**

```json
{
  "device_id": "client-generated unique ID",
  "device_name": "Laptop"
}
```

**PUT /keys/backup**

```json
{
  "encrypted_blob": "base64-encoded encrypted backup"
}
```
