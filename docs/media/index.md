# Media Transport

Vox uses **QUIC datagrams** for real-time voice, video, and screen sharing. QUIC
provides multiplexed, encrypted transport with lower head-of-line blocking than TCP,
making it well suited for media where low latency matters more than guaranteed delivery.

## Voice Room Flow

1. **Join** -- The client calls `POST /rooms/{room_id}/voice/join` to reserve a slot.
   The response includes a `media_url` and a `token`.
2. **Connect** -- The client opens a QUIC connection to `media_url` and authenticates
   with the token.
3. **Codec Negotiation** -- The client and SFU exchange codec capabilities via a
   `voice_codec_neg` message on the gateway.
4. **Send/Receive** -- Media frames are sent as QUIC datagrams using the frame format
   described below.

## Media Frame Format

Every media frame begins with a **22-byte fixed header**, optionally followed by a
variable-length dependency descriptor and the media payload.

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    Version    |     Type      |   Codec ID    |     Flags     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           Room ID                             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           User ID                             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                          Sequence                             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                          Timestamp                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Spatial | Temporal|DTX| Rsvd  |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   Dependency Descriptor ...   |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          Payload ...          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### Field Reference

| Field | Size | Description |
|-------|------|-------------|
| Version | 8 bits | Protocol version |
| Type | 8 bits | Media type (see table below) |
| Codec ID | 8 bits | Codec identifier (see table below) |
| Flags | 8 bits | Bitfield (see table below) |
| Room ID | 32 bits | Voice room identifier |
| User ID | 32 bits | Sending user identifier |
| Sequence | 32 bits | Per-stream packet sequence number |
| Timestamp | 32 bits | Capture timestamp |
| Spatial ID | 4 bits | SVC spatial layer index |
| Temporal ID | 4 bits | SVC temporal layer index |
| DTX | 1 bit | Discontinuous transmission flag |
| Reserved | 7 bits | Reserved for future use |
| Dependency Descriptor | variable | Codec-agnostic SVC metadata (present when `HAS_DEP_DESC` flag is set) |
| Payload | variable | Encoded media data |

### Flags

| Bit | Name | Description |
|-----|------|-------------|
| 0 | `KEYFRAME` | Frame is a keyframe / IDR |
| 1 | `END_OF_FRAME` | Last packet of a multi-packet frame |
| 2 | `FEC` | Packet contains forward error correction data |
| 3 | `MARKER` | Generic marker (codec-specific semantics) |
| 4 | `HAS_DEP_DESC` | Dependency descriptor is present after the fixed header |
| 5-7 | Reserved | Reserved for future use |

### Media Types

| Value | Name |
|-------|------|
| `0x00` | `AUDIO` |
| `0x01` | `VIDEO` |
| `0x02` | `SCREEN` |
| `0x03` | `FEC` |
| `0x04` | `RTCP_FB` |

### Codec IDs

| Value | Name |
|-------|------|
| `0x00` | None |
| `0x01` | Opus |
| `0x02` | AV1 |
| `0x03` | AV1 (screen share profile) |

## Discontinuous Transmission (DTX)

Opus supports discontinuous transmission for audio. When the encoder detects silence, it
stops sending regular audio packets and instead sends packets with the **DTX flag** set
at a reduced rate.

Receivers detect the DTX flag and generate **comfort noise** locally, maintaining the
perception of an active connection without consuming bandwidth during silence.

## Priority

Media streams are prioritized for bandwidth allocation and scheduling:

| Priority | Media Type |
|----------|-----------|
| 0 (highest) | Audio |
| 1 | Video |
| 2 | Screen share |

Audio is always prioritized over video and screen share. Under congestion, the SFU will
drop video and screen share layers before reducing audio quality.
