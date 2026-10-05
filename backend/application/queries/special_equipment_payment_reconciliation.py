"""Employee read model for special-equipment payment reconciliation."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories import (
    special_equipment_commerce_repository as repository,
)


def _resource(row: dict[str, Any]) -> dict[str, Any]:
    reason = row.get("manual_review_reason")
    return {
        "id": row["id"],
        "payment_id": row.get("payment_id"),
        "purchase_order_id": row.get("purchase_order_id"),
        "gateway_transaction_id": row["gateway_transaction_id"],
        "status": row["status"],
        "attempt_count": row["attempt_count"],
        "last_error_code": row.get("last_error_code"),
        "manual_review_reason": reason,
        "refund_required": bool(
            isinstance(reason, str) and reason.startswith("LATE_SUCCESS")
        ),
        "provider_state": row["payload"],
        "received_at": row["received_at"],
        "processed_at": row.get("processed_at"),
        "updated_at": row["updated_at"],
    }


async def list_payment_reconciliations(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    rows = await repository.list_manual_review_payment_callbacks(
        session,
        limit=page_size + 1,
        offset=(page - 1) * page_size,
    )
    return {
        "items": [_resource(row) for row in rows[:page_size]],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "has_more": len(rows) > page_size,
        },
    }


async def get_payment_reconciliation(
    session: AsyncSession,
    reconciliation_id: UUID,
) -> dict[str, Any]:
    row = await repository.get_payment_callback_inbox(
        session,
        reconciliation_id,
    )
    if row is None or row["status"] != "manual_review":
        raise ServiceError("Payment reconciliation not found", status_code=404)
    return {"reconciliation": _resource(row)}
