from vox_sdk.models.base import VoxModel


class MemberResponse(VoxModel):
    user_id: int
    display_name: str | None = None
    avatar: str | None = None
    nickname: str | None = None
    role_ids: list[int] = []


class MemberListResponse(VoxModel):
    items: list[MemberResponse] = []
    cursor: str | None = None


class BanResponse(VoxModel):
    user_id: int
    display_name: str | None = None
    reason: str | None = None
    created_at: int | None = None


class BanListResponse(VoxModel):
    items: list[BanResponse] = []
    cursor: str | None = None
