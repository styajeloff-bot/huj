"""Post-commit compatibility publication for automatic Exchange expiration.

Notification guarantees belong to the transactional outbox. These existing
analytics/status publishers retain their current best-effort delivery contract.
"""

from uuid import UUID

from application.common import _isoformat
from application.services.exchange_dates import dwh_expiration_date
from infrastructure.database import AsyncSessionLocal
from infrastructure.messaging.dwh_events import emit_exchange_request_changed
from infrastructure.messaging.status_events import emit_exchange_request_status_changed
from infrastructure.repositories import exchange_request_repository as repo


async def publish_finalized_exchange_snapshots(request_ids: list[UUID]) -> None:
    async with AsyncSessionLocal() as session:
        snapshots = [
            row
            for request_id in dict.fromkeys(request_ids)
            if (row := await repo.get_by_id(session, request_id)) is not None
        ]
    for row in snapshots:
        if row["status"] != "archived":
            continue
        expiry = row.get("expiration_at")
        payload = {
            key: row.get(key)
            for key in (
                "lc_user_id",
                "vehicle_id",
                "quantity",
                "discount_type",
                "file_url",
                "file_name",
                "status",
                "accepted_bid_id",
                "batch_number",
                "batch_index",
            )
        }
        payload.update(
            request_id=row["id"],
            expiration_date=dwh_expiration_date(expiry),
            discount_value=str(row["discount_value"])
            if row.get("discount_value") is not None
            else None,
            created_at=_isoformat(row.get("created_at")),
            updated_at=_isoformat(row.get("updated_at")),
            _deleted=False,
        )
        emit_exchange_request_changed(payload)
        emit_exchange_request_status_changed(
            row["id"], "open", "archived", reason="expired"
        )
