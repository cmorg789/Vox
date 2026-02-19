from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel

from vox.config import str_limit
from vox.models.base import VoxModel


class PermissionOverrideInput(BaseModel):
    target_type: Literal["role", "user"]
    target_id: int
    allow: int
    deny: int


class PermissionOverrideOutput(VoxModel):
    target_type: str
    target_id: int
    allow: int
    deny: int


# --- Categories ---


class CreateCategoryRequest(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(min_attr="channel_name_min", max_attr="channel_name_max"))]
    position: int


class UpdateCategoryRequest(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(max_attr="channel_name_max"))] | None = None
    position: int | None = None


class CategoryResponse(VoxModel):
    category_id: int
    name: str
    position: int


# --- Feeds ---


class CreateFeedRequest(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(min_attr="channel_name_min", max_attr="channel_name_max"))]
    type: Literal["text", "forum", "announcement"]
    category_id: int | None = None
    permission_overrides: list[PermissionOverrideInput] | None = None


class UpdateFeedRequest(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(max_attr="channel_name_max"))] | None = None
    topic: Annotated[str, AfterValidator(str_limit(max_attr="topic_max"))] | None = None


class FeedResponse(VoxModel):
    feed_id: int
    name: str
    type: str
    topic: str | None = None
    category_id: int | None = None
    position: int = 0
    permission_overrides: list[PermissionOverrideOutput] = []


# --- Rooms ---


class CreateRoomRequest(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(min_attr="channel_name_min", max_attr="channel_name_max"))]
    type: Literal["voice", "stage"]
    category_id: int | None = None
    permission_overrides: list[PermissionOverrideInput] | None = None


class UpdateRoomRequest(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(max_attr="channel_name_max"))] | None = None


class RoomResponse(VoxModel):
    room_id: int
    name: str
    type: str
    category_id: int | None = None
    position: int = 0
    permission_overrides: list[PermissionOverrideOutput] = []


# --- Threads ---


class CreateThreadRequest(BaseModel):
    parent_msg_id: int
    name: Annotated[str, AfterValidator(str_limit(min_attr="channel_name_min", max_attr="channel_name_max"))]


class UpdateThreadRequest(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(max_attr="channel_name_max"))] | None = None
    archived: bool | None = None
    locked: bool | None = None


class ThreadResponse(VoxModel):
    thread_id: int
    parent_feed_id: int
    parent_msg_id: int
    name: str
    archived: bool
    locked: bool


class CategoryListResponse(VoxModel):
    items: list[CategoryResponse]


class ThreadListResponse(VoxModel):
    items: list[ThreadResponse]
    cursor: str | None = None
