"""Dispatch helper — called by REST routes to broadcast gateway events."""

from __future__ import annotations

import json
import time
from typing import Any

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
}


async def dispatch(event: dict[str, Any], user_ids: list[int] | None = None) -> None:
    """Broadcast a gateway event to connected users.

    Args:
        event: Event dict from gateway.events ({"type": ..., "d": {...}}).
        user_ids: Target user IDs. None = broadcast to all connected users.
    """
    hub = get_hub()
    await hub.broadcast(event, user_ids=user_ids)

    # Persist syncable events to DB for the sync endpoint
    event_type = event.get("type", "")
    if event_type in SYNCABLE_EVENTS:
        await _persist_event(event_type, event.get("d", {}))


async def _persist_event(event_type: str, data: dict[str, Any]) -> None:
    from vox.api.messages import _snowflake
    from vox.db.engine import get_session_factory
    from vox.db.models import EventLog

    factory = get_session_factory()
    async with factory() as session:
        entry = EventLog(
            id=await _snowflake(),
            event_type=event_type,
            payload=json.dumps(data),
            timestamp=int(time.time() * 1000),
        )
        session.add(entry)
        await session.commit()
