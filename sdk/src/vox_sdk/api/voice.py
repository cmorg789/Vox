"""Voice API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vox_sdk.errors import VoxHTTPError
from vox_sdk.models.errors import ErrorCode
from vox_sdk.models.voice import (
    MediaCertResponse,
    MediaTokenResponse,
    StageTopicResponse,
    VoiceJoinResponse,
    VoiceMembersResponse,
)

if TYPE_CHECKING:
    from vox_sdk.http import HTTPClient


class VoiceAPI:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def get_media_cert(self) -> MediaCertResponse | None:
        """Fetch the SFU's TLS certificate for pinning.

        Returns ``None`` when the server uses a CA-signed certificate
        (404 / ``NO_CERT_PINNING``).
        """
        try:
            r = await self._http.get("/api/v1/voice/media-cert")
            return MediaCertResponse.model_validate(r.json())
        except VoxHTTPError as exc:
            if exc.status == 404 and exc.code == ErrorCode.NO_CERT_PINNING:
                return None
            raise

    async def get_members(self, room_id: int) -> VoiceMembersResponse:
        r = await self._http.get(f"/api/v1/rooms/{room_id}/voice")
        return VoiceMembersResponse.model_validate(r.json())

    async def join(
        self, room_id: int, *, self_mute: bool = False, self_deaf: bool = False
    ) -> VoiceJoinResponse:
        r = await self._http.post(
            f"/api/v1/rooms/{room_id}/voice/join",
            json={"self_mute": self_mute, "self_deaf": self_deaf},
        )
        return VoiceJoinResponse.model_validate(r.json())

    async def leave(self, room_id: int) -> None:
        await self._http.post(f"/api/v1/rooms/{room_id}/voice/leave")

    async def refresh_token(self, room_id: int) -> MediaTokenResponse:
        r = await self._http.post(f"/api/v1/rooms/{room_id}/voice/token-refresh")
        return MediaTokenResponse.model_validate(r.json())

    async def kick(self, room_id: int, user_id: int) -> None:
        await self._http.post(
            f"/api/v1/rooms/{room_id}/voice/kick", json={"user_id": user_id}
        )

    async def move(self, room_id: int, user_id: int, to_room_id: int) -> None:
        await self._http.post(
            f"/api/v1/rooms/{room_id}/voice/move",
            json={"user_id": user_id, "to_room_id": to_room_id},
        )

    async def server_mute(self, room_id: int, user_id: int, muted: bool) -> None:
        await self._http.post(
            f"/api/v1/rooms/{room_id}/voice/mute",
            json={"user_id": user_id, "muted": muted},
        )

    async def server_deafen(self, room_id: int, user_id: int, deafened: bool) -> None:
        await self._http.post(
            f"/api/v1/rooms/{room_id}/voice/deafen",
            json={"user_id": user_id, "deafened": deafened},
        )

    async def stage_request(self, room_id: int) -> None:
        await self._http.post(f"/api/v1/rooms/{room_id}/stage/request")

    async def stage_invite(self, room_id: int, user_id: int) -> None:
        await self._http.post(
            f"/api/v1/rooms/{room_id}/stage/invite", json={"user_id": user_id}
        )

    async def stage_respond(self, room_id: int, accepted: bool) -> None:
        await self._http.post(
            f"/api/v1/rooms/{room_id}/stage/invite/respond", json={"accepted": accepted}
        )

    async def stage_revoke(self, room_id: int, user_id: int) -> None:
        await self._http.post(
            f"/api/v1/rooms/{room_id}/stage/revoke", json={"user_id": user_id}
        )

    async def stage_set_topic(self, room_id: int, topic: str) -> StageTopicResponse:
        r = await self._http.patch(
            f"/api/v1/rooms/{room_id}/stage/topic", json={"topic": topic}
        )
        return StageTopicResponse.model_validate(r.json())
