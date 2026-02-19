from vox_sdk.models.base import VoxModel


class DevicePrekey(VoxModel):
    device_id: str
    identity_key: str
    signed_prekey: str
    one_time_prekey: str | None = None


class PrekeyBundleResponse(VoxModel):
    user_id: int
    devices: list[DevicePrekey] = []


class PairDeviceResponse(VoxModel):
    pair_id: str


class DeviceInfo(VoxModel):
    device_id: str
    device_name: str
    created_at: int | None = None


class DeviceListResponse(VoxModel):
    devices: list[DeviceInfo] = []


class AddDeviceResponse(VoxModel):
    device_id: str


class KeyBackupResponse(VoxModel):
    encrypted_blob: str
