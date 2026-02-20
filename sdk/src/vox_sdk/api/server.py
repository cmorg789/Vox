"""Server API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.models.server import GatewayInfoResponse, ServerInfoResponse, ServerLayoutResponse

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class ServerAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def info(self) -> ServerInfoResponse:
        r = await self._http.get("/api/v1/server")
        return ServerInfoResponse.model_validate(r.json())

    async def update(
        self,
        *,
        name: str | None = None,
        icon: str | None = None,
        description: str | None = None,
    ) -> ServerInfoResponse:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if icon is not None:
            payload["icon"] = icon
        if description is not None:
            payload["description"] = description
        r = await self._http.patch("/api/v1/server", json=payload)
        return ServerInfoResponse.model_validate(r.json())

    async def layout(self) -> ServerLayoutResponse:
        r = await self._http.get("/api/v1/server/layout")
        return ServerLayoutResponse.model_validate(r.json())

    async def gateway_info(self) -> GatewayInfoResponse:
        r = await self._http.get("/api/v1/gateway")
        return GatewayInfoResponse.model_validate(r.json())

    async def get_limits(self) -> dict:
        r = await self._http.get("/api/v1/server/limits")
        return r.json()

    async def update_limits(self, **limits: Any) -> dict:
        r = await self._http.patch("/api/v1/server/limits", json={"limits": limits})
        return r.json()
