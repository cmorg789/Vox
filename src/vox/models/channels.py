from pydantic import BaseModel

from vox.models.base import VoxModel


# --- Categories ---


class CreateCategoryRequest(BaseModel):
    name: str
    position: int


class UpdateCategoryRequest(BaseModel):
    name: str | None = None
    position: int | None = None


class CategoryResponse(VoxModel):
    category_id: int
    name: str
    position: int


# --- Feeds ---


class CreateFeedRequest(BaseModel):
    name: str
    type: str  # text, forum, announcement
    category_id: int | None = None
    permission_overrides: list | None = None


class UpdateFeedRequest(BaseModel):
    name: str | None = None
    topic: str | None = None


class FeedResponse(VoxModel):
    feed_id: int
    name: str
    type: str
    topic: str | None = None
    category_id: int | None = None
    permission_overrides: list = []


# --- Rooms ---


class CreateRoomRequest(BaseModel):
    name: str
    type: str  # voice, stage
    category_id: int | None = None
    permission_overrides: list | None = None


class UpdateRoomRequest(BaseModel):
    name: str | None = None


class RoomResponse(VoxModel):
    room_id: int
    name: str
    type: str
    category_id: int | None = None


# --- Threads ---


class CreateThreadRequest(BaseModel):
    parent_msg_id: int
    name: str


class UpdateThreadRequest(BaseModel):
    name: str | None = None
    archived: bool | None = None
    locked: bool | None = None


class ThreadResponse(VoxModel):
    thread_id: int
    parent_feed_id: int
    parent_msg_id: int
    name: str
    archived: bool
    locked: bool
