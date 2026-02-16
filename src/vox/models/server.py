from pydantic import BaseModel, Field

from vox.limits import SERVER_DESCRIPTION_MAX, SERVER_ICON_MAX, SERVER_NAME_MAX
from vox.models.base import VoxModel


class ServerInfoResponse(VoxModel):
    name: str
    icon: str | None
    description: str | None
    member_count: int


class UpdateServerRequest(BaseModel):
    name: str | None = Field(default=None, max_length=SERVER_NAME_MAX)
    icon: str | None = Field(default=None, max_length=SERVER_ICON_MAX)
    description: str | None = Field(default=None, max_length=SERVER_DESCRIPTION_MAX)


class PermissionOverrideData(VoxModel):
    target_type: str  # role or user
    target_id: int
    allow: int
    deny: int


class FeedInfo(VoxModel):
    feed_id: int
    name: str
    type: str
    topic: str | None = None
    category_id: int | None = None
    permission_overrides: list[PermissionOverrideData] = []


class RoomInfo(VoxModel):
    room_id: int
    name: str
    type: str
    category_id: int | None = None
    permission_overrides: list[PermissionOverrideData] = []


class CategoryInfo(VoxModel):
    category_id: int
    name: str
    position: int


class ServerLayoutResponse(VoxModel):
    categories: list[CategoryInfo]
    feeds: list[FeedInfo]
    rooms: list[RoomInfo]


# --- Gateway Info ---


class GatewayInfoResponse(VoxModel):
    url: str
    media_url: str
    protocol_version: int
    min_version: int
    max_version: int
