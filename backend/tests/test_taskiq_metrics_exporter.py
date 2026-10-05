"""Scrape the container entrypoint, not a process-local registry substitute."""

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from prometheus_client.parser import text_string_to_metric_families

_BACKEND = Path(__file__).resolve().parents[1]


def _scrape_until(port: int, process: subprocess.Popen[bytes], sent_count: int) -> str:
    body = ""
    deadline = time.monotonic() + 12
    with httpx.Client(timeout=0.3, trust_env=False) as client:
        while time.monotonic() < deadline and process.poll() is None:
            try:
                response = client.get(f"http://127.0.0.1:{port}/metrics")
                response.raise_for_status()
                body = response.text
                if f'notification_email_outcomes_total{{state="sent"}} {sent_count}.0' in body:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
    return body


@pytest.mark.parametrize("launch", [1, 2])
def test_taskiq_http_export_sums_two_real_worker_processes(launch: int, tmp_path: Path) -> None:
    stale = tmp_path / f"stale-{launch}"
    stale.mkdir()
    marker = stale / "owned-by-another-launch"
    marker.write_text("keep", encoding="utf-8")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    command = [
        sys.executable, "-m", "infrastructure.container_entrypoint",
        str(Path(sys.executable).with_name("taskiq")), "worker",
        "tests.fixtures.taskiq_metrics_broker:broker", "--workers", "2",
        "--shutdown-timeout", "1", "--wait-tasks-timeout", "1",
    ]
    process = subprocess.Popen(  # noqa: S603 - fixed local CLI and test broker
        command, cwd=_BACKEND, env={
            **os.environ, "METRICS_PORT": str(port), "TMPDIR": str(tmp_path),
            # The launcher must ignore an inherited stale/shared directory and
            # start each container lifetime with independent empty counters.
            "PROMETHEUS_MULTIPROC_DIR": str(stale),
        },
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
    )
    try:
        body = _scrape_until(port, process, 4)
        samples = [sample for metric in text_string_to_metric_families(body) for sample in metric.samples]
        sent = [sample.value for sample in samples if sample.name == "notification_email_outcomes_total" and sample.labels == {"state": "sent"}]
        assert sent == [4.0], f"Missing aggregated worker counters in HTTP scrape: {body}"
        assert [sample.value for sample in samples if sample.name == "notification_email_outcomes_total" and sample.labels == {"state": "failed"}] == [2.0]
        assert [sample.value for sample in samples if sample.name == "notification_events_total" and sample.labels == {"stage": "published"}] == [6.0]
        assert [sample.value for sample in samples if sample.name == "notification_smtp_duration_seconds_count"] == [2.0]
        assert [sample.value for sample in samples if sample.name == "notification_smtp_duration_seconds_sum"] == [0.5]
        # Durable backlog belongs to the event-worker collector, not zero-valued
        # per-child gauges that would be misleading on this scrape target.
        assert not any(sample.name == "notification_email_backlog" for sample in samples)
        # A worker replacement must keep earlier counter/histogram increments.
        # SIGHUP is Taskiq's own full-reload contract, forwarded by the launcher.
        process.send_signal(signal.SIGHUP)
        body = _scrape_until(port, process, 8)
        samples = [sample for metric in text_string_to_metric_families(body) for sample in metric.samples]
        assert [sample.value for sample in samples if sample.name == "notification_email_outcomes_total" and sample.labels == {"state": "sent"}] == [8.0]
        assert [sample.value for sample in samples if sample.name == "notification_smtp_duration_seconds_count"] == [4.0]
    finally:
        process.terminate()
        try:
            process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=3)
    assert process.returncode == 0
    assert marker.read_text(encoding="utf-8") == "keep"
    assert not list(tmp_path.glob("carcraft-taskiq-metrics-*"))
