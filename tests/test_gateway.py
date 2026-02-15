import json

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
