from typing import Annotated

from pydantic import AfterValidator, BaseModel

from vox.config import str_limit
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
    prekey_warning: str | None = None


# --- Devices ---


class AddDeviceRequest(BaseModel):
    device_id: Annotated[str, AfterValidator(str_limit(max_attr="device_id_max"))]
    device_name: Annotated[str, AfterValidator(str_limit(max_attr="device_name_max"))]


class PairDeviceRequest(BaseModel):
    device_name: Annotated[str, AfterValidator(str_limit(max_attr="device_name_max"))]
    method: str  # cpace or qr
    temp_public_key: str | None = None  # QR method only


class PairDeviceResponse(VoxModel):
    pair_id: str


class PairRespondRequest(BaseModel):
    approved: bool


# --- Key Backup ---


class KeyBackupRequest(BaseModel):
    encrypted_blob: Annotated[str, AfterValidator(str_limit(max_attr="key_backup_max"))]  # base64


class DeviceInfo(VoxModel):
    device_id: str
    device_name: str
    created_at: int | None = None


class DeviceListResponse(VoxModel):
    devices: list[DeviceInfo]


class AddDeviceResponse(VoxModel):
    device_id: str


class KeyBackupResponse(VoxModel):
    encrypted_blob: str


# --- MLS Key Packages ---


class UploadMLSKeyPackagesRequest(BaseModel):
    key_packages: list[str]  # base64-encoded MLS KeyPackage bytes


class MLSKeyPackagesResponse(VoxModel):
    key_packages: list[str]  # base64-encoded MLS KeyPackage bytes
