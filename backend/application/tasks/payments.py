"""Payment-related scheduled tasks."""
from __future__ import annotations

import logging
from uuid import UUID

from infrastructure.database import AsyncSessionLocal
from infrastructure.services.payment_gateway import (
    expire_stale_payments,
    fiscalize_special_equipment_payments,
    retry_pending_special_equipment_receipts,
)
from infrastructure.services.special_equipment_payment_callbacks import (
    retry_pending_callbacks,
)
from infrastructure.taskiq_broker import broker

logger = logging.getLogger("carcraft-backend")


@broker.task(
    task_name="payments.expire_stale",
    schedule=[{"cron": "* * * * *"}],
)
async def expire_stale_payments_task() -> None:
    """Every minute: transition pending payments past their TTL to expired."""
    async with AsyncSessionLocal() as session:
        try:
            await expire_stale_payments(session)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error("payments.expire_stale error=%s", exc)
            raise


@broker.task(
    task_name="payments.retry_special_equipment_receipts",
    schedule=[{"cron": "* * * * *"}],
)
async def retry_special_equipment_receipts_task() -> None:
    """Retry due fiscal-receipt ingestion jobs without an open DB session."""

    try:
        claimed = await retry_pending_special_equipment_receipts()
        if claimed:
            logger.info(
                "payments.retry_special_equipment_receipts claimed=%s",
                claimed,
            )
    except Exception as exc:
        logger.error(
            "payments.retry_special_equipment_receipts error=%s",
            type(exc).__name__,
        )
        raise


@broker.task(task_name="payments.fiscalize_special_equipment")
async def fiscalize_special_equipment_payment_task(payment_id: str) -> None:
    """Run one durable fiscal attempt for a committed equipment payment."""

    await fiscalize_special_equipment_payments(
        payment_id=UUID(payment_id),
        limit=1,
    )


@broker.task(
    task_name="payments.retry_special_equipment_fiscalization",
    schedule=[{"cron": "* * * * *"}],
)
async def retry_special_equipment_fiscalization_task() -> None:
    """Recover pending/failed/stale-sent fiscal work after enqueue failure."""

    claimed = await fiscalize_special_equipment_payments()
    if claimed:
        logger.info(
            "payments.retry_special_equipment_fiscalization claimed=%s",
            claimed,
        )


@broker.task(
    task_name="payments.retry_special_equipment_callbacks",
    schedule=[{"cron": "* * * * *"}],
)
async def retry_special_equipment_callbacks_task() -> None:
    """Recover verified callbacks left pending by crashes or transient errors."""

    claimed = await retry_pending_callbacks()
    if claimed:
        logger.info(
            "payments.retry_special_equipment_callbacks claimed=%s",
            claimed,
        )
