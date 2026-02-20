from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from vox.config import str_limit
from vox.models.base import VoxModel


class RelayMessageRequest(BaseModel):
    model_config = {"populate_by_name": True}

    from_: Annotated[str, AfterValidator(str_limit(max_attr="federation_address_max"))] = Field(alias="from")
    to: Annotated[str, AfterValidator(str_limit(max_attr="federation_address_max"))]
    opaque_blob: str


class RelayTypingRequest(BaseModel):
    model_config = {"populate_by_name": True}

    from_: Annotated[str, AfterValidator(str_limit(max_attr="federation_address_max"))] = Field(alias="from")
    to: Annotated[str, AfterValidator(str_limit(max_attr="federation_address_max"))]


class RelayReadRequest(BaseModel):
    model_config = {"populate_by_name": True}

    from_: Annotated[str, AfterValidator(str_limit(max_attr="federation_address_max"))] = Field(alias="from")
    to: Annotated[str, AfterValidator(str_limit(max_attr="federation_address_max"))]
    up_to_msg_id: int


class FederatedDevicePrekey(VoxModel):
    device_id: str
    identity_key: str
    signed_prekey: str
    one_time_prekey: str | None = None


class FederatedPrekeyResponse(VoxModel):
    user_address: str
    devices: list[FederatedDevicePrekey]
    prekey_warning: str | None = None


class FederatedUserProfile(VoxModel):
    display_name: str
    avatar_url: str | None = None
    bio: str | None = None


class PresenceSubscribeRequest(BaseModel):
    user_address: Annotated[str, AfterValidator(str_limit(max_attr="federation_address_max"))]


class PresenceNotifyRequest(BaseModel):
    user_address: Annotated[str, AfterValidator(str_limit(max_attr="federation_address_max"))]
    status: str
    activity: str | None = None


class FederationJoinRequest(BaseModel):
    user_address: Annotated[str, AfterValidator(str_limit(max_attr="federation_address_max"))]
    invite_code: str | None = None
    voucher: str


class FederationJoinResponse(VoxModel):
    accepted: bool
    federation_token: str
    server_info: dict


class FederationBlockRequest(BaseModel):
    reason: Annotated[str, AfterValidator(str_limit(max_attr="ban_reason_max"))] | None = None


class FederationJoinClientRequest(BaseModel):
    target_domain: str
    invite_code: str | None = None


class AdminFederationBlockRequest(BaseModel):
    domain: str
    reason: str | None = None


class AdminFederationAllowRequest(BaseModel):
    domain: str
    reason: str | None = None


class FederationEntryResponse(VoxModel):
    domain: str
    reason: str | None
    created_at: str


class FederationEntryListResponse(VoxModel):
    items: list[FederationEntryResponse]
