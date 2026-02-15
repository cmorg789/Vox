from pydantic import BaseModel

from vox.models.base import VoxModel


class MemberResponse(VoxModel):
    user_id: int
    display_name: str | None
    avatar: str | None
    nickname: str | None
    role_ids: list[int]


class MemberListResponse(VoxModel):
    items: list[MemberResponse]
    cursor: str | None = None


class JoinRequest(BaseModel):
    invite_code: str


class UpdateMemberRequest(BaseModel):
    nickname: str | None = None


class KickRequest(BaseModel):
    reason: str | None = None


class BanRequest(BaseModel):
    reason: str | None = None
    delete_msg_days: int | None = None


class BanResponse(VoxModel):
    user_id: int
    display_name: str | None
    reason: str | None
