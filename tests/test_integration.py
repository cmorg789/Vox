"""End-to-end integration smoke test.

Covers the full client lifecycle:
  register → gateway connect → identify → create feed → send message → receive event
"""

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


class TestFullLifecycle:
    """Smoke test: auth → gateway → messaging → events."""

    def test_register_connect_message_event(self, app, db):
        with TestClient(app) as tc:
            # 1. Register two users
            r1 = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            assert r1.status_code == 201
            token_a = r1.json()["token"]

            r2 = tc.post("/api/v1/auth/register", json={"username": "bob", "password": "password456"})
            assert r2.status_code == 201
            token_b = r2.json()["token"]

            # 2. Create a text feed
            r = tc.post(
                "/api/v1/feeds",
                headers={"Authorization": f"Bearer {token_a}"},
                json={"name": "general", "type": "text"},
            )
            assert r.status_code == 201
            feed_id = r.json()["feed_id"]

            # 3. Bob connects to gateway and identifies
            with tc.websocket_connect("/gateway") as ws_bob:
                hello = ws_bob.receive_json()
                assert hello["type"] == "hello"

                ws_bob.send_json({
                    "type": "identify",
                    "d": {"token": token_b, "protocol_version": 1},
                })
                ready = ws_bob.receive_json()
                assert ready["type"] == "ready"
                assert "session_id" in ready["d"]

                # 4. Alice sends a message to the feed (via REST)
                r = tc.post(
                    f"/api/v1/feeds/{feed_id}/messages",
                    headers={"Authorization": f"Bearer {token_a}"},
                    json={"body": "Hello from Alice!"},
                )
                assert r.status_code == 201
                msg_id = r.json()["msg_id"]

                # 5. Bob should receive message_create event via gateway
                event = ws_bob.receive_json()
                assert event["type"] == "message_create"
                assert event["d"]["msg_id"] == msg_id
                assert event["d"]["body"] == "Hello from Alice!"
                assert event["d"]["feed_id"] == feed_id
                assert "seq" in event

    def test_gateway_zstd_compression(self, app, db):
        """Verify zstd compression works when compress=zstd query param is set."""
        try:
            import zstandard as zstd
        except ImportError:
            pytest.skip("zstandard not installed")

        with TestClient(app) as tc:
            r = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = r.json()["token"]

            with tc.websocket_connect("/gateway?compress=zstd") as ws:
                # Server sends compressed binary frames
                raw = ws.receive_bytes()
                decompressor = zstd.ZstdDecompressor()
                data = json.loads(decompressor.decompress(raw))
                assert data["type"] == "hello"

                # Send identify (client->server is NOT compressed per spec)
                ws.send_json({
                    "type": "identify",
                    "d": {"token": token, "protocol_version": 1},
                })
                raw = ws.receive_bytes()
                ready = json.loads(decompressor.decompress(raw))
                assert ready["type"] == "ready"

    def test_friend_block_events(self, app, db):
        """Verify friend/block REST actions dispatch gateway events."""
        with TestClient(app) as tc:
            r1 = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token_a = r1.json()["token"]
            uid_a = r1.json()["user_id"]

            r2 = tc.post("/api/v1/auth/register", json={"username": "bob", "password": "password456"})
            token_b = r2.json()["token"]
            uid_b = r2.json()["user_id"]

            # Bob connects to gateway
            with tc.websocket_connect("/gateway") as ws_bob:
                ws_bob.receive_json()  # hello
                ws_bob.send_json({
                    "type": "identify",
                    "d": {"token": token_b, "protocol_version": 1},
                })
                ws_bob.receive_json()  # ready

                # Alice adds Bob as friend
                r = tc.put(
                    f"/api/v1/users/@me/friends/{uid_b}",
                    headers={"Authorization": f"Bearer {token_a}"},
                )
                assert r.status_code == 204

                event = ws_bob.receive_json()
                assert event["type"] == "friend_request"
                assert event["d"]["user_id"] == uid_a
                assert event["d"]["target_id"] == uid_b

                # Alice blocks Bob
                r = tc.put(
                    f"/api/v1/users/@me/blocks/{uid_b}",
                    headers={"Authorization": f"Bearer {token_a}"},
                )
                assert r.status_code == 204

                event = ws_bob.receive_json()
                assert event["type"] == "block_add"

    def test_cursor_pagination(self, app, db):
        """Verify cursor-based pagination on list endpoints."""
        with TestClient(app) as tc:
            r = tc.post("/api/v1/auth/register", json={"username": "alice", "password": "password123"})
            token = r.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            # Create several invites
            for _ in range(3):
                tc.post("/api/v1/invites", headers=headers, json={})

            # Fetch with limit=2
            r = tc.get("/api/v1/invites?limit=2", headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert len(data["items"]) == 2
            assert data["cursor"] is not None

            # Fetch next page using cursor
            r = tc.get(f"/api/v1/invites?limit=2&after={data['cursor']}", headers=headers)
            assert r.status_code == 200
            data2 = r.json()
            assert len(data2["items"]) == 1
