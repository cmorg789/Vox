"""Messages API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.models.messages import (
    EditMessageResponse,
    MessageListResponse,
    MessageResponse,
    ReactionListResponse,
    SendMessageResponse,
)

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class MessagesAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    # --- Feed messages ---

    async def list(
        self, feed_id: int, *, before: int | None = None, after: int | None = None, limit: int = 50
    ) -> MessageListResponse:
        params: dict[str, Any] = {"limit": limit}
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after
        r = await self._http.get(f"/api/v1/feeds/{feed_id}/messages", params=params)
        return MessageListResponse.model_validate(r.json())

    async def get(self, feed_id: int, msg_id: int) -> MessageResponse:
        r = await self._http.get(f"/api/v1/feeds/{feed_id}/messages/{msg_id}")
        return MessageResponse.model_validate(r.json())

    async def send(
        self,
        feed_id: int,
        body: str | None = None,
        *,
        reply_to: int | None = None,
        attachments: list[str] | None = None,
        mentions: list[int] | None = None,
        embed: str | None = None,
    ) -> SendMessageResponse:
        payload: dict[str, Any] = {}
        if body is not None:
            payload["body"] = body
        if reply_to is not None:
            payload["reply_to"] = reply_to
        if attachments is not None:
            payload["attachments"] = attachments
        if mentions is not None:
            payload["mentions"] = mentions
        if embed is not None:
            payload["embed"] = embed
        r = await self._http.post(f"/api/v1/feeds/{feed_id}/messages", json=payload)
        return SendMessageResponse.model_validate(r.json())

    async def edit(self, feed_id: int, msg_id: int, body: str) -> EditMessageResponse:
        r = await self._http.patch(
            f"/api/v1/feeds/{feed_id}/messages/{msg_id}", json={"body": body}
        )
        return EditMessageResponse.model_validate(r.json())

    async def delete(self, feed_id: int, msg_id: int) -> None:
        await self._http.delete(f"/api/v1/feeds/{feed_id}/messages/{msg_id}")

    async def bulk_delete(self, feed_id: int, msg_ids: list[int]) -> None:
        await self._http.post(
            f"/api/v1/feeds/{feed_id}/messages/bulk-delete", json={"msg_ids": msg_ids}
        )

    # --- Thread messages ---

    async def list_thread(
        self, feed_id: int, thread_id: int, *, before: int | None = None, limit: int = 50
    ) -> MessageListResponse:
        params: dict[str, Any] = {"limit": limit}
        if before is not None:
            params["before"] = before
        r = await self._http.get(
            f"/api/v1/feeds/{feed_id}/threads/{thread_id}/messages", params=params
        )
        return MessageListResponse.model_validate(r.json())

    async def send_thread(
        self, feed_id: int, thread_id: int, body: str | None = None, **kwargs: Any
    ) -> SendMessageResponse:
        payload: dict[str, Any] = {}
        if body is not None:
            payload["body"] = body
        payload.update(kwargs)
        r = await self._http.post(
            f"/api/v1/feeds/{feed_id}/threads/{thread_id}/messages", json=payload
        )
        return SendMessageResponse.model_validate(r.json())

    # --- Reactions ---

    async def list_reactions(self, feed_id: int, msg_id: int) -> ReactionListResponse:
        r = await self._http.get(f"/api/v1/feeds/{feed_id}/messages/{msg_id}/reactions")
        return ReactionListResponse.model_validate(r.json())

    async def add_reaction(self, feed_id: int, msg_id: int, emoji: str) -> None:
        await self._http.put(f"/api/v1/feeds/{feed_id}/messages/{msg_id}/reactions/{emoji}")

    async def remove_reaction(self, feed_id: int, msg_id: int, emoji: str) -> None:
        await self._http.delete(f"/api/v1/feeds/{feed_id}/messages/{msg_id}/reactions/{emoji}")

    # --- Pins ---

    async def pin(self, feed_id: int, msg_id: int) -> None:
        await self._http.put(f"/api/v1/feeds/{feed_id}/pins/{msg_id}")

    async def unpin(self, feed_id: int, msg_id: int) -> None:
        await self._http.delete(f"/api/v1/feeds/{feed_id}/pins/{msg_id}")

    async def list_pins(self, feed_id: int) -> MessageListResponse:
        r = await self._http.get(f"/api/v1/feeds/{feed_id}/pins")
        return MessageListResponse.model_validate(r.json())
