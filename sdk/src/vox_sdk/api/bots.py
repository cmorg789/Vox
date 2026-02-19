"""Bots API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.models.bots import CommandListResponse, OkResponse

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class BotsAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def register_commands(
        self, user_id: int, commands: list[dict[str, Any]]
    ) -> OkResponse:
        r = await self._http.put(
            f"/api/v1/bots/{user_id}/commands", json={"commands": commands}
        )
        return OkResponse.model_validate(r.json())

    async def list_bot_commands(self, user_id: int) -> CommandListResponse:
        r = await self._http.get(f"/api/v1/bots/{user_id}/commands")
        return CommandListResponse.model_validate(r.json())

    async def deregister_commands(
        self, user_id: int, command_names: list[str]
    ) -> OkResponse:
        r = await self._http.delete(
            f"/api/v1/bots/{user_id}/commands", json={"command_names": command_names}
        )
        return OkResponse.model_validate(r.json())

    async def list_commands(self) -> CommandListResponse:
        r = await self._http.get("/api/v1/commands")
        return CommandListResponse.model_validate(r.json())

    async def respond_to_interaction(
        self,
        interaction_id: str,
        *,
        body: str | None = None,
        embeds: list[dict] | None = None,
        components: list[dict] | None = None,
        ephemeral: bool = False,
    ) -> None:
        payload: dict[str, Any] = {"ephemeral": ephemeral}
        if body is not None:
            payload["body"] = body
        if embeds is not None:
            payload["embeds"] = embeds
        if components is not None:
            payload["components"] = components
        await self._http.post(f"/api/v1/interactions/{interaction_id}/response", json=payload)

    async def component_interaction(self, msg_id: int, component_id: str) -> None:
        await self._http.post(
            "/api/v1/interactions/component",
            json={"msg_id": msg_id, "component_id": component_id},
        )
