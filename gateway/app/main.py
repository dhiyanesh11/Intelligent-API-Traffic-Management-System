import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from redis.asyncio import Redis

from app.config import settings
from app.routing import downstream_path, match_route, refresh_routes, route_refresh_loop
from app.security import authenticate

log = logging.getLogger(__name__)
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=3.0), follow_redirects=False)
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await refresh_routes()
    refresh_task = asyncio.create_task(route_refresh_loop())
    yield
    refresh_task.cancel()
    try:
        await refresh_task
    except asyncio.CancelledError:
        pass
    await app.state.http.aclose()
    await app.state.redis.aclose()

app = FastAPI(title="Intelligent API Traffic Gateway", version="0.2.0", lifespan=lifespan)

@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "gateway"}

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
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("x-forwarded-for")
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP and k.lower() not in {"x-api-key", "authorization"}}
    headers["x-request-id"] = request_id
    headers["x-forwarded-for"] = f"{forwarded_for}, {client_ip}" if forwarded_for else client_ip
    destination = route.base_url + downstream_path("/" + path, route)
    try:
        upstream = await request.app.state.http.request(request.method, destination, params=request.query_params, content=await request.body(), headers=headers)
    except httpx.TimeoutException:
        raise HTTPException(503, "upstream timed out", headers={"X-Request-ID": request_id})
    except httpx.HTTPError:
        log.exception("upstream request failed route=%s request_id=%s", route.name, request_id)
        raise HTTPException(502, "upstream unavailable", headers={"X-Request-ID": request_id})
    response_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in HOP_BY_HOP}
    response_headers["X-Request-ID"] = request_id
    return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)
