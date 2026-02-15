from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.db.models import Room, StageSpeaker, User, VoiceState
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
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
from vox.permissions import CONNECT, MOVE_MEMBERS, STAGE_MODERATOR
from vox.voice import service as voice_service

router = APIRouter(tags=["voice"])


async def _dispatch_voice_state(db: AsyncSession, room_id: int) -> None:
    members = await voice_service.get_room_members(db, room_id)
    evt = gw.voice_state_update(room_id=room_id, members=[m.model_dump() for m in members])
    await dispatch(evt)


@router.post("/api/v1/rooms/{room_id}/voice/join")
async def join_voice(
    room_id: int,
    body: VoiceJoinRequest,
    db: AsyncSession = Depends(get_db),
    user: User = require_permission(CONNECT, space_type="room", space_id_param="room_id"),
) -> VoiceJoinResponse:
    # Verify room exists
    result = await db.execute(select(Room).where(Room.id == room_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Room not found."}})

    token, members = await voice_service.join_room(db, room_id, user.id, body.self_mute, body.self_deaf)
    media_url = await voice_service.get_media_url(db)

    await _dispatch_voice_state(db, room_id)
    return VoiceJoinResponse(media_url=media_url, media_token=token, members=members)


@router.post("/api/v1/rooms/{room_id}/voice/leave", status_code=204)
async def leave_voice(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await voice_service.leave_room(db, room_id, user.id)
    await _dispatch_voice_state(db, room_id)


@router.post("/api/v1/rooms/{room_id}/voice/kick", status_code=204)
async def kick_from_voice(
    room_id: int,
    body: VoiceKickRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MOVE_MEMBERS, space_type="room", space_id_param="room_id"),
):
    await voice_service.kick_user(db, room_id, body.user_id)
    await _dispatch_voice_state(db, room_id)


@router.post("/api/v1/rooms/{room_id}/voice/move", status_code=204)
async def move_to_room(
    room_id: int,
    body: VoiceMoveRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MOVE_MEMBERS, space_type="room", space_id_param="room_id"),
):
    await voice_service.move_user(db, room_id, body.to_room_id, body.user_id)
    await _dispatch_voice_state(db, room_id)
    await _dispatch_voice_state(db, body.to_room_id)


# --- Stage ---

@router.post("/api/v1/rooms/{room_id}/stage/request", status_code=204)
async def stage_request_to_speak(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify user is in room
    result = await db.execute(
        select(VoiceState).where(VoiceState.user_id == user.id, VoiceState.room_id == room_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail={"error": {"code": "NOT_IN_VOICE", "message": "Not in this voice room."}})

    evt = gw.stage_request(room_id=room_id, user_id=user.id)
    await dispatch(evt)


@router.post("/api/v1/rooms/{room_id}/stage/invite", status_code=204)
async def stage_invite_to_speak(
    room_id: int,
    body: StageInviteRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(STAGE_MODERATOR, space_type="room", space_id_param="room_id"),
):
    # Verify target user is in room
    result = await db.execute(
        select(VoiceState).where(VoiceState.user_id == body.user_id, VoiceState.room_id == room_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail={"error": {"code": "NOT_IN_VOICE", "message": "Target user is not in this voice room."}})

    evt = gw.stage_invite(room_id=room_id, user_id=body.user_id)
    await dispatch(evt, user_ids=[body.user_id])


@router.post("/api/v1/rooms/{room_id}/stage/invite/respond", status_code=204)
async def stage_respond_to_invite(
    room_id: int,
    body: StageInviteResponseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if body.accepted:
        speaker = StageSpeaker(
            room_id=room_id,
            user_id=user.id,
            granted_at=datetime.now(timezone.utc),
        )
        db.add(speaker)
        await db.commit()
        await _dispatch_voice_state(db, room_id)
    else:
        evt = gw.stage_invite_decline(room_id=room_id, user_id=user.id)
        await dispatch(evt)


@router.post("/api/v1/rooms/{room_id}/stage/revoke", status_code=204)
async def stage_revoke_speaker(
    room_id: int,
    body: StageRevokeRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(STAGE_MODERATOR, space_type="room", space_id_param="room_id"),
):
    from sqlalchemy import delete
    await db.execute(delete(StageSpeaker).where(StageSpeaker.room_id == room_id, StageSpeaker.user_id == body.user_id))
    await db.commit()
    evt = gw.stage_revoke(room_id=room_id, user_id=body.user_id)
    await dispatch(evt)


@router.patch("/api/v1/rooms/{room_id}/stage/topic")
async def stage_set_topic(
    room_id: int,
    body: StageTopicRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if room is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Room not found."}})
    room.topic = body.topic
    await db.commit()
    evt = gw.stage_topic_update(room_id=room_id, topic=body.topic)
    await dispatch(evt)
    return {"topic": body.topic}
