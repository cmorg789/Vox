# SVC and Congestion Control

## Scalable Video Coding (AV1 SVC)

Vox uses AV1 **Scalable Video Coding** (SVC) to adapt video quality to each receiver's
available bandwidth. Instead of encoding multiple independent streams (simulcast), the
encoder produces a single bitstream with embedded **spatial** and **temporal** layers
that can be selectively forwarded by the SFU.

### Layer Structure

**Camera video:**

| Spatial Layer | Resolution | Temporal Layers | Frame Rate |
|---------------|-----------|-----------------|------------|
| S0 | 180p | T0 / T1 | 15 fps / 30 fps |
| S1 | 360p | T0 / T1 | 15 fps / 30 fps |
| S2 | 720p | T0 / T1 | 15 fps / 30 fps |

**Screen share:**

| Spatial Layer | Resolution | Temporal Layers | Frame Rate |
|---------------|-----------|-----------------|------------|
| S0 | 540p | T0 / T1 | 5 fps / 15 fps |
| S1 | 1080p | T0 / T1 | 5 fps / 15 fps |

Each higher spatial layer depends on the layer below it. Temporal layers are
independent: T0 frames can be decoded without T1, but T1 frames reference T0 frames.

## Dependency Descriptor

The **dependency descriptor** is a codec-agnostic metadata structure carried in the
media frame header (when the `HAS_DEP_DESC` flag is set). It allows the SFU to make
forwarding decisions without parsing the AV1 bitstream.

### Fields

| Field | Description |
|-------|-------------|
| `start_of_frame` | First packet of a frame |
| `end_of_frame` | Last packet of a frame |
| `template_id` | Index into the negotiated template table |
| `frame_number` | Monotonically increasing frame counter |
| `frame_dependencies` | List of frames this frame depends on (by frame number delta) |
| `decode_target_indications` | Per-decode-target status: not present, discardable, switch, required |
| `chain_diffs` | Per-chain distance to the previous chain frame (for layer switch points) |

The template table is negotiated during codec negotiation (`voice_codec_neg`) and
defines the structure of the SVC layer hierarchy. Each template specifies a spatial ID,
temporal ID, and the set of dependencies.

## SFU Layer Forwarding

The SFU operates purely as a **selective forwarder**. It reads the dependency descriptor
in each packet to determine whether to forward or drop the packet. It never decodes or
re-encodes media.

### Forwarding Logic

For each receiver, the SFU maintains a target spatial and temporal layer based on the
receiver's estimated bandwidth. Packets are forwarded if:

1. The packet's spatial ID is less than or equal to the target spatial layer.
2. The packet's temporal ID is less than or equal to the target temporal layer.
3. All dependencies of the packet have been forwarded.

### Layer Switching Rules

| Switch Type | Condition |
|-------------|-----------|
| Drop to lower spatial | Immediate (lower layers are always a subset) |
| Raise to higher spatial | Must wait for a **keyframe** or **chain boundary** |
| Drop to lower temporal | Immediate |
| Raise to higher temporal | Immediate |

Spatial layer upgrades require a keyframe because higher spatial layers reference the
lower layer of the same frame. The SFU requests a keyframe via PLI when it needs to
switch up.

## Congestion Control (TWCC)

Vox uses **Transport-Wide Congestion Control (TWCC)** for bandwidth estimation. TWCC
works by attaching a transport-wide sequence number to every media packet and
periodically reporting per-packet arrival times back to the sender.

### Two Feedback Paths

```
Sender ---[media]---> SFU ---[media]---> Receiver
Sender <--[TWCC]---- SFU <--[TWCC]----- Receiver
```

1. **Downlink (Receiver to SFU):** The receiver reports TWCC feedback to the SFU. The
   SFU uses this to estimate the receiver's available bandwidth and adjusts which SVC
   layers to forward.
2. **Uplink (SFU to Sender):** The SFU reports TWCC feedback to the sender. The sender
   uses this to estimate the uplink bandwidth and adjusts encoder quality (bitrate,
   resolution, frame rate).

### TWCC Report Format

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Base Sequence                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Packet Count                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                      Reference Time                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|             Packet Statuses (variable) ...                    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|             Receive Deltas (variable) ...                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Field | Size | Description |
|-------|------|-------------|
| Base Sequence | 32 bits | Sequence number of the first packet in this report |
| Packet Count | 32 bits | Number of packets covered by this report |
| Reference Time | 32 bits | Base timestamp for delta computation |
| Packet Statuses | variable | Per-packet received/lost status |
| Receive Deltas | variable | Per-packet arrival time delta from reference time |

### Bandwidth Estimation

The bandwidth estimation algorithm is **implementation-defined**. A typical
implementation uses GCC (Google Congestion Control) with AIMD (Additive Increase
Multiplicative Decrease):

- **Additive increase:** Gradually increase the estimated bandwidth when packets arrive
  on time.
- **Multiplicative decrease:** Rapidly reduce the estimate when delay increases or
  packet loss is detected.

## SFU Layer Selection

The SFU selects the target layer for each receiver based on estimated available
bandwidth:

| Bandwidth | Spatial | Temporal | Result |
|-----------|---------|----------|--------|
| > 2 Mbps | S2 | T1 | 720p at 30 fps |
| > 800 kbps | S1 | T1 | 360p at 30 fps |
| > 300 kbps | S1 | T0 | 360p at 15 fps |
| > 150 kbps | S0 | T1 | 180p at 30 fps |
| < 150 kbps | S0 | T0 | 180p at 15 fps |

These thresholds are guidelines. The SFU may adjust based on the number of active
senders and available server capacity.

## Additional RTCP Signals

Beyond TWCC, two additional feedback signals are used:

### NACK (Negative Acknowledgement)

Requests retransmission of specific packets identified by sequence number. Used for
**video only** -- audio packets are too time-sensitive for retransmission to be useful.

### PLI (Picture Loss Indication)

Requests a new keyframe from the sender. The SFU sends PLI when:

- A receiver joins mid-stream and has no keyframe to start decoding.
- A spatial layer upgrade requires a keyframe.
- Sustained packet loss has corrupted the decoder state.
