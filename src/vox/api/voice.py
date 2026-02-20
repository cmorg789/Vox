import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db, require_permission
from vox.db.models import Room, StageSpeaker, StageInvite, User, VoiceState
from vox.gateway import events as gw
from vox.gateway.dispatch import dispatch
from vox.models.voice import (
    MediaTokenResponse,
    StageInviteRequest,
    StageInviteResponseRequest,
    StageRevokeRequest,
    StageTopicRequest,
    StageTopicResponse,
    VoiceJoinRequest,
    VoiceJoinResponse,
    VoiceKickRequest,
    VoiceMembersResponse,
    VoiceMoveRequest,
    VoiceServerDeafenRequest,
    VoiceServerMuteRequest,
)
from vox.permissions import CONNECT, DEAFEN_MEMBERS, MOVE_MEMBERS, MUTE_MEMBERS, SPEAK, STAGE_MODERATOR, has_permission, resolve_permissions
from vox.voice import service as voice_service

router = APIRouter(tags=["voice"])

_STAGE_INVITE_TTL = 300  # 5 minutes


async def _dispatch_voice_state(db: AsyncSession, room_id: int) -> None:
    members = await voice_service.get_room_members(db, room_id)
    evt = gw.voice_state_update(room_id=room_id, members=[m.model_dump() for m in members])
    await dispatch(evt, db=db)


@router.get("/api/v1/voice/media-cert")
async def get_media_cert(_: User = Depends(get_current_user)):
    """Return the SFU TLS certificate DER bytes for client pinning.

    Only returns data when the SFU is using a self-signed certificate.
    When using a CA-signed domain certificate, returns 404 — clients
    should verify via the standard CA chain instead.
    """
    import hashlib

    from vox.voice.service import get_sfu

    cert_der = bytes(get_sfu().get_cert_der())
    if not cert_der:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NO_CERT_PINNING", "message": "SFU is using a CA-signed certificate; no pinning required."}},
        )
    fingerprint = hashlib.sha256(cert_der).hexdigest()
    return {"fingerprint": f"sha256:{fingerprint}", "cert_der": list(cert_der)}


@router.get("/api/v1/rooms/{room_id}/voice")
async def get_voice_members(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> VoiceMembersResponse:
    members = await voice_service.get_room_members(db, room_id)
    return VoiceMembersResponse(room_id=room_id, members=members)


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

    # Enforce SPEAK permission
    perms = await resolve_permissions(db, user.id, space_type="room", space_id=room_id)
    if not has_permission(perms, SPEAK):
        raise HTTPException(status_code=403, detail={"error": {"code": "MISSING_PERMISSIONS", "message": "You lack the SPEAK permission for this room."}})

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


@router.post("/api/v1/rooms/{room_id}/voice/token-refresh")
async def refresh_media_token(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    token = await voice_service.refresh_media_token(db, room_id, user.id)
    await dispatch(gw.media_token_refresh(room_id=room_id, media_token=token), user_ids=[user.id], db=db)
    return MediaTokenResponse(media_token=token)


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


@router.post("/api/v1/rooms/{room_id}/voice/mute", status_code=204)
async def server_mute(
    room_id: int,
    body: VoiceServerMuteRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(MUTE_MEMBERS, space_type="room", space_id_param="room_id"),
):
    result = await db.execute(
        select(VoiceState).where(VoiceState.user_id == body.user_id, VoiceState.room_id == room_id)
    )
    vs = result.scalar_one_or_none()
    if vs is None:
        raise HTTPException(status_code=400, detail={"error": {"code": "NOT_IN_VOICE", "message": "Target user is not in this voice room."}})
    vs.server_mute = body.muted
    await db.commit()
    await _dispatch_voice_state(db, room_id)


@router.post("/api/v1/rooms/{room_id}/voice/deafen", status_code=204)
async def server_deafen(
    room_id: int,
    body: VoiceServerDeafenRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(DEAFEN_MEMBERS, space_type="room", space_id_param="room_id"),
):
    result = await db.execute(
        select(VoiceState).where(VoiceState.user_id == body.user_id, VoiceState.room_id == room_id)
    )
    vs = result.scalar_one_or_none()
    if vs is None:
        raise HTTPException(status_code=400, detail={"error": {"code": "NOT_IN_VOICE", "message": "Target user is not in this voice room."}})
    vs.server_deaf = body.deafened
    await db.commit()
    await _dispatch_voice_state(db, room_id)


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

    # Find moderators in the room to target the notification
    vs_result = await db.execute(select(VoiceState.user_id).where(VoiceState.room_id == room_id))
    room_user_ids = [row[0] for row in vs_result.all()]
    moderator_ids = []
    for uid in room_user_ids:
        perms = await resolve_permissions(db, uid, space_type="room", space_id=room_id)
        if has_permission(perms, STAGE_MODERATOR):
            moderator_ids.append(uid)

    evt = gw.stage_request(room_id=room_id, user_id=user.id)
    await dispatch(evt, user_ids=moderator_ids if moderator_ids else None, db=db)


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

    # Clean up stale invites
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    from datetime import timedelta
    await db.execute(
        delete(StageInvite).where(StageInvite.created_at < now - timedelta(seconds=_STAGE_INVITE_TTL))
    )

    # Upsert invite
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    stmt = sqlite_insert(StageInvite).values(
        room_id=room_id, user_id=body.user_id, created_at=now
    ).on_conflict_do_nothing()
    await db.execute(stmt)
    await db.commit()

    evt = gw.stage_invite(room_id=room_id, user_id=body.user_id)
    await dispatch(evt, user_ids=[body.user_id], db=db)


@router.post("/api/v1/rooms/{room_id}/stage/invite/respond", status_code=204)
async def stage_respond_to_invite(
    room_id: int,
    body: StageInviteResponseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(StageInvite).where(StageInvite.room_id == room_id, StageInvite.user_id == user.id)
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=400, detail={"error": {"code": "NO_PENDING_INVITE", "message": "You have not been invited to speak."}})

    # Check TTL
    from datetime import timedelta
    if invite.created_at + timedelta(seconds=_STAGE_INVITE_TTL) < datetime.now(tz=timezone.utc).replace(tzinfo=None):
        await db.delete(invite)
        await db.commit()
        raise HTTPException(status_code=400, detail={"error": {"code": "NO_PENDING_INVITE", "message": "Stage invite has expired."}})

    await db.delete(invite)

    if body.accepted:
        speaker = StageSpeaker(
            room_id=room_id,
            user_id=user.id,
            granted_at=datetime.now(tz=timezone.utc).replace(tzinfo=None),
        )
        db.add(speaker)
        await db.commit()
        await _dispatch_voice_state(db, room_id)
    else:
        await db.commit()
        evt = gw.stage_invite_decline(room_id=room_id, user_id=user.id)
        await dispatch(evt, db=db)


@router.post("/api/v1/rooms/{room_id}/stage/revoke", status_code=204)
async def stage_revoke_speaker(
    room_id: int,
    body: StageRevokeRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(STAGE_MODERATOR, space_type="room", space_id_param="room_id"),
):
    await db.execute(delete(StageSpeaker).where(StageSpeaker.room_id == room_id, StageSpeaker.user_id == body.user_id))
    await db.commit()
    evt = gw.stage_revoke(room_id=room_id, user_id=body.user_id)
    await dispatch(evt, db=db)


@router.patch("/api/v1/rooms/{room_id}/stage/topic")
async def stage_set_topic(
    room_id: int,
    body: StageTopicRequest,
    db: AsyncSession = Depends(get_db),
    _: User = require_permission(STAGE_MODERATOR, space_type="room", space_id_param="room_id"),
):
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if room is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Room not found."}})
    room.topic = body.topic
    await db.commit()
    evt = gw.stage_topic_update(room_id=room_id, topic=body.topic)
    await dispatch(evt, db=db)
    return StageTopicResponse(topic=body.topic)
