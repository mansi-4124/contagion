"""
Shared async Redis client factory. Backed by Upstash's rediss:// TCP
endpoint (already verified in D0-12's smoke test). Lazily initialized,
reused across dedup, rate limiting, and caching — anything needing Redis
imports get_redis_client() rather than constructing its own connection.
"""

import redis.asyncio as redis_async

from app.config.settings import settings

_client: redis_async.Redis | None = None


def get_redis_client() -> redis_async.Redis:
    global _client
    if _client is None:
        _client = redis_async.from_url(settings.redis.url, decode_responses=True)
    return _client


async def reset_redis_client_for_testing() -> None:
    """Test-only helper — forces a fresh client on next get_redis_client()
    call, so tests don't leak connections/mocks across test cases."""
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None