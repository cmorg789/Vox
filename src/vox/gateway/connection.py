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

    async def send_json(self, data: dict[str, Any]) -> None:
        if not self._closed:
            try:
                if self._compress:
                    raw = json.dumps(data).encode()
                    await self.ws.send_bytes(_zstd_compressor.compress(raw))
                else:
                    await self.ws.send_json(data)
            except Exception:
                self._closed = True

    async def send_event(self, event: dict[str, Any]) -> None:
        """Send a sequenced event to this client."""
        self.seq += 1
        msg = {**event, "seq": self.seq}
        self._replay_buffer.append(msg)
        # Also write to hub session buffer so resume works after disconnect
        session = self.hub.get_session(self.session_id)
        if session is not None:
            session.replay_buffer.append(msg)
            session.seq = self.seq
        await self.send_json(msg)

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
                # Preserve session state in hub for resume
                state = SessionState(
                    user_id=self.user_id,
                    replay_buffer=deque(self._replay_buffer, maxlen=REPLAY_BUFFER_SIZE),
                    seq=self.seq,
                )
                self.hub.save_session(self.session_id, state)
                await self.hub.disconnect(self)
                # If no remaining sessions, clear presence and broadcast offline
                # clear_presence must be inside the lock to prevent a race where
                # a new connection registers between the check and the clear
                async with self.hub._lock:
                    has_connections = self.user_id in self.hub.connections
                    if not has_connections:
                        self.hub.clear_presence(self.user_id)
                if not has_connections:
                    await self.hub.broadcast(events.presence_update(user_id=self.user_id, status="offline"))

    async def _handle_identify(self, data: dict[str, Any], db_factory: Any) -> None:
        token = data.get("token", "")
        if not token:
            await self.close(CLOSE_AUTH_FAILED, "AUTH_FAILED")
            return

        # Version negotiation
        protocol_version = data.get("protocol_version", 1)
        if not (PROTOCOL_VERSION_MIN <= protocol_version <= PROTOCOL_VERSION_MAX):
            await self.close(CLOSE_VERSION_MISMATCH, "VERSION_MISMATCH")
            return

        async with db_factory() as db:
            user = await get_user_by_token(db, token)
            if user is None:
                await self.close(CLOSE_AUTH_FAILED, "AUTH_FAILED")
                return

            # Read server config from DB
            from vox.api.server import _get_config
            from vox.db.models import ConfigKey
            server_name = await _get_config(db, ConfigKey.SERVER_NAME) or "Vox Server"
            server_icon = await _get_config(db, ConfigKey.SERVER_ICON)

        self.user_id = user.id
        self.session_id = "sess_" + secrets.token_hex(12)
        self.protocol_version = protocol_version
        self.capabilities = data.get("capabilities", [])
        self.authenticated = True
        self.hub.connect(self)

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

        # Send current presence snapshot to newly connected client
        for uid, pdata in self.hub.presence.items():
            if uid != self.user_id:
                await self.send_event(events.presence_update(**pdata))

    async def _handle_resume(self, data: dict[str, Any], db_factory: Any) -> None:
        token = data.get("token", "")
        session_id = data.get("session_id", "")
        last_seq = data.get("last_seq", 0)

        if not token or not session_id:
            await self.close(CLOSE_AUTH_FAILED, "AUTH_FAILED")
            return

        async with db_factory() as db:
            user = await get_user_by_token(db, token)

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
        self.authenticated = True
        self.hub.connect(self)

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

            elif msg_type == "presence_update":
                status = data.get("status", "online")
                if status not in ("online", "idle", "dnd", "invisible"):
                    await self.send_json({"type": "error", "d": {"code": "INVALID_STATUS", "message": "Status must be one of: online, idle, dnd, invisible."}})
                    continue
                custom_status = data.get("custom_status")
                activity = data.get("activity")
                presence_data: dict[str, Any] = {"status": status}
                if custom_status is not None:
                    presence_data["custom_status"] = custom_status
                if activity is not None:
                    presence_data["activity"] = activity
                self.hub.set_presence(self.user_id, presence_data)
                # If invisible, broadcast offline to others
                broadcast_status = "offline" if status == "invisible" else status
                broadcast_data = {**presence_data, "status": broadcast_status}
                other_ids = [uid for uid in self.hub.connections if uid != self.user_id]
                if other_ids:
                    await self.hub.broadcast(events.presence_update(user_id=self.user_id, **broadcast_data), user_ids=other_ids)

            elif msg_type == "voice_state_update":
                from vox.gateway.dispatch import dispatch
                await self._handle_voice_state_update(data, db_factory)

            elif msg_type == "mls_relay":
                mls_type = data.get("mls_type", "")
                mls_data = data.get("data", "")
                from vox.limits import limits as _limits
                if len(mls_data) > _limits.relay_payload_max:
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
                from vox.limits import limits as _limits
                if len(cpace_data) > _limits.relay_payload_max:
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
                params = {k: v for k, v in data.items() if k not in ("media_type", "codec", "room_id")}
                evt = events.voice_codec_neg(media_type=media_type, codec=codec, **params)
                if room_id is not None:
                    room_user_ids = await self._get_voice_room_users(room_id, db_factory)
                    await self.hub.broadcast(evt, user_ids=room_user_ids)
                else:
                    await self.hub.broadcast(evt)

            elif msg_type == "stage_response":
                room_id = data.get("room_id")
                stage_data = {k: v for k, v in data.items() if k != "room_id"}
                evt = events.stage_response(user_id=self.user_id, **stage_data)
                if room_id is not None:
                    room_user_ids = await self._get_voice_room_users(room_id, db_factory)
                    await self.hub.broadcast(evt, user_ids=room_user_ids)
                else:
                    await self.hub.broadcast(evt)

            # Unknown types are silently ignored per spec tolerance

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
                vs.video = data["video"]
            if "streaming" in data:
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
