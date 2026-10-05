from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.compensations import (
    ListCompensationsQuery,
    handle_list_compensations,
)
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company
from infrastructure.models.compensations import CompensationModel
from infrastructure.models.support import ApplicationAppliedSupport, SupportProgram

pytestmark = pytest.mark.asyncio


async def _seed_compensation(
    db: AsyncSession, *, distributor_id: UUID | None = None
) -> tuple[LeasingApplication, ApplicationAppliedSupport, CompensationModel]:
    company = Company(
        name="Compensation Query Client",
        inn=f"77{uuid4().int % 10**8:08d}",
        company_type="other",
        is_active=True,
    )
    db.add(company)
    await db.flush()

    application = LeasingApplication(
        company_id=company.id,
        name="Compensation query app",
        email="compensation-query@example.local",
        status="active",
        selected_leasing_companies=[],
        display_number="CC-QUERY-001",
    )
    db.add(application)

    support_program = SupportProgram(
        name="Тестовая программа компенсации",
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 100000},
        is_active=True,
        distributor_id=distributor_id,
    )
    db.add(support_program)
    await db.flush()

    applied_support = ApplicationAppliedSupport(
        application_id=application.id,
        support_program_id=support_program.id,
        name="Применённая тестовая поддержка",
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 100000},
        base_amount=Decimal("1000000"),
        support_amount=Decimal("100000"),
    )
    db.add(applied_support)
    await db.flush()

    compensation = CompensationModel(
        applied_support_id=applied_support.id,
        application_id=application.id,
        payer="carcraft",
        recipient="client",
        calculation_base="support_amount",
        calculation_base_amount=Decimal("100000"),
        value_type="percent",
        value=Decimal("100"),
        amount=Decimal("100000"),
        status="under_review",
        payment_schedule_type="days_count",
        payment_schedule_value="1",
    )
    db.add(compensation)
    await db.flush()
    return application, applied_support, compensation


async def test_distributor_sees_only_compensations_of_own_programs(
    db_session: AsyncSession,
) -> None:
    first_distributor = Company(
        name="Compensation scope D1", company_type="distributor", is_active=True
    )
    second_distributor = Company(
        name="Compensation scope D2", company_type="distributor", is_active=True
    )
    db_session.add_all([first_distributor, second_distributor])
    await db_session.flush()
    own = await _seed_compensation(db_session, distributor_id=first_distributor.id)
    foreign = await _seed_compensation(db_session, distributor_id=second_distributor.id)

    result = await handle_list_compensations(
        ListCompensationsQuery(
            user_role="distributor",
            actor_company_id=first_distributor.id,
        ),
        db_session,
    )

    assert result["pagination"]["total"] == 1
    assert [item["id"] for item in result["compensations"]] == [own[2].id]
    assert foreign[2].id not in {item["id"] for item in result["compensations"]}


async def test_list_compensations_searches_by_application_display_number(
    db_session: AsyncSession,
) -> None:
    application, _applied_support, compensation = await _seed_compensation(db_session)

    result = await handle_list_compensations(
        ListCompensationsQuery(
            user_role="carcraft_employee",
            application_query="QUERY-001",
        ),
        db_session,
    )

    assert result["pagination"]["total"] == 1
    row = result["compensations"][0]
    assert row["id"] == compensation.id
    assert row["application_id"] == application.id
    assert row["application_display_number"] == "CC-QUERY-001"


async def test_list_compensations_searches_by_support_text_and_program_uuid(
    db_session: AsyncSession,
) -> None:
    _application, applied_support, compensation = await _seed_compensation(db_session)

    by_name = await handle_list_compensations(
        ListCompensationsQuery(
            user_role="carcraft_employee",
            support_query="тестовая поддержка",
        ),
        db_session,
    )
    by_program_uuid = await handle_list_compensations(
        ListCompensationsQuery(
            user_role="carcraft_employee",
            support_query=str(applied_support.support_program_id),
        ),
        db_session,
    )

    assert by_name["compensations"][0]["id"] == compensation.id
    assert by_name["compensations"][0]["applied_support_name"] == applied_support.name
    assert by_program_uuid["compensations"][0]["id"] == compensation.id
