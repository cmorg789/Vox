import secrets

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.db.models import User
from vox.permissions import CONNECT, MOVE_MEMBERS, STAGE_MODERATOR
from vox.models.voice import (
    StageInviteRequest,
    StageInviteResponseRequest,
    StageRevokeRequest,
    StageTopicRequest,
    VoiceJoinRequest,
    VoiceJoinResponse,
    VoiceKickRequest,
    VoiceMoveRequest,
)

router = APIRouter(tags=["voice"])


@router.post("/api/v1/rooms/{room_id}/voice/join")
async def join_voice(
    room_id: int,
    body: VoiceJoinRequest,
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(CONNECT, space_type="room", space_id_param="room_id"),
) -> VoiceJoinResponse:
    media_token = "media_" + secrets.token_urlsafe(32)
    return VoiceJoinResponse(media_url="quic://localhost:4443", media_token=media_token, members=[])


@router.post("/api/v1/rooms/{room_id}/voice/leave", status_code=204)
async def leave_voice(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # TODO: track voice state, remove from SFU
    pass


@router.post("/api/v1/rooms/{room_id}/voice/kick", status_code=204)
async def kick_from_voice(
    room_id: int,
    body: VoiceKickRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MOVE_MEMBERS, space_type="room", space_id_param="room_id"),
):
    pass


@router.post("/api/v1/rooms/{room_id}/voice/move", status_code=204)
async def move_to_room(
    room_id: int,
    body: VoiceMoveRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MOVE_MEMBERS, space_type="room", space_id_param="room_id"),
):
    pass


# --- Stage ---

@router.post("/api/v1/rooms/{room_id}/stage/request", status_code=204)
async def stage_request_to_speak(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # TODO: send stage_request event via gateway
    pass


@router.post("/api/v1/rooms/{room_id}/stage/invite", status_code=204)
async def stage_invite_to_speak(
    room_id: int,
    body: StageInviteRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(STAGE_MODERATOR, space_type="room", space_id_param="room_id"),
):
    pass


@router.post("/api/v1/rooms/{room_id}/stage/invite/respond", status_code=204)
async def stage_respond_to_invite(
    room_id: int,
    body: StageInviteResponseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pass


@router.post("/api/v1/rooms/{room_id}/stage/revoke", status_code=204)
async def stage_revoke_speaker(
    room_id: int,
    body: StageRevokeRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(STAGE_MODERATOR, space_type="room", space_id_param="room_id"),
):
    pass


@router.patch("/api/v1/rooms/{room_id}/stage/topic")
async def stage_set_topic(
    room_id: int,
    body: StageTopicRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    # TODO: store stage topic, broadcast via gateway
    return {"topic": body.topic}
