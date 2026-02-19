from typing import Annotated

from pydantic import AfterValidator, BaseModel

from vox.config import str_limit
from vox.models.base import VoxModel


class ServerInfoResponse(VoxModel):
    name: str
    icon: str | None
    description: str | None
    member_count: int


class UpdateServerRequest(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(max_attr="server_name_max"))] | None = None
    icon: Annotated[str, AfterValidator(str_limit(max_attr="server_icon_max"))] | None = None
    description: Annotated[str, AfterValidator(str_limit(max_attr="server_description_max"))] | None = None


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
