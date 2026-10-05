"""Taskiq scheduler wiring.

``TaskiqScheduler`` is the object the ``taskiq scheduler`` CLI binds to.
It reads pending schedules from :class:`LabelScheduleSource` (which just
walks every registered task and honours their ``schedule=[...]`` labels)
and enqueues them into the broker at the right moment.

Run as a separate process. See the ``taskiq-scheduler`` service in
``docker-compose.dev.yml`` for the exact command.
"""

from __future__ import annotations

import tracemalloc

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

from infrastructure.logging import log_event
from infrastructure.settings import settings
from infrastructure.taskiq_broker import broker, configure_taskiq_logging


def _start_tracemalloc_if_enabled() -> None:
    if not settings.tracemalloc_enabled:
        return
    if not tracemalloc.is_tracing():
        tracemalloc.start()
    current, peak = tracemalloc.get_traced_memory()
    log_event(
        "debug",
        "runtime.tracemalloc.started",
        "Taskiq scheduler memory tracing is active",
        component="runtime",
        current_memory_mb=round(current / 1024 / 1024, 2),
        peak_memory_mb=round(peak / 1024 / 1024, 2),
    )


configure_taskiq_logging(service_name="carcraft-taskiq-scheduler")
_start_tracemalloc_if_enabled()
log_event(
    "info",
    "taskiq.scheduler.ready",
    "Taskiq scheduler is ready",
    component="taskiq",
)

scheduler: TaskiqScheduler = TaskiqScheduler(
    broker=broker,
    sources=[LabelScheduleSource(broker)],
)
