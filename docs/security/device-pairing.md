# Device Pairing

When a user adds a new device, it must be paired with an existing device to receive MLS
group keys. Vox supports two pairing methods: CPace (primary) and QR code (alternative).

## CPace Method

CPace (Composable Password-Authenticated Connection Establishment) is the primary
pairing protocol. It uses a short numeric code as a shared password to establish a
secure channel between the new and existing devices, even though all communication is
relayed through the server.

### Parameters

| Parameter | Value |
|-----------|-------|
| Group | ristretto255 |
| Hash | SHA-512 |
| Code | 6 decimal digits |
| KDF | HKDF-SHA256, info=`vox-cpace-session`, salt=`pair_id` |
| Confirmation | HMAC-SHA256 |
| Encryption | AES-256-GCM |
| Timeout | 5 minutes |

### Flow

```
New Device                    Server                    Existing Device
    |                           |                           |
    |-- POST /keys/devices/pair -->                         |
    |<-- {pair_id} ------------|                            |
    |                           |-- device_pair_prompt ---->|
    |                           |                   user approves
    |                           |                   sees 6-digit code
    |   user enters 6-digit code|                           |
    |                           |                           |
    |========= CPace exchange (via gateway) ===============|
    |-- isi (initiator share) --|-------------------------->|
    |<-------------------------|-- rsi (responder share) ---|
    |-- confirm ----------------|-------------------------->|
    |<-------------------------|-- new_device_key (encrypted)|
    |                           |                           |
    |                           |   existing device adds new
    |                           |   leaf to all MLS groups
    |<-- Welcome messages ------|---------------------------|
```

1. The new device authenticates (username + password) and calls
   `POST /keys/devices/pair`. The server returns a `pair_id`.
2. The server sends a `device_pair_prompt` event to the existing device.
3. The user approves the pairing on the existing device and sees a 6-digit code.
4. The user enters the same 6-digit code on the new device.
5. Both devices perform a CPace key exchange relayed through the gateway:
    - The new device sends its **initiator share** (`isi`).
    - The existing device responds with its **responder share** (`rsi`).
    - The new device sends a **confirmation** (HMAC over the transcript).
    - The existing device verifies the confirmation and sends the new device's public
      key encrypted with AES-256-GCM using the derived session key.
6. The existing device issues MLS `Add` + `Commit` for every DM group, and the new
   device receives `Welcome` messages.

### Security Properties

- **Server cannot derive the session key.** The server relays CPace messages but does
  not know the 6-digit code, so it cannot compute the shared secret.
- **The new device's public key is sent encrypted.** The server never sees the new
  device's key material in plaintext.
- **Short code is safe against offline attacks.** CPace is a balanced PAKE; an attacker
  must perform an online interaction for each guess. The 5-minute timeout and
  rate-limiting make brute-forcing the 6-digit code infeasible.

## QR Code Method

The QR code method is an alternative when both devices are physically co-located.

### Flow

1. The new device generates a keypair and displays a QR code containing its public key
   and a session identifier.
2. The existing device scans the QR code.
3. The existing device verifies the new device's key and adds it to all MLS groups.
4. The new device receives `Welcome` messages.

This method skips the CPace exchange entirely because the QR code provides an
out-of-band authenticated channel. The existing device trusts the public key because it
was read directly from the new device's screen.

## REST Endpoints

### Initiate Pairing

```
POST /keys/devices/pair
```

**Response:**

```json
{
  "pair_id": "unique pairing session ID"
}
```

### Respond to Pairing

```
POST /keys/devices/pair/{pair_id}/respond
```

**Request:**

```json
{
  "approved": true
}
```

If the user denies the pairing request (`"approved": false`), the server flags the
session and no further CPace messages are accepted for that `pair_id`.
