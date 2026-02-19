"""Users API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.models.users import (
    BlockListResponse,
    DMSettingsResponse,
    FriendListResponse,
    PresenceResponse,
    UserResponse,
)

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class UsersAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def get(self, user_id: int) -> UserResponse:
        r = await self._http.get(f"/api/v1/users/{user_id}")
        return UserResponse.model_validate(r.json())

    async def update_profile(
        self,
        user_id: int,
        *,
        display_name: str | None = None,
        avatar: str | None = None,
        bio: str | None = None,
    ) -> UserResponse:
        payload: dict[str, Any] = {}
        if display_name is not None:
            payload["display_name"] = display_name
        if avatar is not None:
            payload["avatar"] = avatar
        if bio is not None:
            payload["bio"] = bio
        r = await self._http.patch(f"/api/v1/users/{user_id}", json=payload)
        return UserResponse.model_validate(r.json())

    async def get_presence(self, user_id: int) -> PresenceResponse:
        r = await self._http.get(f"/api/v1/users/{user_id}/presence")
        return PresenceResponse.model_validate(r.json())

    # --- Friends ---

    async def list_friends(self, user_id: int) -> FriendListResponse:
        r = await self._http.get(f"/api/v1/users/{user_id}/friends")
        return FriendListResponse.model_validate(r.json())

    async def add_friend(self, user_id: int, target_id: int) -> None:
        await self._http.put(f"/api/v1/users/{user_id}/friends/{target_id}")

    async def accept_friend(self, user_id: int, target_id: int) -> None:
        await self._http.post(f"/api/v1/users/{user_id}/friends/{target_id}/accept")

    async def reject_friend(self, user_id: int, target_id: int) -> None:
        await self._http.post(f"/api/v1/users/{user_id}/friends/{target_id}/reject")

    async def remove_friend(self, user_id: int, target_id: int) -> None:
        await self._http.delete(f"/api/v1/users/{user_id}/friends/{target_id}")

    # --- Blocks ---

    async def list_blocks(self, user_id: int) -> BlockListResponse:
        r = await self._http.get(f"/api/v1/users/{user_id}/blocks")
        return BlockListResponse.model_validate(r.json())

    async def block(self, user_id: int, target_id: int) -> None:
        await self._http.put(f"/api/v1/users/{user_id}/blocks/{target_id}")

    async def unblock(self, user_id: int, target_id: int) -> None:
        await self._http.delete(f"/api/v1/users/{user_id}/blocks/{target_id}")

    # --- DM Settings ---

    async def get_dm_settings(self, user_id: int) -> DMSettingsResponse:
        r = await self._http.get(f"/api/v1/users/{user_id}/dm-settings")
        return DMSettingsResponse.model_validate(r.json())

    async def update_dm_settings(self, user_id: int, dm_permission: str) -> DMSettingsResponse:
        r = await self._http.patch(
            f"/api/v1/users/{user_id}/dm-settings", json={"dm_permission": dm_permission}
        )
        return DMSettingsResponse.model_validate(r.json())
