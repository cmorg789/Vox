"""WebSocket gateway client — lifecycle, heartbeat, resume, event dispatch."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import websockets
import websockets.asyncio.client

from vox_sdk.errors import VoxGatewayError
from vox_sdk.models.events import GatewayEvent, Hello, Ready, parse_event

log = logging.getLogger(__name__)

try:
    import zstandard as zstd
    _zstd_decompressor = zstd.ZstdDecompressor()
except ImportError:
    zstd = None  # type: ignore[assignment]
    _zstd_decompressor = None  # type: ignore[assignment]

EventHandler = Callable[[GatewayEvent], Coroutine[Any, Any, None]]


class GatewayClient:
    """Manages the WebSocket connection to the Vox gateway.

    Usage::

        gw = GatewayClient("https://vox.example.com", token)

        @gw.on("message_create")
        async def on_message(event):
            print(event.body)

        await gw.connect()  # blocks until closed
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        compress: bool = True,
        protocol_version: int = 1,
    ) -> None:
        # Build ws:// URL from http:// base
        ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = ws_url.rstrip("/")
        params = []
        if compress and _zstd_decompressor is not None:
            params.append("compress=zstd")
        self._url = f"{ws_url}/gateway" + (f"?{'&'.join(params)}" if params else "")
        self._token = token
        self._protocol_version = protocol_version
        self._compress = compress and _zstd_decompressor is not None

        self._ws: Any = None
        self._session_id: str | None = None
        self._seq: int = 0
        self._heartbeat_interval: float = 45.0
        self._heartbeat_task: asyncio.Task | None = None
        self._handlers: dict[str, list[EventHandler]] = {}
        self._closed = False
        self._ready_event: asyncio.Event = asyncio.Event()
        self._ready_data: Ready | None = None

    def on(self, event_type: str) -> Callable[[EventHandler], EventHandler]:
        """Decorator to register an event handler."""
        def decorator(func: EventHandler) -> EventHandler:
            self._handlers.setdefault(event_type, []).append(func)
            return func
        return decorator

    def add_handler(self, event_type: str, handler: EventHandler) -> None:
        """Register an event handler programmatically."""
        self._handlers.setdefault(event_type, []).append(handler)

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def last_seq(self) -> int:
        return self._seq

    async def connect(self) -> None:
        """Connect, identify, and enter the receive loop. Blocks until closed."""
        self._closed = False
        self._ready_event.clear()
        try:
            async with websockets.asyncio.client.connect(self._url) as ws:
                self._ws = ws
                await self._run(ws)
        except websockets.exceptions.ConnectionClosedError as e:
            raise VoxGatewayError(e.code, e.reason) from e
        finally:
            self._ws = None

    async def connect_in_background(self) -> Ready:
        """Start the gateway in a background task. Returns when READY is received."""
        self._closed = False
        self._ready_event.clear()
        asyncio.create_task(self._background_connect())
        await self._ready_event.wait()
        assert self._ready_data is not None
        return self._ready_data

    async def _background_connect(self) -> None:
        try:
            await self.connect()
        except Exception:
            log.exception("Gateway background connection error")

    async def close(self) -> None:
        """Cleanly close the gateway connection."""
        self._closed = True
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass

    async def send(self, msg_type: str, data: dict[str, Any] | None = None) -> None:
        """Send a client message to the gateway."""
        payload: dict[str, Any] = {"type": msg_type}
        if data:
            payload["d"] = data
        if self._ws:
            await self._ws.send(json.dumps(payload))

    async def _run(self, ws: Any) -> None:
        # Step 1: Receive hello
        raw = await self._recv(ws)
        hello = parse_event(raw)
        if not isinstance(hello, Hello):
            raise VoxGatewayError(4000, "Expected hello")
        self._heartbeat_interval = hello.heartbeat_interval / 1000.0

        # Step 2: Identify or resume
        if self._session_id:
            await self.send("resume", {
                "token": self._token,
                "session_id": self._session_id,
                "last_seq": self._seq,
            })
        else:
            await self.send("identify", {
                "token": self._token,
                "protocol_version": self._protocol_version,
            })

        # Step 3: Start heartbeat
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))

        # Step 4: Receive loop
        try:
            while not self._closed:
                raw = await self._recv(ws)
                event = parse_event(raw)

                if event.seq is not None:
                    self._seq = event.seq

                if isinstance(event, Ready):
                    self._session_id = event.session_id
                    self._ready_data = event
                    self._ready_event.set()

                # Dispatch heartbeat_ack silently
                if event.type == "heartbeat_ack":
                    continue

                await self._dispatch(event)
        except websockets.exceptions.ConnectionClosed as e:
            if not self._closed:
                raise VoxGatewayError(e.code, e.reason) from e
        finally:
            if self._heartbeat_task:
                self._heartbeat_task.cancel()

    async def _recv(self, ws: Any) -> dict[str, Any]:
        """Receive and decode a message, handling zstd compression."""
        msg = await ws.recv()
        if isinstance(msg, bytes) and self._compress and _zstd_decompressor:
            msg = _zstd_decompressor.decompress(msg).decode()
        if isinstance(msg, bytes):
            msg = msg.decode()
        return json.loads(msg)

    async def _heartbeat_loop(self, ws: Any) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(self._heartbeat_interval)
                if not self._closed:
                    await self.send("heartbeat")
        except asyncio.CancelledError:
            pass

    async def _dispatch(self, event: GatewayEvent) -> None:
        handlers = self._handlers.get(event.type, [])
        wildcard = self._handlers.get("*", [])
        for handler in [*handlers, *wildcard]:
            try:
                await handler(event)
            except Exception:
                log.exception("Error in event handler for %s", event.type)
