from pydantic import BaseModel, Field

from vox.limits import BAN_DELETE_DAYS_MAX, BAN_REASON_MAX, KICK_REASON_MAX, NICKNAME_MAX
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
    nickname: str | None = Field(default=None, max_length=NICKNAME_MAX)


class KickRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=KICK_REASON_MAX)


class BanRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=BAN_REASON_MAX)
    delete_msg_days: int | None = Field(default=None, ge=0, le=BAN_DELETE_DAYS_MAX)


class BanResponse(VoxModel):
    user_id: int
    display_name: str | None
    reason: str | None
