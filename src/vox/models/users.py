from typing import Annotated

from pydantic import AfterValidator, BaseModel

from vox.limits import str_limit
from vox.models.base import VoxModel


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
    dm_permission: str  # everyone | friends_only | mutual_servers | nobody


class UpdateDMSettingsRequest(BaseModel):
    dm_permission: str
