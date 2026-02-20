from vox_sdk.models.base import VoxModel


class FederatedDevicePrekey(VoxModel):
    device_id: str
    identity_key: str
    signed_prekey: str
    one_time_prekey: str | None = None


class FederatedPrekeyResponse(VoxModel):
    user_address: str
    devices: list[FederatedDevicePrekey] = []


class FederatedUserProfile(VoxModel):
    display_name: str
    avatar_url: str | None = None
    bio: str | None = None


class FederationJoinResponse(VoxModel):
    accepted: bool
    federation_token: str
    server_info: dict = {}


class FederationEntryResponse(VoxModel):
    domain: str
    reason: str | None = None
    created_at: str = ""


class FederationEntryListResponse(VoxModel):
    items: list[FederationEntryResponse] = []
