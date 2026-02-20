# Transport Layers

This page documents the three Vox transport layers in detail: REST API, Gateway
WebSocket, and Media QUIC.

---

## REST API

### Base URL

All REST endpoints live under:

```
https://<domain>/api/v1/
```

### Authentication

Requests must include an `Authorization` header with one of two schemes:

| Scheme | Format | Used By |
|---|---|---|
| Bearer | `Authorization: Bearer <session_token>` | User sessions |
| Bot | `Authorization: Bot <bot_token>` | Bot integrations |

### Content Types

- **Request body**: `application/json` (unless uploading files, which use
  `multipart/form-data`).
- **Response body**: `application/json`.

### Pagination

List endpoints use **cursor-based pagination**. The following query parameters
control paging:

| Parameter | Type | Description |
|---|---|---|
| `limit` | integer | Maximum number of items to return (server-defined max and default). |
| `after` | string | Return items after this ID (exclusive). |
| `cursor` | string | Opaque cursor returned by the previous page. |

A response that has more pages will include a `cursor` field in the JSON body.
Pass it as the `cursor` query parameter to fetch the next page. When `cursor`
is absent or `null`, there are no more results.

---

## Gateway (WebSocket)

### Overview

The Gateway is a persistent WebSocket connection (`wss://`) that delivers
real-time events from the server to the client and accepts client commands.
All frames are JSON-encoded.

### Connection Lifecycle

The full client startup sequence is:

```
1. Authenticate         POST /api/v1/auth/login  ->  session token
2. Get Gateway URL      GET  /api/v1/gateway      ->  wss:// URL
3. Connect Gateway      open WebSocket to the returned URL
4. Receive HELLO        server sends hello with heartbeat interval
5. Send IDENTIFY        client sends session token
6. Receive READY        server sends initial state snapshot
7. Fetch initial state  client hydrates via REST (member lists, history, etc.)
8. (optional) Join voice  client sends voice-state-update to join a room
```

#### HELLO

Immediately after the WebSocket connection is established the server sends a
`hello` payload containing the **heartbeat interval** in milliseconds. The
client must begin sending heartbeat frames at this interval to keep the
connection alive.

#### IDENTIFY

The client responds to `hello` by sending an `identify` payload that includes
the session token obtained during authentication.

#### READY

Once the server validates the token it sends a `ready` payload containing the
client's user object, a list of joined servers, and other initial state the
client needs to render.

### Event Delivery

After `ready`, the server pushes events as they occur: new messages, presence
updates, typing indicators, member changes, and so on. Each event has an
opcode and a JSON data payload.

### Voice Signaling

Voice and video session negotiation happens over the Gateway. The client sends
a `voice-state-update` command to join or leave a room; the server responds
with connection parameters for the Media transport.

### MLS Relay

MLS (Messaging Layer Security) handshake messages for group E2E encryption are
relayed through the Gateway as opaque binary blobs wrapped in JSON.

---

## Media (QUIC)

### Overview

The Media transport carries real-time voice, video, and screen-share streams
over **QUIC datagrams**. QUIC provides low-latency, multiplexed delivery
without head-of-line blocking.

### Connection Flow

1. The client joins a voice/video room via Gateway signaling.
2. The server responds with Media transport connection parameters (host, port,
   token).
3. The client opens a QUIC connection to the Media endpoint and authenticates
   with the provided token.
4. Audio, video, and screen-share frames are exchanged as encrypted QUIC
   datagrams.

### Frame Format

Media frames are binary-encoded. Each datagram contains a header (stream type,
sequence number, timestamp) followed by the encrypted media payload. Encryption
is applied end-to-end; the server forwards frames without decrypting them.

---

## Connection Lifecycle Summary

```
  Client                          Server
    |                                |
    |  POST /api/v1/auth/login       |
    |------------------------------->|
    |  200 { token }                 |
    |<-------------------------------|
    |                                |
    |  GET /api/v1/gateway           |
    |------------------------------->|
    |  200 { url: "wss://..." }      |
    |<-------------------------------|
    |                                |
    |  WebSocket CONNECT             |
    |------------------------------->|
    |  <- HELLO { heartbeat_interval }|
    |<-------------------------------|
    |  IDENTIFY { token }            |
    |------------------------------->|
    |  <- READY { user, servers }    |
    |<-------------------------------|
    |                                |
    |  REST: fetch history, members  |
    |------------------------------->|
    |  200 { ... }                   |
    |<-------------------------------|
    |                                |
    |  VOICE_STATE_UPDATE (join)     |
    |------------------------------->|
    |  <- VOICE_SERVER { host, port }|
    |<-------------------------------|
    |                                |
    |  QUIC CONNECT (media)          |
    |------------------------------->|
    |  <-> encrypted media frames    |
    |<=============================>|
```
