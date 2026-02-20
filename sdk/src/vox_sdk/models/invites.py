from vox_sdk.models.base import VoxModel


class InviteResponse(VoxModel):
    code: str
    creator_id: int
    feed_id: int | None = None
    max_uses: int | None = None
    uses: int = 0
    expires_at: int | None = None
    created_at: int | None = None


class InviteListResponse(VoxModel):
    items: list[InviteResponse] = []
    cursor: str | None = None


class InvitePreviewResponse(VoxModel):
    code: str
    server_name: str
    server_icon: str | None = None
