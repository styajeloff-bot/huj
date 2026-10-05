
"""Delete support program (soft via deactivation, parity with Express) and bill-of-lading file."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from domain.entities.support_program import SupportProgram
from domain.errors import (
    BillOfLadingFileNotFoundError,
    SupportProgramNotFoundError,
)
from infrastructure.repositories import support_repository


@dataclass
class DeleteSupportProgramCommand:
    program_id: UUID


@dataclass
class DeleteBillOfLadingCommand:
    program_id: UUID
    file_id: UUID


async def handle_delete_support_program(
    cmd: DeleteSupportProgramCommand, session: AsyncSession
) -> dict[str, Any]:
    """Soft-delete by deactivating — matches Express SupportAdminService.deleteSupportProgram."""
    existing = await support_repository.get_program_by_id(session, cmd.program_id)
    if existing is None:
        raise SupportProgramNotFoundError(cmd.program_id)
    program = SupportProgram.from_dict(existing)
    program.deactivate()
    await support_repository.set_program_active(
        session, cmd.program_id, program.is_active
    )
    from infrastructure.messaging.dwh_events import emit_support_program_changed
    emit_support_program_changed({
        "program_id": cmd.program_id,
        "name": existing.get("name"),
        "mark_id": existing.get("mark_id"),
        "model_id": existing.get("model_id"),
        "model_ids": existing.get("model_ids"),
        "complectation_ids": existing.get("complectation_ids"),
        "vin": existing.get("vin"),
        "vins": existing.get("vins"),
        "dealer_group_id": existing.get("dealer_group_id"),
        "distributor_id": existing.get("distributor_id"),
        "support_type": existing.get("support_type"),
        "support_params": existing.get("support_params"),
        "production_year_from": existing.get("production_year_from"),
        "production_year_to": existing.get("production_year_to"),
        "production_date_from": _isoformat(existing.get("production_date_from")),
        "production_date_to": _isoformat(existing.get("production_date_to")),
        "delivery_date_from": _isoformat(existing.get("delivery_date_from")),
        "delivery_date_to": _isoformat(existing.get("delivery_date_to")),
        "starts_at": _isoformat(existing.get("starts_at")),
        "ends_at": _isoformat(existing.get("ends_at")),
        "is_active": 0,
        "is_compatible": 1 if existing.get("is_compatible") else 0,
        "compatible_support_ids": existing.get("compatible_support_ids"),
        "show_to_leasing_company": 1 if existing.get("show_to_leasing_company") else 0,
        "show_to_client": 1 if existing.get("show_to_client") else 0,
        "comment": existing.get("comment"),
        "created_by": existing.get("created_by"),
        "created_at": _isoformat(existing.get("created_at")),
        "updated_at": _isoformat(existing.get("updated_at")),
        "_deleted": False,
    })
    return {"message": "Программа поддержки деактивирована"}


async def handle_delete_bill_of_lading(
    cmd: DeleteBillOfLadingCommand, session: AsyncSession
) -> dict[str, Any]:
    program = await support_repository.get_program_by_id(session, cmd.program_id)
    if program is None:
        raise SupportProgramNotFoundError(cmd.program_id)

    deleted = await support_repository.delete_bill_of_lading(
        session, cmd.program_id, cmd.file_id
    )
    if not deleted:
        raise BillOfLadingFileNotFoundError(cmd.file_id)

    refreshed = await support_repository.get_program_by_id(session, cmd.program_id)
    assert refreshed is not None
    return {"message": "Файл накладной удалён", "support_program": refreshed}
