"""Admin commands for SOPD contractors."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories import (
    company_change_history_repository as history_repo,
)
from infrastructure.repositories import (
    contractors_repository as repo,
)
from infrastructure.services.excel_io import read_workbook


@dataclass(frozen=True)
class CreateContractorCommand:
    contractor_name: str
    contractor_inn: str


@dataclass(frozen=True)
class CreateContractorLinkCommand:
    leasing_company_id: UUID
    contractor_name: str
    contractor_inn: str


@dataclass(frozen=True)
class SetLeasingCompanyContractorsCommand:
    leasing_company_id: UUID
    contractor_ids: list[UUID]
    # Legacy direct callers predate audit history. They retain their mutation
    # behavior but deliberately cannot create an unattributable audit row.
    actor_user_id: UUID | None = None


@dataclass(frozen=True)
class SetContractorLeasingCompaniesCommand:
    contractor_id: UUID
    leasing_company_ids: list[UUID]


@dataclass(frozen=True)
class UpdateContractorCommand:
    contractor_id: UUID
    name: str


@dataclass(frozen=True)
class DeleteContractorLinkCommand:
    link_id: UUID


@dataclass(frozen=True)
class ImportContractorLinksCommand:
    filename: str
    data: bytes


@dataclass(frozen=True)
class ImportRowError:
    row: int
    message: str


@dataclass
class ImportContractorLinksResult:
    rows_total: int
    links_created: int = 0
    links_skipped: int = 0
    contractors_created: int = 0
    errors: list[ImportRowError] = field(default_factory=list)


async def handle_create_contractor(
    cmd: CreateContractorCommand, session: AsyncSession
) -> dict[str, Any]:
    contractor_name = _validate_name(cmd.contractor_name)
    contractor_inn = _validate_inn(cmd.contractor_inn)

    contractor = await repo.get_contractor_by_inn(session, contractor_inn)
    created = False
    if contractor is None:
        contractor = await repo.create_contractor(
            session, name=contractor_name, inn=contractor_inn
        )
        created = True
    return {"contractor": contractor, "created": created}


async def handle_create_contractor_link(
    cmd: CreateContractorLinkCommand, session: AsyncSession
) -> dict[str, Any]:
    contractor_name = _validate_name(cmd.contractor_name)
    contractor_inn = _validate_inn(cmd.contractor_inn)

    leasing_company = await repo.get_leasing_company_by_id(
        session, cmd.leasing_company_id
    )
    if leasing_company is None:
        raise ServiceError("Лизинговая компания не найдена.", 404)

    contractor_created = False
    contractor = await repo.get_contractor_by_inn(session, contractor_inn)
    if contractor is None:
        contractor = await repo.create_contractor(
            session, name=contractor_name, inn=contractor_inn
        )
        contractor_created = True

    link = await repo.get_link_by_pair(
        session,
        leasing_company_id=cmd.leasing_company_id,
        contractor_id=contractor["id"],
    )
    link_created = False
    if link is None:
        link = await repo.create_link(
            session,
            leasing_company_id=cmd.leasing_company_id,
            contractor_id=contractor["id"],
        )
        link_created = True

    return {
        "item": link,
        "contractor_created": contractor_created,
        "link_created": link_created,
    }


async def handle_update_contractor(
    cmd: UpdateContractorCommand, session: AsyncSession
) -> dict[str, Any]:
    name = _validate_name(cmd.name)
    contractor = await repo.update_contractor_name(
        session, contractor_id=cmd.contractor_id, name=name
    )
    if contractor is None:
        raise ServiceError("Подрядчик не найден.", 404)
    return {"contractor": contractor}


async def handle_list_leasing_company_contractor_links(
    leasing_company_id: UUID, session: AsyncSession
) -> dict[str, Any]:
    leasing_company = await repo.get_leasing_company_by_id(
        session, leasing_company_id
    )
    if leasing_company is None:
        raise ServiceError("Лизинговая компания не найдена.", 404)
    return {
        "items": await repo.list_links_for_leasing_company(
            session, leasing_company_id=leasing_company_id
        )
    }


async def handle_set_leasing_company_contractors(
    cmd: SetLeasingCompanyContractorsCommand, session: AsyncSession
) -> dict[str, Any]:
    leasing_company = await repo.get_leasing_company_by_id(
        session, cmd.leasing_company_id
    )
    if leasing_company is None:
        raise ServiceError("Лизинговая компания не найдена.", 404)

    contractor_ids = set(cmd.contractor_ids)
    contractors = await repo.get_contractors_by_ids(session, contractor_ids)
    found_ids = {contractor["id"] for contractor in contractors}
    missing_ids = contractor_ids.difference(found_ids)
    if missing_ids:
        raise ServiceError("Один или несколько подрядчиков не найдены.", 404)

    current_items = await repo.list_links_for_leasing_company(
        session, leasing_company_id=cmd.leasing_company_id
    )
    current_ids = {item["contractor_id"] for item in current_items}
    if current_ids == contractor_ids:
        return {"items": current_items}
    items = await repo.set_links_for_leasing_company(
        session, leasing_company_id=cmd.leasing_company_id, contractor_ids=contractor_ids
    )
    company_id = leasing_company["company_id"]
    if company_id is None:
        raise ServiceError("У лизинговой компании отсутствует базовая компания.", 409)
    if cmd.actor_user_id is not None:
        await history_repo.write_snapshot(
            session, company_id=company_id, actor_user_id=cmd.actor_user_id,
            action="leasing_contractors_saved", include_contractors=True,
        )
    return {"items": items}


async def handle_list_contractor_leasing_company_links(
    contractor_id: UUID, session: AsyncSession
) -> dict[str, Any]:
    contractor = await repo.get_contractor_by_id(session, contractor_id)
    if contractor is None:
        raise ServiceError("Подрядчик не найден.", 404)
    return {
        "items": await repo.list_links_for_contractor(
            session, contractor_id=contractor_id
        )
    }


async def handle_set_contractor_leasing_companies(
    cmd: SetContractorLeasingCompaniesCommand, session: AsyncSession
) -> dict[str, Any]:
    contractor = await repo.get_contractor_by_id(session, cmd.contractor_id)
    if contractor is None:
        raise ServiceError("Подрядчик не найден.", 404)

    leasing_company_ids = set(cmd.leasing_company_ids)
    leasing_companies = await repo.get_leasing_companies_by_ids(
        session, leasing_company_ids
    )
    found_ids = {leasing_company["id"] for leasing_company in leasing_companies}
    missing_ids = leasing_company_ids.difference(found_ids)
    if missing_ids:
        raise ServiceError("Одна или несколько лизинговых компаний не найдены.", 404)

    return {
        "items": await repo.set_links_for_contractor(
            session,
            contractor_id=cmd.contractor_id,
            leasing_company_ids=leasing_company_ids,
        )
    }


async def handle_delete_contractor_link(
    cmd: DeleteContractorLinkCommand, session: AsyncSession
) -> None:
    deleted = await repo.delete_link(session, link_id=cmd.link_id)
    if not deleted:
        raise ServiceError("Связь ЛК с подрядчиком не найдена.", 404)


async def handle_import_contractor_links(
    cmd: ImportContractorLinksCommand, session: AsyncSession
) -> ImportContractorLinksResult:
    if not cmd.filename.lower().endswith((".xlsx", ".xls")):
        raise ServiceError("Поддерживаются только файлы .xlsx и .xls.", 415)
    if not cmd.data:
        raise ServiceError("Файл не загружен.", 400)

    try:
        headers, rows = await read_workbook(cmd.data)
    except Exception as exc:
        raise ServiceError(f"Не удалось прочитать Excel-файл: {exc}", 422) from exc
    required = {"leasing_company_inn", "contractor_name", "contractor_inn"}
    missing = sorted(required.difference(headers))
    if missing:
        raise ServiceError(
            "В Excel отсутствуют обязательные колонки: " + ", ".join(missing),
            422,
        )

    result = ImportContractorLinksResult(rows_total=len(rows))
    for index, row in enumerate(rows, start=2):
        try:
            leasing_company_inn = _validate_inn(
                _cell(row.get("leasing_company_inn"))
            )
            contractor_name = _validate_name(_cell(row.get("contractor_name")))
            contractor_inn = _validate_inn(_cell(row.get("contractor_inn")))

            leasing_company = await repo.get_leasing_company_by_inn(
                session, leasing_company_inn
            )
            _ensure_leasing_company_found(leasing_company, leasing_company_inn)

            link_result = await handle_create_contractor_link(
                CreateContractorLinkCommand(
                    leasing_company_id=leasing_company["id"],
                    contractor_name=contractor_name,
                    contractor_inn=contractor_inn,
                ),
                session,
            )
            if link_result["contractor_created"]:
                result.contractors_created += 1
            if link_result["link_created"]:
                result.links_created += 1
            else:
                result.links_skipped += 1
        except ServiceError as exc:
            result.errors.append(ImportRowError(row=index, message=str(exc)))

    return result


def _cell(value: object) -> str:
    return "" if value is None else str(value).strip()


def _ensure_leasing_company_found(
    leasing_company: object | None, inn: str
) -> None:
    if leasing_company is None:
        raise ServiceError(f"ЛК с ИНН {inn} не найдена.", 404)


def _validate_inn(value: str) -> str:
    inn = "".join(ch for ch in value.strip() if ch.isdigit())
    if len(inn) not in {10, 12}:
        raise ServiceError("ИНН должен содержать 10 или 12 цифр.", 422)
    return inn


def _validate_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ServiceError("Наименование подрядчика обязательно.", 422)
    if len(name) > 255:
        raise ServiceError(
            "Наименование подрядчика не должно превышать 255 символов.",
            422,
        )
    return name
