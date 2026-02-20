import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from vox.db.engine import get_engine, get_session_factory, init_engine
from vox.db.models import Base
from vox.gateway.connection import Connection
from vox.gateway.hub import get_hub, init_hub
from vox.ratelimit import RateLimitMiddleware
from vox.voice.service import stop_sfu

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Configure structured JSON logging (or plain text for dev)."""
    log_format = os.environ.get("VOX_LOG_FORMAT", "json")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Remove existing handlers
    for h in root.handlers[:]:
        root.removeHandler(h)
    handler = logging.StreamHandler()
    if log_format == "json":
        import json as _json

        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                d = {
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                if record.exc_info:
                    d["exception"] = self.formatException(record.exc_info)
                return _json.dumps(d)

        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)


async def _periodic_cleanup(db_factory):
    """Background task: clean expired sessions, federation nonces, event log, rate limiter, and presence hourly."""
    while True:
        await asyncio.sleep(3600)
        from vox.auth.service import cleanup_expired_sessions
        from vox.db.models import EventLog, FederationNonce
        from sqlalchemy import delete
        from datetime import datetime, timezone
        import time

        # Each step runs independently so one failure doesn't block the rest
        try:
            async with db_factory() as db:
                await cleanup_expired_sessions(db)
        except Exception:
            logger.error("Periodic cleanup: session cleanup failed", exc_info=True)

        try:
            async with db_factory() as db:
                now = datetime.now(timezone.utc)
                await db.execute(
                    delete(FederationNonce).where(FederationNonce.expires_at <= now)
                )
                await db.commit()
        except Exception:
            logger.error("Periodic cleanup: nonce cleanup failed", exc_info=True)

        try:
            async with db_factory() as db:
                retention_ms = 7 * 24 * 60 * 60 * 1000  # 7 days
                cutoff_ts = int(time.time() * 1000) - retention_ms
                cutoff_snowflake = cutoff_ts << 22
                await db.execute(
                    delete(EventLog).where(EventLog.id < cutoff_snowflake)
                )
                await db.commit()
        except Exception:
            logger.error("Periodic cleanup: event log cleanup failed", exc_info=True)

        try:
            from vox.ratelimit import evict_stale, evict_token_cache
            evict_stale()
            evict_token_cache()
        except Exception:
            logger.error("Periodic cleanup: rate limiter eviction failed", exc_info=True)

        try:
            hub = get_hub()
            hub.cleanup_orphaned_presence()
            hub.cleanup_auth_failures()
        except Exception:
            logger.error("Periodic cleanup: presence/auth cleanup failed", exc_info=True)


# --- Health and readiness endpoints ---
_health_router = APIRouter(tags=["health"])


@_health_router.get("/health")
async def health():
    return {"status": "ok"}


@_health_router.get("/ready")
async def ready():
    from sqlalchemy import text
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"status": "unavailable"})


def create_app(database_url: str | None = None) -> FastAPI:
    if database_url is None:
        database_url = os.environ.get("VOX_DATABASE_URL", "sqlite+aiosqlite:///vox.db")
    init_engine(database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Configure logging
        _configure_logging()

        # Create tables on startup
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # Initialize storage backend
        from vox.storage import init_storage
        init_storage()
        # Load runtime-configurable limits from DB
        from vox.config import load_config
        async with get_session_factory()() as db:
            await load_config(db)
        # Initialize the gateway hub
        init_hub()

        # Startup warnings
        from vox.config import config
        if config.webauthn.rp_id is None:
            logger.warning("WebAuthn is not configured (VOX_WEBAUTHN_RP_ID / VOX_WEBAUTHN_ORIGIN not set)")
        logger.warning(
            "Vox uses in-memory state (rate limiter, gateway hub, presence). "
            "Run with a single worker process only."
        )

        # Start background cleanup task
        cleanup_task = asyncio.create_task(_periodic_cleanup(get_session_factory()))
        yield
        # Graceful WebSocket shutdown
        hub = get_hub()
        await hub.close_all(4008, "Server restarting")
        await asyncio.sleep(1)
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

    # Body size limit middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from fastapi.responses import JSONResponse

    _UPLOAD_PATHS = frozenset({"/api/v1/files", "/api/v1/emoji", "/api/v1/server/icon"})

    class BodySizeLimitMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.method in ("POST", "PUT", "PATCH"):
                # Skip upload routes — they enforce their own limits
                if not any(request.url.path.startswith(p) for p in _UPLOAD_PATHS):
                    from vox.config import config as _cfg
                    cl = int(request.headers.get("content-length", 0))
                    if cl > _cfg.limits.max_request_body:
                        return JSONResponse(
                            status_code=413,
                            content={"error": {"code": "PAYLOAD_TOO_LARGE", "message": f"Request body exceeds maximum of {_cfg.limits.max_request_body} bytes."}},
                        )
            return await call_next(request)

    app.add_middleware(BodySizeLimitMiddleware)

    from fastapi.exceptions import RequestValidationError

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

    app.include_router(_health_router)
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
