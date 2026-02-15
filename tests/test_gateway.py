import json
import time

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from vox.api.app import create_app
from vox.db.engine import get_engine
from vox.db.models import Base
from vox.gateway.hub import init_hub


@pytest.fixture()
def app():
    return create_app("sqlite+aiosqlite://")


@pytest.fixture()
async def db(app):
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    init_hub()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture()
async def client(app, db):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def _register(client: AsyncClient, username: str = "alice", password: str = "password123") -> str:
    resp = await client.post("/api/v1/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 201
    return resp.json()["token"]


class TestGatewayConnect:
    """Test basic WebSocket connection flow."""

    def test_hello_on_connect(self, app, db):
        """Connect -> receive hello with heartbeat_interval."""
        with TestClient(app) as tc:
            with tc.websocket_connect("/gateway") as ws:
                data = ws.receive_json()
                assert data["type"] == "hello"
                assert "heartbeat_interval" in data["d"]
                assert data["d"]["heartbeat_interval"] == 45000

    def test_no_identify_timeout(self, app, db):
        """If client sends nothing, connection closes with 4003."""
        # We can't easily test the timeout without waiting 30s,
        # so test sending a non-identify message instead
        with TestClient(app) as tc:
            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "heartbeat"})
                # Should get closed with 4003 NOT_AUTHENTICATED
                with pytest.raises(Exception):
                    ws.receive_json()


class TestGatewayIdentify:
    """Test identify flow."""

    def test_identify_success(self, app, db):
        """Send identify with valid token -> receive ready."""
        with TestClient(app) as tc:
            # Register a user first
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            assert resp.status_code == 201
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                hello = ws.receive_json()
                assert hello["type"] == "hello"

                ws.send_json({
                    "type": "identify",
                    "d": {"token": token, "protocol_version": 1}
                })

                ready = ws.receive_json()
                assert ready["type"] == "ready"
                assert "seq" in ready
                assert ready["seq"] == 1
                assert ready["d"]["user_id"] is not None
                assert "session_id" in ready["d"]
                assert ready["d"]["server_name"] == "Vox Server"

    def test_identify_bad_token(self, app, db):
        """Send identify with invalid token -> close 4004."""
        with TestClient(app) as tc:
            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({
                    "type": "identify",
                    "d": {"token": "vox_sess_invalid_token"}
                })
                with pytest.raises(Exception):
                    ws.receive_json()

    def test_identify_empty_token(self, app, db):
        """Send identify with empty token -> close 4004."""
        with TestClient(app) as tc:
            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({
                    "type": "identify",
                    "d": {"token": ""}
                })
                with pytest.raises(Exception):
                    ws.receive_json()

    def test_double_identify(self, app, db):
        """Send identify twice -> close 4005 ALREADY_AUTHENTICATED."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ws.receive_json()  # ready

                ws.send_json({"type": "identify", "d": {"token": token}})
                with pytest.raises(Exception):
                    ws.receive_json()


class TestGatewayHeartbeat:
    """Test heartbeat flow."""

    def test_heartbeat_ack(self, app, db):
        """Send heartbeat after identify -> receive heartbeat_ack."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ws.receive_json()  # ready

                ws.send_json({"type": "heartbeat"})
                ack = ws.receive_json()
                assert ack["type"] == "heartbeat_ack"


class TestGatewayEvents:
    """Test that REST actions dispatch events to WS clients."""

    def test_message_create_event(self, app, db):
        """Send message via REST -> receive message_create on WS."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            # Create a feed
            feed_resp = tc.post("/api/v1/feeds", json={"name": "general", "type": "text"}, headers=headers)
            assert feed_resp.status_code == 201
            feed_id = feed_resp.json()["feed_id"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ws.receive_json()  # ready

                # Send message via REST
                msg_resp = tc.post(
                    f"/api/v1/feeds/{feed_id}/messages",
                    json={"body": "Hello, world!"},
                    headers=headers,
                )
                assert msg_resp.status_code == 201

                # Should receive message_create event
                event = ws.receive_json()
                assert event["type"] == "message_create"
                assert "seq" in event
                assert event["d"]["body"] == "Hello, world!"
                assert event["d"]["feed_id"] == feed_id

    def test_feed_create_event(self, app, db):
        """Create feed via REST -> receive feed_create on WS."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ws.receive_json()  # ready

                # Create feed
                tc.post("/api/v1/feeds", json={"name": "announcements", "type": "text"}, headers=headers)

                event = ws.receive_json()
                assert event["type"] == "feed_create"
                assert event["d"]["name"] == "announcements"

    def test_member_join_event(self, app, db):
        """Join server -> receive member_join on WS."""
        with TestClient(app) as tc:
            # Register first user (admin-like)
            resp1 = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token1 = resp1.json()["token"]
            headers1 = {"Authorization": f"Bearer {token1}"}

            # Create an invite before WS connects (so no event to drain)
            invite_resp = tc.post("/api/v1/invites", json={}, headers=headers1)
            assert invite_resp.status_code == 201
            code = invite_resp.json()["code"]

            # Register second user
            resp2 = tc.post("/api/v1/auth/register", json={"username": "bob", "password": "password123"})
            token2 = resp2.json()["token"]
            headers2 = {"Authorization": f"Bearer {token2}"}

            # Connect alice on WS
            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token1}})
                ws.receive_json()  # ready

                # Bob joins
                ws.send_json({"type": "heartbeat"})
                ws.receive_json()  # heartbeat_ack

                tc.post("/api/v1/members/@me/join", json={"invite_code": code}, headers=headers2)

                event = ws.receive_json()
                assert event["type"] == "member_join"
                assert event["d"]["user_id"] is not None

    def test_role_create_event(self, app, db):
        """Create role via REST -> receive role_create on WS."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ws.receive_json()  # ready

                ws.send_json({"type": "heartbeat"})
                ws.receive_json()  # heartbeat_ack

                tc.post("/api/v1/roles", json={"name": "moderator", "color": 0xFF0000, "permissions": 0, "position": 1}, headers=headers)

                event = ws.receive_json()
                assert event["type"] == "role_create"
                assert event["d"]["name"] == "moderator"

    def test_server_update_event(self, app, db):
        """Update server -> receive server_update on WS."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ws.receive_json()  # ready

                tc.patch("/api/v1/server", json={"name": "Cool Server"}, headers=headers)

                event = ws.receive_json()
                assert event["type"] == "server_update"
                assert event["d"]["name"] == "Cool Server"


class TestGatewaySequence:
    """Test sequence number tracking."""

    def test_seq_increments(self, app, db):
        """Sequence numbers increment with each event."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello (no seq)
                ws.send_json({"type": "identify", "d": {"token": token}})
                ready = ws.receive_json()  # ready (seq=1)
                assert ready["seq"] == 1

                # Create two feeds
                tc.post("/api/v1/feeds", json={"name": "feed1", "type": "text"}, headers=headers)
                evt1 = ws.receive_json()
                assert evt1["seq"] == 2

                tc.post("/api/v1/feeds", json={"name": "feed2", "type": "text"}, headers=headers)
                evt2 = ws.receive_json()
                assert evt2["seq"] == 3


class TestGatewayProtocol:
    """Test protocol edge cases."""

    def test_invalid_json(self, app, db):
        """Send invalid JSON -> close 4002."""
        with TestClient(app) as tc:
            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_text("not json at all{{{")
                with pytest.raises(Exception):
                    ws.receive_json()

    def test_typing_relay(self, app, db):
        """Typing events are relayed to other connected users."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ws.receive_json()  # ready

                ws.send_json({"type": "typing", "d": {"feed_id": 1}})
                event = ws.receive_json()
                assert event["type"] == "typing_start"
                assert event["d"]["feed_id"] == 1


class TestVersionNegotiation:
    """Test protocol version negotiation."""

    def test_version_mismatch_too_high(self, app, db):
        """Identify with unsupported version -> close 4011."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({
                    "type": "identify",
                    "d": {"token": token, "protocol_version": 99}
                })
                with pytest.raises(Exception):
                    ws.receive_json()

    def test_version_mismatch_zero(self, app, db):
        """Identify with version 0 -> close 4011."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({
                    "type": "identify",
                    "d": {"token": token, "protocol_version": 0}
                })
                with pytest.raises(Exception):
                    ws.receive_json()

    def test_version_default_accepted(self, app, db):
        """Identify without protocol_version defaults to 1 and succeeds."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({
                    "type": "identify",
                    "d": {"token": token}
                })
                ready = ws.receive_json()
                assert ready["type"] == "ready"
                assert ready["d"]["protocol_version"] == 1


class TestReadyEvent:
    """Test ready event completeness."""

    def test_ready_has_server_time(self, app, db):
        """Ready event includes server_time as unix timestamp."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ready = ws.receive_json()
                assert ready["type"] == "ready"
                assert "server_time" in ready["d"]
                # Should be a reasonable unix timestamp (after 2024)
                assert ready["d"]["server_time"] > 1700000000

    def test_ready_has_display_name(self, app, db):
        """Ready event includes display_name."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ready = ws.receive_json()
                assert ready["d"]["display_name"] == "alice"


class TestResume:
    """Test session resume via hub session store."""

    def test_resume_session_expired(self, app, db):
        """Resume with unknown session_id -> close 4009."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({
                    "type": "resume",
                    "d": {"token": token, "session_id": "sess_nonexistent", "last_seq": 0}
                })
                with pytest.raises(Exception):
                    ws.receive_json()

    def test_resume_replays_events(self, app, db):
        """Disconnect and resume -> replays missed events."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            # First connection: identify, get session_id, generate some events
            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ready = ws.receive_json()
                session_id = ready["d"]["session_id"]
                assert ready["seq"] == 1

                # Create a feed to get seq=2
                tc.post("/api/v1/feeds", json={"name": "general", "type": "text"}, headers=headers)
                evt = ws.receive_json()
                assert evt["seq"] == 2

            # Second connection: resume from seq=1 -> should replay seq=2
            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({
                    "type": "resume",
                    "d": {"token": token, "session_id": session_id, "last_seq": 1}
                })
                # Should get the feed_create event replayed
                replayed = ws.receive_json()
                assert replayed["seq"] == 2
                assert replayed["type"] == "feed_create"

    def test_resume_wrong_user(self, app, db):
        """Resume with different user's token -> close 4004."""
        with TestClient(app) as tc:
            resp1 = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token1 = resp1.json()["token"]
            resp2 = tc.post("/api/v1/auth/register", json={"username": "bob", "password": "password123"})
            token2 = resp2.json()["token"]

            # Alice connects and gets a session
            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token1}})
                ready = ws.receive_json()
                session_id = ready["d"]["session_id"]

            # Bob tries to resume Alice's session
            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({
                    "type": "resume",
                    "d": {"token": token2, "session_id": session_id, "last_seq": 0}
                })
                with pytest.raises(Exception):
                    ws.receive_json()


class TestRelayHandlers:
    """Test client->server relay handlers."""

    def test_mls_relay(self, app, db):
        """MLS relay broadcasts to same user's connections."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ws.receive_json()  # ready

                ws.send_json({
                    "type": "mls_relay",
                    "d": {"mls_type": "welcome", "data": "base64data"}
                })
                event = ws.receive_json()
                assert event["type"] == "mls_welcome"
                assert event["d"]["data"] == "base64data"

    def test_cpace_relay(self, app, db):
        """CPace relay broadcasts to same user's connections."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ws.receive_json()  # ready

                ws.send_json({
                    "type": "cpace_relay",
                    "d": {"cpace_type": "isi", "pair_id": "pair_123", "data": "sharedata"}
                })
                event = ws.receive_json()
                assert event["type"] == "cpace_isi"
                assert event["d"]["pair_id"] == "pair_123"
                assert event["d"]["data"] == "sharedata"

    def test_voice_codec_neg_relay(self, app, db):
        """Voice codec neg broadcasts to all."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ws.receive_json()  # ready

                ws.send_json({
                    "type": "voice_codec_neg",
                    "d": {"media_type": "video", "codec": "av1", "spatial_layers": 3}
                })
                event = ws.receive_json()
                assert event["type"] == "voice_codec_neg"
                assert event["d"]["media_type"] == "video"
                assert event["d"]["codec"] == "av1"
                assert event["d"]["spatial_layers"] == 3

    def test_stage_response_relay(self, app, db):
        """Stage response broadcasts to all."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ws.receive_json()  # ready

                ws.send_json({
                    "type": "stage_response",
                    "d": {"room_id": 5, "response_type": "request_ack", "accepted": True}
                })
                event = ws.receive_json()
                assert event["type"] == "stage_response"
                assert event["d"]["room_id"] == 5
                assert event["d"]["accepted"] is True

    def test_unknown_type_ignored(self, app, db):
        """Unknown message types are silently ignored."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ws.receive_json()  # ready

                # Send unknown type
                ws.send_json({"type": "totally_made_up", "d": {}})

                # Should still be alive — send heartbeat to verify
                ws.send_json({"type": "heartbeat"})
                ack = ws.receive_json()
                assert ack["type"] == "heartbeat_ack"

    def test_cpace_new_device_key_with_nonce(self, app, db):
        """CPace new_device_key relay includes nonce parameter."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ws.receive_json()  # ready

                ws.send_json({
                    "type": "cpace_relay",
                    "d": {
                        "cpace_type": "new_device_key",
                        "pair_id": "pair_456",
                        "data": "keydata",
                        "nonce": "abc123",
                    }
                })
                event = ws.receive_json()
                assert event["type"] == "cpace_new_device_key"
                assert event["d"]["pair_id"] == "pair_456"
                assert event["d"]["data"] == "keydata"
                assert event["d"]["nonce"] == "abc123"

    def test_presence_update_message(self, app, db):
        """Presence update message dispatches presence_update event."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ws.receive_json()  # ready

                ws.send_json({
                    "type": "presence_update",
                    "d": {"status": "idle"}
                })
                event = ws.receive_json()
                assert event["type"] == "presence_update"
                assert event["d"]["status"] == "idle"


class TestResumeReplayExhausted:
    """Test resume with stale sequence number."""

    def test_resume_stale_seq_replay_exhausted(self, app, db):
        """Resume with last_seq older than replay buffer -> close 4010."""
        from vox.gateway.hub import get_hub, SessionState
        from collections import deque

        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            # First connection: identify, get session_id
            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ready = ws.receive_json()
                session_id = ready["d"]["session_id"]

                # Generate some events so replay buffer has entries
                tc.post("/api/v1/feeds", json={"name": "feed1", "type": "text"}, headers=headers)
                ws.receive_json()  # seq=2
                tc.post("/api/v1/feeds", json={"name": "feed2", "type": "text"}, headers=headers)
                ws.receive_json()  # seq=3

            # Now resume with last_seq=0 — oldest buffered is seq=1 (ready)
            # This should succeed since seq=0 < oldest=1 but...
            # Let's manipulate the hub to have a buffer starting at seq=50
            hub = get_hub()
            session = hub.get_session(session_id)
            assert session is not None
            # Clear buffer and add events with high seq numbers
            session.replay_buffer = deque(maxlen=1000)
            session.replay_buffer.append({"type": "test", "seq": 50})
            session.replay_buffer.append({"type": "test", "seq": 51})

            # Resume with last_seq=10, which is < oldest_seq=50 -> REPLAY_EXHAUSTED
            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({
                    "type": "resume",
                    "d": {"token": token, "session_id": session_id, "last_seq": 10}
                })
                with pytest.raises(Exception):
                    ws.receive_json()


class TestVoiceStateUpdate:
    """Test voice_state_update message in gateway."""

    def test_voice_state_update_message(self, app, db):
        """Send voice_state_update modifies voice state in DB."""
        from unittest.mock import MagicMock, patch as _patch
        from vox.voice import service as voice_service

        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            # Create a voice room and join
            room_resp = tc.post("/api/v1/rooms", json={"name": "Voice", "type": "voice"}, headers=headers)
            room_id = room_resp.json()["room_id"]

            join_resp = tc.post(f"/api/v1/rooms/{room_id}/voice/join", json={}, headers=headers)
            assert join_resp.status_code == 200

            with tc.websocket_connect("/gateway") as ws:
                ws.receive_json()  # hello
                ws.send_json({"type": "identify", "d": {"token": token}})
                ws.receive_json()  # ready

                # Send voice state update
                ws.send_json({
                    "type": "voice_state_update",
                    "d": {"self_mute": True, "self_deaf": False}
                })
                event = ws.receive_json()
                assert event["type"] == "voice_state_update"
                assert event["d"]["room_id"] == room_id
                # Check that the mute flag is reflected
                members = event["d"]["members"]
                assert len(members) >= 1
                me = [m for m in members if m["user_id"] == 1][0]
                assert me["mute"] is True


class TestGatewayCompression:
    """Test zstd compression on send_event."""

    def test_send_event_with_zstd_compression(self, app, db):
        """Connecting with compress=zstd sends binary compressed frames."""
        with TestClient(app) as tc:
            resp = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = resp.json()["token"]

            with tc.websocket_connect("/gateway?compress=zstd") as ws:
                # Hello is sent via send_json, which uses compression if available
                data = ws.receive_bytes()
                import zstandard as zstd
                decompressor = zstd.ZstdDecompressor()
                hello = json.loads(decompressor.decompress(data))
                assert hello["type"] == "hello"
