"""Webhooks API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.models.bots import Embed, WebhookListItem, WebhookListWrapper, WebhookResponse

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class WebhooksAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def create(
        self, feed_id: int, name: str, *, avatar: str | None = None
    ) -> WebhookResponse:
        payload: dict[str, Any] = {"name": name}
        if avatar is not None:
            payload["avatar"] = avatar
        r = await self._http.post(f"/api/v1/feeds/{feed_id}/webhooks", json=payload)
        return WebhookResponse.model_validate(r.json())

    async def list(self, feed_id: int) -> WebhookListWrapper:
        r = await self._http.get(f"/api/v1/feeds/{feed_id}/webhooks")
        return WebhookListWrapper.model_validate(r.json())

    async def get(self, webhook_id: int) -> WebhookListItem:
        r = await self._http.get(f"/api/v1/webhooks/{webhook_id}")
        return WebhookListItem.model_validate(r.json())

    async def update(
        self, webhook_id: int, *, name: str | None = None, avatar: str | None = None
    ) -> WebhookListItem:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if avatar is not None:
            payload["avatar"] = avatar
        r = await self._http.patch(f"/api/v1/webhooks/{webhook_id}", json=payload)
        return WebhookListItem.model_validate(r.json())

    async def delete(self, webhook_id: int) -> None:
        await self._http.delete(f"/api/v1/webhooks/{webhook_id}")

    async def execute(
        self,
        webhook_id: int,
        token: str,
        body: str,
        *,
        embeds: list[Embed] | None = None,
    ) -> None:
        payload: dict[str, Any] = {"body": body}
        if embeds is not None:
            payload["embeds"] = [e.model_dump() for e in embeds]
        await self._http.post(f"/api/v1/webhooks/{webhook_id}/{token}", json=payload)
