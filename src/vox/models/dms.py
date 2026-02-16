from pydantic import BaseModel, Field

from vox.limits import DM_ICON_MAX, DM_NAME_MAX, GROUP_DM_RECIPIENTS_MAX
from vox.models.base import VoxModel


class OpenDMRequest(BaseModel):
    recipient_id: int | None = None  # 1:1
    recipient_ids: list[int] | None = Field(default=None, max_length=GROUP_DM_RECIPIENTS_MAX)  # group
    name: str | None = Field(default=None, max_length=DM_NAME_MAX)  # group only


class DMResponse(VoxModel):
    dm_id: int
    participant_ids: list[int]
    is_group: bool
    name: str | None = None


class DMListResponse(VoxModel):
    items: list[DMResponse]
    cursor: str | None = None


class UpdateGroupDMRequest(BaseModel):
    name: str | None = Field(default=None, max_length=DM_NAME_MAX)
    icon: str | None = Field(default=None, max_length=DM_ICON_MAX)


class ReadReceiptRequest(BaseModel):
    up_to_msg_id: int
