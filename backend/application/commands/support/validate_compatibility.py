"""Shared validation for support-program compatibility writes."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.support_program import SupportProgram
from domain.errors import SupportProgramNotFoundError
from infrastructure.repositories import support_repository


async def validate_compatibility_targets(
    session: AsyncSession, program: SupportProgram
) -> list[UUID]:
    """Ensure every referenced neighbor exists and return disabled targets."""
    target_ids = program.compatible_support_ids
    if not target_ids:
        return []

    flags = await support_repository.get_program_compatibility_flags(
        session, target_ids
    )
    missing_ids = [program_id for program_id in target_ids if program_id not in flags]
    if missing_ids:
        raise SupportProgramNotFoundError(missing_ids[0])

    return [
        program_id
        for program_id in target_ids
        if not flags.get(program_id, False)
    ]
