import asyncio
import os
import pytest
from redis.asyncio import Redis
from gateway.app.limiters import RateLimiter

REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")

@pytest.mark.asyncio
async def test_sliding_window_is_atomic_under_concurrency():
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    key = "test:limiter:concurrent"
    await redis.delete(key)
    limiter = RateLimiter(redis)
    results = await asyncio.gather(*(limiter.check(key=key, algorithm="sliding_window", limit=50, window_seconds=10, request_id=str(i)) for i in range(100)))
    assert sum(allowed for allowed, _, _ in results) == 50
    await redis.delete(key)
    await redis.aclose()

@pytest.mark.asyncio
async def test_token_bucket_blocks_until_refill():
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    key = "test:limiter:bucket"
    await redis.delete(key)
    limiter = RateLimiter(redis)
    results = await asyncio.gather(*(limiter.check(key=key, algorithm="token_bucket", limit=5, window_seconds=60, request_id=str(i)) for i in range(8)))
    assert sum(allowed for allowed, _, _ in results) == 5
    assert max(retry for allowed, _, retry in results if not allowed) > 0
    await redis.delete(key)
    await redis.aclose()
