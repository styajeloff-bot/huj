"""Compensation-related scheduled tasks."""
from __future__ import annotations

import logging

from application.commands.compensations import (
    handle_auto_cancel_inactive_support_compensations,
    handle_auto_recalculate_application_compensations,
)
from infrastructure.database import AsyncSessionLocal
from infrastructure.repositories.compensation_repository import (
    mark_overdue_compensations,
)
from infrastructure.taskiq_broker import broker

logger = logging.getLogger("carcraft-backend")


@broker.task(
    task_name="compensations.mark_overdue",
    schedule=[{"cron": "*/5 * * * *"}],
)
async def mark_overdue_compensations_task() -> None:
    """Every 5 minutes: transition compensations past due_date to overdue."""
    async with AsyncSessionLocal() as session:
        try:
            count = await mark_overdue_compensations(session)
            await session.commit()
            if count:
                logger.info("compensations.mark_overdue count=%d", count)
        except Exception as exc:
            await session.rollback()
            logger.error("compensations.mark_overdue error=%s", exc)
            raise


@broker.task(
    task_name="compensations.sync",
    schedule=[{"cron": "*/5 * * * *"}],
)
async def sync_compensations_task() -> None:
    """Every 5 minutes: auto-recalculate + auto-cancel compensations."""
    async with AsyncSessionLocal() as session:
        try:
            recalculated = await handle_auto_recalculate_application_compensations(session)
            cancelled = await handle_auto_cancel_inactive_support_compensations(session)
            await session.commit()
            if recalculated:
                logger.info(
                    "compensations.sync recalculated=%d", recalculated
                )
            if cancelled["cancelled_count"]:
                logger.info(
                    "compensations.sync cancelled=%d supports_processed=%d",
                    cancelled["cancelled_count"],
                    cancelled["supports_processed"],
                )
            if cancelled["warnings"]:
                logger.warning(
                    "compensations.sync manual_handling_needed=%d",
                    len(cancelled["warnings"]),
                )
        except Exception as exc:
            await session.rollback()
            logger.error("compensations.sync error=%s", exc)
            raise
