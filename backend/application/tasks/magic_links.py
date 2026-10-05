"""Magic-link housekeeping tasks."""
from __future__ import annotations

import logging

from infrastructure.database import AsyncSessionLocal
from infrastructure.repositories.magic_link_repository import delete_expired
from infrastructure.taskiq_broker import broker

logger = logging.getLogger("carcraft-backend")


@broker.task(
    task_name="magic_links.cleanup_expired",
    # Run once a day at 03:17 UTC — off-peak for both storage and logs.
    schedule=[{"cron": "17 3 * * *"}],
)
async def cleanup_expired_magic_links() -> None:
    """Drop expired-but-unused magic-link rows.

    Successful consumes already delete the row (see ``consume`` in the
    repo). The only rows left behind are those whose invitees never
    clicked — we purge them after the TTL expires so the table doesn't
    accumulate dead tokens.
    """
    async with AsyncSessionLocal() as session:
        try:
            count = await delete_expired(session)
            await session.commit()
            if count:
                logger.info("magic_links.cleanup_expired removed=%d", count)
        except Exception as exc:
            await session.rollback()
            logger.error("magic_links.cleanup_expired error=%s", exc)
            raise
