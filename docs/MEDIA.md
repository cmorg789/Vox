# VoxProtocol v1: Media Transport

Media frames (voice, video, screen share) use a dedicated binary transport over QUIC datagrams, separate from the REST and gateway connections. Media requires ultra-low latency unreliable delivery that HTTP and WebSocket cannot provide.

## 1. Connecting to Media

After joining a voice room via `POST /api/v1/rooms/{room_id}/voice/join`, the response includes:

```json
{
  "media_url": "quic://vox.example.com:4443",
  "media_token": "media_token_abc..."
}
```

The client opens a QUIC connection to the media endpoint and authenticates with the media token. Media frames are then sent/received as QUIC datagrams.

The media transport version is bound to the gateway protocol version: protocol v1 always uses media transport v1. There is no independent media version negotiation. The version byte in the media frame header MUST match the negotiated protocol version from the gateway `ready` message.

The `media_token` is short-lived (server-configurable). The server sends a `media_token_refresh` gateway event before expiry. See `GATEWAY.md` for the event format.

## 2. Media Frame Header

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Version (8)  |  Type (8)     |  Codec ID (8) |   Flags (8)   |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Room ID (32)                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       User ID (32)                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Sequence (32)                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                      Timestamp (32)                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Spatial ID (4)| Temporal ID(4)| DTX (1)|    Reserved (7)      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|       Dependency Descriptor (variable, 0-32 bytes)         ..|
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Payload (variable)                        ..|
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

Fixed media header: 22 bytes + dependency descriptor
```

Flags: `[KEYFRAME, END_OF_FRAME, FEC, MARKER, HAS_DEP_DESC, RSV, RSV, RSV]` -- 3 reserved bits

- **MARKER**: last packet of a video frame
- **HAS_DEP_DESC**: dependency descriptor is present (always true for video/screen, false for audio)

## 3. Media Types

| Type | Value | Description |
|---|---|---|
| AUDIO | 0x00 | Audio frame |
| VIDEO | 0x01 | Video frame |
| SCREEN | 0x02 | Screen share frame |
| FEC | 0x03 | Forward error correction (reserved) |
| RTCP_FB | 0x04 | TWCC feedback report |

## 4. Codec IDs

| ID | Codec | Use |
|---|---|---|
| 0x00 | None | Reserved (unset) |
| 0x01 | Opus | Voice |
| 0x02 | AV1 | Video |
| 0x03 | AV1 screen profile | Screen share |
| 0x04-0xFF | [reserved] | |

## 5. Scalable Video Coding (SVC)

Video and screen share use AV1 SVC (Scalable Video Coding). The sender encodes a single stream with embedded spatial and temporal layers. The SFU strips layers based on each receiver's available bandwidth.

### Layer Structure

| Layer Type | IDs | Purpose |
|---|---|---|
| Spatial | S0, S1, S2 | Resolution tiers (e.g., 180p, 360p, 720p) |
| Temporal | T0, T1 | Frame rate tiers (e.g., 15fps base, 30fps full) |

Example configuration for video (actual values are negotiated via the `voice_codec_neg` gateway message):

```
S2 (720p)  --- T0 (15fps) --- T1 (30fps)     ~2 Mbps total
S1 (360p)  --- T0 (15fps) --- T1 (30fps)     ~500 kbps total
S0 (180p)  --- T0 (15fps) --- T1 (30fps)     ~150 kbps total
```

Example configuration for screen share:

```
S1 (1080p) --- T0 (5fps)  --- T1 (15fps)     ~4 Mbps total
S0 (540p)  --- T0 (5fps)  --- T1 (15fps)     ~1 Mbps total
```

### Dependency Descriptor

The Dependency Descriptor is a codec-agnostic metadata structure attached to video/screen media packets. It describes the layer dependency graph so the SFU can strip layers without parsing the AV1 bitstream.

Fields:
- `start_of_frame`: is this the first packet of a frame
- `end_of_frame`: is this the last packet of a frame
- `template_id`: references a pre-negotiated frame dependency template
- `frame_number`: frame counter within the stream
- `frame_dependencies`: which previous frames this frame depends on
- `decode_target_indications`: which quality targets this frame contributes to
- `chain_diffs`: chain-based dependency signaling for efficient layer switching

The dependency descriptor is negotiated during `voice_codec_neg` (see `GATEWAY.md`) and sent on every video/screen packet when the HAS_DEP_DESC flag is set.

### SFU Layer Forwarding

The SFU reads the dependency descriptor (not the AV1 bitstream) to make forwarding decisions:

```
Sender                          SFU                         Receivers
  |                               |                            |
  |== S0+S1+S2 video stream ====>|                            |
  |   (all layers, ~2.5 Mbps)    |                            |
  |                               |  [read dependency desc]    |
  |                               |  [check receiver bandwidth]|
  |                               |                            |
  |                               |== S0+S1+S2 ==> Receiver A (good bw)
  |                               |== S0+S1    ==> Receiver B (medium bw)
  |                               |== S0       ==> Receiver C (poor bw)
```

The SFU never decodes or re-encodes video. It only reads metadata and drops packets whose spatial/temporal ID exceeds the target for a given receiver.

### Layer Switching

When a receiver's bandwidth changes, the SFU can:
- **Drop to lower spatial layer**: requires waiting for a keyframe on the lower layer, or using chain-based switching if the dependency structure allows it
- **Drop temporal layers**: can happen immediately (temporal layers are independently decodable)
- **Add higher layers**: immediate if packets are available

## 6. DTX (Discontinuous Transmission)

Opus supports DTX -- sending no packets during silence. In a room with 10 people where 2 are speaking, the other 8 send no audio packets. The DTX flag in the media header signals that the sender is in DTX mode. Receivers should generate comfort noise locally during DTX periods to avoid perceived dead silence.

## 7. Voice Room Flow

```
User A              REST API        Gateway            SFU (Media)         User B, C
  |                    |               |                   |                   |
  |-- POST /rooms/     |               |                   |                   |
  |   {id}/voice/join->|               |                   |                   |
  |<-- {media_url,     |               |                   |                   |
  |     media_token,   |               |                   |                   |
  |     members[]} ----|               |                   |                   |
  |                    |               |                   |                   |
  |                    |  voice_state_update (A joined) -->|                   |
  |                    |               |---event---------->|                   |
  |                    |               |---event-----------|------------------>|
  |                    |               |                   |                   |
  |== QUIC connect to media_url =====>|==================>|                   |
  |                    |               |                   |                   |
  |-- voice_codec_neg ----------------->|                   |                   |
  |<-- voice_codec_neg -----------------|                   |                   |
  |                    |               |                   |                   |
  |== MEDIA_AUDIO =======================================>|== forward ======>|
  |== MEDIA_VIDEO (S0+S1+S2) ============================>|== S0+S1+S2 => B  |
  |                    |               |                   |== S0 =======> C   |
  |                    |               |                   |                   |
  |-- POST /rooms/     |               |                   |                   |
  |   {id}/voice/leave>|               |                   |                   |
  |                    |  voice_state_update (A left) ---->|                   |
```

## 8. Congestion Control (TWCC)

VoxProtocol uses Transport-Wide Congestion Control. Instead of aggregate statistics, receivers report per-packet arrival times. Both the SFU and senders run bandwidth estimation independently.

### Feedback Flow

```
Sender =============> SFU =============> Receiver
  |                    |                    |
  |  (sends all SVC    |  (forwards layers  |
  |   layers)          |   per receiver)    |
  |                    |                    |
  |<-- MEDIA_RTCP_FB --|<-- MEDIA_RTCP_FB --|
  |   (uplink TWCC)    |  (downlink TWCC)   |
  |                    |                    |
  | [sender runs GCC,  | [SFU runs GCC per  |
  |  adjusts encoder]  |  receiver, adjusts |
  |                    |  layer forwarding] |
```

**Downlink path (Receiver -> SFU):** Receiver sends TWCC reports about packets received from the SFU. The SFU runs a bandwidth estimator per receiver and adjusts which SVC layers to forward.

**Uplink path (SFU -> Sender):** The SFU sends TWCC reports about packets received from the sender. The sender runs its own bandwidth estimator and adjusts encoder quality (bitrate, resolution, frame rate) if uplink is constrained.

### TWCC Report Format

Sent via MEDIA_RTCP_FB:

| Field | Size | Description |
|---|---|---|
| base_sequence | 32 bits | First packet sequence number in this report |
| packet_count | 32 bits | Number of packets covered |
| reference_time | 32 bits | Base receive time (64ms resolution) |
| packet_statuses | variable | Bitmap: received / not received / received-with-delta for each packet |
| recv_deltas | variable | Inter-arrival time deltas for received packets (250us or 1ms resolution) |

The sender/SFU uses inter-arrival deltas to detect congestion (increasing delays = congestion, stable = clear).

### Bandwidth Estimation

Implementations use TWCC reports to perform bandwidth estimation and adjust encoding/forwarding accordingly. The choice of algorithm is implementation-defined. One common approach is GCC (Google Congestion Control), which uses inter-arrival delay variation to detect congestion and adjusts bitrate via an AIMD (additive increase, multiplicative decrease) scheme.

### SFU Layer Selection

The SFU maps estimated bandwidth per receiver to SVC layers. The specific thresholds are implementation-defined. Example mapping:

```
Estimated BW    Forwarded Layers          Approx Quality
> 2 Mbps        S2+T1 (720p/30fps)        Full
> 800 kbps      S1+T1 (360p/30fps)        Medium
> 300 kbps      S1+T0 (360p/15fps)        Medium-Low
> 150 kbps      S0+T1 (180p/30fps)        Low
< 150 kbps      S0+T0 (180p/15fps)        Minimum
```

Layer switches happen at dependency descriptor chain boundaries to avoid decoding artifacts.

### Additional Feedback Signals

Beyond TWCC, MEDIA_RTCP_FB also carries:

| Signal | Purpose |
|---|---|
| NACK | Request retransmission of specific sequence numbers (video only, selective) |
| PLI (Picture Loss Indication) | Request new keyframe from sender |

## 9. Priority and QoS

Different media types have different priority levels:

| Priority | Traffic |
|---|---|
| 0 (highest) | Voice audio |
| 1 | Video |
| 2 | Screen share |

The QUIC transport layer uses these priorities when scheduling datagram transmission under congestion.
