from vox_sdk.models.base import VoxModel


class DMResponse(VoxModel):
    dm_id: int
    participant_ids: list[int] = []
    is_group: bool = False
    name: str | None = None
    icon: str | None = None


class DMListResponse(VoxModel):
    items: list[DMResponse] = []
    cursor: str | None = None
