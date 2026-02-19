from vox_sdk.models.base import VoxModel


class RegisterResponse(VoxModel):
    user_id: int
    token: str


class LoginResponse(VoxModel):
    token: str
    user_id: int
    display_name: str | None = None
    roles: list[int] = []


class MFARequiredResponse(VoxModel):
    mfa_required: bool = True
    mfa_ticket: str
    available_methods: list[str] = []


class MFAStatusResponse(VoxModel):
    totp_enabled: bool
    webauthn_enabled: bool
    recovery_codes_left: int


class MFASetupResponse(VoxModel):
    setup_id: str
    method: str
    totp_secret: str | None = None
    totp_uri: str | None = None
    creation_options: dict | None = None


class MFASetupConfirmResponse(VoxModel):
    success: bool
    recovery_codes: list[str] = []


class WebAuthnChallengeResponse(VoxModel):
    challenge_id: str
    options: dict


class WebAuthnCredentialResponse(VoxModel):
    credential_id: str
    name: str
    registered_at: int
    last_used_at: int | None = None


class SessionInfo(VoxModel):
    session_id: int
    created_at: int
    expires_at: int


class SessionListResponse(VoxModel):
    sessions: list[SessionInfo] = []


class SuccessResponse(VoxModel):
    success: bool = True
