"""Taskiq broker configuration.

Single shared broker instance used by every task declared in
``application/tasks/*``. Tasks are decorated with ``@broker.task`` and
optionally ``schedule=[...]`` labels; the taskiq scheduler process reads
those labels via :class:`LabelScheduleSource` and enqueues runs at the
right time, while taskiq worker processes pop the queue and execute.

Transport: Redis list-queue + Redis result backend. Redis is already
provisioned in compose (``REDIS_URL``) and the API uses it for cache
and rate limiting; reusing it avoids introducing another broker. The
faststream KafkaBroker stays dedicated to event-driven catalog flows.
"""

from __future__ import annotations

import logging
import re
import tracemalloc
from contextlib import AbstractContextManager
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from taskiq import TaskiqEvents, TaskiqMiddleware
from taskiq.message import TaskiqMessage
from taskiq.result import TaskiqResult
from taskiq.state import TaskiqState
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from infrastructure.logging import (
    ServiceName,
    bind_log_context,
    configure_logging,
    get_log_context_field,
    log_event,
    normalize_correlation_id,
)
from infrastructure.services.catalog_image_fetchers._client import (
    start as _start_image_client,
)
from infrastructure.services.catalog_image_fetchers._client import (
    stop as _stop_image_client,
)
from infrastructure.settings import settings

_OBSERVABILITY_MARKER_RE = re.compile(
    r"^local_observability_smoke(?:[-_][A-Za-z0-9_-]{1,64})?$"
)
_DUPLICATE_TASKIQ_ERROR_PREFIX = "Exception found while executing function:"


class _DuplicateTaskExecutionFilter(logging.Filter):
    """Drop Taskiq's copy of an exception already owned by our middleware."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith(_DUPLICATE_TASKIQ_ERROR_PREFIX)


class StructuredTaskiqLoggingMiddleware(TaskiqMiddleware):
    """Carry correlation metadata without changing task arguments."""

    def __init__(self) -> None:
        super().__init__()
        self._active_context: ContextVar[AbstractContextManager[None] | None] = (
            ContextVar("taskiq_log_context", default=None)
        )

    def pre_send(self, message: TaskiqMessage) -> TaskiqMessage:
        correlation_id = (
            normalize_correlation_id(message.labels.get("correlation_id"))
            or normalize_correlation_id(get_log_context_field("correlation_id"))
            or str(uuid4())
        )
        return message.model_copy(
            update={
                "labels": {
                    **message.labels,
                    "correlation_id": correlation_id,
                }
            }
        )

    def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        correlation_id = normalize_correlation_id(
            message.labels.get("correlation_id")
        ) or str(uuid4())
        context = bind_log_context(
            correlation_id=correlation_id,
            task_id=message.task_id,
            task_name=message.task_name,
            attempt=_task_attempt(message),
            **_observability_context(message),
        )
        context.__enter__()
        self._active_context.set(context)
        return message

    def post_execute(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],
    ) -> None:
        duration_ms = round(result.execution_time * 1000, 2)
        context = self._active_context.get()
        try:
            if result.is_err:
                log_event(
                    "error",
                    "task.failed",
                    f"Task {message.task_name} failed in {duration_ms} ms",
                    error=result.error,
                    component="taskiq",
                    duration_ms=duration_ms,
                )
            else:
                log_event(
                    "info",
                    "task.completed",
                    f"Task {message.task_name} completed in {duration_ms} ms",
                    component="taskiq",
                    duration_ms=duration_ms,
                )
        finally:
            if context is not None:
                context.__exit__(None, None, None)
            self._active_context.set(None)


def _task_attempt(message: TaskiqMessage) -> int:
    raw_attempt = message.labels.get("attempt", 1)
    try:
        attempt = int(raw_attempt)
    except (TypeError, ValueError):
        return 1
    return max(1, attempt)


def _observability_context(message: TaskiqMessage) -> dict[str, str]:
    raw_marker = message.labels.get("observability_marker")
    if not isinstance(raw_marker, str) or not _OBSERVABILITY_MARKER_RE.fullmatch(
        raw_marker
    ):
        return {}
    return {"marker": raw_marker}


def configure_taskiq_logging(
    *, service_name: ServiceName = "carcraft-taskiq-worker"
) -> None:
    configure_logging(service_name=service_name)
    receiver_logger = logging.getLogger("taskiq.receiver.receiver")
    if not any(
        isinstance(log_filter, _DuplicateTaskExecutionFilter)
        for log_filter in receiver_logger.filters
    ):
        receiver_logger.addFilter(_DuplicateTaskExecutionFilter())


configure_taskiq_logging()

broker: ListQueueBroker = (
    ListQueueBroker(
        url=settings.redis_url,
        queue_name="taskiq:default",
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
        socket_timeout=settings.taskiq_broker_redis_socket_timeout_seconds,
    )
    .with_result_backend(
        RedisAsyncResultBackend(
            redis_url=settings.redis_url,
            socket_connect_timeout=settings.redis_connect_timeout_seconds,
        )
    )
    .with_middlewares(StructuredTaskiqLoggingMiddleware())
)


def _start_tracemalloc_if_enabled() -> None:
    if not settings.tracemalloc_enabled:
        return
    if not tracemalloc.is_tracing():
        tracemalloc.start()
    current, peak = tracemalloc.get_traced_memory()
    log_event(
        "debug",
        "runtime.tracemalloc.started",
        "Taskiq worker memory tracing is active",
        component="runtime",
        current_memory_mb=round(current / 1024 / 1024, 2),
        peak_memory_mb=round(peak / 1024 / 1024, 2),
    )


async def on_worker_init(_state: TaskiqState) -> None:
    """Start the catalog image HTTP client + Kafka broker before tasks run."""
    # Taskiq may install its logging configuration after importing this module.
    configure_taskiq_logging()
    _start_tracemalloc_if_enabled()
    await _start_image_client()
    log_event(
        "info",
        "taskiq.worker.image_client.started",
        "Catalog image HTTP client started",
        component="taskiq",
    )
    # The data-import tasks publish DWH snapshot events to Kafka; the broker
    # must be connected in the worker process for those publishes to land.
    from infrastructure.messaging.broker import start_broker

    try:
        await start_broker()
        log_event(
            "info",
            "taskiq.worker.kafka.started",
            "Kafka broker started in Taskiq worker",
            component="taskiq",
        )
    except Exception as exc:  # pragma: no cover - depends on infra
        log_event(
            "warning",
            "taskiq.worker.kafka.start_failed",
            "Kafka broker could not start in Taskiq worker",
            error=exc,
            component="taskiq",
        )


async def on_worker_shutdown(_state: TaskiqState) -> None:
    """Stop the catalog image HTTP client + Kafka broker during shutdown."""
    await _stop_image_client()
    log_event(
        "info",
        "taskiq.worker.image_client.stopped",
        "Catalog image HTTP client stopped",
        component="taskiq",
    )
    from infrastructure.messaging.broker import stop_broker

    try:
        await stop_broker()
    except Exception as exc:  # pragma: no cover - depends on infra
        log_event(
            "warning",
            "taskiq.worker.kafka.stop_failed",
            "Kafka broker could not stop cleanly in Taskiq worker",
            error=exc,
            component="taskiq",
        )


broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, on_worker_init)
broker.add_event_handler(TaskiqEvents.WORKER_SHUTDOWN, on_worker_shutdown)
