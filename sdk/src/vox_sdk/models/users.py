from typing import Any

from vox_sdk.models.base import VoxModel


class UserResponse(VoxModel):
    user_id: int
    username: str
    display_name: str | None = None
    avatar: str | None = None
    bio: str | None = None
    roles: list[int] = []
    created_at: int | None = None
    federated: bool = False
    home_domain: str | None = None


class FriendResponse(VoxModel):
    user_id: int
    display_name: str | None = None
    avatar: str | None = None
    status: str = "offline"


class FriendListResponse(VoxModel):
    items: list[FriendResponse] = []
    cursor: str | None = None


class DMSettingsResponse(VoxModel):
    dm_permission: str


class PresenceResponse(VoxModel):
    user_id: int
    status: str
    custom_status: str | None = None
    activity: Any = None


class BlockListResponse(VoxModel):
    blocked_user_ids: list[int] = []
