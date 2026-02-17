"""Dispatch helper — called by REST routes to broadcast gateway events."""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from vox.gateway.hub import get_hub

SYNCABLE_EVENTS: set[str] = {
    "member_join", "member_leave", "member_update", "member_ban", "member_unban",
    "role_create", "role_update", "role_delete", "role_assign", "role_revoke",
    "feed_create", "feed_update", "feed_delete",
    "room_create", "room_update", "room_delete",
    "category_create", "category_update", "category_delete",
    "emoji_create", "emoji_delete",
    "sticker_create", "sticker_delete",
    "invite_create", "invite_delete",
    "server_update",
    "permission_override_update", "permission_override_delete",
    "thread_create", "thread_update", "thread_delete",
    "webhook_create", "webhook_update", "webhook_delete",
    "bot_commands_update", "bot_commands_delete",
    "user_update",
}


async def dispatch(
    event: dict[str, Any],
    user_ids: list[int] | None = None,
    db: AsyncSession | None = None,
) -> None:
    """Broadcast a gateway event to connected users.

    Args:
        event: Event dict from gateway.events ({"type": ..., "d": {...}}).
        user_ids: Target user IDs. None = broadcast to all connected users.
        db: Optional existing DB session to reuse for event persistence.
    """
    hub = get_hub()
    await hub.broadcast(event, user_ids=user_ids)

    # Persist syncable events to DB for the sync endpoint
    event_type = event.get("type", "")
    if event_type in SYNCABLE_EVENTS:
        await _persist_event(event_type, event.get("d", {}), db=db)


async def _persist_event(
    event_type: str, data: dict[str, Any], db: AsyncSession | None = None
) -> None:
    from vox.api.messages import _snowflake
    from vox.db.models import EventLog

    entry = EventLog(
        id=await _snowflake(),
        event_type=event_type,
        payload=json.dumps(data),
        timestamp=int(time.time() * 1000),
    )

    if db is not None:
        db.add(entry)
        await db.commit()
    else:
        from vox.db.engine import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            session.add(entry)
            await session.commit()
