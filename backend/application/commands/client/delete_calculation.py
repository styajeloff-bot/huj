"""Delete a saved leasing calculation (owner-checked)."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.client_profile import SavedCalculation
from domain.errors import SavedCalculationNotFoundError
from infrastructure.repositories import client_repository as repo


@dataclass(frozen=True)
class DeleteSavedCalculationCommand:
    user_id: UUID
    calculation_id: UUID


async def handle_delete_saved_calculation(
    cmd: DeleteSavedCalculationCommand, session: AsyncSession
) -> None:
    raw = await repo.get_saved_calculation(session, cmd.calculation_id)
    if raw is None:
        raise SavedCalculationNotFoundError(cmd.calculation_id)
    entity = SavedCalculation.from_dict(raw)
    entity.ensure_owned_by(cmd.user_id)
    await repo.delete_saved_calculation(session, cmd.calculation_id)
