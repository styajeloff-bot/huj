
"""Partial update (PATCH) for a support program.

Focused on narrow state transitions — `{active: bool}` replaces the former
RPC-style `/activate` / `/deactivate` endpoints. Extra fields may be added
later; for now we restrict the patch payload to `is_active` to keep the
domain invariants (ensure_valid) unaffected.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from domain.entities.support_program import SupportProgram
from domain.errors import SupportProgramNotFoundError
from infrastructure.repositories import support_repository


@dataclass
class PatchSupportProgramCommand:
    program_id: UUID
    is_active: bool | None = None


async def handle_patch_support_program(
    cmd: PatchSupportProgramCommand, session: AsyncSession
) -> dict[str, Any]:
    existing = await support_repository.get_program_by_id(session, cmd.program_id)
    if existing is None:
        raise SupportProgramNotFoundError(cmd.program_id)

    program = SupportProgram.from_dict(existing)
    if cmd.is_active is not None:
        if cmd.is_active:
            program.activate()
        else:
            program.deactivate()
        await support_repository.set_program_active(
            session, cmd.program_id, program.is_active
        )

    refreshed = await support_repository.get_program_by_id(
        session, cmd.program_id
    )
    assert refreshed is not None
    from infrastructure.messaging.dwh_events import emit_support_program_changed
    emit_support_program_changed({
        "program_id": cmd.program_id,
        "name": refreshed.get("name"),
        "mark_id": refreshed.get("mark_id"),
        "model_id": refreshed.get("model_id"),
        "model_ids": refreshed.get("model_ids"),
        "complectation_ids": refreshed.get("complectation_ids"),
        "vin": refreshed.get("vin"),
        "vins": refreshed.get("vins"),
        "dealer_group_id": refreshed.get("dealer_group_id"),
        "distributor_id": refreshed.get("distributor_id"),
        "support_type": refreshed.get("support_type"),
        "support_params": refreshed.get("support_params"),
        "production_year_from": refreshed.get("production_year_from"),
        "production_year_to": refreshed.get("production_year_to"),
        "production_date_from": _isoformat(refreshed.get("production_date_from")),
        "production_date_to": _isoformat(refreshed.get("production_date_to")),
        "delivery_date_from": _isoformat(refreshed.get("delivery_date_from")),
        "delivery_date_to": _isoformat(refreshed.get("delivery_date_to")),
        "starts_at": _isoformat(refreshed.get("starts_at")),
        "ends_at": _isoformat(refreshed.get("ends_at")),
        "is_active": 1 if refreshed.get("is_active") else 0,
        "is_compatible": 1 if refreshed.get("is_compatible") else 0,
        "compatible_support_ids": refreshed.get("compatible_support_ids"),
        "show_to_leasing_company": 1 if refreshed.get("show_to_leasing_company") else 0,
        "show_to_client": 1 if refreshed.get("show_to_client") else 0,
        "comment": refreshed.get("comment"),
        "created_by": refreshed.get("created_by"),
        "created_at": _isoformat(refreshed.get("created_at")),
        "updated_at": _isoformat(refreshed.get("updated_at")),
        "_deleted": False,
    })
    return cast("dict[str, Any]", refreshed)
