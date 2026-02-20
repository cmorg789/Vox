"""Embeds API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING

from vox_sdk.models.bots import Embed

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class EmbedsAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def resolve(self, url: str) -> Embed:
        r = await self._http.post("/api/v1/embeds/resolve", json={"url": url})
        return Embed.model_validate(r.json())
