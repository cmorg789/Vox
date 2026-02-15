"""Dispatch helper — called by REST routes to broadcast gateway events."""

from __future__ import annotations

from typing import Any

from vox.gateway.hub import get_hub


async def dispatch(event: dict[str, Any], user_ids: list[int] | None = None) -> None:
    """Broadcast a gateway event to connected users.

    Args:
        event: Event dict from gateway.events ({"type": ..., "d": {...}}).
        user_ids: Target user IDs. None = broadcast to all connected users.
    """
    hub = get_hub()
    await hub.broadcast(event, user_ids=user_ids)
