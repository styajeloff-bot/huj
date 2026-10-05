"""Replace distributor-company vehicle brand settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories import (
    company_change_history_repository as history_repo,
)
from infrastructure.repositories import (
    distributor_brand_repository as repo,
)


@dataclass(frozen=True)
class SetDistributorBrandsCommand:
    company_id: UUID
    brand_ids: list[str]
    # Legacy direct callers predate audit history. They retain their mutation
    # behavior but deliberately cannot create an unattributable audit row.
    actor_user_id: UUID | None = None


async def handle_set_distributor_brands(
    command: SetDistributorBrandsCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    company = await repo.get_company(
        session,
        command.company_id,
        for_update=True,
    )
    if company is None:
        raise ServiceError("Компания не найдена.", 404)
    if company["company_type"] != "distributor":
        raise ServiceError("Компания не является дистрибьютором.", 400)

    brand_ids = list(dict.fromkeys(command.brand_ids))
    existing_ids = await repo.get_existing_brand_ids(session, brand_ids)
    unknown_ids = sorted(set(brand_ids).difference(existing_ids))
    if unknown_ids:
        raise ServiceError(
            "Неизвестные марки: " + ", ".join(unknown_ids),
            400,
        )

    current_ids = await repo.list_active_brand_ids(session, command.company_id)
    if current_ids == sorted(brand_ids):
        return {
            "available_brands": await repo.list_available_brands(session),
            "selected_brand_ids": current_ids,
        }

    try:
        selected_brand_ids = await repo.replace_active_brand_ids(
            session,
            distributor_company_id=command.company_id,
            brand_ids=brand_ids,
        )
    except IntegrityError as exc:
        raise ServiceError(
            "Набор марок был изменён параллельно. Повторите сохранение.",
            409,
        ) from exc

    if command.actor_user_id is not None:
        await history_repo.write_snapshot(
            session,
            company_id=command.company_id,
            actor_user_id=command.actor_user_id,
            action="distributor_brands_saved",
            include_brands=True,
        )
    return {
        "available_brands": await repo.list_available_brands(session),
        "selected_brand_ids": selected_brand_ids,
    }
