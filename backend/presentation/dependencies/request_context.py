"""FastAPI dep extracting IP + User-Agent for session metadata.

The value is surfaced as an :class:`application.commands.auth.RequestContext`
so it can be plumbed into login/register/verify handlers without leaking
``Request`` into the application layer.

IP resolution honours ``X-Forwarded-For`` only when we're behind a trusted
proxy (``settings.trusted_proxy_hops > 0``) — we walk from the rightmost
entry inward by ``trusted_proxy_hops`` and take the first entry past the
proxy chain as the client. Falls back to ``request.client.host``.

Country-code resolution goes through :mod:`infrastructure.services.geoip`,
which returns ``None`` for private IPs / missing DB / disabled feature flag.
Any resolver error is swallowed — GeoIP must never break authentication.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Request

from application.commands.auth import RequestContext
from infrastructure.services.geoip import get_resolver
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")


def _extract_ip(request: Request) -> str | None:
    hops = max(settings.trusted_proxy_hops, 0)
    if hops > 0:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            entries = [entry.strip() for entry in forwarded.split(",") if entry.strip()]
            if entries:
                # Trust the last `hops` entries as proxies; the client IP
                # is what sits just before that chain.
                idx = max(len(entries) - hops - 1, 0)
                return entries[idx] or None
    client = request.client
    if client is not None and client.host:
        return client.host
    return None


def _extract_user_agent(request: Request) -> str | None:
    ua = request.headers.get("user-agent")
    if not ua:
        return None
    # Guard against pathological UAs — the column is varchar-ish, keep it sane.
    return ua[:512]


def _extract_country_code(ip: str | None) -> str | None:
    if not ip or not settings.geoip_lookup_enabled:
        return None
    try:
        return get_resolver().lookup_country(ip)
    except Exception as exc:
        # GeoIP failure must never break authn — log and drop to None.
        logger.debug("GeoIP resolver raised for %s: %s", ip, exc)
        return None


async def get_request_context(request: Request) -> RequestContext:
    """Return the per-request metadata captured for a new session."""
    ip_address = _extract_ip(request)
    return RequestContext(
        ip_address=ip_address,
        user_agent=_extract_user_agent(request),
        country_code=_extract_country_code(ip_address),
    )


RequestContextDep = Annotated[RequestContext, Depends(get_request_context)]
