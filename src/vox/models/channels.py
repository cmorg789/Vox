from pydantic import BaseModel, Field

from vox.limits import CHANNEL_NAME_MAX, CHANNEL_NAME_MIN, TOPIC_MAX
from vox.models.base import VoxModel


# --- Categories ---


class CreateCategoryRequest(BaseModel):
    name: str = Field(min_length=CHANNEL_NAME_MIN, max_length=CHANNEL_NAME_MAX)
    position: int


class UpdateCategoryRequest(BaseModel):
    name: str | None = Field(default=None, max_length=CHANNEL_NAME_MAX)
    position: int | None = None


class CategoryResponse(VoxModel):
    category_id: int
    name: str
    position: int


# --- Feeds ---


class CreateFeedRequest(BaseModel):
    name: str = Field(min_length=CHANNEL_NAME_MIN, max_length=CHANNEL_NAME_MAX)
    type: str  # text, forum, announcement
    category_id: int | None = None
    permission_overrides: list | None = None


class UpdateFeedRequest(BaseModel):
    name: str | None = Field(default=None, max_length=CHANNEL_NAME_MAX)
    topic: str | None = Field(default=None, max_length=TOPIC_MAX)


class FeedResponse(VoxModel):
    feed_id: int
    name: str
    type: str
    topic: str | None = None
    category_id: int | None = None
    permission_overrides: list = []


# --- Rooms ---


class CreateRoomRequest(BaseModel):
    name: str = Field(min_length=CHANNEL_NAME_MIN, max_length=CHANNEL_NAME_MAX)
    type: str  # voice, stage
    category_id: int | None = None
    permission_overrides: list | None = None


class UpdateRoomRequest(BaseModel):
    name: str | None = Field(default=None, max_length=CHANNEL_NAME_MAX)


class RoomResponse(VoxModel):
    room_id: int
    name: str
    type: str
    category_id: int | None = None


# --- Threads ---


class CreateThreadRequest(BaseModel):
    parent_msg_id: int
    name: str = Field(min_length=CHANNEL_NAME_MIN, max_length=CHANNEL_NAME_MAX)


class UpdateThreadRequest(BaseModel):
    name: str | None = Field(default=None, max_length=CHANNEL_NAME_MAX)
    archived: bool | None = None
    locked: bool | None = None


class ThreadResponse(VoxModel):
    thread_id: int
    parent_feed_id: int
    parent_msg_id: int
    name: str
    archived: bool
    locked: bool
