# Architecture Overview

Vox Protocol v1 is a federated, end-to-end encrypted chat platform built on a
**one server = one community** model. Each Vox server is a self-contained
community with its own members, channels, roles, and data.

## Transport Layers

Vox uses three distinct transport layers, each optimised for a different class
of traffic.

```
                         +---------------------+
                         |       Client        |
                         +----+------+---------+
                              |      |         |
              HTTPS (REST)    | WSS  |  QUIC   |
              JSON CRUD       | JSON |  Binary  |
                              |      |         |
                         +----v------v---------v---+
                         |         Server          |
                         |  +-------+  +---------+ |
                         |  |  API  |  | Gateway | |
                         |  +-------+  +---------+ |
                         |        +----------+     |
                         |        |  Media   |     |
                         |        +----------+     |
                         +--------------------------+
```

### REST API

| | |
|---|---|
| **Protocol** | HTTPS |
| **Base URL** | `/api/v1/` |
| **Format** | JSON |
| **Purpose** | CRUD operations, authentication, search, file uploads |

The REST API is the primary interface for stateless operations: creating and
editing resources, authenticating users, searching messages, and uploading
files. Every mutation that does not require real-time delivery flows through
REST.

### Gateway (WebSocket)

| | |
|---|---|
| **Protocol** | WebSocket (`wss://`) |
| **Format** | JSON |
| **Purpose** | Real-time events, presence, typing indicators, voice signaling, MLS relay |

The Gateway maintains a persistent connection between the client and the
server. It pushes real-time events (new messages, presence updates, typing
indicators) and handles voice/video signaling and MLS (Messaging Layer
Security) key-exchange relay traffic.

### Media (QUIC)

| | |
|---|---|
| **Protocol** | QUIC datagrams |
| **Format** | Binary |
| **Purpose** | Voice, video, and screen share streams |

The Media transport carries latency-sensitive audio, video, and screen-share
data over QUIC datagrams. Clients negotiate a media session via Gateway
signaling and then exchange encrypted media frames directly.

## When to Use Each Layer

| Operation | Layer | Reason |
|---|---|---|
| Create / edit / delete a resource | REST API | Stateless CRUD |
| Authenticate / register | REST API | One-off request-response |
| Upload a file | REST API | Large payload, HTTP multipart |
| Search messages | REST API | Query + paginated results |
| Receive new messages in real time | Gateway | Push-based event stream |
| Track who is online | Gateway | Continuous presence updates |
| Show typing indicators | Gateway | Low-latency ephemeral state |
| Voice / video call signaling | Gateway | Session negotiation |
| MLS key exchange relay | Gateway | Group encryption handshake |
| Stream voice audio | Media | Low-latency binary datagrams |
| Stream video / screen share | Media | High-throughput binary datagrams |
