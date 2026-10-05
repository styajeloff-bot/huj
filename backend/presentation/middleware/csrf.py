"""Double-submit-cookie CSRF protection.

Strategy:
- On authenticated responses the server issues a ``csrfToken`` cookie
  (non-HttpOnly so the SPA can read it) alongside ``accessToken`` /
  ``refreshToken``.
- For mutating requests that carry an ``accessToken`` cookie, the client
  must echo the CSRF token in the ``X-CSRF-Token`` header. The middleware
  compares header vs. cookie — a mismatch returns 403.

Why only when the access cookie is present:
  - Unauthenticated requests (/login, /register, webhooks) have no session
    to forge and thus no CSRF risk.
  - Bearer-token requests (no cookie) are immune to CSRF by definition.

Webhook paths are explicitly exempted — ModulBank / ModulKassa auth by
signature, not session.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from infrastructure.settings import settings
from presentation.errors import error_response

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_EXEMPT_PATH_PREFIXES: tuple[str, ...] = (
    "/api/v1/payments/webhook/",
    "/api/v1/health",
    "/api/v1/docs",
    "/api/v1/redoc",
    "/api/v1/openapi.json",
)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Enforce X-CSRF-Token ↔ csrfToken cookie match on mutating cookie-auth requests."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not settings.csrf_enabled:
            return await call_next(request)

        if request.method in _SAFE_METHODS:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(prefix) for prefix in _EXEMPT_PATH_PREFIXES):
            return await call_next(request)

        # No session cookie → no CSRF risk (Bearer / public endpoints).
        if "accessToken" not in request.cookies:
            return await call_next(request)

        cookie_token = request.cookies.get(settings.csrf_cookie_name)
        header_token = request.headers.get(settings.csrf_header_name)
        if not cookie_token or not header_token or cookie_token != header_token:
            request.state.security_rejection = "csrf"
            return error_response(
                status_code=403,
                detail="CSRF-токен отсутствует или не совпадает",
                code="CSRF_INVALID",
            )

        return await call_next(request)
