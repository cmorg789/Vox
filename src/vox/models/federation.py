from pydantic import BaseModel, Field

from vox.limits import BAN_REASON_MAX, FEDERATION_ADDRESS_MAX
from vox.models.base import VoxModel


class RelayMessageRequest(BaseModel):
    model_config = {"populate_by_name": True}

    from_: str = Field(alias="from", max_length=FEDERATION_ADDRESS_MAX)
    to: str = Field(max_length=FEDERATION_ADDRESS_MAX)
    opaque_blob: str


class RelayTypingRequest(BaseModel):
    model_config = {"populate_by_name": True}

    from_: str = Field(alias="from", max_length=FEDERATION_ADDRESS_MAX)
    to: str = Field(max_length=FEDERATION_ADDRESS_MAX)


class RelayReadRequest(BaseModel):
    model_config = {"populate_by_name": True}

    from_: str = Field(alias="from", max_length=FEDERATION_ADDRESS_MAX)
    to: str = Field(max_length=FEDERATION_ADDRESS_MAX)
    up_to_msg_id: int


class FederatedDevicePrekey(VoxModel):
    device_id: str
    identity_key: str
    signed_prekey: str
    one_time_prekey: str | None = None


class FederatedPrekeyResponse(VoxModel):
    user_address: str
    devices: list[FederatedDevicePrekey]


class FederatedUserProfile(VoxModel):
    display_name: str
    avatar_url: str | None = None
    bio: str | None = None


class PresenceSubscribeRequest(BaseModel):
    user_address: str = Field(max_length=FEDERATION_ADDRESS_MAX)


class PresenceNotifyRequest(BaseModel):
    user_address: str = Field(max_length=FEDERATION_ADDRESS_MAX)
    status: str
    activity: str | None = None


class FederationJoinRequest(BaseModel):
    user_address: str = Field(max_length=FEDERATION_ADDRESS_MAX)
    invite_code: str | None = None
    voucher: str


class FederationJoinResponse(VoxModel):
    accepted: bool
    federation_token: str
    server_info: dict


class FederationBlockRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=BAN_REASON_MAX)
