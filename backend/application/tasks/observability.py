"""Side-effect-free Taskiq diagnostic used by the local observability smoke."""

from __future__ import annotations

import re
from uuid import UUID

from taskiq.task import AsyncTaskiqTask

from infrastructure.taskiq_broker import broker

_MARKER_RE = re.compile(r"^local_observability_smoke(?:[-_][A-Za-z0-9_-]{1,64})?$")


def _validated_inputs(marker: str, correlation_id: str) -> tuple[str, str]:
    if not _MARKER_RE.fullmatch(marker):
        raise ValueError("invalid observability smoke marker")
    try:
        normalized_correlation_id = str(UUID(correlation_id))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid observability smoke correlation ID") from exc
    return marker, normalized_correlation_id


@broker.task(task_name="observability.smoke")
async def observability_smoke_task(marker: str) -> None:
    """Validate safe inputs; Taskiq middleware emits the sole terminal event."""
    if not _MARKER_RE.fullmatch(marker):
        raise ValueError("invalid observability smoke marker")


async def enqueue_observability_smoke(
    *, marker: str, correlation_id: str
) -> AsyncTaskiqTask[None]:
    """Enqueue a diagnostic run with correlation carried only as metadata."""
    safe_marker, safe_correlation_id = _validated_inputs(marker, correlation_id)
    return (
        await observability_smoke_task.kicker()
        .with_labels(
            correlation_id=safe_correlation_id,
            observability_marker=safe_marker,
        )
        .kiq(
            marker=safe_marker,
        )
    )


__all__ = ["enqueue_observability_smoke", "observability_smoke_task"]
