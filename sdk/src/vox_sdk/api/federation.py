"""Federation API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from vox_sdk.models.federation import (
    FederatedPrekeyResponse,
    FederatedUserProfile,
    FederationEntryListResponse,
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

    async def admin_unblock(self, domain: str) -> None:
        encoded = quote(domain, safe="")
        await self._http.delete(f"/api/v1/federation/admin/block/{encoded}")

    async def admin_block_list(
        self, *, limit: int = 100, offset: int = 0
    ) -> FederationEntryListResponse:
        r = await self._http.get(
            "/api/v1/federation/admin/block",
            params={"limit": limit, "offset": offset},
        )
        return FederationEntryListResponse.model_validate(r.json())

    async def admin_allow(self, domain: str, reason: str | None = None) -> None:
        payload: dict[str, Any] = {"domain": domain}
        if reason is not None:
            payload["reason"] = reason
        await self._http.post("/api/v1/federation/admin/allow", json=payload)

    async def admin_unallow(self, domain: str) -> None:
        encoded = quote(domain, safe="")
        await self._http.delete(f"/api/v1/federation/admin/allow/{encoded}")

    async def admin_allow_list(
        self, *, limit: int = 100, offset: int = 0
    ) -> FederationEntryListResponse:
        r = await self._http.get(
            "/api/v1/federation/admin/allow",
            params={"limit": limit, "offset": offset},
        )
        return FederationEntryListResponse.model_validate(r.json())
