from pydantic import BaseModel, Field

from vox.limits import DEVICE_ID_MAX, DEVICE_NAME_MAX, KEY_BACKUP_MAX
from vox.models.base import VoxModel


# --- Prekeys ---


class UploadPrekeysRequest(BaseModel):
    identity_key: str  # base64
    signed_prekey: str  # base64
    one_time_prekeys: list[str]  # base64 array


class DevicePrekey(VoxModel):
    device_id: str
    identity_key: str
    signed_prekey: str
    one_time_prekey: str | None = None


class PrekeyBundleResponse(VoxModel):
    user_id: int
    devices: list[DevicePrekey]


# --- Devices ---


class AddDeviceRequest(BaseModel):
    device_id: str = Field(max_length=DEVICE_ID_MAX)
    device_name: str = Field(max_length=DEVICE_NAME_MAX)


class PairDeviceRequest(BaseModel):
    device_name: str = Field(max_length=DEVICE_NAME_MAX)
    method: str  # cpace or qr
    temp_public_key: str | None = None  # QR method only


class PairDeviceResponse(VoxModel):
    pair_id: str


class PairRespondRequest(BaseModel):
    approved: bool


# --- Key Backup ---


class KeyBackupRequest(BaseModel):
    encrypted_blob: str = Field(max_length=KEY_BACKUP_MAX)  # base64


class KeyBackupResponse(VoxModel):
    encrypted_blob: str
