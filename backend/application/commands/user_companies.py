"""Commands for the user-companies domain."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from domain.errors import AccessDeniedError, UserNotFoundError
from infrastructure.repositories import admin_users_repository as admin_users_repo
from infrastructure.repositories import company_registration_repository as repo
from infrastructure.repositories.company_registration_repository import CompanyPayload
from infrastructure.services.company_enrichment import (
    get_company_enrichment_scheduler,
)


@dataclass(frozen=True)
class AddCompanyToUserCommand:
    user_id: UUID
    company: dict[str, Any]
    grant_administrator: bool = False
    require_client: bool = False


@dataclass(frozen=True)
class AddCompanyToUserResult:
    company_id: UUID
    companies: list[dict[str, Any]]


@dataclass(frozen=True)
class SetCompanySelectHistoryCommand:
    user_id: UUID
    company_id: UUID


async def handle_add_company_to_user(
    session: AsyncSession, cmd: AddCompanyToUserCommand
) -> AddCompanyToUserResult:
    """Add a pre-resolved company to the user's companies list.

    Mirrors Express UserService.addCompanyToUser 1:1:
    - create or get company row by INN
    - reject if already linked
    - insert into user_companies
    - schedule a background 1C enrichment refresh
    """
    inn = cmd.company.get("inn")
    if not inn:
        raise ServiceError("Укажите данные компании (требуется ИНН)", 400)

    if cmd.require_client:
        user = await admin_users_repo.get_by_id(session, cmd.user_id)
        if user is None:
            raise UserNotFoundError()
        if user["role"] != "client":
            raise ServiceError("Компанию можно добавлять только клиенту", 400)

    company = await repo.create_or_get_company(
        session, cast("CompanyPayload", cmd.company)
    )
    if not company:
        raise ServiceError("Не удалось сохранить компанию", 400)

    existing = await repo.list_user_companies(session, cmd.user_id)
    if any(c["id"] == company["id"] for c in existing):
        raise ServiceError("Эта компания уже привязана к вашему аккаунту", 400)

    is_new_company = bool(company.get("is_new"))
    grant_administrator = cmd.grant_administrator or is_new_company
    await repo.insert_user_company_links(
        session,
        cmd.user_id,
        [
            (
                company["id"],
                "administrator" if grant_administrator else "employee",
                grant_administrator,
                grant_administrator,
            )
        ],
    )
    if not cmd.require_client:
        await repo.set_primary_company_if_absent(session, cmd.user_id, company["id"])
    history = await repo.get_company_select_history(session, cmd.user_id)
    if history is None:
        await repo.upsert_company_select_history(session, cmd.user_id, company["id"])
    await repo.create_or_update_pending_enrichment(session, inn)

    scheduler = get_company_enrichment_scheduler()
    await scheduler.schedule_refresh(inn)

    companies = await repo.list_user_companies(session, cmd.user_id)
    return AddCompanyToUserResult(company_id=company["id"], companies=companies)


async def handle_set_company_select_history(
    session: AsyncSession, cmd: SetCompanySelectHistoryCommand
) -> dict[str, Any]:
    """Persist the user's currently selected company.

    Company must be linked to the user (via user_companies or users.company_id);
    otherwise raises :class:`AccessDeniedError` → 403.
    """
    companies = await repo.list_user_companies(session, cmd.user_id)
    active_company_ids = {
        c["id"] for c in companies if c.get("is_active", True)
    } | {
        UUID(str(c["id"])) for c in companies if c.get("is_active", True)
    }
    if cmd.company_id not in active_company_ids:
        raise AccessDeniedError("Компания не привязана к пользователю")

    await repo.upsert_company_select_history(session, cmd.user_id, cmd.company_id)
    row = await repo.get_company_select_history(session, cmd.user_id)
    assert row is not None
    return cast("dict[str, Any]", row)
