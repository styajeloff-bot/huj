"""Request session plus optional post-commit notification publisher wakeup."""

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from application.tasks.notifications import publish_outbox
from infrastructure.database import get_db as database_session
from infrastructure.logging import log_event


async def get_db(
    session: AsyncSession = Depends(database_session),
) -> AsyncGenerator[AsyncSession, None]:
    yield session
    if (
        session.info.pop("notification_outbox_pending", False)
        and not session.in_transaction()
    ):
        try:
            await publish_outbox.kiq()
        except Exception as exc:
            log_event(
                "warning",
                "notification.outbox.wakeup_failed",
                "Scheduled publisher will recover committed events",
                error_code=type(exc).__name__,
            )
