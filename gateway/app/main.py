import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from redis.asyncio import Redis

from app.config import settings
from app.limiters import RateLimiter
from app.routing import downstream_path, match_route, refresh_routes, route_refresh_loop
from app.resilience import Resilience, cache_key, health_check_loop
from app.security import authenticate
from app.events import enqueue_event
from app.metrics import BLOCKED, LATENCY, REQUESTS, metrics_response

log = logging.getLogger(__name__)
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=3.0), follow_redirects=False)
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.limiter = RateLimiter(app.state.redis)
    app.state.resilience = Resilience(app.state.redis)
    await refresh_routes()
    refresh_task = asyncio.create_task(route_refresh_loop())
    health_task = asyncio.create_task(health_check_loop(app.state.http, app.state.redis))
    yield
    refresh_task.cancel()
    health_task.cancel()
    try:
        await refresh_task
    except asyncio.CancelledError:
        pass
    try:
        await health_task
    except asyncio.CancelledError:
        pass
    await app.state.http.aclose()
    await app.state.redis.aclose()

app = FastAPI(title="Intelligent API Traffic Gateway", version="0.2.0", lifespan=lifespan)

@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "gateway"}

@app.get("/metrics", include_in_schema=False)
async def metrics():
    return metrics_response()

@app.middleware("http")
async def observe_request(request: Request, call_next):
    if request.url.path in {"/health", "/metrics"}:
        return await call_next(request)
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - started
    status = response.status_code
    REQUESTS.labels(request.method, str(status)).inc()
    LATENCY.labels(request.method).observe(elapsed)
    if status == 429:
        BLOCKED.inc()
    route = match_route(request.url.path, request.method)
    client = request.client.host if request.client else "unknown"
    enqueue_event(request.app.state.redis, request_id=request_id, client=client, route_name=route.name if route else "unmatched", status_code=status, latency_ms=round(elapsed * 1000, 3), decision="blocked" if status == 429 else "error" if status >= 500 else "allowed")
    response.headers.setdefault("X-Request-ID", request_id)
    return response

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy(path: str, request: Request):
    if path in {"health", "metrics"}:
        raise HTTPException(404, "route not found")
    route = match_route("/" + path, request.method)
    if route is None:
        raise HTTPException(404, "route not found")
    api_key = request.headers.get("x-api-key")
    auth_header = request.headers.get("authorization", "")
    bearer = auth_header[7:] if auth_header.lower().startswith("bearer ") else None
    principal = None
    if route.auth_required:
        principal = await authenticate(api_key, bearer, request.app.state.redis)
        if principal is None:
            raise HTTPException(401, "valid API key or bearer token required", headers={"WWW-Authenticate": "Bearer"})
    request_id = getattr(request.state, "request_id", request.headers.get("x-request-id") or str(uuid.uuid4()))
    client_ip = request.client.host if request.client else "unknown"
    redis = request.app.state.redis
    whitelisted = bool(await redis.sismember("policy:whitelist", client_ip)) or bool(principal and await redis.sismember("policy:whitelist", principal))
    if not whitelisted and await redis.exists(f"policy:blocked:{client_ip}"):
        raise HTTPException(429, "client temporarily blocked by adaptive policy", headers={"Retry-After": "60", "X-Request-ID": request_id})
    effective_limit = route.limit
    dynamic_limit = await redis.get(f"policy:manual:{route.id}") or await redis.get(f"policy:limit:{route.id}")
    if dynamic_limit:
        effective_limit = max(1, int(dynamic_limit))
    subject = principal if route.scope == "api_key" and principal else client_ip if route.scope == "ip" else f"route:{route.id}"
    limit_key = f"rate:{route.id}:{route.scope}:{subject}"
    rate_headers = {"X-RateLimit-Limit": str(effective_limit), "X-Request-ID": request_id}
    try:
        allowed, remaining, retry_after = await request.app.state.limiter.check(key=limit_key, algorithm=route.algorithm, limit=effective_limit, window_seconds=route.window_seconds, request_id=request_id)
        rate_headers["X-RateLimit-Remaining"] = str(remaining)
        if not allowed:
            rate_headers["Retry-After"] = str(retry_after)
            raise HTTPException(429, "rate limit exceeded", headers=rate_headers)
    except HTTPException:
        raise
    except Exception:
        log.exception("rate limiter unavailable route=%s", route.name)
        if not settings.redis_fail_open:
            raise HTTPException(503, "rate limiter unavailable", headers=rate_headers)
    forwarded_for = request.headers.get("x-forwarded-for")
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP and k.lower() not in {"x-api-key", "authorization"}}
    headers["x-request-id"] = request_id
    headers["x-forwarded-for"] = f"{forwarded_for}, {client_ip}" if forwarded_for else client_ip
    try:
        backend_url = await request.app.state.resilience.choose(route.id, route.strategy, route.backends)
    except RuntimeError:
        raise HTTPException(503, "no healthy backend available", headers=rate_headers)
    destination = backend_url + downstream_path("/" + path, route)
    resilience = request.app.state.resilience
    if await resilience.is_circuit_open(backend_url):
        raise HTTPException(503, "upstream circuit is open", headers=rate_headers)
    cache_id = cache_key(route.id, destination, str(request.url.query))
    if request.method == "GET":
        cached = await resilience.cached(cache_id)
        if cached:
            cached_headers = dict(cached["headers"])
            cached_headers.update(rate_headers)
            cached_headers["X-Cache"] = "HIT"
            return Response(content=bytes.fromhex(cached["body_hex"]), status_code=cached["status"], headers=cached_headers)
    if route.strategy == "least_connections":
        await resilience.acquire_connection(backend_url)
    try:
        upstream = await request.app.state.http.request(request.method, destination, params=request.query_params, content=await request.body(), headers=headers)
        if request.method == "GET" and upstream.status_code >= 500:
            upstream = await request.app.state.http.request(request.method, destination, params=request.query_params, content=b"", headers=headers)
        if upstream.status_code < 500:
            await resilience.success(backend_url)
        else:
            await resilience.failure(backend_url)
    except httpx.TimeoutException:
        if route.strategy == "least_connections": await resilience.release_connection(backend_url)
        raise HTTPException(503, "upstream timed out", headers={"X-Request-ID": request_id})
    except httpx.HTTPError:
        if route.strategy == "least_connections": await resilience.release_connection(backend_url)
        log.exception("upstream request failed route=%s request_id=%s", route.name, request_id)
        raise HTTPException(502, "upstream unavailable", headers={"X-Request-ID": request_id})
    if route.strategy == "least_connections":
        await resilience.release_connection(backend_url)
    response_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in HOP_BY_HOP}
    response_headers.update(rate_headers)
    response_headers["X-Cache"] = "MISS" if request.method == "GET" else "BYPASS"
    if request.method == "GET" and upstream.status_code < 400:
        await resilience.cache(cache_id, {"status": upstream.status_code, "headers": response_headers, "body_hex": upstream.content.hex()}, ttl=10)
    response_headers["X-Request-ID"] = request_id
    response_headers["X-RateLimit-Limit"] = str(effective_limit)
    if "X-RateLimit-Remaining" in rate_headers:
        response_headers["X-RateLimit-Remaining"] = rate_headers["X-RateLimit-Remaining"]
    return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)
