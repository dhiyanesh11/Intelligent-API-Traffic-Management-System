import asyncio
import logging
from dataclasses import dataclass
from sqlalchemy import select
from app.database import Session
from app.models import Backend, Route

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

_routes: tuple[RouteConfig, ...] = ()

async def refresh_routes():
    global _routes
    async with Session() as session:
        result = await session.execute(select(Route, Backend).join(Backend, Route.backend_id == Backend.id).where(Route.is_active.is_(True), Backend.is_active.is_(True)))
        _routes = tuple(RouteConfig(r.id, r.name, r.path_prefix.rstrip("/") or "/", tuple(r.methods), b.base_url.rstrip("/"), r.auth_required, r.policy_id) for r, b in result.all())

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
