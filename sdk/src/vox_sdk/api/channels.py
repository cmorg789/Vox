"""Channels API methods (feeds, rooms, categories, threads)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.models.channels import (
    CategoryListResponse,
    CategoryResponse,
    FeedResponse,
    RoomResponse,
    ThreadListResponse,
    ThreadResponse,
)

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class ChannelsAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    # --- Feeds ---

    async def get_feed(self, feed_id: int) -> FeedResponse:
        r = await self._http.get(f"/api/v1/feeds/{feed_id}")
        return FeedResponse.model_validate(r.json())

    async def create_feed(
        self,
        name: str,
        type: str = "text",
        *,
        category_id: int | None = None,
        permission_overrides: list[dict] | None = None,
    ) -> FeedResponse:
        payload: dict[str, Any] = {"name": name, "type": type}
        if category_id is not None:
            payload["category_id"] = category_id
        if permission_overrides is not None:
            payload["permission_overrides"] = permission_overrides
        r = await self._http.post("/api/v1/feeds", json=payload)
        return FeedResponse.model_validate(r.json())

    async def update_feed(
        self, feed_id: int, *, name: str | None = None, topic: str | None = None
    ) -> FeedResponse:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if topic is not None:
            payload["topic"] = topic
        r = await self._http.patch(f"/api/v1/feeds/{feed_id}", json=payload)
        return FeedResponse.model_validate(r.json())

    async def delete_feed(self, feed_id: int) -> None:
        await self._http.delete(f"/api/v1/feeds/{feed_id}")

    async def subscribe_feed(self, feed_id: int) -> None:
        await self._http.put(f"/api/v1/feeds/{feed_id}/subscribers")

    async def unsubscribe_feed(self, feed_id: int) -> None:
        await self._http.delete(f"/api/v1/feeds/{feed_id}/subscribers")

    # --- Rooms ---

    async def get_room(self, room_id: int) -> RoomResponse:
        r = await self._http.get(f"/api/v1/rooms/{room_id}")
        return RoomResponse.model_validate(r.json())

    async def create_room(
        self,
        name: str,
        type: str = "voice",
        *,
        category_id: int | None = None,
        permission_overrides: list[dict] | None = None,
    ) -> RoomResponse:
        payload: dict[str, Any] = {"name": name, "type": type}
        if category_id is not None:
            payload["category_id"] = category_id
        if permission_overrides is not None:
            payload["permission_overrides"] = permission_overrides
        r = await self._http.post("/api/v1/rooms", json=payload)
        return RoomResponse.model_validate(r.json())

    async def update_room(self, room_id: int, *, name: str | None = None) -> RoomResponse:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        r = await self._http.patch(f"/api/v1/rooms/{room_id}", json=payload)
        return RoomResponse.model_validate(r.json())

    async def delete_room(self, room_id: int) -> None:
        await self._http.delete(f"/api/v1/rooms/{room_id}")

    # --- Categories ---

    async def list_categories(self) -> CategoryListResponse:
        r = await self._http.get("/api/v1/categories")
        return CategoryListResponse.model_validate(r.json())

    async def get_category(self, category_id: int) -> CategoryResponse:
        r = await self._http.get(f"/api/v1/categories/{category_id}")
        return CategoryResponse.model_validate(r.json())

    async def create_category(self, name: str, position: int = 0) -> CategoryResponse:
        r = await self._http.post(
            "/api/v1/categories", json={"name": name, "position": position}
        )
        return CategoryResponse.model_validate(r.json())

    async def update_category(
        self, category_id: int, *, name: str | None = None, position: int | None = None
    ) -> CategoryResponse:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if position is not None:
            payload["position"] = position
        r = await self._http.patch(f"/api/v1/categories/{category_id}", json=payload)
        return CategoryResponse.model_validate(r.json())

    async def delete_category(self, category_id: int) -> None:
        await self._http.delete(f"/api/v1/categories/{category_id}")

    # --- Threads ---

    async def get_thread(self, thread_id: int) -> ThreadResponse:
        r = await self._http.get(f"/api/v1/threads/{thread_id}")
        return ThreadResponse.model_validate(r.json())

    async def list_threads(self, feed_id: int) -> ThreadListResponse:
        r = await self._http.get(f"/api/v1/feeds/{feed_id}/threads")
        return ThreadListResponse.model_validate(r.json())

    async def create_thread(
        self, feed_id: int, parent_msg_id: int, name: str
    ) -> ThreadResponse:
        r = await self._http.post(
            f"/api/v1/feeds/{feed_id}/threads",
            json={"parent_msg_id": parent_msg_id, "name": name},
        )
        return ThreadResponse.model_validate(r.json())

    async def update_thread(
        self,
        thread_id: int,
        *,
        name: str | None = None,
        archived: bool | None = None,
        locked: bool | None = None,
    ) -> ThreadResponse:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if archived is not None:
            payload["archived"] = archived
        if locked is not None:
            payload["locked"] = locked
        r = await self._http.patch(f"/api/v1/threads/{thread_id}", json=payload)
        return ThreadResponse.model_validate(r.json())

    async def delete_thread(self, thread_id: int) -> None:
        await self._http.delete(f"/api/v1/threads/{thread_id}")

    async def subscribe_thread(self, feed_id: int, thread_id: int) -> None:
        await self._http.put(f"/api/v1/feeds/{feed_id}/threads/{thread_id}/subscribers")

    async def unsubscribe_thread(self, feed_id: int, thread_id: int) -> None:
        await self._http.delete(f"/api/v1/feeds/{feed_id}/threads/{thread_id}/subscribers")
