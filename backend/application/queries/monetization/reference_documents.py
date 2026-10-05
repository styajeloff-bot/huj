"""Registry documents keep their own access policy even within readable conditions."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories import (
    document_registry_monetization_repository as links,
)
from infrastructure.repositories import document_registry_repository as registry
from infrastructure.repositories import monetization_repository as programs


async def context_from_program(session: AsyncSession, program: dict[str, Any]) -> dict[str, Any]:
    catalog = await links.resolve_catalog(session, program.get("brand"), program.get("model"))
    if catalog is None:
        raise ServiceError("Марка или модель условий не найдена однозначно в каталоге", 409)
    return {
        "leasing_company_id": program["leasing_company_id"],
        "dealer_company_id": program.get("dealer_company_id"),
        "distributor_company_id": program.get("distributor_company_id"),
        **catalog,
        "platform_ml": any(
            row.get("participant_type") == "platform"
            for source in program.get("sources", [])
            for side in ("expenses", "incomes") for row in source.get(side, [])
        ),
    }


async def context_for_program(session: AsyncSession, program_id: UUID,
                              actor: dict[str, Any]) -> dict[str, Any]:
    program_actor = await programs.resolve_actor(
        session, actor["user_id"], actor["role"], actor.get("company_id"))
    if program_actor is None:
        raise ServiceError("Нет доступа к условиям монетизации", 403)
    program = await programs.get_program(session, program_id, program_actor)
    if program is None:
        raise ServiceError("Условия монетизации не найдены", 404)
    return await context_from_program(session, program)


async def list_reference_documents(session: AsyncSession, program_id: UUID,
                                    actor: dict[str, Any], *, for_update: bool = False) -> dict[str, Any]:
    if for_update:
        await links.lock_program(session, program_id)
        await registry.lock_documents(session, await links.linked_ids(session, program_id))
    if await programs.get_program(session, program_id, actor) is None:
        raise ServiceError("Условия монетизации не найдены", 404)
    items = []
    for document_id in await links.linked_ids(session, program_id):
        document = await registry.get_document(session, document_id, actor)
        if document is not None:
            items.append(document)
    return {"items": items}
