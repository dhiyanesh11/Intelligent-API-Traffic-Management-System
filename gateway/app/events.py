import asyncio
import logging
from redis.asyncio import Redis

log = logging.getLogger(__name__)
STREAM = "traffic:events"

async def publish_event(redis: Redis, **event):
    try:
        await redis.xadd(STREAM, {key: str(value) for key, value in event.items()}, maxlen=100000, approximate=True)
    except Exception:
        log.exception("failed to publish traffic event request_id=%s", event.get("request_id"))

def enqueue_event(redis: Redis, **event):
    asyncio.create_task(publish_event(redis, **event))
