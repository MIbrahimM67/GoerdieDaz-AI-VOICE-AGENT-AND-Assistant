"""
GeordieDaz — Async Redis Client
Provides a connection pool for all Redis operations.
"""
import redis.asyncio as aioredis

from app.config import get_settings

settings = get_settings()

# Module-level pool — created once at startup
_redis_pool: aioredis.ConnectionPool | None = None
_redis_client: aioredis.Redis | None = None


def get_redis_pool() -> aioredis.ConnectionPool:
    """Return the shared connection pool, creating it if needed."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=50,
            decode_responses=True,  # Return strings directly, no manual .decode()
        )
    return _redis_pool


def get_redis() -> aioredis.Redis:
    """Return the shared Redis client instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.Redis(connection_pool=get_redis_pool())
    return _redis_client


async def close_redis():
    """Gracefully close the Redis connection pool on shutdown."""
    global _redis_client, _redis_pool
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None
