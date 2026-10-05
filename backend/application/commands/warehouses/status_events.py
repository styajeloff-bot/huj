"""Explicit command results and post-commit warehouse status publishing."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NotRequired, TypedDict
from uuid import UUID


class WarehouseStatusEvent(TypedDict):
    warehouse_id: UUID
    old_status: str | None
    new_status: str
    company_id: UUID | None
    payload: NotRequired[dict[str, Any]]


class WarehouseMutationResult(TypedDict):
    warehouse: dict[str, Any]
    status_events: list[WarehouseStatusEvent]


class WarehouseDeleteResult(TypedDict):
    status_events: list[WarehouseStatusEvent]


def publish_warehouse_status_events(
    events: Sequence[WarehouseStatusEvent],
) -> None:
    """Publish command-prepared events after the caller commits the DB work."""

    from infrastructure.messaging.status_events import emit_warehouse_status_changed

    for event in events:
        emit_warehouse_status_changed(**event)
