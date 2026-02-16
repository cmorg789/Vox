from pydantic import BaseModel, Field

from vox.limits import (
    DISPLAY_NAME_MAX,
    MFA_CODE_MAX,
    MFA_TICKET_MAX,
    PASSWORD_MAX,
    PASSWORD_MIN,
    USERNAME_MAX,
    USERNAME_MIN,
    WEBAUTHN_FIELD_MAX,
)
from vox.models.base import VoxModel


# --- Register ---


class RegisterRequest(BaseModel):
    username: str = Field(min_length=USERNAME_MIN, max_length=USERNAME_MAX)
    password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)
    display_name: str | None = Field(default=None, max_length=DISPLAY_NAME_MAX)


class RegisterResponse(VoxModel):
    user_id: int
    token: str


# --- Login ---


class LoginRequest(BaseModel):
    username: str = Field(max_length=USERNAME_MAX)
    password: str = Field(max_length=PASSWORD_MAX)


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
    mfa_ticket: str = Field(max_length=MFA_TICKET_MAX)
    method: str  # totp, webauthn, recovery
    code: str | None = Field(default=None, max_length=MFA_CODE_MAX)
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
    code: str | None = Field(default=None, max_length=MFA_CODE_MAX)  # TOTP
    attestation: dict | None = None  # WebAuthn
    credential_name: str | None = None


class MFASetupConfirmResponse(VoxModel):
    success: bool
    recovery_codes: list[str]


class MFARemoveRequest(BaseModel):
    method: str
    code: str = Field(max_length=MFA_CODE_MAX)


# --- WebAuthn ---


class WebAuthnChallengeRequest(BaseModel):
    username: str = Field(max_length=USERNAME_MAX)


class WebAuthnChallengeResponse(VoxModel):
    challenge_id: str
    options: dict


class WebAuthnLoginRequest(BaseModel):
    username: str = Field(max_length=USERNAME_MAX)
    client_data_json: str = Field(max_length=WEBAUTHN_FIELD_MAX)
    authenticator_data: str = Field(max_length=WEBAUTHN_FIELD_MAX)
    signature: str = Field(max_length=WEBAUTHN_FIELD_MAX)
    credential_id: str = Field(max_length=WEBAUTHN_FIELD_MAX)
    user_handle: str | None = Field(default=None, max_length=WEBAUTHN_FIELD_MAX)


class WebAuthnCredentialResponse(VoxModel):
    credential_id: str
    name: str
    registered_at: int
    last_used_at: int | None


# --- Federation Token Login ---


class FederationTokenLoginRequest(BaseModel):
    federation_token: str
