"""Real notification Kafka transport for the isolated monetization E2E stack."""
from __future__ import annotations

import argparse
import asyncio
import signal
import time
from pathlib import Path

READY = Path("/tmp/monetization22268-notifications-ready")


def healthy() -> bool:
    try:
        return time.time() - READY.stat().st_mtime < 30
    except FileNotFoundError:
        return False


async def run() -> None:
    from runtime import guard, require

    settings = guard()
    require(settings.kafka_brokers == "redpanda:9092", "Refusing non-fixture Kafka")
    require(settings.redis_url == "redis://redis:6379/0", "Refusing non-fixture Redis")
    require(
        settings.kafka_notification_consumer_group == "monetization22268-notifications",
        "Refusing non-fixture consumer group",
    )

    # Register the production consumer before starting Kafka. Its transaction,
    # acknowledgement and receipt deduplication stay exactly as in event-worker.
    import application.notification_events  # noqa: F401
    from application.notifications.publisher import publish_outbox_batch
    from infrastructure.database import engine
    from infrastructure.logging import configure_logging, log_event
    from infrastructure.messaging.admin import ensure_topics
    from infrastructure.messaging.broker import start_broker, stop_broker

    configure_logging(service_name="carcraft-event-worker")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for event in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(event, stop.set)
    READY.unlink(missing_ok=True)
    await ensure_topics()
    await start_broker()
    log_event(
        "info", "monetization.e2e.notifications.started",
        "Isolated notification publisher and Kafka consumer started",
    )
    try:
        while not stop.is_set():
            # A short local scheduler drives the production outbox publisher;
            # SMTP and unrelated Taskiq jobs are never executed in this stack.
            await publish_outbox_batch()
            READY.touch()
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.5)
            except TimeoutError:
                pass
    finally:
        READY.unlink(missing_ok=True)
        await stop_broker()
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["run", "healthcheck"], default="run", nargs="?")
    args = parser.parse_args()
    if args.action == "healthcheck":
        raise SystemExit(0 if healthy() else 1)
    asyncio.run(run())
