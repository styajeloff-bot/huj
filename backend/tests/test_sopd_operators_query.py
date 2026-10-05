from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.sopd_operators import (
    SOURCE_ACTIVE_LEASING_COMPANIES_FALLBACK,
    resolve_sopd_operator_snapshot,
)
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.contractors import Contractor, LeasingCompanyContractor
from infrastructure.repositories.sopd_operator_snapshot_repository import (
    DEFAULT_SOURCE,
)

pytestmark = pytest.mark.asyncio


async def test_resolve_sopd_operator_snapshot_formats_empty_lists_as_blank(
    db_session: AsyncSession,
) -> None:
    snapshot = await resolve_sopd_operator_snapshot(db_session, application_id=None)

    assert snapshot.leasing_companies_text == ""
    assert snapshot.contractors_text == ""


async def _create_lc(
    db_session: AsyncSession,
    *,
    name: str,
    inn: str,
    is_active: bool = True,
) -> LeasingCompany:
    company = Company(name=name, inn=inn, company_type="leasing_company")
    db_session.add(company)
    await db_session.flush()
    lc = LeasingCompany(company_id=company.id, is_active=is_active)
    db_session.add(lc)
    await db_session.flush()
    return lc


async def test_resolve_sopd_operator_snapshot_uses_selected_lcs_and_contractors(
    db_session: AsyncSession,
) -> None:
    client_company = Company(
        name="Клиент для СОПД",
        inn="7710000421",
        company_type="other",
    )
    db_session.add(client_company)
    await db_session.flush()

    reso = await _create_lc(
        db_session, name="ООО РЕСО-Лизинг", inn="7709401087"
    )
    vtb = await _create_lc(
        db_session,
        name="АО ВТБ Лизинг",
        inn="7709378229",
        is_active=False,
    )
    application = LeasingApplication(
        company_id=client_company.id,
        selected_leasing_companies=[reso.id, vtb.id],
    )
    shared = Contractor(name="ОКБ", inn="7710000001")
    reso_only = Contractor(name="Скоринг-Сервис", inn="7710000002")
    db_session.add_all([application, shared, reso_only])
    await db_session.flush()
    db_session.add_all(
        [
            LeasingCompanyContractor(
                leasing_company_id=reso.id,
                contractor_id=shared.id,
            ),
            LeasingCompanyContractor(
                leasing_company_id=vtb.id,
                contractor_id=shared.id,
            ),
            LeasingCompanyContractor(
                leasing_company_id=reso.id,
                contractor_id=reso_only.id,
            ),
        ]
    )
    await db_session.flush()

    snapshot = await resolve_sopd_operator_snapshot(
        db_session, application_id=application.id
    )

    assert [item["id"] for item in snapshot.leasing_companies] == [
        str(reso.id),
        str(vtb.id),
    ]
    assert [item["inn"] for item in snapshot.leasing_companies] == [
        "7709401087",
        "7709378229",
    ]
    assert snapshot.source == DEFAULT_SOURCE
    assert len(snapshot.contractors) == 2

    shared_snapshot = next(
        item for item in snapshot.contractors if item["inn"] == "7710000001"
    )
    assert shared_snapshot["leasing_company_ids"] == [
        str(reso.id),
        str(vtb.id),
    ]
    assert "ООО РЕСО-Лизинг, ИНН 7709401087" in snapshot.leasing_companies_text
    assert "ОКБ, ИНН 7710000001" in snapshot.contractors_text
    assert "подрядчик лизинговых компаний" in snapshot.contractors_text


async def test_resolve_sopd_operator_snapshot_falls_back_to_active_lcs(
    db_session: AsyncSession,
) -> None:
    client_company = Company(
        name="Клиент без распределения",
        inn="7710000521",
        company_type="other",
    )
    db_session.add(client_company)
    await db_session.flush()

    reso = await _create_lc(
        db_session,
        name="ООО Активная РЕСО",
        inn="7709401187",
    )
    vtb = await _create_lc(
        db_session,
        name="АО Активная ВТБ",
        inn="7709378329",
    )
    inactive = await _create_lc(
        db_session,
        name="ООО Неактивная ЛК",
        inn="7709378330",
        is_active=False,
    )
    application = LeasingApplication(
        company_id=client_company.id,
        selected_leasing_companies=[],
    )
    shared = Contractor(name="Общий подрядчик", inn="7710000101")
    inactive_only = Contractor(
        name="Подрядчик неактивной ЛК",
        inn="7710000102",
    )
    db_session.add_all([application, shared, inactive_only])
    await db_session.flush()
    db_session.add_all(
        [
            LeasingCompanyContractor(
                leasing_company_id=reso.id,
                contractor_id=shared.id,
            ),
            LeasingCompanyContractor(
                leasing_company_id=vtb.id,
                contractor_id=shared.id,
            ),
            LeasingCompanyContractor(
                leasing_company_id=inactive.id,
                contractor_id=inactive_only.id,
            ),
        ]
    )
    await db_session.flush()

    snapshot = await resolve_sopd_operator_snapshot(
        db_session,
        application_id=application.id,
    )

    assert snapshot.source == SOURCE_ACTIVE_LEASING_COMPANIES_FALLBACK
    assert {item["id"] for item in snapshot.leasing_companies} == {
        str(reso.id),
        str(vtb.id),
    }
    assert str(inactive.id) not in {
        item["id"] for item in snapshot.leasing_companies
    }
    assert [item["id"] for item in snapshot.contractors] == [str(shared.id)]
    assert set(snapshot.contractors[0]["leasing_company_ids"]) == {
        str(reso.id),
        str(vtb.id),
    }
    await db_session.refresh(application)
    assert application.selected_leasing_companies == []
