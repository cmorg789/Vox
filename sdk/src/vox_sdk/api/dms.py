"""DMs API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.models.dms import DMListResponse, DMResponse
from vox_sdk.models.messages import EditMessageResponse, MessageListResponse, SendMessageResponse

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class DMsAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def open(
        self,
        *,
        recipient_id: int | None = None,
        recipient_ids: list[int] | None = None,
        name: str | None = None,
    ) -> DMResponse:
        payload: dict[str, Any] = {}
        if recipient_id is not None:
            payload["recipient_id"] = recipient_id
        if recipient_ids is not None:
            payload["recipient_ids"] = recipient_ids
        if name is not None:
            payload["name"] = name
        r = await self._http.post("/api/v1/dms", json=payload)
        return DMResponse.model_validate(r.json())

    async def list(self) -> DMListResponse:
        r = await self._http.get("/api/v1/dms")
        return DMListResponse.model_validate(r.json())

    async def close(self, dm_id: int) -> None:
        await self._http.delete(f"/api/v1/dms/{dm_id}")

    async def update(
        self, dm_id: int, *, name: str | None = None, icon: str | None = None
    ) -> DMResponse:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if icon is not None:
            payload["icon"] = icon
        r = await self._http.patch(f"/api/v1/dms/{dm_id}", json=payload)
        return DMResponse.model_validate(r.json())

    async def add_recipient(self, dm_id: int, user_id: int) -> None:
        await self._http.put(f"/api/v1/dms/{dm_id}/recipients/{user_id}")

    async def remove_recipient(self, dm_id: int, user_id: int) -> None:
        await self._http.delete(f"/api/v1/dms/{dm_id}/recipients/{user_id}")

    async def convert_to_group(self, dm_id: int) -> DMResponse:
        r = await self._http.post(f"/api/v1/dms/{dm_id}/convert-to-group")
        return DMResponse.model_validate(r.json())

    async def send_read_receipt(self, dm_id: int, up_to_msg_id: int) -> None:
        await self._http.post(
            f"/api/v1/dms/{dm_id}/read", json={"up_to_msg_id": up_to_msg_id}
        )

    # --- DM Messages ---

    async def send_message(
        self, dm_id: int, body: str | None = None, **kwargs: Any
    ) -> SendMessageResponse:
        payload: dict[str, Any] = {}
        if body is not None:
            payload["body"] = body
        payload.update(kwargs)
        r = await self._http.post(f"/api/v1/dms/{dm_id}/messages", json=payload)
        return SendMessageResponse.model_validate(r.json())

    async def list_messages(
        self, dm_id: int, *, before: int | None = None, limit: int = 50
    ) -> MessageListResponse:
        params: dict[str, Any] = {"limit": limit}
        if before is not None:
            params["before"] = before
        r = await self._http.get(f"/api/v1/dms/{dm_id}/messages", params=params)
        return MessageListResponse.model_validate(r.json())

    async def edit_message(self, dm_id: int, msg_id: int, body: str) -> EditMessageResponse:
        r = await self._http.patch(
            f"/api/v1/dms/{dm_id}/messages/{msg_id}", json={"body": body}
        )
        return EditMessageResponse.model_validate(r.json())

    async def delete_message(self, dm_id: int, msg_id: int) -> None:
        await self._http.delete(f"/api/v1/dms/{dm_id}/messages/{msg_id}")

    async def add_reaction(self, dm_id: int, msg_id: int, emoji: str) -> None:
        await self._http.put(f"/api/v1/dms/{dm_id}/messages/{msg_id}/reactions/{emoji}")

    async def remove_reaction(self, dm_id: int, msg_id: int, emoji: str) -> None:
        await self._http.delete(f"/api/v1/dms/{dm_id}/messages/{msg_id}/reactions/{emoji}")
