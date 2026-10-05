
"""Create support program command."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.support.validate_compatibility import (
    validate_compatibility_targets,
)
from application.common import _isoformat
from domain.entities.support_program import SupportProgram
from domain.errors import (
    DealerGroupNotFoundError,
    DistributorNotFoundError,
    InvalidSupportProgramError,
    LeasingCompanyNotFoundError,
)
from infrastructure.repositories import (
    compensation_repository,
    dealer_group_repository,
    support_repository,
)


@dataclass
class CreateSupportProgramCommand:
    name: str
    mark_id: UUID | str | None
    support_type: str
    support_params: dict[str, Any]
    mark_ids: list[Any] = field(default_factory=list)
    model_id: UUID | str | None = None
    model_ids: list[Any] | None = None
    complectation_ids: list[str] | None = None
    vin: str | None = None
    vins: list[str] | None = None
    dealer_group_ids: list[UUID] = field(default_factory=list)
    distributor_id: UUID | None = None
    distributor_ids: list[UUID] = field(default_factory=list)
    leasing_company_ids: list[UUID] = field(default_factory=list)
    compensation_templates: list[dict[str, Any]] = field(default_factory=list)
    production_year_from: int | None = None
    production_year_to: int | None = None
    production_date_from: _dt.date | None = None
    production_date_to: _dt.date | None = None
    delivery_date_from: _dt.date | None = None
    delivery_date_to: _dt.date | None = None
    starts_at: _dt.date | None = None
    ends_at: _dt.date | None = None
    is_active: bool = False
    is_compatible: bool = False
    compatible_support_ids: list[UUID] = field(default_factory=list)
    show_to_leasing_company: bool = True
    show_to_client: bool = True
    comment: str | None = None
    created_by: UUID | None = None


async def handle_create_support_program(
    cmd: CreateSupportProgramCommand, session: AsyncSession
) -> dict[str, Any]:
    dealer_group_ids = list(cmd.dealer_group_ids or [])
    mark_ids = list(cmd.mark_ids or ([] if not cmd.mark_id else [cmd.mark_id]))
    distributor_ids = list(
        cmd.distributor_ids
        or ([] if cmd.distributor_id is None else [cmd.distributor_id])
    )
    program = SupportProgram(
        program_id=None,
        name=cmd.name,
        mark_id=mark_ids[0] if mark_ids else cmd.mark_id,
        mark_ids=mark_ids,
        support_type=cmd.support_type,
        support_params=cmd.support_params,
        model_id=cmd.model_id,
        model_ids=cmd.model_ids,
        complectation_ids=cmd.complectation_ids,
        vin=cmd.vin,
        vins=cmd.vins,
        dealer_group_id=dealer_group_ids[0] if len(dealer_group_ids) == 1 else None,
        dealer_group_ids=dealer_group_ids,
        distributor_id=distributor_ids[0] if len(distributor_ids) == 1 else None,
        distributor_ids=distributor_ids,
        leasing_company_ids=list(cmd.leasing_company_ids or []),
        production_year_from=cmd.production_year_from,
        production_year_to=cmd.production_year_to,
        production_date_from=cmd.production_date_from,
        production_date_to=cmd.production_date_to,
        delivery_date_from=cmd.delivery_date_from,
        delivery_date_to=cmd.delivery_date_to,
        starts_at=cmd.starts_at,
        ends_at=cmd.ends_at,
        is_active=cmd.is_active,
        is_compatible=cmd.is_compatible,
        compatible_support_ids=list(cmd.compatible_support_ids or []),
        show_to_leasing_company=cmd.show_to_leasing_company,
        show_to_client=cmd.show_to_client,
        comment=cmd.comment,
        created_by=cmd.created_by,
    )
    program.ensure_valid()
    disabled_compatibility_targets = await validate_compatibility_targets(
        session, program
    )

    if program.dealer_group_ids:
        if program.distributor_id is None:
            raise InvalidSupportProgramError(
                "Для групп дилеров выберите одного дистрибьютора"
            )
        existing = await dealer_group_repository.get_group_distributor_ids(
            session, program.dealer_group_ids
        )
        missing = [g for g in program.dealer_group_ids if g not in existing]
        if missing:
            raise DealerGroupNotFoundError(missing[0])
        mismatched = [
            g
            for g, distributor_id in existing.items()
            if distributor_id != program.distributor_id
        ]
        if mismatched:
            raise InvalidSupportProgramError(
                "Группы дилеров должны принадлежать выбранному дистрибьютору"
            )

    if program.distributor_ids:
        existing_distributors = await support_repository.get_existing_distributor_ids(
            session, program.distributor_ids
        )
        missing_distributors = [
            distributor_id
            for distributor_id in program.distributor_ids
            if distributor_id not in existing_distributors
        ]
        if missing_distributors:
            raise DistributorNotFoundError(missing_distributors[0])

    if program.leasing_company_ids:
        existing_lc = await support_repository.get_existing_leasing_company_ids(
            session, program.leasing_company_ids
        )
        missing_lc = [
            lc for lc in program.leasing_company_ids if lc not in existing_lc
        ]
        if missing_lc:
            raise LeasingCompanyNotFoundError(missing_lc[0])

    await support_repository.enable_program_compatibility(
        session, disabled_compatibility_targets
    )

    program_id = await support_repository.create_program(
        session, program.to_persistence_dict()
    )
    await support_repository.replace_leasing_companies(
        session, program_id, program.leasing_company_ids
    )
    await support_repository.replace_marks(session, program_id, program.mark_ids)
    await support_repository.replace_distributors(
        session, program_id, program.distributor_ids
    )
    await support_repository.replace_dealer_groups(
        session, program_id, program.dealer_group_ids
    )
    await support_repository.replace_compatible_supports(
        session, program_id, program.compatible_support_ids
    )
    await compensation_repository.replace_compensation_templates(
        session,
        program_id,
        list(cmd.compensation_templates or []),
        created_by=cmd.created_by,
    )
    saved = await support_repository.get_program_by_id(session, program_id)
    assert saved is not None
    from infrastructure.messaging.dwh_events import emit_support_program_changed
    emit_support_program_changed({
        "program_id": program_id,
        "name": saved.get("name"),
        "mark_id": saved.get("mark_id"),
        "mark_ids": saved.get("mark_ids"),
        "model_id": saved.get("model_id"),
        "model_ids": saved.get("model_ids"),
        "complectation_ids": saved.get("complectation_ids"),
        "vin": saved.get("vin"),
        "vins": saved.get("vins"),
        "dealer_group_id": saved.get("dealer_group_id"),
        "distributor_id": saved.get("distributor_id"),
        "distributor_ids": saved.get("distributor_ids"),
        "support_type": saved.get("support_type"),
        "support_params": saved.get("support_params"),
        "production_year_from": saved.get("production_year_from"),
        "production_year_to": saved.get("production_year_to"),
        "production_date_from": _isoformat(saved.get("production_date_from")),
        "production_date_to": _isoformat(saved.get("production_date_to")),
        "delivery_date_from": _isoformat(saved.get("delivery_date_from")),
        "delivery_date_to": _isoformat(saved.get("delivery_date_to")),
        "starts_at": _isoformat(saved.get("starts_at")),
        "ends_at": _isoformat(saved.get("ends_at")),
        "is_active": 1 if saved.get("is_active") else 0,
        "is_compatible": 1 if saved.get("is_compatible") else 0,
        "compatible_support_ids": saved.get("compatible_support_ids"),
        "show_to_leasing_company": 1 if saved.get("show_to_leasing_company") else 0,
        "show_to_client": 1 if saved.get("show_to_client") else 0,
        "comment": saved.get("comment"),
        "created_by": saved.get("created_by"),
        "created_at": _isoformat(saved.get("created_at")),
        "updated_at": _isoformat(saved.get("updated_at")),
        "_deleted": False,
    })
    return cast("dict[str, Any]", saved)
