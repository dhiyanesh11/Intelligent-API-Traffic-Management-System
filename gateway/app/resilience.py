"""Redis-backed health, circuit-breaker, retry and GET cache helpers."""
import hashlib
import json
import asyncio
import random
from sqlalchemy import select
from app.database import Session
from app.models import Backend
from app.metrics import CIRCUIT
from redis.asyncio import Redis

FAILURE_LUA = """
local failures = redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], 60)
if failures >= tonumber(ARGV[1]) then
  redis.call('SET', KEYS[2], 'open', 'EX', tonumber(ARGV[2]))
  return 1
end
return failures
"""

class Resilience:
    def __init__(self, redis: Redis):
        self.redis = redis
        self.failure_script = redis.register_script(FAILURE_LUA)

    async def is_circuit_open(self, backend: str) -> bool:
        return await self.redis.get(f"circuit:{backend}") == "open"

    async def success(self, backend: str):
        await self.redis.delete(f"circuit:{backend}", f"failures:{backend}")
        await self.redis.set(f"backend:healthy:{backend}", "1", ex=20)
        CIRCUIT.labels(backend).set(0)

    async def failure(self, backend: str):
        await self.redis.set(f"backend:healthy:{backend}", "0", ex=20)
        opened = await self.failure_script(keys=[f"failures:{backend}", f"circuit:{backend}"], args=[5, 10])
        if int(opened) == 1:
            CIRCUIT.labels(backend).set(1)

    async def cached(self, key: str):
        raw = await self.redis.get(key)
        return json.loads(raw) if raw else None

    async def cache(self, key: str, value: dict, ttl: int = 10):
        await self.redis.set(key, json.dumps(value), ex=ttl)

    async def choose(self, route_id: int, strategy: str, backends: tuple[tuple[str, int], ...]) -> str:
        healthy = []
        for url, weight in backends:
            if await self.is_circuit_open(url):
                continue
            status = await self.redis.get(f"backend:healthy:{url}")
            if status != "0":
                healthy.append((url, max(1, weight)))
        if not healthy:
            raise RuntimeError("no healthy backend available")
        if strategy == "least_connections":
            values = await asyncio.gather(*(self.redis.get(f"backend:connections:{url}") for url, _ in healthy))
            return min(zip(healthy, values), key=lambda item: int(item[1] or 0))[0][0]
        if strategy == "weighted":
            total = sum(weight for _, weight in healthy)
            ticket = random.randrange(total)
            for url, weight in healthy:
                if ticket < weight:
                    return url
                ticket -= weight
        counter = await self.redis.incr(f"balancer:rr:{route_id}")
        return healthy[(counter - 1) % len(healthy)][0]

async def health_check_loop(client, redis):
    while True:
        try:
            async with Session() as session:
                backends = (await session.scalars(select(Backend).where(Backend.is_active.is_(True)))).all()
            for backend in backends:
                try:
                    response = await client.get(backend.base_url.rstrip("/") + "/health", timeout=2.0)
                    await redis.set(f"backend:healthy:{backend.base_url.rstrip('/')}", "1" if response.is_success else "0", ex=20)
                except Exception:
                    await redis.set(f"backend:healthy:{backend.base_url.rstrip('/')}", "0", ex=20)
        except Exception:
            pass
        await asyncio.sleep(5)

def cache_key(route_id: int, url: str, query: str) -> str:
    digest = hashlib.sha256(f"{url}?{query}".encode()).hexdigest()
    return f"response:{route_id}:{digest}"
