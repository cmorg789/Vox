"""Invites API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.models.invites import InviteListResponse, InvitePreviewResponse, InviteResponse
from vox_sdk.pagination import PaginatedIterator

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class InvitesAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def create(
        self,
        *,
        feed_id: int | None = None,
        max_uses: int | None = None,
        max_age: int | None = None,
    ) -> InviteResponse:
        payload: dict[str, Any] = {}
        if feed_id is not None:
            payload["feed_id"] = feed_id
        if max_uses is not None:
            payload["max_uses"] = max_uses
        if max_age is not None:
            payload["max_age"] = max_age
        r = await self._http.post("/api/v1/invites", json=payload)
        return InviteResponse.model_validate(r.json())

    async def delete(self, code: str) -> None:
        await self._http.delete(f"/api/v1/invites/{code}")

    async def resolve(self, code: str) -> InvitePreviewResponse:
        r = await self._http.get(f"/api/v1/invites/{code}")
        return InvitePreviewResponse.model_validate(r.json())

    async def list(self) -> InviteListResponse:
        r = await self._http.get("/api/v1/invites")
        return InviteListResponse.model_validate(r.json())

    def iter_invites(self, *, limit: int = 50) -> PaginatedIterator[InviteResponse]:
        return PaginatedIterator(self._http, "/api/v1/invites", InviteResponse, limit=limit)
