from vox_sdk.models.base import VoxModel


class PermissionOverrideOutput(VoxModel):
    target_type: str
    target_id: int
    allow: int
    deny: int


class CategoryResponse(VoxModel):
    category_id: int
    name: str
    position: int


class FeedResponse(VoxModel):
    feed_id: int
    name: str
    type: str
    topic: str | None = None
    category_id: int | None = None
    position: int = 0
    permission_overrides: list[PermissionOverrideOutput] = []


class RoomResponse(VoxModel):
    room_id: int
    name: str
    type: str
    category_id: int | None = None
    position: int = 0
    permission_overrides: list[PermissionOverrideOutput] = []


class ThreadResponse(VoxModel):
    thread_id: int
    parent_feed_id: int
    parent_msg_id: int
    name: str
    archived: bool = False
    locked: bool = False


class CategoryListResponse(VoxModel):
    items: list[CategoryResponse] = []


class ThreadListResponse(VoxModel):
    items: list[ThreadResponse] = []
    cursor: str | None = None
