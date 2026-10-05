"""Network-free broker for the real Taskiq multi-process exporter contract."""

import asyncio
from collections.abc import AsyncGenerator

from taskiq import InMemoryBroker, TaskiqEvents
from taskiq.state import TaskiqState

from infrastructure.metrics import (
    NOTIFICATION_DELIVERIES,
    NOTIFICATION_EVENTS,
    NOTIFICATION_SMTP_SECONDS,
)


class MetricsProbeBroker(InMemoryBroker):
    async def listen(self) -> AsyncGenerator[bytes, None]:
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        while True:
            yield await queue.get()


broker = MetricsProbeBroker()


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def publish_metrics(_state: TaskiqState) -> None:
    NOTIFICATION_DELIVERIES.labels(state="sent").inc(2)
    NOTIFICATION_DELIVERIES.labels(state="failed").inc()
    NOTIFICATION_EVENTS.labels(stage="published").inc(3)
    NOTIFICATION_SMTP_SECONDS.observe(0.25)
