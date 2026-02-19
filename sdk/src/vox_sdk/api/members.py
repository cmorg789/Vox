"""Members API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.models.members import BanListResponse, BanResponse, MemberListResponse, MemberResponse
from vox_sdk.pagination import PaginatedIterator

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class MembersAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def list(self, **params: Any) -> MemberListResponse:
        r = await self._http.get("/api/v1/members", params=params)
        return MemberListResponse.model_validate(r.json())

    def iter(self, *, limit: int = 50) -> PaginatedIterator[MemberResponse]:
        return PaginatedIterator(self._http, "/api/v1/members", MemberResponse, limit=limit)

    async def get(self, user_id: int) -> MemberResponse:
        r = await self._http.get(f"/api/v1/members/{user_id}")
        return MemberResponse.model_validate(r.json())

    async def join(self, invite_code: str) -> None:
        await self._http.post("/api/v1/members/join", json={"invite_code": invite_code})

    async def update(self, user_id: int, *, nickname: str | None = None) -> MemberResponse:
        payload: dict[str, Any] = {}
        if nickname is not None:
            payload["nickname"] = nickname
        r = await self._http.patch(f"/api/v1/members/{user_id}", json=payload)
        return MemberResponse.model_validate(r.json())

    async def remove(self, user_id: int, *, reason: str | None = None) -> None:
        payload: dict[str, Any] = {}
        if reason is not None:
            payload["reason"] = reason
        await self._http.delete(f"/api/v1/members/{user_id}", json=payload)

    async def ban(
        self, user_id: int, *, reason: str | None = None, delete_msg_days: int | None = None
    ) -> BanResponse:
        payload: dict[str, Any] = {}
        if reason is not None:
            payload["reason"] = reason
        if delete_msg_days is not None:
            payload["delete_msg_days"] = delete_msg_days
        r = await self._http.put(f"/api/v1/bans/{user_id}", json=payload)
        return BanResponse.model_validate(r.json())

    async def unban(self, user_id: int) -> None:
        await self._http.delete(f"/api/v1/bans/{user_id}")

    async def list_bans(self, **params: Any) -> BanListResponse:
        r = await self._http.get("/api/v1/bans", params=params)
        return BanListResponse.model_validate(r.json())
