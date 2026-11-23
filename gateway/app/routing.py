import asyncio
import logging
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.orm import aliased
from app.database import Session
from app.models import Backend, RateLimitPolicy, Route, RouteBackend

log = logging.getLogger(__name__)

@dataclass(frozen=True)
class RouteConfig:
    id: int
    name: str
    path_prefix: str
    methods: tuple[str, ...]
    base_url: str
    auth_required: bool
    policy_id: int | None
    limit: int = 60
    window_seconds: int = 60
    algorithm: str = "token_bucket"
    scope: str = "api_key"
    strategy: str = "round_robin"
    backends: tuple[tuple[str, int], ...] = ()

_routes: tuple[RouteConfig, ...] = ()

async def refresh_routes():
    global _routes
    pooled_backend = aliased(Backend)
    async with Session() as session:
        result = await session.execute(select(Route, Backend, RateLimitPolicy, RouteBackend, pooled_backend).join(Backend, Route.backend_id == Backend.id).outerjoin(RateLimitPolicy, Route.policy_id == RateLimitPolicy.id).outerjoin(RouteBackend, (RouteBackend.route_id == Route.id) & RouteBackend.is_active.is_(True)).outerjoin(pooled_backend, RouteBackend.backend_id == pooled_backend.id).where(Route.is_active.is_(True)))
        grouped = {}
        for r, primary, p, rb, pooled in result.all():
            row = grouped.setdefault(r.id, {"route": r, "policy": p, "backends": []})
            if rb and pooled and pooled.is_active:
                row["backends"].append((pooled.base_url.rstrip("/"), rb.weight))
            elif not row["backends"] and primary.is_active:
                row["backends"].append((primary.base_url.rstrip("/"), primary.weight))
        _routes = tuple(RouteConfig(row["route"].id, row["route"].name, row["route"].path_prefix.rstrip("/") or "/", tuple(row["route"].methods), row["backends"][0][0], row["route"].auth_required, row["route"].policy_id, row["policy"].limit if row["policy"] else 60, row["policy"].window_seconds if row["policy"] else 60, row["policy"].algorithm if row["policy"] else "token_bucket", row["policy"].scope if row["policy"] else "api_key", row["route"].strategy, tuple(row["backends"])) for row in grouped.values() if row["backends"])

async def route_refresh_loop():
    while True:
        try:
            await refresh_routes()
        except Exception:
            log.exception("route config refresh failed; retaining last good snapshot")
        await asyncio.sleep(5)

def match_route(path: str, method: str) -> RouteConfig | None:
    for route in sorted(_routes, key=lambda item: len(item.path_prefix), reverse=True):
        prefix = route.path_prefix
        if method.upper() in route.methods and (path == prefix or path.startswith(prefix.rstrip("/") + "/")):
            return route
    return None

def downstream_path(path: str, route: RouteConfig) -> str:
    suffix = path[len(route.path_prefix):]
    return "/" + suffix.lstrip("/")
