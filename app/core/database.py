"""Async SQLAlchemy engine.

Works against either a local Postgres (docker compose) or Supabase's hosted
Postgres. For Supabase we:

* require TLS (``db_ssl`` / auto-detected from the host), and
* disable asyncpg's prepared-statement cache so the connection survives
  Supabase's transaction pooler (pgBouncer), which does not support
  prepared statements.

See ``SUPABASE.md`` for the connection-string formats.
"""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()


def _build_connect_args() -> dict:
    """asyncpg connect args derived from settings."""
    args: dict = {}
    # Disable prepared-statement caching for pgBouncer/transaction-pooler
    # compatibility. Harmless on a direct connection.
    if settings.db_statement_cache_size is not None:
        args["statement_cache_size"] = settings.db_statement_cache_size
    # Supabase requires TLS. asyncpg accepts libpq-style ssl mode strings.
    if settings.db_ssl or settings.is_supabase:
        args["ssl"] = "require"
    return args


engine = create_async_engine(
    settings.database_url,
    echo=not settings.is_production,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    connect_args=_build_connect_args(),
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
