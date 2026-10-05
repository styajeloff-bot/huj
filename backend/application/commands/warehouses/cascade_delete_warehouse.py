"""Warehouse cascade delete command handlers."""
from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import (
    warehouse_cascade_repository as cascade_repo,
)


async def handle_preview_warehouse_cascade_delete(
    warehouse_id: UUID,
    session: AsyncSession,
) -> dict[str, Any]:
    """Calculate cascade delete plan and blockers without mutating data."""
    return cast(
        "dict[str, Any]",
        await cascade_repo.get_warehouse_cascade_preview(session, warehouse_id),
    )


async def handle_cascade_delete_warehouse(
    *,
    warehouse_id: UUID,
    confirmation: str,
    preview_token: str,
    user_id: UUID | None,
    session: AsyncSession,
) -> dict[str, Any]:
    """Execute confirmed warehouse cascade deletion under lock."""
    return cast(
        "dict[str, Any]",
        await cascade_repo.execute_warehouse_cascade_delete(
            session,
            warehouse_id=warehouse_id,
            confirmation=confirmation,
            preview_token=preview_token,
            user_id=user_id,
        ),
    )


get_warehouse_delete_preview = handle_preview_warehouse_cascade_delete
execute_warehouse_cascade_delete = handle_cascade_delete_warehouse

__all__ = [
    "execute_warehouse_cascade_delete",
    "get_warehouse_delete_preview",
    "handle_cascade_delete_warehouse",
    "handle_preview_warehouse_cascade_delete",
]
