from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Default to async SQLite for development. Override with Postgres URI for production:
#   postgresql+asyncpg://user:pass@host/dbname
_engine = None
_session_factory = None


def init_engine(database_url: str):
    global _engine, _session_factory
    _engine = create_async_engine(database_url)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def get_engine():
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_engine() first.")
    return _engine


def get_session_factory():
    if _session_factory is None:
        raise RuntimeError("Database engine not initialized. Call init_engine() first.")
    return _session_factory
