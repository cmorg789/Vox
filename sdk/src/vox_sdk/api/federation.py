"""Federation API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from vox_sdk.models.federation import (
    FederatedPrekeyResponse,
    FederatedUserProfile,
    FederationJoinResponse,
)

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class FederationAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def get_prekeys(self, user_address: str) -> FederatedPrekeyResponse:
        encoded = quote(user_address, safe="@")
        r = await self._http.get(f"/api/v1/federation/users/{encoded}/prekeys")
        return FederatedPrekeyResponse.model_validate(r.json())

    async def get_profile(self, user_address: str) -> FederatedUserProfile:
        encoded = quote(user_address, safe="@")
        r = await self._http.get(f"/api/v1/federation/users/{encoded}")
        return FederatedUserProfile.model_validate(r.json())

    async def join_request(
        self, target_domain: str, *, invite_code: str | None = None
    ) -> FederationJoinResponse:
        payload: dict[str, Any] = {"target_domain": target_domain}
        if invite_code is not None:
            payload["invite_code"] = invite_code
        r = await self._http.post("/api/v1/federation/join-request", json=payload)
        return FederationJoinResponse.model_validate(r.json())

    async def block(self, reason: str | None = None) -> None:
        payload: dict[str, Any] = {}
        if reason is not None:
            payload["reason"] = reason
        await self._http.post("/api/v1/federation/block", json=payload)

    async def admin_block(self, domain: str, reason: str | None = None) -> None:
        payload: dict[str, Any] = {"domain": domain}
        if reason is not None:
            payload["reason"] = reason
        await self._http.post("/api/v1/federation/admin/block", json=payload)
