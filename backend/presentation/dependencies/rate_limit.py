"""FastAPI dependencies for per-endpoint rate limiting (fastapi-limiter).

Each dependency is a no-op when ``settings.rate_limit_enabled`` is False —
useful for unit tests and environments without Redis.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, Request, Response

from infrastructure.settings import settings


async def _noop() -> None:
    return None


class _SafeRateLimiter:
    """Compatibility wrapper for fastapi-limiter with FastAPI's router tree.

    ``fastapi-limiter==0.1.6`` assumes every ``request.app.routes`` item has
    ``path`` and ``methods``. Newer FastAPI can expose included-router marker
    objects in that list, so the upstream dependency raises AttributeError
    before it even checks Redis.
    """

    def __init__(self, *, times: int, seconds: int = 60) -> None:
        from fastapi_limiter.depends import RateLimiter

        self._inner = RateLimiter(times=times, seconds=seconds)
        self.identifier = self._inner.identifier
        self.callback = self._inner.callback

    async def _check(self, key: str) -> Any:
        return await self._inner._check(key)

    async def __call__(self, request: Request, response: Response) -> Any:
        import redis as pyredis
        from fastapi_limiter import FastAPILimiter

        if not FastAPILimiter.redis:
            raise RuntimeError("You must call FastAPILimiter.init in startup event of fastapi!")

        route_index = 0
        dep_index = 0
        for i, route in enumerate(request.app.routes):
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            if path != request.scope["path"] or not methods or request.method not in methods:
                continue
            route_index = i
            for j, dependency in enumerate(getattr(route, "dependencies", ())):
                if self is dependency.dependency:
                    dep_index = j
                    break
            break

        identifier = self.identifier or FastAPILimiter.identifier
        callback = self.callback or FastAPILimiter.http_callback
        rate_key = await identifier(request)
        key = f"{FastAPILimiter.prefix}:{rate_key}:{route_index}:{dep_index}"
        try:
            pexpire = await self._check(key)
        except pyredis.exceptions.NoScriptError:
            FastAPILimiter.lua_sha = await FastAPILimiter.redis.script_load(
                FastAPILimiter.lua_script,
            )
            pexpire = await self._check(key)
        if pexpire != 0:
            return await callback(request, response, pexpire)
        return None


def _limiter(times: int, seconds: int = 60) -> Any:
    if not settings.rate_limit_enabled:
        return Depends(_noop)

    return Depends(_SafeRateLimiter(times=times, seconds=seconds))


rate_limit_login = _limiter(settings.rate_limit_login_per_minute)
rate_limit_register = _limiter(settings.rate_limit_register_per_minute)
rate_limit_verify = _limiter(settings.rate_limit_verify_per_minute)
rate_limit_refresh = _limiter(settings.rate_limit_refresh_per_minute)
rate_limit_resend = _limiter(settings.rate_limit_resend_per_minute)
rate_limit_analytics = _limiter(100)
rate_limit_special_equipment_catalog = _limiter(
    settings.rate_limit_special_equipment_catalog_per_minute
)


__all__ = [
    "rate_limit_analytics",
    "rate_limit_login",
    "rate_limit_refresh",
    "rate_limit_register",
    "rate_limit_resend",
    "rate_limit_special_equipment_catalog",
    "rate_limit_verify",
]
