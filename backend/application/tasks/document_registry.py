"""Recovery of uploaded registry objects that never acquired a DB reference."""

from infrastructure.database import AsyncSessionLocal
from infrastructure.logging import log_event
from infrastructure.services.document_registry_cleanup import (
    cleanup_orphaned_registry_files,
)
from infrastructure.taskiq_broker import broker


@broker.task(task_name="document_registry.cleanup_orphaned_files", schedule=[{"cron": "23 * * * *"}])
async def cleanup_orphaned_files() -> None:
    async with AsyncSessionLocal() as session:
        result = await cleanup_orphaned_registry_files(session)
        await session.commit()
    log_event(
        "info", "document_registry.orphans.cleaned", "Registry orphan upload cleanup completed",
        scanned=result["scanned"], deleted=result["deleted"], retained=result["retained"],
    )
