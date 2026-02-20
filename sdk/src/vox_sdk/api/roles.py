"""Roles API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.models.members import MemberListResponse
from vox_sdk.models.roles import RoleListResponse, RoleResponse
from vox_sdk.pagination import PaginatedIterator

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class RolesAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def list(self) -> RoleListResponse:
        r = await self._http.get("/api/v1/roles")
        return RoleListResponse.model_validate(r.json())

    def iter_roles(self, *, limit: int = 50) -> PaginatedIterator[RoleResponse]:
        return PaginatedIterator(self._http, "/api/v1/roles", RoleResponse, limit=limit)

    async def list_members(self, role_id: int) -> MemberListResponse:
        r = await self._http.get(f"/api/v1/roles/{role_id}/members")
        return MemberListResponse.model_validate(r.json())

    async def create(
        self,
        name: str,
        *,
        color: int | None = None,
        permissions: int = 0,
        position: int = 0,
    ) -> RoleResponse:
        payload: dict[str, Any] = {
            "name": name,
            "permissions": permissions,
            "position": position,
        }
        if color is not None:
            payload["color"] = color
        r = await self._http.post("/api/v1/roles", json=payload)
        return RoleResponse.model_validate(r.json())

    async def update(
        self,
        role_id: int,
        *,
        name: str | None = None,
        color: int | None = None,
        permissions: int | None = None,
        position: int | None = None,
    ) -> RoleResponse:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if color is not None:
            payload["color"] = color
        if permissions is not None:
            payload["permissions"] = permissions
        if position is not None:
            payload["position"] = position
        r = await self._http.patch(f"/api/v1/roles/{role_id}", json=payload)
        return RoleResponse.model_validate(r.json())

    async def delete(self, role_id: int) -> None:
        await self._http.delete(f"/api/v1/roles/{role_id}")

    async def assign(self, user_id: int, role_id: int) -> None:
        await self._http.put(f"/api/v1/members/{user_id}/roles/{role_id}")

    async def revoke(self, user_id: int, role_id: int) -> None:
        await self._http.delete(f"/api/v1/members/{user_id}/roles/{role_id}")

    async def set_feed_override(
        self, feed_id: int, target_type: str, target_id: int, allow: int, deny: int
    ) -> None:
        await self._http.put(
            f"/api/v1/feeds/{feed_id}/permissions/{target_type}/{target_id}",
            json={"allow": allow, "deny": deny},
        )

    async def delete_feed_override(
        self, feed_id: int, target_type: str, target_id: int
    ) -> None:
        await self._http.delete(
            f"/api/v1/feeds/{feed_id}/permissions/{target_type}/{target_id}"
        )

    async def set_room_override(
        self, room_id: int, target_type: str, target_id: int, allow: int, deny: int
    ) -> None:
        await self._http.put(
            f"/api/v1/rooms/{room_id}/permissions/{target_type}/{target_id}",
            json={"allow": allow, "deny": deny},
        )

    async def delete_room_override(
        self, room_id: int, target_type: str, target_id: int
    ) -> None:
        await self._http.delete(
            f"/api/v1/rooms/{room_id}/permissions/{target_type}/{target_id}"
        )
