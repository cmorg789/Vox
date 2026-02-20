import os

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Default to async SQLite for development. Override with Postgres URI for production:
#   postgresql+asyncpg://user:pass@host/dbname
_engine = None
_session_factory = None


def init_engine(database_url: str):
    global _engine, _session_factory

    kwargs: dict = {}
    is_sqlite = database_url.startswith("sqlite")

    if is_sqlite:
        kwargs["connect_args"] = {"timeout": 30}
    else:
        kwargs["pool_size"] = int(os.environ.get("VOX_DB_POOL_SIZE", "10"))
        kwargs["max_overflow"] = int(os.environ.get("VOX_DB_MAX_OVERFLOW", "20"))
        kwargs["pool_recycle"] = int(os.environ.get("VOX_DB_POOL_RECYCLE", "1800"))
        kwargs["pool_pre_ping"] = True

    _engine = create_async_engine(database_url, **kwargs)

    if is_sqlite:
        @event.listens_for(_engine.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def get_engine():
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_engine() first.")
    return _engine


def get_session_factory():
    if _session_factory is None:
        raise RuntimeError("Database engine not initialized. Call init_engine() first.")
    return _session_factory
