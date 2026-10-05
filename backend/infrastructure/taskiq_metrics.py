"""One scrape endpoint for all Taskiq children in a container lifetime.

The launcher owns a fresh metrics directory, never shared with another replica
or cleared on an individual worker restart. Counters/histograms therefore keep
the contributions of exited workers until the container itself restarts.
"""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Iterable, Sequence
from contextlib import suppress
from tempfile import TemporaryDirectory
from types import FrameType


def run_worker_with_metrics(command: Sequence[str]) -> int:
    """Run the CLI, export aggregated metrics, and forward container signals.

    Call before importing Prometheus or application modules. The child command
    is trusted container configuration, not request input. METRICS_PORT comes
    from Settings; the generated directory is a protocol value for the Python
    Prometheus client, not user configuration and never a shared volume.
    """
    with TemporaryDirectory(prefix="carcraft-taskiq-metrics-") as directory:
        # Export only: configuration is still read exclusively through Settings.
        # Set this before child imports choose Prometheus's value implementation.
        os.putenv("PROMETHEUS_MULTIPROC_DIR", directory)

        from prometheus_client import CollectorRegistry, start_http_server
        from prometheus_client.metrics_core import Metric
        from prometheus_client.multiprocess import MultiProcessCollector

        from infrastructure.logging import configure_logging, log_event
        from infrastructure.settings import settings

        class WorkerCounters(MultiProcessCollector):
            def collect(self) -> Iterable[Metric]:
                # Global durable gauges are owned by the event-worker. Do not
                # emit a misleading zero/PID series from each Taskiq child.
                return (metric for metric in super().collect() if metric.type != "gauge")

        registry = CollectorRegistry()
        WorkerCounters(registry, path=directory)
        configure_logging(service_name="carcraft-taskiq-worker")
        server, thread = start_http_server(settings.metrics_port, registry=registry)
        process: subprocess.Popen[bytes] | None = None
        previous_handlers = {}
        try:
            process = subprocess.Popen(list(command), start_new_session=True)  # noqa: S603

            def forward(signum: int, _frame: FrameType | None) -> None:
                # The Taskiq process manager owns graceful child shutdown/reload.
                if process is not None:
                    with suppress(ProcessLookupError):
                        process.send_signal(signum)

            for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                previous_handlers[signum] = signal.signal(signum, forward)
            log_event(
                "info", "taskiq.metrics.started", "Taskiq multiprocess metrics exporter started",
                component="metrics", metrics_port=settings.metrics_port,
            )
            result = process.wait()
            return result if result >= 0 else 128 - result
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)
            if process is not None:
                # If the manager crashed, do not leave orphan workers writing
                # into the directory that this launcher is about to release.
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            server.shutdown()
            server.server_close()
            thread.join()
