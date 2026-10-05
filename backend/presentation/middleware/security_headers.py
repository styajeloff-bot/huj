"""Security-headers middleware.

Ingress on Yandex Managed Kubernetes normally sets these headers at the
edge, but the application layer emits them as a fallback so a misconfigured
Ingress can't silently drop CSP/HSTS.

Values are configurable via ``settings`` — set any individual header to an
empty string to suppress it. Flip ``security_headers_enabled=False`` to
disable the middleware entirely.

OpenAPI documentation paths (``/api/v1/docs``, ``/api/v1/redoc``,
``/api/v1/openapi.json``) are exempted from the ``Content-Security-Policy``
header so Swagger UI / ReDoc can still load their inline scripts and CDN
assets. The rest of the security headers still apply to those paths.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from infrastructure.settings import settings

_CSP_EXEMPT_PATHS: frozenset[str] = frozenset(
    {
        "/api/v1/docs",
        "/api/v1/redoc",
        "/api/v1/openapi.json",
    }
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Set a conservative set of security response headers as a fallback."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        if not settings.security_headers_enabled:
            return response

        path = request.url.path

        # Each tuple is (header_name, configured_value, skip_for_docs).
        headers: tuple[tuple[str, str, bool], ...] = (
            ("Strict-Transport-Security", settings.security_hsts, False),
            ("X-Content-Type-Options", settings.security_content_type_options, False),
            ("X-Frame-Options", settings.security_frame_options, False),
            ("Referrer-Policy", settings.security_referrer_policy, False),
            ("Permissions-Policy", settings.security_permissions_policy, False),
            ("Content-Security-Policy", settings.security_csp, True),
        )

        for name, value, skip_for_docs in headers:
            if not value:
                continue
            if skip_for_docs and path in _CSP_EXEMPT_PATHS:
                continue
            response.headers[name] = value

        return response
