"""Create and activate isolated monetization conditions."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.monetization.deals import require_write
from application.commands.monetization.reference_documents import (
    replace_reference_documents,
)
from application.errors import ServiceError
from application.queries.monetization.reference_documents import (
    list_reference_documents,
)
from application.queries.monetization.views import program_view
from domain.monetization.programs import (
    CURRENT_RULES_VERSION,
    CURRENT_VEHICLE_FILTER_VERSION,
    validate_program,
)
from infrastructure.repositories import monetization_repository as repo


async def create_program(session: AsyncSession, payload: dict[str, Any],
                         actor: dict[str, Any]) -> dict[str, Any]:
    require_write(actor)
    payload = dict(
        payload,
        rules_version=CURRENT_RULES_VERSION,
        vehicle_filter_version=CURRENT_VEHICLE_FILTER_VERSION,
    )
    validate_program(payload)
    created = await repo.create_program(session, payload, actor["user_id"])
    linked = await replace_reference_documents(
        session, created["id"], payload.get("reference_document_ids", []), actor)
    result = program_view(created, actor)
    result["reference_documents"] = linked["items"]
    return {"program": result}


async def change_program_status(session: AsyncSession, program_id: UUID, status: str,
                                actor: dict[str, Any]) -> dict[str, Any]:
    require_write(actor)
    current = await repo.get_program(session, program_id, actor)
    if current is None:
        raise ServiceError("Условия монетизации не найдены", 404)
    saved = await repo.set_program_status(session, program_id, status)
    if saved is None:
        raise ServiceError("Условия монетизации не найдены", 404)
    result = program_view(saved, actor)
    result["reference_documents"] = (await list_reference_documents(session, program_id, actor, for_update=True))["items"]
    return {"program": result}
