"""In-memory pub/sub hub — tracks connected clients, routes events."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vox.gateway.connection import Connection

log = logging.getLogger(__name__)

_hub: Hub | None = None

SESSION_MAX_AGE_S = 300
SESSION_REPLAY_BUFFER_SIZE = 1000


@dataclass
class SessionState:
    user_id: int
    replay_buffer: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=SESSION_REPLAY_BUFFER_SIZE))
    seq: int = 0
    created_at: float = field(default_factory=time.monotonic)


class Hub:
    def __init__(self) -> None:
        # user_id -> set of active connections (supports multiple sessions)
        self.connections: dict[int, set[Connection]] = {}
        # session_id -> preserved session state for resume
        self.sessions: dict[str, SessionState] = {}

    def connect(self, conn: Connection) -> None:
        self.connections.setdefault(conn.user_id, set()).add(conn)
        log.info("Hub: user %d connected (session %s)", conn.user_id, conn.session_id)

    def disconnect(self, conn: Connection) -> None:
        conns = self.connections.get(conn.user_id)
        if conns:
            conns.discard(conn)
            if not conns:
                del self.connections[conn.user_id]
        log.info("Hub: user %d disconnected (session %s)", conn.user_id, conn.session_id)

    def save_session(self, session_id: str, state: SessionState) -> None:
        self.sessions[session_id] = state
        self.cleanup_sessions()

    def get_session(self, session_id: str) -> SessionState | None:
        state = self.sessions.get(session_id)
        if state is None:
            return None
        if time.monotonic() - state.created_at > SESSION_MAX_AGE_S:
            del self.sessions[session_id]
            return None
        return state

    def cleanup_sessions(self) -> None:
        now = time.monotonic()
        expired = [sid for sid, s in self.sessions.items() if now - s.created_at > SESSION_MAX_AGE_S]
        for sid in expired:
            del self.sessions[sid]

    async def broadcast(self, event: dict[str, Any], user_ids: list[int] | None = None) -> None:
        """Send event to specific users, or all connected users if user_ids is None."""
        if user_ids is None:
            targets = self.connections
        else:
            targets = {uid: self.connections[uid] for uid in user_ids if uid in self.connections}

        tasks = []
        for conns in targets.values():
            for conn in conns:
                tasks.append(conn.send_event(event))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_all(self, event: dict[str, Any]) -> None:
        """Send event to all connected users."""
        await self.broadcast(event, user_ids=None)

    @property
    def connected_user_ids(self) -> set[int]:
        return set(self.connections.keys())


def get_hub() -> Hub:
    global _hub
    if _hub is None:
        _hub = Hub()
    return _hub


def init_hub() -> Hub:
    global _hub
    _hub = Hub()
    return _hub
