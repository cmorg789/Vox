"""Search API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.models.messages import SearchResponse

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class SearchAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def messages(self, **params: Any) -> SearchResponse:
        r = await self._http.get("/api/v1/messages/search", params=params)
        return SearchResponse.model_validate(r.json())
