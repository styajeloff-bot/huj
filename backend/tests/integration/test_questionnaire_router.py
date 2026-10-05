"""Integration tests for `PUT /api/v1/questionnaire/:id` (Phase 14 G3)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    ApplicationQuestionnaire,
    LeasingApplication,
)
from infrastructure.models.companies import Company
from infrastructure.models.users import User

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def questionnaire_company(db_session: AsyncSession) -> Company:
    c = Company(name="Q Company", company_type="other")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def questionnaire_app(
    db_session: AsyncSession,
    questionnaire_company: Company,
    client_user: User,
) -> LeasingApplication:
    app = LeasingApplication(
        company_id=questionnaire_company.id,
        email="questionnaire@test.local",
        status="active",
    )
    db_session.add(app)
    await db_session.flush()
    await db_session.refresh(app)
    return app


async def test_put_questionnaire_anon_unauthorised(
    client: AsyncClient,
) -> None:
    response = await client.put("/api/v1/questionnaire/1", json={})
    assert response.status_code == 401


async def test_put_questionnaire_creates_row_and_marks_completed(
    client: AsyncClient,
    db_session: AsyncSession,
    questionnaire_app: LeasingApplication,
    employee_token: str,
) -> None:
    payload = {
        "full_company_name": "Full Co LLC",
        "short_company_name": "Full Co",
        "inn": "7799000002",
        "kpp": "779900001",
        "legal_address": "Moscow, 123",
        "director_full_name": "Ivanov Ivan",
        "director_position": "CEO",
    }
    response = await client.put(
        f"/api/v1/questionnaire/{questionnaire_app.id}",
        json=payload,
        headers=_auth(employee_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["completed"] is True
    assert 0 <= body["progress"] <= 100

    stmt = select(ApplicationQuestionnaire).where(
        ApplicationQuestionnaire.application_id == questionnaire_app.id
    )
    row = (await db_session.execute(stmt)).scalar_one()
    assert row.full_company_name == "Full Co LLC"
    assert row.director_full_name == "Ivanov Ivan"


async def test_put_questionnaire_missing_application_returns_404(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.put(
        "/api/v1/questionnaire/a0b1c2d3-e4f5-6789-0123-456789abcdef",
        json={"inn": "1234567890"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


async def test_put_questionnaire_second_call_updates_existing_row(
    client: AsyncClient,
    db_session: AsyncSession,
    questionnaire_app: LeasingApplication,
    employee_token: str,
) -> None:
    first = await client.put(
        f"/api/v1/questionnaire/{questionnaire_app.id}",
        json={"full_company_name": "First"},
        headers=_auth(employee_token),
    )
    assert first.status_code == 200, first.text

    second = await client.put(
        f"/api/v1/questionnaire/{questionnaire_app.id}",
        json={"full_company_name": "Second"},
        headers=_auth(employee_token),
    )
    assert second.status_code == 200, second.text

    stmt = select(ApplicationQuestionnaire).where(
        ApplicationQuestionnaire.application_id == questionnaire_app.id
    )
    rows = (await db_session.execute(stmt)).scalars().all()
    assert len(rows) == 1
    assert rows[0].full_company_name == "Second"


async def test_put_questionnaire_syncs_company_fields(
    client: AsyncClient,
    db_session: AsyncSession,
    questionnaire_app: LeasingApplication,
    employee_token: str,
) -> None:
    payload = {
        "full_company_name": "New Full Name LLC",
        "short_company_name": "New Short",
        "legal_address": "New Legal Addr",
        "actual_address": "New Actual Addr",
        "phone": "+7 999 000-00-00",
        "email": "new@example.com",
        "website": "https://new.example.com",
        "tax_system": "УСН",
    }
    response = await client.put(
        f"/api/v1/questionnaire/{questionnaire_app.id}",
        json=payload,
        headers=_auth(employee_token),
    )
    assert response.status_code == 200, response.text

    stmt = select(Company).where(Company.id == questionnaire_app.company_id)
    company = (await db_session.execute(stmt)).scalar_one()
    assert company.name == "New Full Name LLC"
    assert company.full_name == "New Full Name LLC"
    assert company.short_name == "New Short"
    assert company.legal_address == "New Legal Addr"
    assert company.actual_address == "New Actual Addr"
    assert company.phone == "+7 999 000-00-00"
    assert company.email == "new@example.com"
    assert company.website == "https://new.example.com"
    assert company.tax_system == "УСН"
