"""Atomically validate and replace links without changing financial snapshots."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.queries.monetization.reference_documents import (
    context_from_program,
    list_reference_documents,
)
from infrastructure.repositories import (
    document_registry_monetization_repository as links,
)
from infrastructure.repositories import document_registry_repository as registry
from infrastructure.repositories import monetization_repository as programs


async def replace_reference_documents(session: AsyncSession, program_id: UUID,
                                      document_ids: list[UUID],
                                      actor: dict[str, Any]) -> dict[str, Any]:
    if not await links.lock_program(session, program_id):
        raise ServiceError("Условия монетизации не найдены", 404)
    program = await programs.get_program(session, program_id, actor)
    if program is None:
        raise ServiceError("Условия монетизации не найдены", 404)
    desired = list(dict.fromkeys(document_ids))
    current = set(await links.linked_ids(session, program_id))
    await registry.lock_documents(session, sorted(current | set(desired), key=str))
    # Existing expired/deactivated links may be retained, but deleted links never may.
    for document_id in desired:
        if await registry.get_document(session, document_id, actor) is None:
            raise ServiceError("Выбранный документ удалён или недоступен", 409)
    added = set(desired) - current
    if added:
        context = await context_from_program(session, program)
        from application.queries.document_registry.views import candidates
        available = await candidates(session, actor, context)
        allowed = {item["id"] for item in available["items"]}
        if not added.issubset(allowed):
            raise ServiceError("Выбранный документ больше не подходит к условиям монетизации", 409)
    await links.replace_links(session, program_id, desired, actor["user_id"])
    return await list_reference_documents(session, program_id, actor)
