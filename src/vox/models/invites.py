from pydantic import BaseModel

from vox.models.base import VoxModel


class CreateInviteRequest(BaseModel):
    feed_id: int | None = None
    max_uses: int | None = None
    max_age: int | None = None  # seconds


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
