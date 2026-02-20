"""Shared fixtures for SDK integration tests.

These tests wire the SDK client directly to the in-memory ASGI app
via ASGITransport, so no real network I/O is needed for REST tests.
Gateway tests use a real uvicorn server on a random port.
"""

from __future__ import annotations

import asyncio
import os

import pytest
import uvicorn
from httpx import ASGITransport, AsyncClient

from vox.api.app import create_app
from vox.db.engine import get_engine
from vox.db.models import Base
from vox.interactions import reset as reset_interactions
from vox.ratelimit import reset as reset_ratelimit
from vox.voice.service import reset as reset_voice

from vox_sdk import Client
from vox_sdk.models.auth import RegisterResponse

# Use port 0 so each SFU picks a random free port (avoids conflicts)
os.environ.setdefault("VOX_MEDIA_BIND", "127.0.0.1:0")


def _reset_config():
    """Reset the in-memory config singleton to defaults."""
    import vox.config as _cfg
    _cfg._db_values.clear()
    _cfg._reload_all()


# ---------------------------------------------------------------------------
# Server fixtures (mirrored from tests/conftest.py)
# ---------------------------------------------------------------------------

@pytest.fixture()
def app():
    return create_app("sqlite+aiosqlite://")


@pytest.fixture()
async def db(app):
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(autouse=True)
def _clear_state():
    _reset_config()
    reset_ratelimit()
    reset_interactions()
    reset_voice()
    yield
    _reset_config()
    reset_ratelimit()
    reset_interactions()
    reset_voice()


# ---------------------------------------------------------------------------
# SDK helpers
# ---------------------------------------------------------------------------

async def make_sdk_client(app) -> Client:
    """Create an SDK Client wired to the ASGI app."""
    c = Client("http://test")
    await c.http._client.aclose()
    c.http._client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return c


async def register(sdk: Client, username: str, password: str) -> RegisterResponse:
    """Register a user and store the token on the client."""
    resp = await sdk.auth.register(username, password)
    sdk.http.token = resp.token
    return resp


# ---------------------------------------------------------------------------
# SDK fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
async def sdk(app, db):
    """Yield an SDK Client wired to the ASGI app."""
    c = await make_sdk_client(app)
    yield c
    await c.close()


# ---------------------------------------------------------------------------
# Live server (for gateway / WebSocket tests)
# ---------------------------------------------------------------------------

@pytest.fixture()
async def live_server(app, db):
    """Start uvicorn on a random port, yield the base URL, then shut down."""
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    await task


async def make_live_sdk_client(base_url: str) -> Client:
    """Create an SDK Client pointed at the live server (real HTTP)."""
    return Client(base_url)


async def register_live(client: Client, username: str, password: str) -> RegisterResponse:
    """Register a user via real HTTP and store the token on the client."""
    resp = await client.auth.register(username, password)
    client.http.token = resp.token
    return resp
