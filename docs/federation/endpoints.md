# Federation Endpoints

All federation endpoints are server-to-server HTTPS REST calls. Every request
**must** include the following headers:

| Header            | Description                                            |
|-------------------|--------------------------------------------------------|
| `X-Vox-Origin`    | The sending server's domain.                           |
| `X-Vox-Signature` | Base64-encoded Ed25519 signature of the request body.  |

The receiving server verifies the signature against the public key published in
the `_voxkey` TXT DNS record for the `X-Vox-Origin` domain.

---

## Message Relay

### POST /federation/relay/message

Relay an E2EE-encrypted DM message to a user on this server.

**Request Body:**

```json
{
  "from": "alice@remote.example.com",
  "to": "bob@local.example.com",
  "opaque_blob": "base64-e2ee-encrypted-payload"
}
```

| Field         | Type   | Description                                     |
|---------------|--------|-------------------------------------------------|
| `from`        | string | Sender's federated address (`user@domain`).     |
| `to`          | string | Recipient's federated address (`user@domain`).  |
| `opaque_blob` | string | E2EE-encrypted message payload (base64).        |

**Response:** `204 No Content`

---

## Typing Relay

### POST /federation/relay/typing

Indicate that a remote user is typing in a DM.

**Request Body:**

```json
{
  "from": "alice@remote.example.com",
  "to": "bob@local.example.com"
}
```

**Response:** `204 No Content`

---

## Read Receipt Relay

### POST /federation/relay/read

Relay a read receipt for a DM conversation.

**Request Body:**

```json
{
  "from": "alice@remote.example.com",
  "to": "bob@local.example.com",
  "up_to_msg_id": 1050
}
```

| Field          | Type   | Description                                    |
|----------------|--------|------------------------------------------------|
| `from`         | string | The user who read the messages.                |
| `to`           | string | The other participant in the DM.               |
| `up_to_msg_id` | int    | All messages up to and including this ID are read. |

**Response:** `204 No Content`

---

## Prekey Exchange

### GET /federation/users/{user_address}/prekeys

Retrieve E2EE prekeys for a remote user's devices, used to establish encrypted
sessions.

**Path Parameters:**

| Parameter      | Type   | Description                        |
|----------------|--------|------------------------------------|
| `user_address` | string | Federated address (`user@domain`). |

**Response:** `200 OK`

```json
{
  "user_address": "bob@local.example.com",
  "devices": [
    {
      "device_id": "device-abc",
      "identity_key": "base64-identity-key",
      "signed_prekey": "base64-signed-prekey",
      "prekey_signature": "base64-signature",
      "one_time_prekey": "base64-otpk"
    }
  ]
}
```

---

## User Profile Lookup

### GET /federation/users/{user_address}

Look up a remote user's public profile.

**Path Parameters:**

| Parameter      | Type   | Description                        |
|----------------|--------|------------------------------------|
| `user_address` | string | Federated address (`user@domain`). |

**Response:** `200 OK`

```json
{
  "display_name": "bob",
  "avatar_url": "https://cdn.local.example.com/avatars/bob.png",
  "bio": "Hello from the other side"
}
```

---

## Presence

### POST /federation/presence/subscribe

Subscribe to presence updates for a remote user. The remote server will send
`presence/notify` callbacks when the user's status changes.

**Request Body:**

```json
{
  "user_address": "bob@local.example.com"
}
```

**Response:** `204 No Content`

### POST /federation/presence/notify

Push a presence update to a server that has subscribed.

**Request Body:**

```json
{
  "user_address": "alice@remote.example.com",
  "status": "online",
  "activity": {
    "type": "playing",
    "name": "Some Game"
  }
}
```

| Field          | Type   | Required | Description                                |
|----------------|--------|----------|--------------------------------------------|
| `user_address` | string | Yes      | The user whose presence changed.           |
| `status`       | string | Yes      | One of `online`, `idle`, `dnd`, `offline`. |
| `activity`     | object | No       | Optional activity information.             |

**Response:** `204 No Content`

---

## Server Joining

### POST /federation/join

Request to join a server on behalf of a federated user.

**Request Body:**

```json
{
  "user_address": "alice@remote.example.com",
  "invite_code": "abc123",
  "voucher": {
    "user_address": "alice@remote.example.com",
    "target_domain": "local.example.com",
    "issued_at": "2026-02-19T12:00:00Z",
    "expires_at": "2026-02-19T13:00:00Z",
    "nonce": "random-unique-nonce",
    "signature": "base64-ed25519-signature"
  }
}
```

| Field          | Type   | Required | Description                                      |
|----------------|--------|----------|--------------------------------------------------|
| `user_address` | string | Yes      | The user requesting to join.                     |
| `invite_code`  | string | No       | An invite code, if one is required.              |
| `voucher`      | object | Yes      | Signed voucher from the user's home server.      |

**Response:** `200 OK`

```json
{
  "accepted": true,
  "federation_token": "token-for-direct-gateway-connection",
  "server_info": {
    "name": "Local Server",
    "icon": "https://cdn.local.example.com/icon.png",
    "member_count": 1500
  }
}
```

| Field              | Type   | Description                                          |
|--------------------|--------|------------------------------------------------------|
| `accepted`         | bool   | Whether the join request was accepted.               |
| `federation_token` | string | Token the remote user uses to connect directly.      |
| `server_info`      | object | Basic information about the server.                  |

---

## Domain Blocking

### POST /federation/block

Block the sending domain from federating with this server. This is a courtesy
notification sent by the blocking server.

**Request Body:**

```json
{
  "reason": "Repeated abuse policy violations"
}
```

| Field    | Type   | Required | Description                    |
|----------|--------|----------|--------------------------------|
| `reason` | string | No       | Optional reason for the block. |

**Response:** `204 No Content`
