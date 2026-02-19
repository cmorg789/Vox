from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from vox.config import str_limit
from vox.models.base import VoxModel


# --- Register ---


class RegisterRequest(BaseModel):
    username: Annotated[str, AfterValidator(str_limit(min_attr="username_min", max_attr="username_max"))]
    password: Annotated[str, AfterValidator(str_limit(min_attr="password_min", max_attr="password_max"))]
    display_name: Annotated[str, AfterValidator(str_limit(max_attr="display_name_max"))] | None = None


class RegisterResponse(VoxModel):
    user_id: int
    token: str


# --- Login ---


class LoginRequest(BaseModel):
    username: Annotated[str, AfterValidator(str_limit(max_attr="username_max"))]
    password: Annotated[str, AfterValidator(str_limit(max_attr="password_max"))]


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
    mfa_ticket: Annotated[str, AfterValidator(str_limit(max_attr="mfa_ticket_max"))]
    method: str  # totp, webauthn, recovery
    code: Annotated[str, AfterValidator(str_limit(max_attr="mfa_code_max"))] | None = None
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
    code: Annotated[str, AfterValidator(str_limit(max_attr="mfa_code_max"))] | None = None  # TOTP
    attestation: dict | None = None  # WebAuthn
    credential_name: str | None = None


class MFASetupConfirmResponse(VoxModel):
    success: bool
    recovery_codes: list[str]


class MFARemoveRequest(BaseModel):
    method: str
    code: Annotated[str, AfterValidator(str_limit(max_attr="mfa_code_max"))] | None = None
    assertion: dict | None = None  # WebAuthn assertion object


# --- WebAuthn ---


class WebAuthnChallengeRequest(BaseModel):
    username: Annotated[str, AfterValidator(str_limit(max_attr="username_max"))]


class WebAuthnChallengeResponse(VoxModel):
    challenge_id: str
    options: dict


class WebAuthnLoginRequest(BaseModel):
    username: Annotated[str, AfterValidator(str_limit(max_attr="username_max"))]
    client_data_json: Annotated[str, AfterValidator(str_limit(max_attr="webauthn_field_max"))]
    authenticator_data: Annotated[str, AfterValidator(str_limit(max_attr="webauthn_field_max"))]
    signature: Annotated[str, AfterValidator(str_limit(max_attr="webauthn_field_max"))]
    credential_id: Annotated[str, AfterValidator(str_limit(max_attr="webauthn_field_max"))]
    user_handle: Annotated[str, AfterValidator(str_limit(max_attr="webauthn_field_max"))] | None = None


class WebAuthnCredentialResponse(VoxModel):
    credential_id: str
    name: str
    registered_at: int
    last_used_at: int | None


# --- Federation Token Login ---


class SessionInfo(VoxModel):
    session_id: int
    created_at: int
    expires_at: int


class SessionListResponse(VoxModel):
    sessions: list[SessionInfo]


class SuccessResponse(VoxModel):
    success: bool = True


class FederationTokenLoginRequest(BaseModel):
    federation_token: str
