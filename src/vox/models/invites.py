from pydantic import BaseModel, Field

from vox.limits import INVITE_MAX_AGE_MAX, INVITE_MAX_USES_MAX
from vox.models.base import VoxModel


class CreateInviteRequest(BaseModel):
    feed_id: int | None = None
    max_uses: int | None = Field(default=None, ge=0, le=INVITE_MAX_USES_MAX)
    max_age: int | None = Field(default=None, ge=0, le=INVITE_MAX_AGE_MAX)  # seconds


class InviteResponse(VoxModel):
    code: str
    creator_id: int
    feed_id: int | None = None
    max_uses: int | None = None
    uses: int
    expires_at: int | None = None


class InvitePreviewResponse(VoxModel):
    code: str
    server_name: str
    server_icon: str | None = None
    member_count: int
