"""Minute sweep persists reminder/finalization facts in the caller transaction."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from application.services.exchange_notification_events import record_exchange_event
from infrastructure.repositories import exchange_request_repository as repo


async def scan_exchange_deadlines(session: AsyncSession, now: datetime) -> int:
    if now.utcoffset() is None:
        raise ValueError("Timezone-aware now required")
    count = 0
    for request in await repo.list_due_deadlines(session, now):
        expiration = request["expiration_at"].astimezone(UTC)
        remaining = int((expiration - now).total_seconds())
        if remaining <= 0:
            await repo.set_status(session, request["id"], status="archived")
            session.info.setdefault("notification_exchange_finalized_ids", []).append(
                request["id"]
            )
            count += bool(
                await record_exchange_event(
                    session,
                    event_type="exchange.request_finalized",
                    request={**request, "status": "archived"},
                    previous=request,
                    payload={"reason": "expired"},
                    occurrence_key=f"exchange.request_finalized:{request['id']}:{expiration.isoformat()}",
                )
            )
            continue
        # A late recovery emits only the most relevant reminder, never both
        # an already-missed 24h and 1h email in the last hour.
        event_type = (
            "exchange.deadline_1h" if remaining <= 3600 else "exchange.deadline_24h"
        )
        count += bool(
            await record_exchange_event(
                session,
                event_type=event_type,
                request=request,
                payload={
                    "remaining_seconds": remaining,
                    "remaining_time": f"{remaining // 3600} ч {(remaining % 3600) // 60} мин",
                },
                occurrence_key=f"{event_type}:{request['id']}:{expiration.isoformat()}",
            )
        )
    return count
