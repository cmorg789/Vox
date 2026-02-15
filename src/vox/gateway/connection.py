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
from vox.gateway.hub import Hub

log = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_MS = 45_000
IDENTIFY_TIMEOUT_S = 30
HEARTBEAT_TIMEOUT_FACTOR = 1.5
REPLAY_BUFFER_SIZE = 1000


class Connection:
    def __init__(self, ws: WebSocket, hub: Hub) -> None:
        self.ws = ws
        self.hub = hub
        self.user_id: int = 0
        self.session_id: str = ""
        self.seq: int = 0
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
                await self.close(4003, "NOT_AUTHENTICATED")
                return
            except WebSocketDisconnect:
                return

            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                await self.close(4002, "DECODE_ERROR")
                return

            msg_type = msg.get("type")
            data = msg.get("d", {}) or {}

            if msg_type == "identify":
                await self._handle_identify(data, db_factory)
            elif msg_type == "resume":
                await self._handle_resume(data, db_factory)
            else:
                await self.close(4003, "NOT_AUTHENTICATED")
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
        finally:
            if self.authenticated:
                self.hub.disconnect(self)

    async def _handle_identify(self, data: dict[str, Any], db_factory: Any) -> None:
        token = data.get("token", "")
        if not token:
            await self.close(4004, "AUTH_FAILED")
            return

        async with db_factory() as db:
            user = await get_user_by_token(db, token)

        if user is None:
            await self.close(4004, "AUTH_FAILED")
            return

        self.user_id = user.id
        self.session_id = "sess_" + secrets.token_hex(12)
        self.capabilities = data.get("capabilities", [])
        self.authenticated = True
        self.hub.connect(self)

        ready_event = events.ready(
            session_id=self.session_id,
            user_id=user.id,
            display_name=user.display_name or user.username,
            server_name="Vox Server",
        )
        await self.send_event(ready_event)

    async def _handle_resume(self, data: dict[str, Any], db_factory: Any) -> None:
        token = data.get("token", "")
        session_id = data.get("session_id", "")
        last_seq = data.get("last_seq", 0)

        if not token or not session_id:
            await self.close(4004, "AUTH_FAILED")
            return

        async with db_factory() as db:
            user = await get_user_by_token(db, token)

        if user is None:
            await self.close(4004, "AUTH_FAILED")
            return

        self.user_id = user.id
        self.session_id = session_id
        self.authenticated = True
        self.hub.connect(self)

        # Replay buffered events since last_seq
        for buffered in self._replay_buffer:
            if buffered.get("seq", 0) > last_seq:
                await self.send_json(buffered)

    async def _heartbeat_monitor(self) -> None:
        timeout = HEARTBEAT_INTERVAL_MS / 1000 * HEARTBEAT_TIMEOUT_FACTOR
        while not self._closed:
            await asyncio.sleep(timeout)
            if time.monotonic() - self.last_heartbeat > timeout:
                await self.close(4007, "SESSION_TIMEOUT")
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
                await self.close(4002, "DECODE_ERROR")
                return

            msg_type = msg.get("type")
            data = msg.get("d", {}) or {}

            if msg_type == "heartbeat":
                self.last_heartbeat = time.monotonic()
                await self.send_json(events.heartbeat_ack())

            elif msg_type == "identify":
                await self.close(4005, "ALREADY_AUTHENTICATED")
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

            # Unknown types are silently ignored per spec tolerance
