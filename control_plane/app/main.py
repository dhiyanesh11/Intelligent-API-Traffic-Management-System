import hashlib
import hmac
import os
import secrets
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from jose import jwt
from redis.asyncio import Redis
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import APIKey, Backend, RateLimitPolicy, Route, TrafficEvent

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://traffic:traffic-dev-only@localhost:5432/traffic")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "local-admin-token-change-me")
JWT_SECRET = os.getenv("JWT_SECRET", "replace-this-with-a-long-random-secret")
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)

@asynccontextmanager
async def lifespan(app):
    app.state.redis = Redis.from_url(REDIS_URL, decode_responses=True)
    yield
    await app.state.redis.aclose()
    await engine.dispose()

app = FastAPI(title="Traffic Control Plane", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3001", "http://127.0.0.1:3001", "http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])

async def admin_guard(x_admin_token: str = Header(default="")):
    if not hmac.compare_digest(x_admin_token, ADMIN_TOKEN):
        raise HTTPException(401, "admin token required")

class BackendIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str
    weight: int = Field(default=1, ge=1)
    is_active: bool = True

class PolicyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    algorithm: str = "token_bucket"
    limit: int = Field(default=60, ge=1)
    window_seconds: int = Field(default=60, ge=1)
    scope: str = "api_key"
    is_active: bool = True

class RouteIn(BaseModel):
    name: str
    path_prefix: str
    methods: list[str] = ["GET"]
    backend_id: int
    policy_id: int | None = None
    auth_required: bool = True
    strategy: str = "round_robin"
    is_active: bool = True

class WhitelistIn(BaseModel):
    client: str

class OverrideIn(BaseModel):
    limit: int = Field(ge=1)
    ttl_seconds: int = Field(default=3600, ge=0, le=604800)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "control-plane"}

@app.post("/api/token", dependencies=[Depends(admin_guard)])
async def create_admin_jwt():
    from datetime import datetime, timedelta, timezone
    token = jwt.encode({"sub": "local-admin", "iat": datetime.now(timezone.utc), "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, JWT_SECRET, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer", "expires_in": 3600}

@app.get("/api/routes", dependencies=[Depends(admin_guard)])
async def list_routes():
    async with Session() as db:
        rows = (await db.scalars(select(Route).order_by(Route.id))).all()
        return [{"id": r.id, "name": r.name, "path_prefix": r.path_prefix, "methods": r.methods, "backend_id": r.backend_id, "policy_id": r.policy_id, "auth_required": r.auth_required, "strategy": r.strategy, "is_active": r.is_active} for r in rows]

@app.post("/api/routes", status_code=201, dependencies=[Depends(admin_guard)])
async def create_route(payload: RouteIn):
    async with Session.begin() as db:
        row = Route(**payload.model_dump())
        db.add(row)
        await db.flush()
        return {"id": row.id, "name": row.name}

@app.put("/api/routes/{route_id}", dependencies=[Depends(admin_guard)])
async def update_route(route_id: int, payload: RouteIn):
    async with Session.begin() as db:
        row = await db.get(Route, route_id)
        if not row: raise HTTPException(404, "route not found")
        for key, value in payload.model_dump().items(): setattr(row, key, value)
        return {"id": row.id, "name": row.name}

@app.delete("/api/routes/{route_id}", status_code=204, dependencies=[Depends(admin_guard)])
async def delete_route(route_id: int):
    async with Session.begin() as db:
        row = await db.get(Route, route_id)
        if not row: raise HTTPException(404, "route not found")
        await db.delete(row)

@app.get("/api/backends", dependencies=[Depends(admin_guard)])
async def list_backends():
    async with Session() as db:
        rows = (await db.scalars(select(Backend).order_by(Backend.id))).all()
        return [{"id": r.id, "name": r.name, "base_url": r.base_url, "weight": r.weight, "is_active": r.is_active} for r in rows]

@app.post("/api/backends", status_code=201, dependencies=[Depends(admin_guard)])
async def create_backend(payload: BackendIn):
    async with Session.begin() as db:
        row = Backend(**payload.model_dump())
        db.add(row)
        await db.flush()
        return {"id": row.id, "name": row.name}

@app.get("/api/policies", dependencies=[Depends(admin_guard)])
async def list_policies():
    async with Session() as db:
        rows = (await db.scalars(select(RateLimitPolicy).order_by(RateLimitPolicy.id))).all()
        return [{"id": r.id, "name": r.name, "algorithm": r.algorithm, "limit": r.limit, "window_seconds": r.window_seconds, "scope": r.scope, "is_active": r.is_active} for r in rows]

@app.post("/api/policies", status_code=201, dependencies=[Depends(admin_guard)])
async def create_policy(payload: PolicyIn):
    async with Session.begin() as db:
        row = RateLimitPolicy(**payload.model_dump())
        db.add(row)
        await db.flush()
        return {"id": row.id, "name": row.name}

@app.get("/api/keys", dependencies=[Depends(admin_guard)])
async def list_keys():
    async with Session() as db:
        rows = (await db.scalars(select(APIKey).order_by(desc(APIKey.id)))).all()
        return [{"id": r.id, "name": r.name, "prefix": r.key_prefix, "active": r.is_active, "created_at": r.created_at} for r in rows]

@app.post("/api/keys", status_code=201, dependencies=[Depends(admin_guard)])
async def create_key(name: str):
    raw = "iatm_" + secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    async with Session.begin() as db:
        row = APIKey(user_id=1, key_hash=digest, key_prefix=raw[:12], name=name, is_active=True)
        db.add(row)
        await db.flush()
        key_id = row.id
    return {"id": key_id, "name": name, "api_key": raw}

@app.delete("/api/keys/{key_id}", dependencies=[Depends(admin_guard)])
async def revoke_key(key_id: int):
    async with Session.begin() as db:
        row = await db.get(APIKey, key_id)
        if not row: raise HTTPException(404, "key not found")
        row.is_active = False
        digest = row.key_hash
    await app.state.redis.delete(f"auth:key:{digest}")
    return {"id": key_id, "active": False}

@app.get("/api/traffic", dependencies=[Depends(admin_guard)])
async def recent_traffic(limit: int = 100):
    async with Session() as db:
        rows = (await db.scalars(select(TrafficEvent).order_by(desc(TrafficEvent.created_at)).limit(min(max(limit, 1), 500)))).all()
        return [{"request_id": r.request_id, "client": r.client, "route": r.route_name, "status": r.status_code, "latency_ms": r.latency_ms, "decision": r.decision, "created_at": r.created_at} for r in rows]

@app.get("/api/whitelist", dependencies=[Depends(admin_guard)])
async def get_whitelist():
    return [{"client": client, "whitelisted": True} for client in sorted(await app.state.redis.smembers("policy:whitelist"))]

@app.post("/api/whitelist", status_code=201, dependencies=[Depends(admin_guard)])
async def add_whitelist(payload: WhitelistIn):
    await app.state.redis.sadd("policy:whitelist", payload.client)
    await app.state.redis.delete(f"policy:blocked:{payload.client}")
    return {"client": payload.client, "whitelisted": True}

@app.delete("/api/whitelist/{client}", dependencies=[Depends(admin_guard)])
async def remove_whitelist(client: str):
    await app.state.redis.srem("policy:whitelist", client)
    return {"client": client, "whitelisted": False}

@app.put("/api/policies/{policy_id}/override", dependencies=[Depends(admin_guard)])
async def set_manual_override(policy_id: int, payload: OverrideIn):
    async with Session() as db:
        routes = (await db.scalars(select(Route).where(Route.policy_id == policy_id, Route.is_active.is_(True)))).all()
    if not routes: raise HTTPException(404, "no active route uses this policy")
    for route in routes:
        key = f"policy:manual:{route.id}"
        await app.state.redis.set(key, payload.limit, ex=payload.ttl_seconds or None)
    return {"policy_id": policy_id, "limit": payload.limit, "ttl_seconds": payload.ttl_seconds}

@app.delete("/api/policies/{policy_id}/override", dependencies=[Depends(admin_guard)])
async def clear_manual_override(policy_id: int):
    async with Session() as db:
        routes = (await db.scalars(select(Route).where(Route.policy_id == policy_id))).all()
    await app.state.redis.delete(*(f"policy:manual:{route.id}" for route in routes))
    return {"policy_id": policy_id, "cleared": True}
