"""WebSocket gateway client — lifecycle, heartbeat, resume, event dispatch."""

from __future__ import annotations

import asyncio
import json
import logging
import random
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

_MAX_BACKOFF = 60.0
_BASE_BACKOFF = 1.0


class GatewayClient:
    """Manages the WebSocket connection to the Vox gateway.

    Usage::

        gw = GatewayClient("wss://vox.example.com/gateway", token)

        @gw.on("message_create")
        async def on_message(event):
            print(event.body)

        await gw.run()  # blocks until closed or fatal error
    """

    def __init__(
        self,
        gateway_url: str,
        token: str,
        *,
        compress: bool = True,
        protocol_version: int = 1,
    ) -> None:
        # Convert http(s) URL to ws(s) if needed
        ws_url = gateway_url.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = ws_url.rstrip("/")
        params = []
        if compress and _zstd_decompressor is not None:
            params.append("compress=zstd")
        self._url = ws_url + (f"?{'&'.join(params)}" if params else "")
        self._token = token
        self._protocol_version = protocol_version
        self._compress = compress and _zstd_decompressor is not None

        self._ws: Any = None
        self._session_id: str | None = None
        self._seq: int = 0
        self._heartbeat_interval: float = 45.0
        self._heartbeat_task: asyncio.Task | None = None
        self._last_heartbeat_ack: float = 0.0
        self._handlers: dict[str, list[EventHandler]] = {}
        self._closed = False
        self._ready_event: asyncio.Event = asyncio.Event()
        self._ready_data: Ready | None = None
        self._connect_error: BaseException | None = None

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
        self._connect_error = None
        try:
            async with websockets.asyncio.client.connect(self._url) as ws:
                self._ws = ws
                await self._run(ws)
        except websockets.exceptions.ConnectionClosedError as e:
            raise VoxGatewayError(e.code, e.reason) from e
        finally:
            self._ws = None

    async def run(self, *, max_reconnect_attempts: int | None = None) -> None:
        """Connect with automatic reconnection on recoverable errors.

        Wraps connect() in a reconnect loop with exponential backoff + jitter.
        Fatal close codes re-raise immediately.
        """
        attempt = 0
        while True:
            try:
                await self.connect()
                return  # clean close
            except VoxGatewayError as exc:
                if exc.can_resume:
                    # Keep session_id and seq for resume
                    log.info("Gateway closed with resumable code %d, reconnecting...", exc.code)
                elif exc.can_reconnect:
                    # Reset session for fresh identify
                    log.info("Gateway closed with code %d, reconnecting fresh...", exc.code)
                    self._session_id = None
                    self._seq = 0
                else:
                    # Fatal — re-raise
                    raise

                attempt += 1
                if max_reconnect_attempts is not None and attempt >= max_reconnect_attempts:
                    raise

                delay = min(_BASE_BACKOFF * (2 ** (attempt - 1)), _MAX_BACKOFF)
                delay *= 0.5 + random.random()  # jitter
                log.info("Reconnecting in %.1fs (attempt %d)...", delay, attempt)
                await asyncio.sleep(delay)

    async def connect_in_background(self, *, timeout: float = 30.0) -> Ready:
        """Start the gateway in a background task. Returns when READY is received."""
        self._closed = False
        self._ready_event.clear()
        self._connect_error = None
        asyncio.create_task(self._background_connect())
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout)
        except asyncio.TimeoutError:
            raise VoxGatewayError(4000, "Timed out waiting for READY") from None
        if self._connect_error is not None:
            raise self._connect_error
        assert self._ready_data is not None
        return self._ready_data

    async def _background_connect(self) -> None:
        try:
            await self.connect()
        except Exception as exc:
            self._connect_error = exc
            self._ready_event.set()
            if not isinstance(exc, VoxGatewayError):
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
        if self._ws is None:
            raise VoxGatewayError(4000, "Not connected")
        await self._ws.send(json.dumps(payload))

    async def send_typing(self, feed_id: int) -> None:
        """Send a typing indicator for a feed."""
        await self.send("typing_start", {"feed_id": feed_id})

    async def update_presence(
        self, status: str, custom_status: str | None = None
    ) -> None:
        """Update the client's presence status."""
        data: dict[str, Any] = {"status": status}
        if custom_status is not None:
            data["custom_status"] = custom_status
        await self.send("presence_update", data)

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
        self._last_heartbeat_ack = asyncio.get_event_loop().time()
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

                # Handle heartbeat_ack — update timestamp, don't dispatch
                if event.type == "heartbeat_ack":
                    self._last_heartbeat_ack = asyncio.get_event_loop().time()
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
                if self._closed:
                    break
                # Check for heartbeat timeout
                now = asyncio.get_event_loop().time()
                if now - self._last_heartbeat_ack > 2 * self._heartbeat_interval:
                    log.warning("Heartbeat ACK timeout, closing connection")
                    await ws.close()
                    return
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
