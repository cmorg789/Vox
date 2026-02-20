"""Auth API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.models.auth import (
    LoginResponse,
    MFARequiredResponse,
    MFASetupConfirmResponse,
    MFASetupResponse,
    MFAStatusResponse,
    RegisterResponse,
    SessionListResponse,
    SuccessResponse,
    WebAuthnChallengeResponse,
    WebAuthnCredentialResponse,
)

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class AuthAPI:
    """Methods for /api/v1/auth endpoints."""

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def register(
        self, username: str, password: str, display_name: str | None = None
    ) -> RegisterResponse:
        payload: dict[str, Any] = {"username": username, "password": password}
        if display_name is not None:
            payload["display_name"] = display_name
        r = await self._http.post("/api/v1/auth/register", json=payload)
        return RegisterResponse.model_validate(r.json())

    async def login(self, username: str, password: str) -> LoginResponse | MFARequiredResponse:
        r = await self._http.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        data = r.json()
        if data.get("mfa_required"):
            return MFARequiredResponse.model_validate(data)
        return LoginResponse.model_validate(data)

    async def login_2fa(
        self,
        mfa_ticket: str,
        method: str,
        code: str | None = None,
        assertion: dict | None = None,
    ) -> LoginResponse:
        payload: dict[str, Any] = {"mfa_ticket": mfa_ticket, "method": method}
        if code is not None:
            payload["code"] = code
        if assertion is not None:
            payload["assertion"] = assertion
        r = await self._http.post("/api/v1/auth/login/2fa", json=payload)
        return LoginResponse.model_validate(r.json())

    async def login_webauthn_challenge(self, username: str) -> WebAuthnChallengeResponse:
        r = await self._http.post(
            "/api/v1/auth/login/webauthn/challenge", json={"username": username}
        )
        return WebAuthnChallengeResponse.model_validate(r.json())

    async def login_webauthn(
        self,
        username: str,
        challenge_id: str,
        client_data_json: str,
        authenticator_data: str,
        signature: str,
        credential_id: str,
        user_handle: str | None = None,
    ) -> LoginResponse:
        payload: dict[str, Any] = {
            "username": username,
            "challenge_id": challenge_id,
            "client_data_json": client_data_json,
            "authenticator_data": authenticator_data,
            "signature": signature,
            "credential_id": credential_id,
        }
        if user_handle is not None:
            payload["user_handle"] = user_handle
        r = await self._http.post("/api/v1/auth/login/webauthn", json=payload)
        return LoginResponse.model_validate(r.json())

    async def login_federation(self, federation_token: str) -> LoginResponse:
        r = await self._http.post(
            "/api/v1/auth/login/federation", json={"federation_token": federation_token}
        )
        return LoginResponse.model_validate(r.json())

    async def logout(self) -> None:
        await self._http.post("/api/v1/auth/logout")

    async def mfa_status(self) -> MFAStatusResponse:
        r = await self._http.get("/api/v1/auth/2fa")
        return MFAStatusResponse.model_validate(r.json())

    async def mfa_setup(self, method: str) -> MFASetupResponse:
        r = await self._http.post("/api/v1/auth/2fa/setup", json={"method": method})
        return MFASetupResponse.model_validate(r.json())

    async def mfa_setup_confirm(
        self,
        setup_id: str,
        code: str | None = None,
        attestation: dict | None = None,
        credential_name: str | None = None,
    ) -> MFASetupConfirmResponse:
        payload: dict[str, Any] = {"setup_id": setup_id}
        if code is not None:
            payload["code"] = code
        if attestation is not None:
            payload["attestation"] = attestation
        if credential_name is not None:
            payload["credential_name"] = credential_name
        r = await self._http.post("/api/v1/auth/2fa/setup/confirm", json=payload)
        return MFASetupConfirmResponse.model_validate(r.json())

    async def mfa_remove(
        self,
        method: str,
        code: str | None = None,
        assertion: dict | None = None,
    ) -> SuccessResponse:
        payload: dict[str, Any] = {"method": method}
        if code is not None:
            payload["code"] = code
        if assertion is not None:
            payload["assertion"] = assertion
        r = await self._http.delete("/api/v1/auth/2fa", json=payload)
        return SuccessResponse.model_validate(r.json())

    async def list_webauthn_credentials(self) -> list[WebAuthnCredentialResponse]:
        r = await self._http.get("/api/v1/auth/webauthn/credentials")
        return [WebAuthnCredentialResponse.model_validate(c) for c in r.json()]

    async def delete_webauthn_credential(self, credential_id: str) -> SuccessResponse:
        r = await self._http.delete(f"/api/v1/auth/webauthn/credentials/{credential_id}")
        return SuccessResponse.model_validate(r.json())

    async def list_sessions(self) -> SessionListResponse:
        r = await self._http.get("/api/v1/auth/sessions")
        return SessionListResponse.model_validate(r.json())

    async def revoke_session(self, session_id: int) -> None:
        await self._http.delete(f"/api/v1/auth/sessions/{session_id}")
