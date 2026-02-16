from typing import Annotated

from pydantic import AfterValidator, BaseModel

from vox.limits import list_limit, str_limit
from vox.models.base import VoxModel


class OpenDMRequest(BaseModel):
    recipient_id: int | None = None  # 1:1
    recipient_ids: Annotated[list[int], AfterValidator(list_limit(max_attr="group_dm_recipients_max"))] | None = None  # group
    name: Annotated[str, AfterValidator(str_limit(max_attr="dm_name_max"))] | None = None  # group only


class DMResponse(VoxModel):
    dm_id: int
    participant_ids: list[int]
    is_group: bool
    name: str | None = None


class DMListResponse(VoxModel):
    items: list[DMResponse]
    cursor: str | None = None


class UpdateGroupDMRequest(BaseModel):
    name: Annotated[str, AfterValidator(str_limit(max_attr="dm_name_max"))] | None = None
    icon: Annotated[str, AfterValidator(str_limit(max_attr="dm_icon_max"))] | None = None


class ReadReceiptRequest(BaseModel):
    up_to_msg_id: int
