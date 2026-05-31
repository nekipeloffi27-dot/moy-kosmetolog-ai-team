"""asyncpg connection pool. Single shared pool across the app."""
from __future__ import annotations

import asyncpg
from loguru import logger

from core.config import get_settings

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    """Create the global pool. Idempotent."""
    global _pool
    if _pool is not None:
        return _pool

    settings = get_settings()
    logger.info("Connecting to Postgres at {}:{}/{}", settings.postgres_host, settings.postgres_port, settings.postgres_db)
    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    logger.info("Postgres pool created")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Postgres pool closed")


def get_pool() -> asyncpg.Pool:
    """Return the global pool. init_pool() must have been called."""
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_pool() at startup")
    return _pool


async def health_check() -> bool:
    """Returns True if DB responds to SELECT 1."""
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            return result == 1
    except Exception as e:
        logger.error("DB health check failed: {}", e)
        return False
