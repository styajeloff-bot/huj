"""Container entrypoint that keeps Taskiq CLI logs compact from process start."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path

_COMPACT_LOG_FORMAT = "%(message)s"


def _taskiq_subcommand_index(command: Sequence[str]) -> int | None:
    if command and Path(command[0]).name == "taskiq":
        return 1 if len(command) > 1 else None
    if (
        len(command) >= 3
        and Path(command[0]).name == "uv"
        and command[1] == "run"
        and Path(command[2]).name == "taskiq"
    ):
        return 3 if len(command) > 3 else None
    return None


def normalize_container_command(argv: Sequence[str]) -> list[str]:
    """Inject Taskiq logging flags without changing unrelated container commands."""

    command = list(argv)
    subcommand_index = _taskiq_subcommand_index(command)
    if subcommand_index is None:
        return command

    subcommand = command[subcommand_index]
    if subcommand == "worker" and "--log-format" not in command:
        command[subcommand_index + 1 : subcommand_index + 1] = [
            "--log-format",
            _COMPACT_LOG_FORMAT,
        ]
    elif subcommand == "scheduler" and "--no-configure-logging" not in command:
        command.insert(subcommand_index + 1, "--no-configure-logging")
    return command


def main() -> None:
    command = normalize_container_command(sys.argv[1:])
    if not command:
        raise SystemExit("container command is required")
    subcommand_index = _taskiq_subcommand_index(command)
    if subcommand_index is not None and command[subcommand_index] == "worker":
        # This launcher, not a worker-startup callback, owns the one scrape port.
        # The import stays lazy so the multiprocess env is set before metrics.
        from infrastructure.taskiq_metrics import run_worker_with_metrics

        raise SystemExit(run_worker_with_metrics(command))
    # Docker supplies the command; exec preserves signal delivery to the service.
    os.execvp(command[0], command)  # noqa: S606


if __name__ == "__main__":
    main()
