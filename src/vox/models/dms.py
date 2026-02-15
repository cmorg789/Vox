from pydantic import BaseModel

from vox.models.base import VoxModel


class OpenDMRequest(BaseModel):
    recipient_id: int | None = None  # 1:1
    recipient_ids: list[int] | None = None  # group
    name: str | None = None  # group only


class DMResponse(VoxModel):
    dm_id: int
    participant_ids: list[int]
    is_group: bool
    name: str | None = None


class DMListResponse(VoxModel):
    items: list[DMResponse]
    cursor: str | None = None


class UpdateGroupDMRequest(BaseModel):
    name: str | None = None
    icon: str | None = None


class ReadReceiptRequest(BaseModel):
    up_to_msg_id: int
