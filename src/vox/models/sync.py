from pydantic import BaseModel

from vox.models.base import VoxModel


class SyncRequest(BaseModel):
    since_timestamp: int
    categories: list[str]
    limit: int = 500
    after: int | None = None  # cursor: event ID


class SyncEvent(VoxModel):
    type: str
    payload: dict
    timestamp: int


class ReadState(VoxModel):
    feed_id: int | None = None
    dm_id: int | None = None
    last_read_msg_id: int


class SyncResponse(VoxModel):
    events: list[SyncEvent]
    server_timestamp: int
    cursor: int | None = None
    read_states: list[ReadState] = []
