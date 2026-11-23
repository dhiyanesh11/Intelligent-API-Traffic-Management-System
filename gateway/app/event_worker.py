"""Consume gateway traffic events from Redis Streams and persist in batches."""
import asyncio
import logging
from sqlalchemy import insert
from redis.exceptions import ResponseError
from redis.asyncio import Redis
from app.config import settings
from app.database import Session
from app.events import STREAM
from app.models import TrafficEvent

logging.basicConfig(level=logging.INFO)

async def run():
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    group, consumer = "traffic-writers", "writer-1"
    try:
        await redis.xgroup_create(STREAM, group, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
    try:
        while True:
            batches = await redis.xreadgroup(group, consumer, {STREAM: ">"}, count=100, block=1000)
            for _, messages in batches:
                rows = []
                ids = []
                for message_id, fields in messages:
                    ids.append(message_id)
                    try:
                        rows.append({"request_id": fields["request_id"], "client": fields["client"], "route_name": fields["route_name"], "status_code": int(fields["status_code"]), "latency_ms": float(fields["latency_ms"]), "decision": fields["decision"]})
                    except (KeyError, ValueError):
                        logging.exception("invalid stream message %s", message_id)
                if rows:
                    async with Session.begin() as session:
                        await session.execute(insert(TrafficEvent), rows)
                if ids:
                    await redis.xack(STREAM, group, *ids)
    finally:
        await redis.aclose()

if __name__ == "__main__":
    asyncio.run(run())
