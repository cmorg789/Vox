"""Tests for the gateway client and event parsing."""

import asyncio
import json
from collections import deque
from unittest.mock import AsyncMock, patch

import pytest
import websockets.exceptions

from vox_sdk.errors import VoxGatewayError
from vox_sdk.gateway import GatewayClient
from vox_sdk.models.events import (
    GatewayEvent,
    Hello,
    MessageCreate,
    Ready,
    FeedUpdate,
    NotificationCreate,
    parse_event,
)


# ---------------------------------------------------------------------------
# FakeWebSocket — feeds scripted messages and records sent messages
# ---------------------------------------------------------------------------

class FakeWebSocket:
    """Mimics a websockets connection for testing _run() directly."""

    def __init__(self, messages: list[dict]):
        self._messages = deque(json.dumps(m) for m in messages)
        self.sent: list[dict] = []
        self._closed = False

    async def recv(self):
        if not self._messages:
            raise websockets.exceptions.ConnectionClosed(None, None)
        return self._messages.popleft()

    async def send(self, data):
        self.sent.append(json.loads(data))

    async def close(self):
        self._closed = True


class TestParseEvent:
    def test_hello(self):
        raw = {"type": "hello", "d": {"heartbeat_interval": 45000}}
        event = parse_event(raw)
        assert isinstance(event, Hello)
        assert event.heartbeat_interval == 45000

    def test_ready(self):
        raw = {
            "type": "ready",
            "seq": 1,
            "d": {
                "session_id": "sess_abc",
                "user_id": 42,
                "display_name": "Alice",
                "server_name": "Test",
                "protocol_version": 1,
                "capabilities": ["voice", "e2ee"],
            },
        }
        event = parse_event(raw)
        assert isinstance(event, Ready)
        assert event.session_id == "sess_abc"
        assert event.user_id == 42
        assert event.seq == 1
        assert event.capabilities == ["voice", "e2ee"]

    def test_message_create(self):
        raw = {
            "type": "message_create",
            "seq": 5,
            "d": {
                "msg_id": 100,
                "feed_id": 1,
                "author_id": 42,
                "body": "Hello world",
                "timestamp": 1700000000,
            },
        }
        event = parse_event(raw)
        assert isinstance(event, MessageCreate)
        assert event.msg_id == 100
        assert event.body == "Hello world"
        assert event.feed_id == 1

    def test_unknown_event(self):
        raw = {"type": "some_future_event", "d": {"foo": "bar"}}
        event = parse_event(raw)
        assert isinstance(event, GatewayEvent)
        assert event.type == "some_future_event"
        assert event.raw == raw

    def test_event_with_extra_fields(self):
        raw = {
            "type": "feed_update",
            "seq": 3,
            "d": {"feed_id": 1, "name": "renamed", "topic": "new topic"},
        }
        event = parse_event(raw)
        assert isinstance(event, FeedUpdate)
        assert event.feed_id == 1
        assert event.extra == {"name": "renamed", "topic": "new topic"}

    def test_notification_create_type_mapping(self):
        raw = {
            "type": "notification_create",
            "seq": 10,
            "d": {
                "user_id": 1,
                "type": "mention",
                "feed_id": 5,
                "msg_id": 100,
                "actor_id": 2,
                "body_preview": "hey @you",
            },
        }
        event = parse_event(raw)
        assert isinstance(event, NotificationCreate)
        assert event.type == "notification_create"
        assert event.notification_type == "mention"
        assert event.user_id == 1


class TestVoxGatewayError:
    def test_can_resume(self):
        err = VoxGatewayError(4007, "SESSION_TIMEOUT")
        assert err.can_resume is True
        assert err.can_reconnect is True

    def test_cannot_resume_auth_failed(self):
        err = VoxGatewayError(4004, "AUTH_FAILED")
        assert err.can_resume is False
        assert err.can_reconnect is False

    def test_can_reconnect_not_resume(self):
        err = VoxGatewayError(4009, "SESSION_EXPIRED")
        assert err.can_resume is False
        assert err.can_reconnect is True


class TestGatewayClientUnit:
    """Unit tests for GatewayClient without a live server."""

    def test_handler_registration(self):
        """on() decorator and add_handler() both register handlers."""
        from vox_sdk.gateway import GatewayClient

        gw = GatewayClient("http://localhost/gateway", "tok")

        @gw.on("message_create")
        async def handler_a(event):
            pass

        async def handler_b(event):
            pass

        gw.add_handler("message_create", handler_b)

        assert handler_a in gw._handlers["message_create"]
        assert handler_b in gw._handlers["message_create"]
        assert len(gw._handlers["message_create"]) == 2

    def test_wildcard_handler(self):
        """Wildcard '*' handlers are stored under the '*' key."""
        from vox_sdk.gateway import GatewayClient

        gw = GatewayClient("http://localhost/gateway", "tok")

        @gw.on("*")
        async def catch_all(event):
            pass

        assert catch_all in gw._handlers["*"]

    @pytest.mark.asyncio
    async def test_dispatch_error_does_not_propagate(self):
        """Handler exceptions are caught, don't crash dispatch."""
        from vox_sdk.gateway import GatewayClient
        from vox_sdk.models.events import GatewayEvent

        gw = GatewayClient("http://localhost/gateway", "tok")
        bad_called = []
        called = []

        @gw.on("test_event")
        async def bad_handler(event):
            bad_called.append(event)
            raise RuntimeError("boom")

        @gw.on("test_event")
        async def good_handler(event):
            called.append(event)

        event = GatewayEvent(type="test_event", raw={"type": "test_event", "d": {}})
        # Should not raise
        await gw._dispatch(event)
        assert len(bad_called) == 1, "bad_handler should have been called"
        assert len(called) == 1

    def test_url_construction(self):
        """Verify http->ws URL conversion and query params."""
        from vox_sdk.gateway import GatewayClient

        gw = GatewayClient("http://localhost/gateway", "tok", compress=False)
        assert gw._url.startswith("ws://")
        assert "compress" not in gw._url

        gw2 = GatewayClient("https://example.com/gateway", "tok", compress=False)
        assert gw2._url.startswith("wss://")

    def test_session_id_and_last_seq_defaults(self):
        """Before connect, session_id is None and last_seq is 0."""
        from vox_sdk.gateway import GatewayClient

        gw = GatewayClient("http://localhost/gateway", "tok")
        assert gw.session_id is None
        assert gw.last_seq == 0


class TestGatewayRun:
    """Tests for GatewayClient._run() using FakeWebSocket."""

    def _make_gw(self, **kwargs):
        gw = GatewayClient("http://localhost/gateway", "tok", compress=False, **kwargs)
        return gw

    @pytest.mark.asyncio
    async def test_run_identify_flow(self):
        """Hello → identify with token + protocol_version → ready sets session_id."""
        ws = FakeWebSocket([
            {"type": "hello", "d": {"heartbeat_interval": 30000}},
            {
                "type": "ready", "seq": 1,
                "d": {
                    "session_id": "sess_1", "user_id": 1,
                    "display_name": "A", "server_name": "S",
                    "protocol_version": 1, "capabilities": [],
                },
            },
        ])
        gw = self._make_gw()
        gw._ws = ws  # send() requires _ws to be set
        # _run will exhaust messages then get ConnectionClosed → VoxGatewayError
        with pytest.raises(VoxGatewayError):
            await gw._run(ws)

        # Verify identify was sent
        identify = ws.sent[0]
        assert identify["type"] == "identify"
        assert identify["d"]["token"] == "tok"
        assert identify["d"]["protocol_version"] == 1

        # Verify session set from ready
        assert gw._session_id == "sess_1"

    @pytest.mark.asyncio
    async def test_run_resume_flow(self):
        """Pre-set session_id → resume sent instead of identify."""
        ws = FakeWebSocket([
            {"type": "hello", "d": {"heartbeat_interval": 30000}},
        ])
        gw = self._make_gw()
        gw._ws = ws  # send() requires _ws to be set
        gw._session_id = "sess_old"
        gw._seq = 42

        with pytest.raises(VoxGatewayError):
            await gw._run(ws)

        resume = ws.sent[0]
        assert resume["type"] == "resume"
        assert resume["d"]["session_id"] == "sess_old"
        assert resume["d"]["last_seq"] == 42

    @pytest.mark.asyncio
    async def test_run_rejects_non_hello_first(self):
        """First message must be hello, otherwise 4000 error."""
        ws = FakeWebSocket([
            {"type": "message_create", "seq": 1, "d": {"msg_id": 1}},
        ])
        gw = self._make_gw()
        with pytest.raises(VoxGatewayError) as exc_info:
            await gw._run(ws)
        assert exc_info.value.code == 4000

    @pytest.mark.asyncio
    async def test_run_tracks_seq(self):
        """Events with seq values update gw._seq."""
        ws = FakeWebSocket([
            {"type": "hello", "d": {"heartbeat_interval": 30000}},
            {"type": "message_create", "seq": 5, "d": {"msg_id": 1}},
            {"type": "message_create", "seq": 12, "d": {"msg_id": 2}},
        ])
        gw = self._make_gw()
        gw._ws = ws
        with pytest.raises(VoxGatewayError):
            await gw._run(ws)
        assert gw._seq == 12

    @pytest.mark.asyncio
    async def test_run_heartbeat_ack_not_dispatched(self):
        """heartbeat_ack events are not dispatched to handlers."""
        ws = FakeWebSocket([
            {"type": "hello", "d": {"heartbeat_interval": 30000}},
            {"type": "heartbeat_ack", "d": {}},
        ])
        gw = self._make_gw()
        gw._ws = ws
        dispatched = []

        @gw.on("heartbeat_ack")
        async def on_hb_ack(event):
            dispatched.append(event)

        @gw.on("*")
        async def catch_all(event):
            dispatched.append(event)

        with pytest.raises(VoxGatewayError):
            await gw._run(ws)
        assert len(dispatched) == 0

    @pytest.mark.asyncio
    async def test_run_connection_closed_while_active(self):
        """ConnectionClosed during recv while _closed=False raises VoxGatewayError."""
        ws = FakeWebSocket([
            {"type": "hello", "d": {"heartbeat_interval": 30000}},
            # No more messages → ConnectionClosed on next recv
        ])
        gw = self._make_gw()
        gw._ws = ws
        with pytest.raises(VoxGatewayError):
            await gw._run(ws)


class TestParseEventParametrized:
    """Parametrized tests for parse_event covering many event types."""

    @pytest.mark.parametrize("event_type,data_cls,data,check_field,check_value", [
        ("message_update", "MessageUpdate", {"msg_id": 1, "body": "edited"}, "msg_id", 1),
        ("message_delete", "MessageDelete", {"msg_id": 1, "feed_id": 2}, "msg_id", 1),
        ("member_join", "MemberJoin", {"user_id": 5, "display_name": "New"}, "user_id", 5),
        ("member_leave", "MemberLeave", {"user_id": 5}, "user_id", 5),
        ("feed_create", "FeedCreate", {"feed_id": 1, "name": "general"}, "feed_id", 1),
        ("role_create", "RoleCreate", {"role_id": 1, "name": "Admin", "color": 0xFF0000, "permissions": 8, "position": 0}, "color", 0xFF0000),
        ("dm_create", "DMCreate", {"dm_id": 1, "participant_ids": [1, 2]}, "dm_id", 1),
        ("typing_start", "TypingStart", {"user_id": 1, "feed_id": 5}, "user_id", 1),
        ("presence_update", "PresenceUpdate", {"user_id": 1, "status": "online"}, "user_id", 1),
        ("voice_state_update", "VoiceStateUpdate", {"room_id": 1, "members": []}, "room_id", 1),
        ("webhook_create", "WebhookCreate", {"webhook_id": 1, "feed_id": 2, "name": "wh"}, "webhook_id", 1),
        ("emoji_create", "EmojiCreate", {"emoji_id": 1, "name": "fire", "creator_id": 2}, "emoji_id", 1),
        ("interaction_create", "InteractionCreate", {"interaction": {"id": "int-1"}}, "interaction", {"id": "int-1"}),
        ("resumed", "Resumed", {}, None, None),
    ])
    def test_parse_event_types(self, event_type, data_cls, data, check_field, check_value):
        from vox_sdk.models import events as ev
        raw = {"type": event_type, "seq": 1, "d": data}
        event = parse_event(raw)
        expected_cls = getattr(ev, data_cls)
        assert isinstance(event, expected_cls)
        assert event.type == event_type
        if check_field is not None:
            assert getattr(event, check_field) == check_value


class TestGatewayEdgeCases:
    @pytest.mark.asyncio
    async def test_send_when_ws_is_none_raises(self):
        """send() raises VoxGatewayError when _ws is None."""
        gw = GatewayClient("http://localhost/gateway", "tok")
        assert gw._ws is None
        with pytest.raises(VoxGatewayError) as exc_info:
            await gw.send("heartbeat")
        assert exc_info.value.code == 4000
        assert "Not connected" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_close_sets_closed_flag(self):
        gw = GatewayClient("http://localhost/gateway", "tok")
        assert gw._closed is False
        await gw.close()
        assert gw._closed is True

    def test_url_construction_with_compress(self):
        """When compress=True and zstd is available, URL has ?compress=zstd."""
        gw = GatewayClient("http://localhost/gateway", "tok", compress=True)
        try:
            import zstandard
            assert "compress=zstd" in gw._url
        except ImportError:
            assert "compress" not in gw._url


class TestGatewayReconnect:
    """Tests for the run() reconnect loop."""

    @pytest.mark.asyncio
    async def test_run_reconnects_on_resumable(self, monkeypatch):
        """run() reconnects preserving session on resumable close codes."""
        call_count = {"n": 0}

        async def mock_connect(self):
            call_count["n"] += 1
            if call_count["n"] == 1:
                self._session_id = "sess_1"
                self._seq = 10
                raise VoxGatewayError(4007, "SESSION_TIMEOUT")
            if call_count["n"] == 2:
                # Verify session preserved
                assert self._session_id == "sess_1"
                assert self._seq == 10
                return  # clean close

        monkeypatch.setattr(GatewayClient, "connect", mock_connect)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        gw = GatewayClient("http://localhost/gateway", "tok", compress=False)
        await gw.run()
        assert call_count["n"] == 2

    @pytest.mark.asyncio
    async def test_run_reconnects_fresh_on_non_resumable(self, monkeypatch):
        """run() resets session on reconnectable-but-not-resumable codes."""
        call_count = {"n": 0}

        async def mock_connect(self):
            call_count["n"] += 1
            if call_count["n"] == 1:
                self._session_id = "sess_1"
                self._seq = 10
                raise VoxGatewayError(4009, "SESSION_EXPIRED")
            if call_count["n"] == 2:
                # Verify session was reset
                assert self._session_id is None
                assert self._seq == 0
                return

        monkeypatch.setattr(GatewayClient, "connect", mock_connect)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        gw = GatewayClient("http://localhost/gateway", "tok", compress=False)
        await gw.run()
        assert call_count["n"] == 2

    @pytest.mark.asyncio
    async def test_run_fatal_code_raises(self, monkeypatch):
        """run() re-raises on fatal (non-reconnectable) close codes."""
        async def mock_connect(self):
            raise VoxGatewayError(4004, "AUTH_FAILED")

        monkeypatch.setattr(GatewayClient, "connect", mock_connect)

        gw = GatewayClient("http://localhost/gateway", "tok", compress=False)
        with pytest.raises(VoxGatewayError) as exc_info:
            await gw.run()
        assert exc_info.value.code == 4004

    @pytest.mark.asyncio
    async def test_run_max_reconnect_attempts(self, monkeypatch):
        """run() stops after max_reconnect_attempts."""
        call_count = {"n": 0}

        async def mock_connect(self):
            call_count["n"] += 1
            raise VoxGatewayError(4000, "UNKNOWN_ERROR")

        monkeypatch.setattr(GatewayClient, "connect", mock_connect)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        gw = GatewayClient("http://localhost/gateway", "tok", compress=False)
        with pytest.raises(VoxGatewayError):
            await gw.run(max_reconnect_attempts=3)
        assert call_count["n"] == 3  # stops after 3 attempts


class TestHeartbeatTimeout:
    """Tests for heartbeat ACK timeout detection."""

    @pytest.mark.asyncio
    async def test_heartbeat_ack_updates_timestamp(self):
        """Receiving heartbeat_ack updates _last_heartbeat_ack."""
        ws = FakeWebSocket([
            {"type": "hello", "d": {"heartbeat_interval": 30000}},
            {"type": "heartbeat_ack", "d": {}},
        ])
        gw = GatewayClient("http://localhost/gateway", "tok", compress=False)
        gw._ws = ws

        with pytest.raises(VoxGatewayError):
            await gw._run(ws)
        # _last_heartbeat_ack should have been updated (not zero)
        assert gw._last_heartbeat_ack > 0

    @pytest.mark.asyncio
    async def test_heartbeat_timeout_closes_ws(self, monkeypatch):
        """If heartbeat ACK is overdue, the heartbeat loop closes the WS."""
        ws = FakeWebSocket([
            {"type": "hello", "d": {"heartbeat_interval": 100}},
        ])
        gw = GatewayClient("http://localhost/gateway", "tok", compress=False)
        gw._ws = ws

        # Simulate stale ack by setting _last_heartbeat_ack far in the past
        loop = asyncio.get_event_loop()
        gw._last_heartbeat_ack = loop.time() - 1000

        # The heartbeat loop should detect timeout and close ws
        # We need to run the heartbeat loop directly with a tiny interval
        gw._heartbeat_interval = 0.01
        gw._closed = False

        await gw._heartbeat_loop(ws)
        assert ws._closed is True


class TestConnectInBackground:
    @pytest.mark.asyncio
    async def test_timeout(self, monkeypatch):
        """connect_in_background raises on timeout."""
        async def mock_connect(self):
            # Never set ready event, just block
            await asyncio.sleep(999)

        monkeypatch.setattr(GatewayClient, "connect", mock_connect)

        gw = GatewayClient("http://localhost/gateway", "tok", compress=False)
        with pytest.raises(VoxGatewayError) as exc_info:
            await gw.connect_in_background(timeout=0.05)
        assert "Timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_error_propagation(self, monkeypatch):
        """connect_in_background propagates connect errors."""
        async def mock_connect(self):
            raise VoxGatewayError(4004, "AUTH_FAILED")

        monkeypatch.setattr(GatewayClient, "connect", mock_connect)

        gw = GatewayClient("http://localhost/gateway", "tok", compress=False)
        with pytest.raises(VoxGatewayError) as exc_info:
            await gw.connect_in_background(timeout=2.0)
        assert exc_info.value.code == 4004


class TestConvenienceHelpers:
    @pytest.mark.asyncio
    async def test_send_typing(self):
        """send_typing sends typing_start with feed_id."""
        ws = FakeWebSocket([])
        gw = GatewayClient("http://localhost/gateway", "tok", compress=False)
        gw._ws = ws
        await gw.send_typing(42)
        assert ws.sent[0]["type"] == "typing_start"
        assert ws.sent[0]["d"]["feed_id"] == 42

    @pytest.mark.asyncio
    async def test_update_presence(self):
        """update_presence sends presence_update with status."""
        ws = FakeWebSocket([])
        gw = GatewayClient("http://localhost/gateway", "tok", compress=False)
        gw._ws = ws
        await gw.update_presence("dnd", custom_status="busy")
        assert ws.sent[0]["type"] == "presence_update"
        assert ws.sent[0]["d"]["status"] == "dnd"
        assert ws.sent[0]["d"]["custom_status"] == "busy"
