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
    def __init__(self, ws: WebSocket, hub: Hub) -> None:
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

    async def send_json(self, data: dict[str, Any]) -> None:
        if not self._closed:
            try:
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
                # Preserve session state in hub for resume
                state = SessionState(
                    user_id=self.user_id,
                    replay_buffer=deque(self._replay_buffer, maxlen=REPLAY_BUFFER_SIZE),
                    seq=self.seq,
                )
                self.hub.save_session(self.session_id, state)
                self.hub.disconnect(self)

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
            server_name = await _get_config(db, "server_name") or "Vox Server"
            server_icon = await _get_config(db, "server_icon")

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
                evt = events.typing_start(user_id=self.user_id, feed_id=feed_id, dm_id=dm_id)
                await dispatch(evt)

            elif msg_type == "presence_update":
                from vox.gateway.dispatch import dispatch
                status = data.get("status", "online")
                evt = events.presence_update(user_id=self.user_id, status=status)
                await dispatch(evt)

            elif msg_type == "voice_state_update":
                from vox.gateway.dispatch import dispatch
                evt = {"type": "voice_state_update", "d": {"user_id": self.user_id, **data}}
                await dispatch(evt)

            elif msg_type == "mls_relay":
                mls_type = data.get("mls_type", "")
                mls_data = data.get("data", "")
                builder = _MLS_EVENT_MAP.get(mls_type)
                if builder:
                    evt = builder(data=mls_data)
                    # Same-user device relay
                    await self.hub.broadcast(evt, user_ids=[self.user_id])

            elif msg_type == "cpace_relay":
                cpace_type = data.get("cpace_type", "")
                pair_id = data.get("pair_id", "")
                cpace_data = data.get("data", "")
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
                params = {k: v for k, v in data.items() if k not in ("media_type", "codec")}
                evt = events.voice_codec_neg(media_type=media_type, codec=codec, **params)
                # Broadcast to all (no room membership tracking yet)
                await self.hub.broadcast(evt)

            elif msg_type == "stage_response":
                evt = {"type": "stage_response", "d": {"user_id": self.user_id, **data}}
                # Broadcast to all (no room membership tracking yet)
                await self.hub.broadcast(evt)

            # Unknown types are silently ignored per spec tolerance
