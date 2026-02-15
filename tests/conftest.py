import pytest
from httpx import ASGITransport, AsyncClient

from vox.api.app import create_app
from vox.db.engine import get_engine
from vox.db.models import Base
from vox.interactions import reset as reset_interactions
from vox.ratelimit import reset as reset_ratelimit


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
    reset_ratelimit()
    reset_interactions()
    yield
    reset_ratelimit()
    reset_interactions()


@pytest.fixture()
async def client(app, db):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
