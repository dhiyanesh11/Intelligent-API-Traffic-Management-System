"""Atomic Redis limiters. Each check and state update executes as one Lua script."""
import math
from redis.asyncio import Redis

TOKEN_BUCKET_LUA = """
local time = redis.call('TIME')
local now = tonumber(time[1]) + tonumber(time[2]) / 1000000
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
local state = redis.call('HMGET', KEYS[1], 'tokens', 'updated')
local tokens = tonumber(state[1]) or capacity
local updated = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now - updated) * refill)
local allowed = 0
local retry = 0
if tokens >= 1 then
  allowed = 1
  tokens = tokens - 1
else
  retry = math.ceil((1 - tokens) / refill)
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated', now)
redis.call('EXPIRE', KEYS[1], ttl)
return {allowed, math.floor(tokens), retry}
"""

SLIDING_WINDOW_LUA = """
local time = redis.call('TIME')
local now = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local member = ARGV[3]
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local count = redis.call('ZCARD', KEYS[1])
local allowed = 0
local retry = 0
if count < limit then
  redis.call('ZADD', KEYS[1], now, member)
  count = count + 1
  allowed = 1
else
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  retry = math.max(1, math.ceil((tonumber(oldest[2]) + window - now) / 1000))
end
redis.call('PEXPIRE', KEYS[1], window)
return {allowed, math.max(0, limit - count), retry}
"""

class RateLimiter:
    def __init__(self, redis: Redis):
        self.token_bucket = redis.register_script(TOKEN_BUCKET_LUA)
        self.sliding_window = redis.register_script(SLIDING_WINDOW_LUA)

    async def check(self, *, key: str, algorithm: str, limit: int, window_seconds: int, request_id: str) -> tuple[bool, int, int]:
        limit = max(1, int(limit))
        window_seconds = max(1, int(window_seconds))
        if algorithm == "sliding_window":
            result = await self.sliding_window(keys=[key], args=[window_seconds * 1000, limit, request_id])
        else:
            refill = limit / window_seconds
            ttl = max(window_seconds * 2, math.ceil(limit / refill * 2))
            result = await self.token_bucket(keys=[key], args=[limit, refill, ttl])
        return bool(int(result[0])), int(result[1]), int(result[2])
