"""Voice service — SFU lifecycle and voice state management."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from vox.db.models import Room, StageSpeaker, VoiceState
from vox.models.voice import VoiceMemberData

try:
    from vox_sfu import SFU
except ImportError:  # pragma: no cover
    SFU = None  # type: ignore[assignment,misc]

_sfu: SFU | None = None


def init_sfu(bind: str) -> None:
    global _sfu
    if SFU is None:
        raise RuntimeError("vox_sfu is not installed")
    if _sfu is not None:
        try:
            _sfu.stop()
        except Exception:
            pass
    from vox.config import config
    _sfu = SFU(bind, tls_cert=config.media.tls_cert, tls_key=config.media.tls_key)


def get_sfu() -> SFU:
    global _sfu
    if _sfu is None:
        if SFU is None:
            raise RuntimeError("vox_sfu is not installed")
        import os
        from vox.config import config
        bind = os.environ.get("VOX_MEDIA_BIND", "0.0.0.0:4443")
        _sfu = SFU(bind, tls_cert=config.media.tls_cert, tls_key=config.media.tls_key)
        _sfu.start()
    return _sfu


def stop_sfu() -> None:
    global _sfu
    if _sfu is not None:
        _sfu.stop()
        _sfu = None


def reset() -> None:
    """Reset SFU state — for tests."""
    global _sfu
    if _sfu is not None:
        try:
            _sfu.stop()
        except Exception:
            pass
    _sfu = None


# ---------------------------------------------------------------------------
# Voice state helpers
# ---------------------------------------------------------------------------

async def get_room_members(db: AsyncSession, room_id: int) -> list[VoiceMemberData]:
    result = await db.execute(select(VoiceState).where(VoiceState.room_id == room_id))
    rows = result.scalars().all()
    return [
        VoiceMemberData(
            user_id=vs.user_id,
            mute=vs.self_mute,
            deaf=vs.self_deaf,
            video=vs.video,
            streaming=vs.streaming,
            server_mute=vs.server_mute,
            server_deaf=vs.server_deaf,
            joined_at=int(vs.joined_at.timestamp()),
        )
        for vs in rows
    ]


async def join_room(
    db: AsyncSession,
    room_id: int,
    user_id: int,
    self_mute: bool = False,
    self_deaf: bool = False,
    flush_only: bool = False,
) -> tuple[str, list[VoiceMemberData]]:
    # Check not already in a voice room
    existing = await db.execute(select(VoiceState).where(VoiceState.user_id == user_id))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "ALREADY_IN_VOICE", "message": "Already connected to a voice room."}},
        )

    vs = VoiceState(
        user_id=user_id,
        room_id=room_id,
        self_mute=self_mute,
        self_deaf=self_deaf,
        video=False,
        streaming=False,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(vs)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "ALREADY_IN_VOICE", "message": "Already connected to a voice room."}},
        )

    # SFU integration
    sfu = get_sfu()
    try:
        sfu.add_room(room_id)
    except Exception:
        pass  # idempotent
    token = "media_" + secrets.token_urlsafe(32)
    sfu.admit_user(room_id, user_id, token)

    members = await get_room_members(db, room_id)
    if not flush_only:
        await db.commit()
    return token, members


async def leave_room(db: AsyncSession, room_id: int, user_id: int) -> None:
    await db.execute(delete(VoiceState).where(VoiceState.user_id == user_id, VoiceState.room_id == room_id))
    await db.execute(delete(StageSpeaker).where(StageSpeaker.user_id == user_id, StageSpeaker.room_id == room_id))
    await db.commit()

    sfu = get_sfu()
    try:
        sfu.remove_user(room_id, user_id)
    except Exception:
        pass
    # If room is now empty, remove from SFU
    try:
        if not sfu.get_room_users(room_id):
            sfu.remove_room(room_id)
    except Exception:
        pass


async def kick_user(db: AsyncSession, room_id: int, user_id: int) -> None:
    await leave_room(db, room_id, user_id)


async def move_user(
    db: AsyncSession,
    from_room_id: int,
    to_room_id: int,
    user_id: int,
    self_mute: bool = False,
    self_deaf: bool = False,
) -> tuple[str, list[VoiceMemberData]]:
    # Remove from old room - flush only, don't commit yet
    await db.execute(delete(VoiceState).where(VoiceState.user_id == user_id, VoiceState.room_id == from_room_id))
    await db.execute(delete(StageSpeaker).where(StageSpeaker.user_id == user_id, StageSpeaker.room_id == from_room_id))
    await db.flush()

    sfu = get_sfu()
    try:
        sfu.remove_user(from_room_id, user_id)
    except Exception:
        pass
    try:
        if not sfu.get_room_users(from_room_id):
            sfu.remove_room(from_room_id)
    except Exception:
        pass

    # Join new room with flush_only, then commit atomically
    token, members = await join_room(db, to_room_id, user_id, self_mute, self_deaf, flush_only=True)
    await db.commit()
    return token, members


async def refresh_media_token(db: AsyncSession, room_id: int, user_id: int) -> str:
    """Generate a new media token for a user already in a voice room."""
    result = await db.execute(
        select(VoiceState).where(VoiceState.user_id == user_id, VoiceState.room_id == room_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "NOT_IN_VOICE", "message": "Not in this voice room."}},
        )
    token = "media_" + secrets.token_urlsafe(32)
    sfu = get_sfu()
    sfu.admit_user(room_id, user_id, token)
    return token


async def get_media_url(db: AsyncSession) -> str:
    from vox.config import config
    return config.media.url
