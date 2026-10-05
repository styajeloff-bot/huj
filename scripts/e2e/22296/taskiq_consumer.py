"""Isolated production Taskiq expiry E2E; launched only by taskiq_run.py."""
# ruff: noqa: E402
# Bootstrap must validate fixture resources before production imports.

import asyncio
import signal
from pathlib import Path
import taskiq_bootstrap  # noqa: F401 - validates and isolates transport before app import
from runtime import guard

guard()


async def main():
    import application.notification_events  # noqa: F401 - registers the production subscriber
    from infrastructure.messaging.admin import ensure_topics
    from infrastructure.messaging.broker import start_broker, stop_broker
    from infrastructure.logging import configure_logging

    configure_logging(service_name="carcraft-event-worker")
    await ensure_topics()
    await start_broker()
    Path("/runtime/taskiq-consumer-ready").write_text("ready")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    try:
        await stop.wait()
    finally:
        await stop_broker()


asyncio.run(main())
