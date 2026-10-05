"""Async decorator for timing repository database queries.

Usage::

    from infrastructure.repository_timing import timed_repository

    @timed_repository
    async def find_user_by_phone(session: AsyncSession, phone: str) -> UserDict | None:
        ...
"""
from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any

from infrastructure.logging import log_event
from infrastructure.metrics import REPOSITORY_QUERY_DURATION_SECONDS
from infrastructure.settings import settings


def timed_repository(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Report only slow or failed repository calls, never arguments."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            result = await fn(*args, **kwargs)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            REPOSITORY_QUERY_DURATION_SECONDS.observe(elapsed_ms / 1000)
            log_event(
                "error",
                "db.repository.failed",
                f"Repository operation {fn.__qualname__} failed",
                error=exc,
                component="database",
                code_module=fn.__module__,
                code_function=fn.__qualname__,
                operation=fn.__qualname__,
                duration_ms=round(elapsed_ms, 2),
            )
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000
        REPOSITORY_QUERY_DURATION_SECONDS.observe(elapsed_ms / 1000)
        if elapsed_ms >= settings.repository_slow_query_ms:
            log_event(
                "warning",
                "db.repository.slow",
                (
                    f"Repository operation {fn.__qualname__} took "
                    f"{elapsed_ms:.2f} ms"
                ),
                component="database",
                code_module=fn.__module__,
                code_function=fn.__qualname__,
                operation=fn.__qualname__,
                duration_ms=round(elapsed_ms, 2),
                threshold_ms=settings.repository_slow_query_ms,
            )
        return result

    return wrapper
