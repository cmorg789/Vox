"""WebSocket connection handler — manages one client lifecycle per the gateway spec."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from collections import deque
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from vox.auth.service import get_user_by_token
from vox.gateway import events
from vox.gateway.hub import Hub, SessionState

log = logging.getLogger(__name__)

# Strong references for fire-and-forget tasks to prevent GC
_background_tasks: set[asyncio.Task] = set()

try:
    import zstandard as zstd

    _zstd_compressor = zstd.ZstdCompressor(level=3)
except ImportError:  # pragma: no cover
    zstd = None  # type: ignore[assignment]
    _zstd_compressor = None  # type: ignore[assignment]

HEARTBEAT_INTERVAL_MS = 45_000
IDENTIFY_TIMEOUT_S = 30
HEARTBEAT_TIMEOUT_FACTOR = 1.5
REPLAY_BUFFER_SIZE = 1000

# Supported protocol version range
PROTOCOL_VERSION_MIN = 1
PROTOCOL_VERSION_MAX = 1

# Close codes per GATEWAY.md §7
CLOSE_UNKNOWN_ERROR = 4000
CLOSE_UNKNOWN_TYPE = 4001
CLOSE_DECODE_ERROR = 4002
CLOSE_NOT_AUTHENTICATED = 4003
CLOSE_AUTH_FAILED = 4004
CLOSE_ALREADY_AUTHENTICATED = 4005
CLOSE_RATE_LIMITED = 4006
CLOSE_SESSION_TIMEOUT = 4007
CLOSE_SERVER_RESTART = 4008
CLOSE_SESSION_EXPIRED = 4009
CLOSE_REPLAY_EXHAUSTED = 4010
CLOSE_VERSION_MISMATCH = 4011
CLOSE_SERVER_FULL = 4012

# MLS type -> event builder mapping
_MLS_EVENT_MAP = {
    "welcome": events.mls_welcome,
    "commit": events.mls_commit,
    "proposal": events.mls_proposal,
}

# CPace type -> event builder mapping
_CPACE_EVENT_MAP = {
    "isi": events.cpace_isi,
    "rsi": events.cpace_rsi,
    "confirm": events.cpace_confirm,
    "new_device_key": events.cpace_new_device_key,
}


class Connection:
    def __init__(self, ws: WebSocket, hub: Hub, compress: str | None = None) -> None:
        self.ws = ws
        self.hub = hub
        self.user_id: int = 0
        self.session_id: str = ""
        self.seq: int = 0
        self.protocol_version: int = 1
        self.last_heartbeat: float = 0.0
        self.capabilities: list[str] = []
        self.authenticated: bool = False
        self._replay_buffer: deque[dict[str, Any]] = deque(maxlen=REPLAY_BUFFER_SIZE)
        self._closed: bool = False
        self._compress = compress == "zstd" and _zstd_compressor is not None
        self._last_typing: dict[int, float] = {}  # feed_id/dm_id -> timestamp
        self._ip: str = ""
        self._msg_timestamps: deque[float] = deque(maxlen=120)
        self._send_lock = asyncio.Lock()

    async def _send_raw(self, data: dict[str, Any]) -> None:
        """Send data over WebSocket without locking — caller must hold _send_lock."""
        if not self._closed:
            try:
                if self._compress:
                    raw = json.dumps(data).encode()
                    await self.ws.send_bytes(_zstd_compressor.compress(raw))
                else:
                    await self.ws.send_json(data)
            except Exception:
                self._closed = True

    async def send_json(self, data: dict[str, Any]) -> None:
        async with self._send_lock:
            await self._send_raw(data)

    async def send_event(self, event: dict[str, Any]) -> None:
        """Send a sequenced event to this client."""
        async with self._send_lock:
            self.seq += 1
            msg = {**event, "seq": self.seq}
            self._replay_buffer.append(msg)
            # Also write to hub session buffer so resume works after disconnect
            session = self.hub.get_session(self.session_id)
            if session is not None:
                session.replay_buffer.append(msg)
                session.seq = self.seq
            await self._send_raw(msg)

    async def close(self, code: int, reason: str = "") -> None:
        self._closed = True
        try:
            await self.ws.close(code=code, reason=reason)
        except Exception:
            pass

    async def run(self, db_factory: Any) -> None:
        """Main connection lifecycle."""
        self._db_factory = db_factory
        try:
            await self.ws.accept()

            # Step 1: Send hello
            await self.send_json(events.hello(HEARTBEAT_INTERVAL_MS))

            # Step 2: Wait for identify or resume
            try:
                raw = await asyncio.wait_for(self.ws.receive_text(), timeout=IDENTIFY_TIMEOUT_S)
            except asyncio.TimeoutError:
                await self.close(CLOSE_NOT_AUTHENTICATED, "NOT_AUTHENTICATED")
                return
            except WebSocketDisconnect:
                return

            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                await self.close(CLOSE_DECODE_ERROR, "DECODE_ERROR")
                return

            msg_type = msg.get("type")
            data = msg.get("d", {}) or {}

            if msg_type == "identify":
                await self._handle_identify(data, db_factory)
            elif msg_type == "resume":
                await self._handle_resume(data, db_factory)
            else:
                await self.close(CLOSE_NOT_AUTHENTICATED, "NOT_AUTHENTICATED")
                return

            if not self.authenticated:
                return

            # Step 3: Enter message loop
            self.last_heartbeat = time.monotonic()
            heartbeat_task = asyncio.create_task(self._heartbeat_monitor())
            try:
                await self._message_loop(db_factory)
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

        except WebSocketDisconnect:
            pass
        except Exception:
            log.exception("Connection error for user %d", self.user_id)
            await self.close(CLOSE_UNKNOWN_ERROR, "UNKNOWN_ERROR")
        finally:
            if self.authenticated:
                # Clean up voice state on disconnect
                try:
                    await self._cleanup_voice_state(db_factory)
                except Exception:
                    log.debug("Voice cleanup skipped for user %d", self.user_id)
                # Preserve session state in hub for resume (keep original TTL)
                existing = self.hub.get_session(self.session_id)
                original_created_at = existing.created_at if existing else time.monotonic()
                state = SessionState(
                    user_id=self.user_id,
                    replay_buffer=deque(self._replay_buffer, maxlen=REPLAY_BUFFER_SIZE),
                    seq=self.seq,
                    created_at=original_created_at,
                )
                self.hub.save_session(self.session_id, state)
                # Disconnect and check presence in a single lock acquisition
                # to prevent a race where a new connection registers between
                # disconnect and the presence check.
                async with self.hub._lock:
                    conns = self.hub.connections.get(self.user_id)
                    if conns:
                        conns.discard(self)
                        if not conns:
                            del self.hub.connections[self.user_id]
                    if self._ip and self._ip in self.hub._ip_connections:
                        self.hub._ip_connections[self._ip] -= 1
                        if self.hub._ip_connections[self._ip] <= 0:
                            del self.hub._ip_connections[self._ip]
                    has_connections = self.user_id in self.hub.connections
                    if not has_connections:
                        self.hub.clear_presence(self.user_id)
                log.info("Hub: user %d disconnected (session %s)", self.user_id, self.session_id)
                if not has_connections:
                    await self.hub.broadcast(events.presence_update(user_id=self.user_id, status="offline"))

    async def _handle_identify(self, data: dict[str, Any], db_factory: Any) -> None:
        token = data.get("token", "")
        ip = self.ws.client.host if self.ws.client else ""

        # Check auth rate limiting by IP
        if ip and self.hub.is_auth_rate_limited(ip):
            await self.close(CLOSE_SERVER_RESTART, "AUTH_RATE_LIMITED")
            return

        if not token:
            if ip:
                self.hub.record_auth_failure(ip)
            await self.close(CLOSE_AUTH_FAILED, "AUTH_FAILED")
            return

        # Version negotiation
        protocol_version = data.get("protocol_version", 1)
        if not (PROTOCOL_VERSION_MIN <= protocol_version <= PROTOCOL_VERSION_MAX):
            await self.close(CLOSE_VERSION_MISMATCH, "VERSION_MISMATCH")
            return

        async with db_factory() as db:
            user, _sess = await get_user_by_token(db, token)
            if user is None:
                if ip:
                    self.hub.record_auth_failure(ip)
                await self.close(CLOSE_AUTH_FAILED, "AUTH_FAILED")
                return

        from vox.config import config
        server_name = config.server.name
        server_icon = config.server.icon

        self.user_id = user.id
        self.session_id = "sess_" + secrets.token_hex(12)
        self.protocol_version = protocol_version
        self.capabilities = data.get("capabilities", [])
        self._ip = self.ws.client.host if self.ws.client else ""
        self.authenticated = True
        rejection = await self.hub.connect(self, ip=self._ip)
        if rejection is not None:
            if rejection == "server_full":
                await self.close(CLOSE_SERVER_FULL, "SERVER_FULL")
            else:
                await self.close(CLOSE_RATE_LIMITED, "RATE_LIMITED")
            self.authenticated = False
            return

        # Register session in hub so send_event can write to it
        self.hub.save_session(self.session_id, SessionState(user_id=self.user_id))

        ready_event = events.ready(
            session_id=self.session_id,
            user_id=user.id,
            display_name=user.display_name or user.username,
            server_name=server_name,
            server_icon=server_icon,
            server_time=int(time.time()),
            protocol_version=protocol_version,
        )
        await self.send_event(ready_event)

        # Set initial presence and broadcast to other users
        self.hub.set_presence(self.user_id, {"status": "online"})
        other_ids = [uid for uid in self.hub.connections if uid != self.user_id]
        if other_ids:
            await self.hub.broadcast(events.presence_update(user_id=self.user_id, status="online"), user_ids=other_ids)

        # Send current presence snapshot to newly connected client (batched)
        async with self.hub._lock:
            presence_snapshot = dict(self.hub.presence)
        presence_events = []
        for uid, pdata in presence_snapshot.items():
            if uid != self.user_id:
                if pdata.get("status") == "invisible":
                    filtered = {**pdata, "status": "offline"}
                    presence_events.append(events.presence_update(**filtered))
                else:
                    presence_events.append(events.presence_update(**pdata))
        # Send in batches of 50 using gather
        for i in range(0, len(presence_events), 50):
            batch = presence_events[i:i + 50]
            await asyncio.gather(*(self.send_event(evt) for evt in batch))

    async def _handle_resume(self, data: dict[str, Any], db_factory: Any) -> None:
        token = data.get("token", "")
        session_id = data.get("session_id", "")
        last_seq = data.get("last_seq", 0)

        if not token or not session_id:
            await self.close(CLOSE_AUTH_FAILED, "AUTH_FAILED")
            return

        async with db_factory() as db:
            user, _sess = await get_user_by_token(db, token)

        if user is None:
            await self.close(CLOSE_AUTH_FAILED, "AUTH_FAILED")
            return

        # Look up session in hub
        session = self.hub.get_session(session_id)
        if session is None:
            await self.close(CLOSE_SESSION_EXPIRED, "SESSION_EXPIRED")
            return

        # Validate user matches
        if session.user_id != user.id:
            await self.close(CLOSE_AUTH_FAILED, "AUTH_FAILED")
            return

        # Check if last_seq is within replay buffer range
        if session.replay_buffer:
            oldest_seq = session.replay_buffer[0].get("seq", 0)
            if last_seq < oldest_seq:
                await self.close(CLOSE_REPLAY_EXHAUSTED, "REPLAY_EXHAUSTED")
                return

        self.user_id = user.id
        self.session_id = session_id
        self.seq = session.seq
        self._replay_buffer = deque(session.replay_buffer, maxlen=REPLAY_BUFFER_SIZE)
        self._ip = self.ws.client.host if self.ws.client else ""
        self.authenticated = True
        rejection = await self.hub.connect(self, ip=self._ip)
        if rejection is not None:
            if rejection == "server_full":
                await self.close(CLOSE_SERVER_FULL, "SERVER_FULL")
            else:
                await self.close(CLOSE_RATE_LIMITED, "RATE_LIMITED")
            self.authenticated = False
            return

        # Replay buffered events since last_seq
        for buffered in session.replay_buffer:
            if buffered.get("seq", 0) > last_seq:
                await self.send_json(buffered)

        # Refresh session timeout
        session.created_at = time.monotonic()

        # Send resumed confirmation (not sequenced — must not pollute replay buffer)
        await self.send_json(events.resumed(seq=self.seq))

    async def _heartbeat_monitor(self) -> None:
        timeout = HEARTBEAT_INTERVAL_MS / 1000 * HEARTBEAT_TIMEOUT_FACTOR
        while not self._closed:
            await asyncio.sleep(timeout)
            if time.monotonic() - self.last_heartbeat > timeout:
                await self.close(CLOSE_SESSION_TIMEOUT, "SESSION_TIMEOUT")
                return

    async def _message_loop(self, db_factory: Any) -> None:
        while not self._closed:
            try:
                raw = await self.ws.receive_text()
            except WebSocketDisconnect:
                return

            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                await self.close(CLOSE_DECODE_ERROR, "DECODE_ERROR")
                return

            # Rate limiting: max 120 messages per 60 seconds
            now = time.monotonic()
            self._msg_timestamps.append(now)
            # Prune entries older than 60 seconds
            while self._msg_timestamps and self._msg_timestamps[0] < now - 60:
                self._msg_timestamps.popleft()
            if len(self._msg_timestamps) > 120:
                await self.close(CLOSE_RATE_LIMITED, "RATE_LIMITED")
                return

            msg_type = msg.get("type")
            data = msg.get("d", {}) or {}

            if msg_type == "heartbeat":
                self.last_heartbeat = time.monotonic()
                await self.send_json(events.heartbeat_ack())

            elif msg_type == "identify":
                await self.close(CLOSE_ALREADY_AUTHENTICATED, "ALREADY_AUTHENTICATED")
                return

            elif msg_type == "typing":
                from vox.gateway.dispatch import dispatch
                feed_id = data.get("feed_id")
                dm_id = data.get("dm_id")
                channel_key = ("feed", feed_id) if feed_id is not None else ("dm", dm_id)
                now = time.monotonic()
                if now - self._last_typing.get(channel_key, 0) < 5.0:
                    continue
                self._last_typing[channel_key] = now
                evt = events.typing_start(user_id=self.user_id, feed_id=feed_id, dm_id=dm_id)
                await dispatch(evt)
                # Federated DM typing relay (fire-and-forget)
                if dm_id is not None:
                    task = asyncio.create_task(self._relay_federated_typing(db_factory, dm_id))
                    _background_tasks.add(task)
                    task.add_done_callback(_background_tasks.discard)

            elif msg_type == "presence_update":
                status = data.get("status", "online")
                if status not in ("online", "idle", "dnd", "invisible"):
                    await self.send_json({"type": "error", "d": {"code": "INVALID_STATUS", "message": "Status must be one of: online, idle, dnd, invisible."}})
                    continue
                custom_status = data.get("custom_status")
                activity = data.get("activity")
                presence_data: dict[str, Any] = {"status": status}
                from vox.config import config as _config
                if custom_status is not None:
                    if isinstance(custom_status, str):
                        custom_status = custom_status[:_config.limits.presence_custom_status_max]
                    presence_data["custom_status"] = custom_status
                if activity is not None:
                    if isinstance(activity, dict):
                        import json as _json
                        serialized = _json.dumps(activity)
                        if len(serialized) > _config.limits.presence_activity_max:
                            await self.send_json({"type": "error", "d": {"code": "PAYLOAD_TOO_LARGE", "message": "Activity payload exceeds size limit."}})
                            continue
                    presence_data["activity"] = activity
                self.hub.set_presence(self.user_id, presence_data)
                # If invisible, broadcast offline to others
                broadcast_status = "offline" if status == "invisible" else status
                broadcast_data = {**presence_data, "status": broadcast_status}
                other_ids = [uid for uid in self.hub.connections if uid != self.user_id]
                if other_ids:
                    await self.hub.broadcast(events.presence_update(user_id=self.user_id, **broadcast_data), user_ids=other_ids)
                # Federated presence notification (fire-and-forget)
                task = asyncio.create_task(self._notify_federated_presence(db_factory, broadcast_status, activity))
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)

            elif msg_type == "voice_state_update":
                from vox.gateway.dispatch import dispatch
                await self._handle_voice_state_update(data, db_factory)

            elif msg_type == "mls_relay":
                mls_type = data.get("mls_type", "")
                mls_data = data.get("data", "")
                from vox.config import config as _config
                if len(mls_data) > _config.limits.relay_payload_max:
                    await self.send_json({"type": "error", "d": {"code": "PAYLOAD_TOO_LARGE", "message": "Relay payload exceeds size limit."}})
                    continue
                builder = _MLS_EVENT_MAP.get(mls_type)
                if builder:
                    evt = builder(data=mls_data)
                    # Same-user device relay
                    await self.hub.broadcast(evt, user_ids=[self.user_id])

            elif msg_type == "cpace_relay":
                cpace_type = data.get("cpace_type", "")
                pair_id = data.get("pair_id", "")
                cpace_data = data.get("data", "")
                from vox.config import config as _config
                if len(cpace_data) > _config.limits.relay_payload_max:
                    await self.send_json({"type": "error", "d": {"code": "PAYLOAD_TOO_LARGE", "message": "Relay payload exceeds size limit."}})
                    continue
                builder = _CPACE_EVENT_MAP.get(cpace_type)
                if builder:
                    if cpace_type == "new_device_key":
                        nonce = data.get("nonce", "")
                        evt = builder(pair_id=pair_id, data=cpace_data, nonce=nonce)
                    else:
                        evt = builder(pair_id=pair_id, data=cpace_data)
                    # Same-user device relay
                    await self.hub.broadcast(evt, user_ids=[self.user_id])

            elif msg_type == "voice_codec_neg":
                media_type = data.get("media_type", "")
                codec = data.get("codec", "")
                room_id = data.get("room_id")
                if room_id is None:
                    await self.send_json({"type": "error", "d": {"code": "MISSING_ROOM_ID", "message": "room_id is required for voice_codec_neg."}})
                    continue
                params = {k: v for k, v in data.items() if k not in ("media_type", "codec", "room_id")}
                evt = events.voice_codec_neg(media_type=media_type, codec=codec, **params)
                room_user_ids = await self._get_voice_room_users(room_id, db_factory)
                await self.hub.broadcast(evt, user_ids=room_user_ids)

            elif msg_type == "stage_response":
                room_id = data.get("room_id")
                if room_id is None:
                    await self.send_json({"type": "error", "d": {"code": "MISSING_ROOM_ID", "message": "room_id is required for stage_response."}})
                    continue
                stage_data = {k: v for k, v in data.items() if k != "room_id"}
                evt = events.stage_response(user_id=self.user_id, **stage_data)
                room_user_ids = await self._get_voice_room_users(room_id, db_factory)
                await self.hub.broadcast(evt, user_ids=room_user_ids)

            # Unknown types are silently ignored per spec tolerance

    async def _relay_federated_typing(self, db_factory: Any, dm_id: int) -> None:
        try:
            from vox.db.models import User, dm_participants
            from vox.federation.client import relay_typing
            from vox.federation.service import get_our_domain
            from sqlalchemy import select as _select
            async with db_factory() as _db:
                our_domain = await get_our_domain(_db)
                if our_domain:
                    # Hoist user lookup above the loop
                    local_user = (await _db.execute(_select(User).where(User.id == self.user_id))).scalar_one_or_none()
                    if local_user is None:
                        return
                    from_addr = f"{local_user.username}@{our_domain}"
                    parts = await _db.execute(
                        _select(User).join(dm_participants, dm_participants.c.user_id == User.id)
                        .where(dm_participants.c.dm_id == dm_id, User.federated == True)
                    )
                    for fed_user in parts.scalars().all():
                        if fed_user.home_domain:
                            await relay_typing(_db, from_addr, fed_user.username)
        except Exception:
            pass  # Fire-and-forget

    async def _notify_federated_presence(self, db_factory: Any, status: str, activity: Any) -> None:
        try:
            from vox.federation.service import get_our_domain, get_presence_subscribers
            from vox.federation.client import notify_presence
            from vox.db.models import User
            from sqlalchemy import select as _select
            async with db_factory() as _db:
                our_domain = await get_our_domain(_db)
                if our_domain:
                    local_user = (await _db.execute(_select(User).where(User.id == self.user_id))).scalar_one_or_none()
                    if local_user:
                        user_address = f"{local_user.username}@{our_domain}"
                        domains = await get_presence_subscribers(_db, user_address)
                        for domain in domains:
                            await notify_presence(_db, domain, user_address, status, activity=activity)
        except Exception:
            pass  # Fire-and-forget

    async def _get_voice_room_users(self, room_id: int, db_factory: Any) -> list[int]:
        from vox.db.models import VoiceState
        from sqlalchemy import select
        async with db_factory() as db:
            result = await db.execute(select(VoiceState.user_id).where(VoiceState.room_id == room_id))
            return [row[0] for row in result.all()]

    async def _handle_voice_state_update(self, data: dict[str, Any], db_factory: Any) -> None:
        from vox.gateway.dispatch import dispatch
        from vox.db.models import VoiceState
        from vox.voice.service import get_room_members
        from vox.permissions import VIDEO, STREAM, has_permission, resolve_permissions
        from sqlalchemy import select

        async with db_factory() as db:
            result = await db.execute(select(VoiceState).where(VoiceState.user_id == self.user_id))
            vs = result.scalar_one_or_none()
            if vs is None:
                return

            if "self_mute" in data:
                vs.self_mute = data["self_mute"]
            if "self_deaf" in data:
                vs.self_deaf = data["self_deaf"]
            if "video" in data:
                if data["video"]:
                    perms = await resolve_permissions(db, self.user_id, space_type="room", space_id=vs.room_id)
                    if not has_permission(perms, VIDEO):
                        await self.send_json({"type": "error", "d": {"code": "MISSING_PERMISSIONS", "message": "You lack the VIDEO permission."}})
                        return
                vs.video = data["video"]
            if "streaming" in data:
                if data["streaming"]:
                    perms = await resolve_permissions(db, self.user_id, space_type="room", space_id=vs.room_id)
                    if not has_permission(perms, STREAM):
                        await self.send_json({"type": "error", "d": {"code": "MISSING_PERMISSIONS", "message": "You lack the STREAM permission."}})
                        return
                vs.streaming = data["streaming"]
            await db.commit()

            members = await get_room_members(db, vs.room_id)
            evt = events.voice_state_update(
                room_id=vs.room_id,
                members=[m.model_dump() for m in members],
            )
            await dispatch(evt)

    async def _cleanup_voice_state(self, db_factory: Any) -> None:
        # Check in-memory SFU state first to avoid unnecessary DB access
        from vox.voice.service import _sfu
        if _sfu is None:
            return
        try:
            users = _sfu.get_room_users  # just check SFU is alive
        except Exception:
            return

        from vox.db.models import VoiceState
        from vox.voice.service import leave_room, get_room_members
        from vox.gateway.dispatch import dispatch
        from sqlalchemy import select

        async with db_factory() as db:
            result = await db.execute(select(VoiceState).where(VoiceState.user_id == self.user_id))
            vs = result.scalar_one_or_none()
            if vs is None:
                return
            room_id = vs.room_id
            await leave_room(db, room_id, self.user_id)

            members = await get_room_members(db, room_id)
            evt = events.voice_state_update(
                room_id=room_id,
                members=[m.model_dump() for m in members],
            )
            await dispatch(evt)
