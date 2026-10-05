from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company, LeasingCompany, LeasingCompanyUser
from infrastructure.models.users import User

pytestmark = pytest.mark.asyncio


async def test_bank_statement_analytics_api_empty_company(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    company = Company(name="Empty Company", inn="7700000000", company_type="other")
    db_session.add(company)
    await db_session.flush()
    user = User(
        phone="+76660002163",
        email="21620-analytics@test.local",
        name="Analytics User",
        role="client",
        company_id=company.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    token, _ = generate_tokens(user.id, "client", company.id)

    response = await client.get(
        f"/api/v1/bank-statements/companies/{company.id}/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["empty"] is True
    assert data["company"]["id"] == str(company.id)
    assert data["period"] is None
    assert data["kpi"]["turnover"] == 0.0


async def test_bank_statement_analytics_api_forbidden_for_other_client_company(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    own_company = Company(name="Own Company", inn="7700000001", company_type="other")
    other_company = Company(name="Other Company", inn="7700000002", company_type="other")
    db_session.add_all([own_company, other_company])
    await db_session.flush()
    user = User(
        phone="+76660002164",
        email="21620-analytics-forbidden@test.local",
        name="Analytics User",
        role="client",
        company_id=own_company.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    token, _ = generate_tokens(user.id, "client", own_company.id)

    response = await client.get(
        f"/api/v1/bank-statements/companies/{other_company.id}/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


async def test_bank_statement_analytics_api_missing_company(
    client: AsyncClient,
    employee_token: str,
) -> None:
    response = await client.get(
        f"/api/v1/bank-statements/companies/{uuid4()}/analytics",
        headers={"Authorization": f"Bearer {employee_token}"},
    )

    assert response.status_code == 404


async def test_bank_statement_analytics_api_forbidden_for_unselected_leasing_company(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    target_company = Company(
        name="Target Company",
        inn="7700000003",
        company_type="other",
    )
    lc_company = Company(
        name="LC Company",
        inn="7700000004",
        company_type="leasing_company",
    )
    db_session.add_all([target_company, lc_company])
    await db_session.flush()
    leasing_company = LeasingCompany(company_id=lc_company.id)
    db_session.add(leasing_company)
    await db_session.flush()
    db_session.add(
        LeasingApplication(
            company_id=target_company.id,
            selected_leasing_companies=[uuid4()],
            status="active",
        )
    )
    user = User(
        phone="+76660002165",
        email="21620-lc-analytics-forbidden@test.local",
        name="LC Analytics User",
        role="leasing_company",
        company_id=lc_company.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        LeasingCompanyUser(
            user_id=user.id,
            leasing_company_id=leasing_company.id,
        )
    )
    await db_session.flush()
    token, _ = generate_tokens(user.id, "leasing_company", lc_company.id)

    response = await client.get(
        f"/api/v1/bank-statements/companies/{target_company.id}/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
