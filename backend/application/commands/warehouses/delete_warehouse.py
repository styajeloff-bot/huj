"""Delete warehouse command."""
from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.warehouses.status_events import WarehouseDeleteResult
from application.errors import ServiceError
from domain.errors import WarehouseNotFoundError
from infrastructure.repositories import warehouse_repository as repo


@dataclass
class DeleteWarehouseCommand:
    warehouse_id: UUID


class WarehouseDeleteBlockedError(ServiceError):
    def __init__(self, blocking_dependencies: dict[str, int]) -> None:
        super().__init__("Warehouse has blocking dependencies", status_code=409)
        self.blocking_dependencies = blocking_dependencies


async def handle_delete_warehouse_integrity_fallback(
    exc: BaseException, cmd: DeleteWarehouseCommand, session: AsyncSession
) -> dict[str, int] | None:
    """Return fresh counts only for known database dependency backstops."""
    if not repo.is_known_delete_dependency_integrity_error(exc):
        return None
    return cast(
        "dict[str, int]",
        await repo.get_delete_blocking_dependencies_read_only(
            session, cmd.warehouse_id
        ),
    )


async def handle_delete_warehouse(
    cmd: DeleteWarehouseCommand, session: AsyncSession
) -> WarehouseDeleteResult:
    existing = await repo.get_locked_by_id(session, cmd.warehouse_id)
    if existing is None:
        raise WarehouseNotFoundError(cmd.warehouse_id)
    dependencies = await repo.get_delete_blocking_dependencies(session, cmd.warehouse_id)
    if any(dependencies.values()):
        raise WarehouseDeleteBlockedError(dependencies)
    await repo.delete_warehouse(session, cmd.warehouse_id)
    return {
        "status_events": [{
            "warehouse_id": cmd.warehouse_id,
            "old_status": existing["status"],
            "new_status": "deleted",
            "company_id": existing["company_id"],
        }]
    }
