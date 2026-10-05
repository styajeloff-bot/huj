"""Functional tests for the company-profile query handlers."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.companies import (
    GetCompanyProfileQuery,
    GetMyCompanyProfileQuery,
    handle_get_company_profile,
    handle_get_my_company_profile,
)
from domain.errors import CompanyAccessDeniedError, CompanyNotFoundError
from infrastructure.models.companies import Company, Distributor, LeasingCompany
from infrastructure.models.users import User, UserCompany

pytestmark = pytest.mark.asyncio


async def _make_company(
    db: AsyncSession,
    *,
    name: str = "Тест Ко",
    inn: str = "7700000001",
    company_type: str = "dealer",
    director_full_name: str | None = None,
    director_inn: str | None = None,
    founders: list[dict[str, object]] | None = None,
) -> Company:
    company = Company(
        name=name,
        inn=inn,
        company_type=company_type,
        is_active=True,
        director_full_name=director_full_name,
        director_inn=director_inn,
        founders=founders,
    )
    db.add(company)
    await db.flush()
    await db.refresh(company)
    return company


async def _link_user_to_company(
    db: AsyncSession, user: User, company_id: UUID
) -> None:
    user.company_id = company_id
    await db.flush()


# ---------------------------------------------------------------------------
# handle_get_company_profile
# ---------------------------------------------------------------------------


async def test_get_by_id_404_when_missing(
    db_session: AsyncSession, client_user: User
) -> None:
    with pytest.raises(CompanyNotFoundError):
        await handle_get_company_profile(
            GetCompanyProfileQuery(
                company_id=uuid4(),
                user_id=client_user.id,
                user_role="client",
            ),
            db_session,
        )


async def test_get_by_id_employee_can_read_any(
    db_session: AsyncSession, employee_user: User
) -> None:
    company = await _make_company(db_session)
    profile = await handle_get_company_profile(
        GetCompanyProfileQuery(
            company_id=company.id,
            user_id=employee_user.id,
            user_role="carcraft_employee",
        ),
        db_session,
    )
    assert profile["id"] == company.id
    assert profile["inn"] == company.inn
    assert "sopd_signer_candidates" not in profile


async def test_get_by_id_owner_via_primary_company_id(
    db_session: AsyncSession, client_user: User
) -> None:
    company = await _make_company(db_session)
    await _link_user_to_company(db_session, client_user, company.id)

    profile = await handle_get_company_profile(
        GetCompanyProfileQuery(
            company_id=company.id,
            user_id=client_user.id,
            user_role="client",
        ),
        db_session,
    )
    assert profile["id"] == company.id


async def test_get_by_id_owner_via_user_companies_join(
    db_session: AsyncSession, client_user: User
) -> None:
    company = await _make_company(db_session, inn="7700000002")
    db_session.add(UserCompany(user_id=client_user.id, company_id=company.id))
    await db_session.flush()

    profile = await handle_get_company_profile(
        GetCompanyProfileQuery(
            company_id=company.id,
            user_id=client_user.id,
            user_role="client",
        ),
        db_session,
    )
    assert profile["id"] == company.id


async def test_get_by_id_stranger_is_denied(
    db_session: AsyncSession, client_user: User
) -> None:
    company = await _make_company(db_session, inn="7700000003")
    with pytest.raises(CompanyAccessDeniedError):
        await handle_get_company_profile(
            GetCompanyProfileQuery(
                company_id=company.id,
                user_id=client_user.id,
                user_role="client",
            ),
            db_session,
        )


async def test_get_by_id_includes_leasing_company_extension(
    db_session: AsyncSession, employee_user: User
) -> None:
    company = await _make_company(
        db_session, inn="7700000004", company_type="leasing_company"
    )
    db_session.add(
        LeasingCompany(
            company_id=company.id,
            average_down_payment_percent=20,
            average_lease_term_months=60,
        )
    )
    await db_session.flush()

    profile = await handle_get_company_profile(
        GetCompanyProfileQuery(
            company_id=company.id,
            user_id=employee_user.id,
            user_role="carcraft_employee",
        ),
        db_session,
    )
    assert profile["leasing_company"] is not None
    assert profile["leasing_company"]["average_down_payment_percent"] == 20


async def test_get_by_id_includes_distributor_extension(
    db_session: AsyncSession, employee_user: User
) -> None:
    company = await _make_company(
        db_session, inn="7700000005", company_type="distributor"
    )
    db_session.add(
        Distributor(
            company_id=company.id,
            regions={"list": ["RU-MOW", "RU-SPE"]},
            brands={"list": ["FAW"]},
        )
    )
    await db_session.flush()

    profile = await handle_get_company_profile(
        GetCompanyProfileQuery(
            company_id=company.id,
            user_id=employee_user.id,
            user_role="carcraft_employee",
        ),
        db_session,
    )
    assert profile["distributor"] is not None
    assert profile["distributor"]["brands"] == {"list": ["FAW"]}


# ---------------------------------------------------------------------------
# handle_get_my_company_profile
# ---------------------------------------------------------------------------


async def test_get_my_404_when_no_company_link(
    db_session: AsyncSession, client_user: User
) -> None:
    with pytest.raises(CompanyNotFoundError):
        await handle_get_my_company_profile(
            GetMyCompanyProfileQuery(
                user_id=client_user.id, user_role="client"
            ),
            db_session,
        )


async def test_get_my_returns_linked_company(
    db_session: AsyncSession, client_user: User
) -> None:
    company = await _make_company(db_session, inn="7700000006")
    await _link_user_to_company(db_session, client_user, company.id)

    profile = await handle_get_my_company_profile(
        GetMyCompanyProfileQuery(
            user_id=client_user.id, user_role="client"
        ),
        db_session,
    )
    assert profile["id"] == company.id
    assert profile["inn"] == company.inn
    assert "sopd_signer_candidates" not in profile
