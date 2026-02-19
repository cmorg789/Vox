import json
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vox.api.deps import get_current_user, get_db
from vox.db.models import DMReadState, EventLog, FeedReadState, User
from vox.models.sync import ReadState, SyncEvent, SyncRequest, SyncResponse

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
    user: User = Depends(get_current_user),
) -> SyncResponse:
    now_ms = int(time.time() * 1000)
    cutoff = now_ms - SYNC_RETENTION_MS

    if body.since_timestamp < cutoff:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "FULL_SYNC_REQUIRED", "message": "Data older than 7 days requires a full refresh."}},
        )

    # Handle read_states as a special side-load category
    want_read_states = "read_states" in body.categories
    remaining_categories = [c for c in body.categories if c != "read_states"]

    # Collect all event types for the requested categories
    event_types: set[str] = set()
    for cat in remaining_categories:
        types = CATEGORY_EVENTS.get(cat)
        if types is None:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "INVALID_CATEGORY", "message": f"Unknown sync category: {cat}"}},
            )
        event_types |= types

    events: list[SyncEvent] = []
    cursor: int | None = None

    if event_types:
        from vox.config import limits
        limit = min(body.limit, limits.page_limit_messages)

        stmt = (
            select(EventLog)
            .where(EventLog.timestamp >= body.since_timestamp, EventLog.event_type.in_(event_types))
            .order_by(EventLog.id)
            .limit(limit)
        )
        if body.after is not None:
            stmt = stmt.where(EventLog.id > body.after)
        result = await db.execute(stmt)
        rows = result.scalars().all()

        events = [
            SyncEvent(type=row.event_type, payload=json.loads(row.payload), timestamp=row.timestamp)
            for row in rows
        ]
        cursor = rows[-1].id if rows else None

    # Side-load read states
    read_states: list[ReadState] = []
    if want_read_states:
        feed_rs = await db.execute(
            select(FeedReadState).where(FeedReadState.user_id == user.id)
        )
        for rs in feed_rs.scalars().all():
            read_states.append(ReadState(feed_id=rs.feed_id, last_read_msg_id=rs.last_read_msg_id))
        dm_rs = await db.execute(
            select(DMReadState).where(DMReadState.user_id == user.id)
        )
        for rs in dm_rs.scalars().all():
            read_states.append(ReadState(dm_id=rs.dm_id, last_read_msg_id=rs.last_read_msg_id))

    return SyncResponse(events=events, server_timestamp=now_ms, cursor=cursor, read_states=read_states)
