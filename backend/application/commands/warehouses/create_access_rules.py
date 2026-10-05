"""Create or upsert warehouse access rules command."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from domain.errors import WarehouseNotFoundError
from infrastructure.repositories import warehouse_access_rule_repository as rule_repo
from infrastructure.repositories import warehouse_repository as wh_repo


@dataclass
class CreateAccessRulesCommand:
    warehouse_id: UUID
    mode: str
    dealers: list[dict[str, Any]] | None = None
    dealer_group_id: UUID | None = None
    group_access_type: str = "B"
    site_id: UUID | None = None
    brand_id: UUID | None = None
    actor_role: str | None = None
    actor_company_ids: list[UUID] | None = None


async def handle_create_access_rules(
    cmd: CreateAccessRulesCommand, session: AsyncSession
) -> list[dict[str, Any]]:
    warehouse = await wh_repo.get_by_id(session, cmd.warehouse_id, is_admin=True)
    if warehouse is None:
        raise WarehouseNotFoundError(cmd.warehouse_id)

    if cmd.actor_role != "carcraft_employee" and cmd.actor_company_ids is not None:
        owner_id = warehouse.get("owner_company_id")
        if owner_id is None or UUID(str(owner_id)) not in cmd.actor_company_ids:
            raise ServiceError("У вас нет прав на управление доступом к этому складу", 403)

    from typing import cast

    return cast(
        "list[dict[str, Any]]",
        await rule_repo.create_or_upsert_rules(
            session,
            warehouse_id=cmd.warehouse_id,
            mode=cmd.mode,
            dealers=cmd.dealers,
            dealer_group_id=cmd.dealer_group_id,
            group_access_type=cmd.group_access_type,
            site_id=cmd.site_id,
            brand_id=cmd.brand_id,
        ),
    )
