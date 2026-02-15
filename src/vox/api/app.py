from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket

from vox.db.engine import get_engine, get_session_factory, init_engine
from vox.db.models import Base
from vox.gateway.connection import Connection
from vox.gateway.hub import get_hub, init_hub
from vox.ratelimit import RateLimitMiddleware
from vox.voice.service import stop_sfu


def create_app(database_url: str) -> FastAPI:
    init_engine(database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Create tables on startup
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # Ensure uploads directory exists
        Path("uploads").mkdir(exist_ok=True)
        # Initialize the gateway hub
        init_hub()
        yield
        # Shutdown SFU
        stop_sfu()
        # Dispose engine on shutdown
        await engine.dispose()

    app = FastAPI(title="Vox", lifespan=lifespan)

    # Rate limiting middleware
    app.add_middleware(RateLimitMiddleware)

    # Register routers
    from vox.api.auth import router as auth_router
    from vox.api.users import router as users_router
    from vox.api.server import router as server_router
    from vox.api.members import router as members_router
    from vox.api.invites import router as invites_router
    from vox.api.roles import router as roles_router
    from vox.api.channels import router as channels_router
    from vox.api.messages import router as messages_router
    from vox.api.dms import router as dms_router
    from vox.api.webhooks import router as webhooks_router
    from vox.api.bots import router as bots_router
    from vox.api.e2ee import router as e2ee_router
    from vox.api.moderation import router as moderation_router
    from vox.api.emoji import router as emoji_router
    from vox.api.voice import router as voice_router
    from vox.api.gateway_info import router as gateway_info_router
    from vox.api.search import router as search_router
    from vox.api.files import router as files_router
    from vox.api.embeds import router as embeds_router
    from vox.api.sync import router as sync_router
    from vox.api.federation import router as federation_router

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(server_router)
    app.include_router(members_router)
    app.include_router(invites_router)
    app.include_router(roles_router)
    app.include_router(channels_router)
    app.include_router(messages_router)
    app.include_router(dms_router)
    app.include_router(webhooks_router)
    app.include_router(bots_router)
    app.include_router(e2ee_router)
    app.include_router(moderation_router)
    app.include_router(emoji_router)
    app.include_router(voice_router)
    app.include_router(gateway_info_router)
    app.include_router(search_router)
    app.include_router(files_router)
    app.include_router(embeds_router)
    app.include_router(sync_router)
    app.include_router(federation_router)

    @app.websocket("/gateway")
    async def gateway_websocket(ws: WebSocket):
        hub = get_hub()
        conn = Connection(ws, hub)
        db_factory = get_session_factory()
        await conn.run(db_factory)

    return app
