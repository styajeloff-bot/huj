"""Delete warehouse access rule command."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories import warehouse_access_rule_repository as rule_repo
from infrastructure.repositories import warehouse_repository as wh_repo


@dataclass
class DeleteAccessRuleCommand:
    rule_id: UUID
    actor_role: str | None = None
    actor_company_ids: list[UUID] | None = None


async def handle_delete_access_rule(
    cmd: DeleteAccessRuleCommand, session: AsyncSession
) -> bool:
    rule = await rule_repo.get_rule_by_id(session, cmd.rule_id)
    if rule is None:
        raise ServiceError("Правило доступа не найдено", 404)

    if cmd.actor_role != "carcraft_employee" and cmd.actor_company_ids is not None:
        wh = await wh_repo.get_by_id(session, UUID(rule["warehouse_id"]), is_admin=True)
        if wh is None:
            raise ServiceError("Склад не найден", 404)
        owner_id = wh.get("owner_company_id")
        if owner_id is None or UUID(str(owner_id)) not in cmd.actor_company_ids:
            raise ServiceError("У вас нет прав на удаление этого правила", 403)

    from typing import cast
    return cast("bool", await rule_repo.delete_access_rule(session, cmd.rule_id, actor_role=cmd.actor_role))
