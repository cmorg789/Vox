from typing import Any

from vox_sdk.models.base import VoxModel


class SyncEvent(VoxModel):
    type: str
    payload: dict[str, Any] = {}
    timestamp: int = 0


class ReadState(VoxModel):
    feed_id: int | None = None
    dm_id: int | None = None
    last_read_msg_id: int = 0


class SyncResponse(VoxModel):
    events: list[SyncEvent] = []
    server_timestamp: int = 0
    cursor: int | None = None
    read_states: list[ReadState] = []
