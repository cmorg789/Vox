from pydantic import BaseModel

from vox.models.base import VoxModel


class UserResponse(VoxModel):
    user_id: int
    display_name: str | None
    avatar: str | None
    bio: str | None
    roles: list[int]


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    avatar: str | None = None
    bio: str | None = None


class FriendResponse(VoxModel):
    user_id: int
    display_name: str | None
    avatar: str | None


class DMSettingsResponse(VoxModel):
    dm_permission: str  # everyone | friends_only | mutual_servers | nobody


class UpdateDMSettingsRequest(BaseModel):
    dm_permission: str
