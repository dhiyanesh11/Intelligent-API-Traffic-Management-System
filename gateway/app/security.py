import hashlib
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy import select
from app.config import settings
from app.database import Session
from app.models import APIKey

def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

async def authenticate(api_key: str | None, bearer: str | None, redis: Redis) -> str | None:
    """Return the authenticated principal, checking API keys before JWT bearer tokens."""
    if api_key:
        digest = hash_api_key(api_key)
        cache_key = f"auth:key:{digest}"
        cached = await redis.get(cache_key)
        if cached:
            return cached.decode() if isinstance(cached, bytes) else cached
        async with Session() as session:
            row = await session.scalar(select(APIKey).where(APIKey.key_hash == digest, APIKey.is_active.is_(True)))
        if row:
            principal = f"key:{row.id}"
            await redis.set(cache_key, principal, ex=30)
            return principal
    if bearer:
        try:
            claims = jwt.decode(bearer, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            subject = claims.get("sub")
            if isinstance(subject, str) and subject:
                return f"jwt:{subject}"
        except JWTError:
            pass
    return None
