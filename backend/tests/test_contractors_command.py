from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.admin_companies import (
    CreateContractorCommand,
    CreateContractorLinkCommand,
    DeleteContractorLinkCommand,
    ImportContractorLinksCommand,
    SetContractorLeasingCompaniesCommand,
    SetLeasingCompanyContractorsCommand,
    UpdateContractorCommand,
    handle_create_contractor,
    handle_create_contractor_link,
    handle_delete_contractor_link,
    handle_import_contractor_links,
    handle_set_contractor_leasing_companies,
    handle_set_leasing_company_contractors,
    handle_update_contractor,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.repositories import contractors_repository as contractors
from infrastructure.services.excel_io import write_workbook

pytestmark = pytest.mark.asyncio


async def _create_lc(
    db_session: AsyncSession, *, name: str, inn: str
) -> LeasingCompany:
    company = Company(
        name=name,
        inn=inn,
        company_type="leasing_company",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    lc = LeasingCompany(company_id=company.id, is_active=True)
    db_session.add(lc)
    await db_session.flush()
    return lc


async def test_create_contractor_link_is_idempotent(
    db_session: AsyncSession,
) -> None:
    lc = await _create_lc(db_session, name="РЕСО-Лизинг", inn="7704786031")

    first = await handle_create_contractor_link(
        CreateContractorLinkCommand(
            leasing_company_id=lc.id,
            contractor_name="АО ОКБ",
            contractor_inn="7701234567",
        ),
        db_session,
    )
    second = await handle_create_contractor_link(
        CreateContractorLinkCommand(
            leasing_company_id=lc.id,
            contractor_name="АО ОКБ",
            contractor_inn="7701234567",
        ),
        db_session,
    )

    assert first["contractor_created"] is True
    assert first["link_created"] is True
    assert second["contractor_created"] is False
    assert second["link_created"] is False
    _, total = await contractors.list_links(db_session, page=1, limit=20)
    assert total == 1


async def test_create_contractor_catalog_is_idempotent(
    db_session: AsyncSession,
) -> None:
    first = await handle_create_contractor(
        CreateContractorCommand(
            contractor_name="АО ОКБ",
            contractor_inn="770 123-45-67",
        ),
        db_session,
    )
    second = await handle_create_contractor(
        CreateContractorCommand(
            contractor_name="АО ОКБ дубль",
            contractor_inn="7701234567",
        ),
        db_session,
    )

    assert first["created"] is True
    assert first["contractor"]["inn"] == "7701234567"
    assert second["created"] is False
    assert second["contractor"]["id"] == first["contractor"]["id"]
    _, total = await contractors.list_contractors(db_session, page=1, limit=20)
    assert total == 1


async def test_one_contractor_can_be_linked_to_multiple_lcs(
    db_session: AsyncSession,
) -> None:
    reso = await _create_lc(db_session, name="РЕСО-Лизинг", inn="7704786031")
    vtb = await _create_lc(db_session, name="ВТБ Лизинг", inn="7701234567")

    await handle_create_contractor_link(
        CreateContractorLinkCommand(
            leasing_company_id=reso.id,
            contractor_name="АО ОКБ",
            contractor_inn="7709990001",
        ),
        db_session,
    )
    result = await handle_create_contractor_link(
        CreateContractorLinkCommand(
            leasing_company_id=vtb.id,
            contractor_name="АО ОКБ",
            contractor_inn="7709990001",
        ),
        db_session,
    )

    assert result["contractor_created"] is False
    assert result["link_created"] is True
    _, total = await contractors.list_links(db_session, page=1, limit=20)
    assert total == 2


async def test_bulk_sync_links_from_lc_and_contractor_sides(
    db_session: AsyncSession,
) -> None:
    reso = await _create_lc(db_session, name="РЕСО-Лизинг", inn="7704786031")
    vtb = await _create_lc(db_session, name="ВТБ Лизинг", inn="7701234567")
    first = await handle_create_contractor(
        CreateContractorCommand(
            contractor_name="АО ОКБ",
            contractor_inn="7709990001",
        ),
        db_session,
    )
    second = await handle_create_contractor(
        CreateContractorCommand(
            contractor_name="ООО Проверка",
            contractor_inn="7709990002",
        ),
        db_session,
    )

    linked = await handle_set_leasing_company_contractors(
        SetLeasingCompanyContractorsCommand(
            leasing_company_id=reso.id,
            contractor_ids=[
                first["contractor"]["id"],
                second["contractor"]["id"],
            ],
        ),
        db_session,
    )
    assert {item["contractor_id"] for item in linked["items"]} == {
        first["contractor"]["id"],
        second["contractor"]["id"],
    }

    reduced = await handle_set_leasing_company_contractors(
        SetLeasingCompanyContractorsCommand(
            leasing_company_id=reso.id,
            contractor_ids=[first["contractor"]["id"]],
        ),
        db_session,
    )
    assert [item["contractor_id"] for item in reduced["items"]] == [
        first["contractor"]["id"]
    ]

    moved = await handle_set_contractor_leasing_companies(
        SetContractorLeasingCompaniesCommand(
            contractor_id=first["contractor"]["id"],
            leasing_company_ids=[vtb.id],
        ),
        db_session,
    )
    assert [item["leasing_company_id"] for item in moved["items"]] == [vtb.id]
    reso_links = await contractors.list_links_for_leasing_company(
        db_session, leasing_company_id=reso.id
    )
    assert reso_links == []


async def test_update_and_unlink_do_not_delete_contractor(
    db_session: AsyncSession,
) -> None:
    lc = await _create_lc(db_session, name="РЕСО-Лизинг", inn="7704786031")
    created = await handle_create_contractor_link(
        CreateContractorLinkCommand(
            leasing_company_id=lc.id,
            contractor_name="АО ОКБ",
            contractor_inn="7701234567",
        ),
        db_session,
    )

    contractor_id = created["item"]["contractor_id"]
    updated = await handle_update_contractor(
        UpdateContractorCommand(
            contractor_id=contractor_id,
            name="АО Объединённое кредитное бюро",
        ),
        db_session,
    )
    await handle_delete_contractor_link(
        DeleteContractorLinkCommand(link_id=created["item"]["id"]),
        db_session,
    )

    assert updated["contractor"]["name"] == "АО Объединённое кредитное бюро"
    contractor = await contractors.get_contractor_by_inn(
        db_session, "7701234567"
    )
    assert contractor is not None
    links, total = await contractors.list_links(db_session, page=1, limit=20)
    assert links == []
    assert total == 0


async def test_import_contractors_reports_duplicates_and_row_errors(
    db_session: AsyncSession,
) -> None:
    lc = await _create_lc(db_session, name="РЕСО-Лизинг", inn="7704786031")
    headers = ["leasing_company_inn", "contractor_name", "contractor_inn"]
    data = await write_workbook(
        headers,
        [
            ["7704786031", "АО ОКБ", "7701234567"],
            ["7704786031", "АО ОКБ", "7701234567"],
            ["7704786031", "ООО Форматированный ИНН", "770 999-00-02"],
            ["7700000000", "ООО Нет ЛК", "7700000001"],
            ["7704786031", "ООО Ошибка", "bad-inn"],
        ],
        sheet_name="contractors",
    )

    result = await handle_import_contractor_links(
        ImportContractorLinksCommand(filename="contractors.xlsx", data=data),
        db_session,
    )

    assert lc.id
    assert result.rows_total == 5
    assert result.contractors_created == 2
    assert result.links_created == 2
    assert result.links_skipped == 1
    assert len(result.errors) == 2
    assert result.errors[0].row == 5
    assert "не найдена" in result.errors[0].message
    assert result.errors[1].row == 6
    assert "ИНН должен содержать" in result.errors[1].message

    second_result = await handle_import_contractor_links(
        ImportContractorLinksCommand(filename="contractors.xlsx", data=data),
        db_session,
    )
    _, total = await contractors.list_links(db_session, page=1, limit=20)

    assert second_result.rows_total == 5
    assert second_result.contractors_created == 0
    assert second_result.links_created == 0
    assert second_result.links_skipped == 3
    assert len(second_result.errors) == 2
    assert total == 2
