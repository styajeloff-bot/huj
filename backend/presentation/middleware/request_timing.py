"""One safe, correlated summary for every non-probe HTTP request."""
from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.types import ASGIApp

from infrastructure.logging import LogLevel, bind_log_context, log_event

# Paths that are too noisy to log at INFO level.
_SKIP_PATHS: frozenset[str] = frozenset({"/api/v1/health", "/metrics"})


def _request_id(request: Request) -> str:
    incoming = request.headers.get("X-Request-ID", "")
    try:
        return str(UUID(incoming))
    except (ValueError, AttributeError):
        return str(uuid4())


def _message(method: str, path: str, status: int, duration_ms: float) -> str:
    return f"{method} {path} -> {status} in {duration_ms:.2f} ms"


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Measure and log request duration."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Any:
        request_id = _request_id(request)
        request.state.request_id = request_id
        path = request.url.path
        start = time.perf_counter()
        with bind_log_context(
            request_id=request_id,
            correlation_id=request_id,
        ):
            try:
                response = await call_next(request)
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000
                if path not in _SKIP_PATHS:
                    log_event(
                        "error",
                        "http.request.failed",
                        _message(request.method, path, 500, elapsed_ms),
                        error=exc,
                        component="http",
                        http_method=request.method,
                        http_route=path,
                        http_status_code=500,
                        duration_ms=round(elapsed_ms, 2),
                    )
                raise

            elapsed_ms = (time.perf_counter() - start) * 1000
            response.headers["X-Request-ID"] = request_id
            if path not in _SKIP_PATHS:
                failed = response.status_code >= 500
                security_rejection = getattr(
                    request.state,
                    "security_rejection",
                    None,
                )
                level: LogLevel = (
                    "error" if failed else "warning" if security_rejection else "info"
                )
                fields: dict[str, Any] = {}
                if security_rejection:
                    fields.update(
                        security_check=str(security_rejection),
                        result="rejected",
                    )
                log_event(
                    level,
                    "http.request.failed" if failed else "http.request.completed",
                    _message(
                        request.method,
                        path,
                        response.status_code,
                        elapsed_ms,
                    ),
                    component="http",
                    http_method=request.method,
                    http_route=path,
                    http_status_code=response.status_code,
                    duration_ms=round(elapsed_ms, 2),
                    **fields,
                )

            return response
