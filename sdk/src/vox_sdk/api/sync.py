"""Sync API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.models.sync import SyncResponse

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class SyncAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def sync(
        self,
        since_timestamp: int,
        categories: list[str] | None = None,
        *,
        limit: int = 100,
        after: int | None = None,
    ) -> SyncResponse:
        payload: dict[str, Any] = {
            "since_timestamp": since_timestamp,
            "categories": categories or [],
            "limit": limit,
        }
        if after is not None:
            payload["after"] = after
        r = await self._http.post("/api/v1/sync", json=payload)
        return SyncResponse.model_validate(r.json())
