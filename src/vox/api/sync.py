import json
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db
from vox.db.models import EventLog, User
from vox.models.sync import SyncEvent, SyncRequest, SyncResponse

router = APIRouter(tags=["sync"])

CATEGORY_EVENTS: dict[str, set[str]] = {
    "members": {"member_join", "member_leave", "member_update", "member_ban", "member_unban"},
    "roles": {"role_create", "role_update", "role_delete", "role_assign", "role_revoke"},
    "feeds": {"feed_create", "feed_update", "feed_delete"},
    "rooms": {"room_create", "room_update", "room_delete"},
    "categories": {"category_create", "category_update", "category_delete"},
    "emoji": {"emoji_create", "emoji_delete", "sticker_create", "sticker_delete"},
    "bans": {"member_ban", "member_unban"},
    "invites": {"invite_create", "invite_delete"},
    "permissions": {"permission_override_update", "permission_override_delete"},
    "threads": {"thread_create", "thread_update", "thread_delete"},
    "webhooks": {"webhook_create", "webhook_update", "webhook_delete"},
    "bots": {"bot_commands_update", "bot_commands_delete"},
    "users": {"user_update"},
    "server": {"server_update"},
}

SYNC_RETENTION_MS = 7 * 24 * 60 * 60 * 1000  # 7 days


@router.post("/api/v1/sync")
async def sync(
    body: SyncRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SyncResponse:
    now_ms = int(time.time() * 1000)
    cutoff = now_ms - SYNC_RETENTION_MS

    if body.since_timestamp < cutoff:
        return SyncResponse(events=[], server_timestamp=now_ms)

    # Collect all event types for the requested categories
    event_types: set[str] = set()
    for cat in body.categories:
        types = CATEGORY_EVENTS.get(cat)
        if types is None:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "INVALID_CATEGORY", "message": f"Unknown sync category: {cat}"}},
            )
        event_types |= types

    if not event_types:
        return SyncResponse(events=[], server_timestamp=now_ms)

    stmt = (
        select(EventLog)
        .where(EventLog.timestamp >= body.since_timestamp, EventLog.event_type.in_(event_types))
        .order_by(EventLog.timestamp)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    events = [
        SyncEvent(type=row.event_type, payload=json.loads(row.payload), timestamp=row.timestamp)
        for row in rows
    ]

    return SyncResponse(events=events, server_timestamp=now_ms)
