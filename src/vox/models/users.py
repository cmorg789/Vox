from pydantic import BaseModel, Field

from vox.limits import AVATAR_MAX, BIO_MAX, DISPLAY_NAME_MAX
from vox.models.base import VoxModel


class UserResponse(VoxModel):
    user_id: int
    display_name: str | None
    avatar: str | None
    bio: str | None
    roles: list[int]


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=DISPLAY_NAME_MAX)
    avatar: str | None = Field(default=None, max_length=AVATAR_MAX)
    bio: str | None = Field(default=None, max_length=BIO_MAX)


class FriendResponse(VoxModel):
    user_id: int
    display_name: str | None
    avatar: str | None


class DMSettingsResponse(VoxModel):
    dm_permission: str  # everyone | friends_only | mutual_servers | nobody


class UpdateDMSettingsRequest(BaseModel):
    dm_permission: str
