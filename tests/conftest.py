import os

import pytest
from httpx import ASGITransport, AsyncClient

from vox.api.app import create_app
from vox.db.engine import get_engine
from vox.db.models import Base
from vox.interactions import reset as reset_interactions
from vox.ratelimit import reset as reset_ratelimit
from vox.voice.service import reset as reset_voice


def _reset_config():
    """Reset the in-memory config singleton to defaults."""
    import vox.config as _cfg
    _cfg._db_values.clear()
    _cfg._reload_all()

# Use port 0 so each SFU picks a random free port (avoids conflicts)
os.environ.setdefault("VOX_MEDIA_BIND", "127.0.0.1:0")


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


@pytest.fixture()
async def client(app, db):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
