from typing import Annotated

from pydantic import AfterValidator, BaseModel

from vox.limits import int_limit
from vox.models.base import VoxModel


class CreateInviteRequest(BaseModel):
    feed_id: int | None = None
    max_uses: Annotated[int, AfterValidator(int_limit(ge=0, max_attr="invite_max_uses_max"))] | None = None
    max_age: Annotated[int, AfterValidator(int_limit(ge=0, max_attr="invite_max_age_max"))] | None = None  # seconds


class InviteResponse(VoxModel):
    code: str
    creator_id: int
    feed_id: int | None = None
    max_uses: int | None = None
    uses: int
    expires_at: int | None = None
    created_at: int | None = None


class InvitePreviewResponse(VoxModel):
    code: str
    server_name: str
    server_icon: str | None = None
    member_count: int
