# ID System

Vox uses two kinds of identifiers: **Snowflake IDs** for messages and
**Entity IDs** for everything else.

---

## Snowflake IDs (uint64) -- Messages

Message IDs are 64-bit unsigned integers generated using a Snowflake scheme.
They are monotonically increasing and encode a creation timestamp, making them
naturally sortable by time.

### Bit Layout

```
 63                                    22 21       12 11          0
+----------------------------------------+-----------+------------+
|          timestamp (42 bits)           | worker_id | sequence   |
|                                        | (10 bits) | (12 bits)  |
+----------------------------------------+-----------+------------+
```

| Field | Bits | Range | Description |
|---|---:|---|---|
| **timestamp** | 42 | 0 -- 4,398,046,511,103 | Milliseconds since the **Vox epoch** |
| **worker_id** | 10 | 0 -- 1,023 | Identifies the generating process / node |
| **sequence** | 12 | 0 -- 4,095 | Per-millisecond counter within a worker |

### Vox Epoch

The Vox epoch is **2025-01-01T00:00:00Z**, which corresponds to Unix
timestamp **1735689600000** milliseconds.

To extract a Unix timestamp from a Snowflake:

```python
VOX_EPOCH_MS = 1_735_689_600_000

def snowflake_to_unix_ms(snowflake: int) -> int:
    return (snowflake >> 22) + VOX_EPOCH_MS
```

### Properties

- **Time-sortable**: higher Snowflake = later message.
- **Unique**: the combination of timestamp + worker + sequence guarantees
  uniqueness across a distributed deployment.
- **Compact**: fits in a single 64-bit integer.

---

## Entity IDs (uint32)

All non-message entities use 32-bit unsigned integer IDs. These are simple
auto-incrementing identifiers scoped as described below.

| Entity | ID type | Scope |
|---|---|---|
| Users | uint32 | Global (unique across the server) |
| Feeds | uint32 | Global |
| DMs | uint32 | Global |
| Rooms | uint32 | Global |
| Threads | uint32 | Scoped to parent feed |
| Roles | uint32 | Global |

### Feed IDs vs DM IDs

Feeds and DMs occupy **separate ID spaces**. A feed and a DM may share the
same numeric ID without conflict. API endpoints and message payloads use
distinct fields (`feed_id` and `dm_id`) so the two are never ambiguous.

### Thread IDs

Thread IDs are scoped to their parent feed. Thread 1 in Feed A is a different
entity from Thread 1 in Feed B. The pair `(feed_id, thread_id)` uniquely
identifies a thread.

---

## Summary

| Kind | Width | Format | Used For |
|---|---|---|---|
| Snowflake | 64-bit | timestamp + worker + sequence | Messages |
| Entity ID | 32-bit | Auto-increment | Users, Feeds, DMs, Rooms, Threads, Roles |
