from pydantic import BaseModel

from vox.models.base import VoxModel


# --- Register ---


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None


class RegisterResponse(VoxModel):
    user_id: int
    token: str


# --- Login ---


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(VoxModel):
    token: str
    user_id: int
    display_name: str | None
    roles: list[int]


class MFARequiredResponse(VoxModel):
    mfa_required: bool = True
    mfa_ticket: str
    available_methods: list[str]


# --- 2FA ---


class Login2FARequest(BaseModel):
    mfa_ticket: str
    method: str  # totp, webauthn, recovery
    code: str | None = None
    assertion: dict | None = None  # WebAuthn assertion object


class MFAStatusResponse(VoxModel):
    totp_enabled: bool
    webauthn_enabled: bool
    recovery_codes_left: int


class MFASetupRequest(BaseModel):
    method: str  # totp or webauthn


class MFASetupResponse(VoxModel):
    setup_id: str
    method: str
    totp_secret: str | None = None
    totp_uri: str | None = None
    creation_options: dict | None = None  # WebAuthn


class MFASetupConfirmRequest(BaseModel):
    setup_id: str
    code: str | None = None  # TOTP
    attestation: dict | None = None  # WebAuthn
    credential_name: str | None = None


class MFASetupConfirmResponse(VoxModel):
    success: bool
    recovery_codes: list[str]


class MFARemoveRequest(BaseModel):
    method: str
    code: str


# --- WebAuthn ---


class WebAuthnLoginRequest(BaseModel):
    username: str
    client_data_json: str
    authenticator_data: str
    signature: str
    credential_id: str
    user_handle: str | None = None


class WebAuthnCredentialResponse(VoxModel):
    credential_id: str
    name: str
    registered_at: int
    last_used_at: int | None
