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
MAX_CONNECTIONS_PER_IP = 10
MAX_SESSIONS_PER_USER = 5


@dataclass
class SessionState:
    user_id: int
    replay_buffer: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=SESSION_REPLAY_BUFFER_SIZE))
    seq: int = 0
    created_at: float = field(default_factory=time.monotonic)


_AUTH_FAIL_THRESHOLD = 10
_AUTH_FAIL_WINDOW = 60.0


class Hub:
    def __init__(self) -> None:
        # user_id -> set of active connections (supports multiple sessions)
        self.connections: dict[int, set[Connection]] = {}
        # session_id -> preserved session state for resume
        self.sessions: dict[str, SessionState] = {}
        # In-memory presence (RAM-only, never persisted to DB)
        self.presence: dict[int, dict[str, Any]] = {}
        # Lock for connection/presence state mutations
        self._lock = asyncio.Lock()
        # IP-based connection tracking
        self._ip_connections: dict[str, int] = {}
        # Auth failure tracking per IP
        self._auth_failures: dict[str, list[float]] = {}

    async def connect(self, conn: Connection, *, ip: str = "") -> str | None:
        """Register a connection. Returns None on success, or a rejection reason string."""
        from vox.config import config
        async with self._lock:
            # Enforce total connection limit
            total = sum(len(conns) for conns in self.connections.values())
            if total >= config.limits.max_total_connections:
                return "server_full"
            # Enforce per-IP limit
            if ip:
                current_ip = self._ip_connections.get(ip, 0)
                if current_ip >= MAX_CONNECTIONS_PER_IP:
                    return "rate_limited"
            # Enforce per-user session limit
            existing = self.connections.get(conn.user_id, set())
            if len(existing) >= MAX_SESSIONS_PER_USER:
                return "rate_limited"
            self.connections.setdefault(conn.user_id, set()).add(conn)
            if ip:
                self._ip_connections[ip] = self._ip_connections.get(ip, 0) + 1
        log.info("Hub: user %d connected (session %s)", conn.user_id, conn.session_id)
        return None

    async def disconnect(self, conn: Connection, *, ip: str = "") -> None:
        async with self._lock:
            conns = self.connections.get(conn.user_id)
            if conns:
                conns.discard(conn)
                if not conns:
                    del self.connections[conn.user_id]
            if ip and ip in self._ip_connections:
                self._ip_connections[ip] -= 1
                if self._ip_connections[ip] <= 0:
                    del self._ip_connections[ip]
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
            targets = {uid: set(conns) for uid, conns in self.connections.items()}
        else:
            targets = {uid: set(self.connections[uid]) for uid in user_ids if uid in self.connections}

        tasks = []
        for conns in targets.values():
            for conn in conns:
                tasks.append(conn.send_event(event))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_all(self, event: dict[str, Any]) -> None:
        """Send event to all connected users."""
        await self.broadcast(event, user_ids=None)

    def set_presence(self, user_id: int, data: dict[str, Any]) -> None:
        self.presence[user_id] = {"user_id": user_id, **data}

    def get_presence(self, user_id: int) -> dict[str, Any]:
        if user_id in self.connections and user_id in self.presence:
            return self.presence[user_id]
        return {"user_id": user_id, "status": "offline"}

    def clear_presence(self, user_id: int) -> None:
        self.presence.pop(user_id, None)

    def record_auth_failure(self, ip: str) -> None:
        now = time.monotonic()
        failures = self._auth_failures.setdefault(ip, [])
        failures.append(now)

    def is_auth_rate_limited(self, ip: str) -> bool:
        failures = self._auth_failures.get(ip)
        if not failures:
            return False
        now = time.monotonic()
        # Prune old entries
        cutoff = now - _AUTH_FAIL_WINDOW
        self._auth_failures[ip] = [t for t in failures if t > cutoff]
        return len(self._auth_failures[ip]) >= _AUTH_FAIL_THRESHOLD

    def cleanup_auth_failures(self) -> None:
        now = time.monotonic()
        cutoff = now - _AUTH_FAIL_WINDOW
        to_delete = []
        for ip, failures in self._auth_failures.items():
            self._auth_failures[ip] = [t for t in failures if t > cutoff]
            if not self._auth_failures[ip]:
                to_delete.append(ip)
        for ip in to_delete:
            del self._auth_failures[ip]

    def cleanup_orphaned_presence(self) -> None:
        """Remove presence entries for users with no active connections."""
        orphaned = [uid for uid in self.presence if uid not in self.connections]
        for uid in orphaned:
            del self.presence[uid]

    async def close_all(self, code: int, reason: str = "") -> None:
        """Send close frame to all connected clients (for graceful shutdown)."""
        tasks = []
        snapshot = {uid: set(conns) for uid, conns in self.connections.items()}
        for conns in snapshot.values():
            for conn in conns:
                tasks.append(conn.close(code, reason))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

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
