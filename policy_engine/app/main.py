"""Consumes ML scores and traffic history to publish expiring gateway policy."""
import asyncio
import logging
import os
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Boolean, DateTime, Float, Integer, String
from datetime import datetime

logging.basicConfig(level=logging.INFO)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://traffic:traffic-dev-only@localhost:5432/traffic")
BLOCK_TTL_SECONDS = int(os.getenv("BLOCK_TTL_SECONDS", "120"))
LATENCY_TARGET_MS = float(os.getenv("LATENCY_TARGET_MS", "250"))
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase): pass
class Policy(Base):
    __tablename__ = "rate_limit_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    limit: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean)
class Route(Base):
    __tablename__ = "routes"
    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean)
class Event(Base):
    __tablename__ = "traffic_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    route_name: Mapped[str] = mapped_column(String(100))
    status_code: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

async def consume_scores(redis: Redis):
    group, consumer, stream = "policy-workers", "policy-1", "ml:scores"
    try: await redis.xgroup_create(stream, group, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc): raise
    while True:
        batches = await redis.xreadgroup(group, consumer, {stream: ">"}, count=100, block=1000)
        for _, messages in batches:
            for message_id, fields in messages:
                client = fields.get("client", "")
                anomalous = fields.get("anomaly") == "true"
                if client and anomalous and not await redis.sismember("policy:whitelist", client):
                    await redis.set(f"policy:blocked:{client}", "ml-anomaly", ex=BLOCK_TTL_SECONDS)
                await redis.xack(stream, group, message_id)

async def adapt_limits(redis: Redis):
    from sqlalchemy import text
    async with Session() as session:
        routes = (await session.execute(select(Route, Policy).join(Policy, Route.policy_id == Policy.id).where(Route.is_active.is_(True), Policy.is_active.is_(True)))).all()
        for route, policy in routes:
            result = await session.execute(text("SELECT status_code, latency_ms FROM traffic_events WHERE route_name = (SELECT name FROM routes WHERE id=:route_id) AND created_at > now() - interval '2 minutes'"), {"route_id": route.id})
            samples = result.all()
            current = int(await redis.get(f"policy:limit:{route.id}") or policy.limit)
            if await redis.exists(f"policy:manual:{route.id}"):
                continue
            if not samples:
                continue
            latencies = sorted(float(row.latency_ms) for row in samples)
            p95 = latencies[min(len(latencies) - 1, int(len(latencies) * .95))]
            errors = sum(row.status_code >= 500 for row in samples) / len(samples)
            if p95 > LATENCY_TARGET_MS or errors > .05:
                current = max(1, int(current * .7))
            else:
                current = min(int(policy.limit), current + max(1, int(policy.limit * .05)))
            await redis.set(f"policy:limit:{route.id}", current, ex=90)

async def run():
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    consumer = asyncio.create_task(consume_scores(redis))
    try:
        while True:
            try: await adapt_limits(redis)
            except Exception: logging.exception("adaptive limit update failed")
            await asyncio.sleep(15)
    finally:
        consumer.cancel()
        try: await consumer
        except asyncio.CancelledError: pass
        await redis.aclose()
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run())
