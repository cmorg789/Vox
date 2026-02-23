from typing import Annotated

from pydantic import AfterValidator, BaseModel

from vox.config import int_limit, str_limit
from vox.models.base import VoxModel


class MemberResponse(VoxModel):
    user_id: int
    username: str
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
    nickname: Annotated[str, AfterValidator(str_limit(max_attr="nickname_max"))] | None = None


class KickRequest(BaseModel):
    reason: Annotated[str, AfterValidator(str_limit(max_attr="kick_reason_max"))] | None = None


class BanRequest(BaseModel):
    reason: Annotated[str, AfterValidator(str_limit(max_attr="ban_reason_max"))] | None = None
    delete_msg_days: Annotated[int, AfterValidator(int_limit(ge=0, max_attr="ban_delete_days_max"))] | None = None


class BanResponse(VoxModel):
    user_id: int
    display_name: str | None
    reason: str | None
    created_at: int | None = None


class BanListResponse(VoxModel):
    items: list[BanResponse]
    cursor: str | None = None
