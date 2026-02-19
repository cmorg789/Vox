import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket

from vox.db.engine import get_engine, get_session_factory, init_engine
from vox.db.models import Base
from vox.gateway.connection import Connection
from vox.gateway.hub import get_hub, init_hub
from vox.ratelimit import RateLimitMiddleware
from vox.voice.service import stop_sfu


async def _periodic_cleanup(db_factory):
    """Background task: clean expired sessions and federation nonces hourly."""
    while True:
        await asyncio.sleep(3600)
        try:
            from vox.auth.service import cleanup_expired_sessions
            from vox.db.models import FederationNonce
            from sqlalchemy import delete
            from datetime import datetime, timezone

            async with db_factory() as db:
                await cleanup_expired_sessions(db)

            async with db_factory() as db:
                now = datetime.now(timezone.utc)
                await db.execute(
                    delete(FederationNonce).where(FederationNonce.expires_at <= now)
                )
                await db.commit()
        except Exception:
            import logging
            logging.getLogger(__name__).warning("Periodic cleanup failed", exc_info=True)


def create_app(database_url: str | None = None) -> FastAPI:
    if database_url is None:
        import os
        database_url = os.environ.get("VOX_DATABASE_URL", "sqlite+aiosqlite:///vox.db")
    init_engine(database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Create tables on startup
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # SQLite ALTER TABLE migration for new columns on existing tables
            from sqlalchemy import text, inspect as sa_inspect
            def _migrate(connection):
                inspector = sa_inspect(connection)
                if "voice_states" in inspector.get_table_names():
                    cols = {c["name"] for c in inspector.get_columns("voice_states")}
                    if "server_mute" not in cols:
                        connection.execute(text("ALTER TABLE voice_states ADD COLUMN server_mute BOOLEAN DEFAULT 0 NOT NULL"))
                    if "server_deaf" not in cols:
                        connection.execute(text("ALTER TABLE voice_states ADD COLUMN server_deaf BOOLEAN DEFAULT 0 NOT NULL"))
            await conn.run_sync(_migrate)
        # Initialize storage backend
        from vox.storage import init_storage
        init_storage()
        # Load runtime-configurable limits from DB
        from vox.config import load_config
        async with get_session_factory()() as db:
            await load_config(db)
        # Initialize the gateway hub
        init_hub()
        # Start background cleanup task
        cleanup_task = asyncio.create_task(_periodic_cleanup(get_session_factory()))
        yield
        # Cancel background cleanup
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        # Shutdown SFU
        stop_sfu()
        # Close federation HTTP client
        from vox.federation.service import close_http_client
        await close_http_client()
        # Dispose engine on shutdown
        await engine.dispose()

    from vox.models.errors import ErrorEnvelope

    app = FastAPI(
        title="Vox",
        version="1.0.0",
        description="Vox chat platform API",
        lifespan=lifespan,
        responses={
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            429: {"model": ErrorEnvelope},
        },
    )

    # Rate limiting middleware
    app.add_middleware(RateLimitMiddleware)

    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "VALIDATION_ERROR", "message": str(exc)}},
        )

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
    async def gateway_websocket(ws: WebSocket, compress: str | None = None):
        hub = get_hub()
        conn = Connection(ws, hub, compress=compress)
        db_factory = get_session_factory()
        await conn.run(db_factory)

    return app
