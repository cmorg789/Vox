from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel

from vox.config import str_limit
from vox.models.base import VoxModel
from vox.models.enums import DMPermission


class UserResponse(VoxModel):
    user_id: int
    username: str
    display_name: str | None
    avatar: str | None
    bio: str | None
    roles: list[int]
    created_at: int
    federated: bool = False
    home_domain: str | None = None


class UpdateProfileRequest(BaseModel):
    display_name: Annotated[str, AfterValidator(str_limit(max_attr="display_name_max"))] | None = None
    avatar: Annotated[str, AfterValidator(str_limit(max_attr="avatar_max"))] | None = None
    bio: Annotated[str, AfterValidator(str_limit(max_attr="bio_max"))] | None = None


class FriendResponse(VoxModel):
    user_id: int
    display_name: str | None
    avatar: str | None
    status: str = "accepted"


class DMSettingsResponse(VoxModel):
    dm_permission: DMPermission


class PresenceResponse(VoxModel):
    user_id: int
    status: str
    custom_status: str | None = None
    activity: Any | None = None


class BlockListResponse(VoxModel):
    blocked_user_ids: list[int]


class FriendListResponse(VoxModel):
    items: list[FriendResponse]
    cursor: str | None = None


class UpdateDMSettingsRequest(BaseModel):
    dm_permission: DMPermission
