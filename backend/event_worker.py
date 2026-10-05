"""Event worker — Kafka FastStream consumer process.

Hosts every ``@broker.subscriber`` handler in the codebase: catalog
upload pipeline, auth audit events, auth notifications. Does NOT serve
HTTP and does NOT run scheduled periodic jobs — those live in the
taskiq-worker (queue executor) and taskiq-scheduler (cron tick)
services. The API process publishes events; this process consumes and
persists them.

Boot sequence:

1. Configure logging (same named logger as the API: ``carcraft-backend``).
2. Serialize and apply ClickHouse Alembic migrations.
3. Start the shared httpx client used by image fetchers.
4. Provision Kafka topics with the partition layout from
   ``infrastructure.messaging.topics.TOPIC_PARTITIONS``.
5. Import the consumer module so its ``@broker.subscriber`` decorators
   register handlers against the module-level ``KafkaBroker``.
6. ``broker.start()`` and block forever until SIGTERM/SIGINT.

The image consumer is the dominant cost; horizontal scaling is achieved
by running multiple replicas of this service — Kafka distributes
partitions across consumers in the same group automatically.
"""

from __future__ import annotations

import asyncio
import signal
import tracemalloc
from contextlib import suppress

from infrastructure.cache import shutdown_redis, startup_redis
from infrastructure.logging import configure_logging, log_event
from infrastructure.messaging.admin import ensure_topics
from infrastructure.messaging.broker import start_broker, stop_broker
from infrastructure.messaging.lag_metrics import run_lag_collector
from infrastructure.services.catalog_image_fetchers import _client as image_http
from infrastructure.settings import settings


def _setup_logging() -> None:
    configure_logging(service_name="carcraft-event-worker")


_setup_logging()


def _start_tracemalloc_if_enabled() -> None:
    if not settings.tracemalloc_enabled:
        return
    if not tracemalloc.is_tracing():
        tracemalloc.start()
    current, peak = tracemalloc.get_traced_memory()
    log_event(
        "debug",
        "runtime.tracemalloc.started",
        "Event worker memory tracing is active",
        component="runtime",
        current_memory_mb=round(current / 1024 / 1024, 2),
        peak_memory_mb=round(peak / 1024 / 1024, 2),
    )


async def _run() -> None:
    log_event(
        "info",
        "event_worker.starting",
        "Event worker is starting",
        component="lifecycle",
    )
    _start_tracemalloc_if_enabled()

    # ClickHouse DDL must be current before runtime bootstrap or any consumer
    # can touch DWH tables.  Migration failures are startup-fatal so the
    # orchestrator retries instead of running with a partially retired schema.
    from infrastructure.clickhouse_migrations import (
        ensure_clickhouse_migrations_current,
    )

    await ensure_clickhouse_migrations_current()
    # Alembic applies its own ``fileConfig`` while running migrations. Restore
    # the process-wide JSON contract before any worker/runtime logger emits.
    _setup_logging()

    await image_http.start()
    # The auth_notifications consumer uses Redis for security-event
    # throttling (idempotency via SET NX + TTL). Without initializing
    # the client here, get_redis() raises at first use and crashes the
    # consumer loop.
    await startup_redis()
    try:
        await ensure_topics()
    except Exception as exc:
        log_event(
            "error",
            "event_worker.kafka_topics.failed",
            "Kafka topic provisioning failed",
            error=exc,
            component="kafka",
        )

    # Allow Redpanda metadata to propagate after topic creation.
    # Without this pause, consumers may hit UnknownTopicOrPartitionError
    # because the metadata cache hasn't caught up yet.
    log_event(
        "debug",
        "event_worker.kafka_metadata.waiting",
        "Waiting for Kafka topic metadata propagation",
        component="kafka",
        duration_ms=3000,
    )
    await asyncio.sleep(3)

    # Ensure ClickHouse tables exist before any consumer runs.
    try:
        from infrastructure.clickhouse import ensure_tables

        ensure_tables()
    except Exception as exc:
        log_event(
            "error",
            "event_worker.clickhouse_tables.failed",
            "ClickHouse runtime table bootstrap failed",
            error=exc,
            component="clickhouse",
        )

    # Importing the consumer modules registers @broker.subscriber handlers
    # against the module-level broker instance BEFORE we start it.
    import application.notification_events as _notification_consumer
    import infrastructure.messaging.consumers.auth_audit as _auth_audit_consumer
    import infrastructure.messaging.consumers.dwh_sync as _dwh_sync_consumer
    import infrastructure.messaging.consumers.lca_status_history as _lca_history_consumer
    from infrastructure.messaging.consumers import (
        auth_notifications as _auth_notifications_consumer,
    )

    _ = (
        _notification_consumer,
        _auth_audit_consumer,
        _dwh_sync_consumer,
        _lca_history_consumer,
        _auth_notifications_consumer,
    )

    # Taskiq producer imports must not leave worker logging on the API or
    # taskiq service identity inside this Kafka process.
    _setup_logging()
    await start_broker()

    # Expose Prometheus metrics on a dedicated port.
    from prometheus_client import start_http_server

    start_http_server(settings.metrics_port)
    log_event(
        "info",
        "event_worker.ready",
        "Event worker is ready",
        component="lifecycle",
        metrics_port=settings.metrics_port,
    )

    # Start background lag collector for all Kafka consumers.
    _background_tasks: set[asyncio.Task[None]] = set()
    _task = asyncio.create_task(run_lag_collector())
    _background_tasks.add(_task)
    _task.add_done_callback(_background_tasks.discard)
    from application.notifications.observability import run_backlog_collector

    _notification_metrics = asyncio.create_task(run_backlog_collector())
    _background_tasks.add(_notification_metrics)
    _notification_metrics.add_done_callback(_background_tasks.discard)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()
    log_event(
        "info",
        "event_worker.stopping",
        "Event worker is stopping",
        component="lifecycle",
    )

    await stop_broker()
    await image_http.stop()
    await shutdown_redis()
    log_event(
        "info",
        "event_worker.stopped",
        "Event worker stopped",
        component="lifecycle",
    )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
