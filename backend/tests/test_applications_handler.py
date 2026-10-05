"""Unit / functional tests for leasing application handlers.

Uses the real Postgres testcontainer for realistic repository behaviour.
Each test fixture creates the minimal graph (user, company, leasing
company, vehicle, application) it needs and relies on the per-test
transaction-rollback shared by all other integration tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.application_vehicles import (
    AssignVinCommand,
    handle_assign_vin,
)
from application.commands.applications import (
    ApplicationVehiclePayload,
    ChangeStatusCommand,
    CreateApplicationCommand,
    CreateDraftCommand,
    handle_change_status,
    handle_create_application,
    handle_create_draft,
)
from application.errors import ServiceError
from application.queries.application_vehicles import (
    ListAvailableVinsQuery,
    handle_list_available_vins,
)
from application.queries.applications import (
    GetApplicationQuery,
    GetSopdSignerCandidatesQuery,
    ListApplicationsQuery,
    handle_get_application,
    handle_get_sopd_signer_candidates,
    handle_list_applications,
)
from application.queries.applications.get_application import _resolve_company
from domain.entities.leasing_application import (
    STATUS_ACTIVE,
    STATUS_ISSUED,
    STATUS_REJECTED,
)
from domain.errors import (
    ApplicationNotFoundError,
    ApplicationNotOwnedError,
    ApplicationNotSubmittableError,
    CompanyLookupUnavailableError,
    CompanyNotFoundError,
    InvalidStatusTransitionError,
)
from domain.storefronts import CatalogScope
from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import (
    Company,
    DistributorBrand,
    DistributorDealerLink,
    LeasingCompany,
)
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.models.users import User, UserCompany
from infrastructure.models.vehicles import Warehouse
from presentation.schemas.applications import (
    ApplicationDetailResponse,
    SopdSignerCandidatesResponse,
)
from tests.fakes.company_lookup import FakeCompanyLookupProvider
from tests.legacy_compat import Mark, Vehicle, VehicleWarehouse

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client_company(db_session: AsyncSession) -> Company:
    company = Company(name="Client Co", company_type="other")
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def leasing_company_company(db_session: AsyncSession) -> Company:
    company = Company(name="Leasing Provider Inc", company_type="leasing_company")
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def leasing_company(
    db_session: AsyncSession, leasing_company_company: Company
) -> LeasingCompany:
    lc = LeasingCompany(company_id=leasing_company_company.id, is_active=True)
    db_session.add(lc)
    await db_session.flush()
    return lc


@pytest_asyncio.fixture
async def dealer(db_session: AsyncSession, client_company: Company) -> User:
    user = User(
        phone="+76660001111",
        email="dealer-handler@test.local",
        name="Dealer Handler",
        role="dealer",
        company_id=client_company.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=user.id,
            company_id=client_company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def client_with_company(
    db_session: AsyncSession, client_company: Company
) -> User:
    user = User(
        phone="+76660002222",
        email="clientwithco@test.local",
        name="Client With Company",
        role="client",
        is_active=True,
        company_id=client_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def available_vehicle(db_session: AsyncSession) -> Vehicle:
    v = Vehicle(
        vin="HANDLERVIN00000001",
        status="available",
        is_available=True,
        complectation_id="COMPL-A",
        base_price=Decimal("1000000.00"),
    )
    db_session.add(v)
    await db_session.flush()
    return v


# ---------------------------------------------------------------------------
# Create / draft
# ---------------------------------------------------------------------------


async def test_create_draft_happy_path(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
) -> None:
    cmd = CreateDraftCommand(
        source_type="platform",
        actor_id=dealer.id,
        actor_role="dealer",
        actor_company_id=client_company.id,
        company_id=client_company.id,
        name="Иванов",
        email="ivanov@test.local",
        vehicles=[
            ApplicationVehiclePayload(
                modification_id="MOD-A", quantity=2, custom_price=Decimal("100")
            )
        ],
    )
    result = await handle_create_draft(cmd, db_session)
    assert result["status"] == STATUS_ACTIVE
    assert isinstance(result["application_id"], uuid.UUID)

    # created_by is recorded
    from infrastructure.models.applications import LeasingApplication
    row = await db_session.get(LeasingApplication, result["application_id"])
    assert row is not None
    assert row.created_by == dealer.id
    assert row.source_type == "platform"


async def test_dealer_creates_draft_for_searched_client_without_user_company_link(
    db_session: AsyncSession,
) -> None:
    dealer_company = Company(name="Dealer Co", company_type="dealer")
    client_company = Company(
        name="Searched Client Co",
        inn="7701234567",
        company_type="other",
    )
    db_session.add_all([dealer_company, client_company])
    await db_session.flush()

    dealer = User(
        phone="+766****3333",
        email="dealer-client-draft@test.local",
        name="Dealer Client Draft",
        role="dealer",
        company_id=dealer_company.id,
        is_active=True,
    )
    db_session.add(dealer)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=dealer.id,
            company_id=dealer_company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    await db_session.flush()

    result = await handle_create_draft(
        CreateDraftCommand(
            source_type="platform",
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=dealer_company.id,
            company_id=None,
            company={"name": client_company.name, "inn": client_company.inn},
            name="Клиентская заявка",
            email="client@test.local",
            vehicles=[ApplicationVehiclePayload(modification_id="MOD-A")],
        ),
        db_session,
    )

    application = await db_session.get(LeasingApplication, result["application_id"])
    assert application is not None
    assert application.company_id == client_company.id
    assert application.dealer_company_id == dealer_company.id

    client_link = await db_session.scalar(
        sa.select(UserCompany).where(
            UserCompany.user_id == dealer.id,
            UserCompany.company_id == client_company.id,
        )
    )
    assert client_link is None


async def test_custom_storefront_draft_rejects_model_order_without_stock_vehicle(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
) -> None:
    command = CreateDraftCommand(
        source_type="platform",
        actor_id=dealer.id,
        actor_role="dealer",
        actor_company_id=client_company.id,
        company_id=client_company.id,
        vehicles=[ApplicationVehiclePayload(modification_id="MOD-CUSTOM")],
        scope=CatalogScope(
            id=uuid4(),
            slug="faw",
            version=1,
            is_default=False,
        ),
    )

    with pytest.raises(
        ApplicationNotSubmittableError,
        match="доступен только автомобиль со склада витрины",
    ):
        await handle_create_draft(command, db_session)


async def test_custom_storefront_application_rejects_model_order_without_stock_vehicle(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
) -> None:
    command = CreateApplicationCommand(
        source_type="platform",
        actor_id=dealer.id,
        actor_role="carcraft_employee",
        company_id=client_company.id,
        name="Иванов",
        email="ivanov@test.local",
        vehicles=[ApplicationVehiclePayload(modification_id="MOD-CUSTOM")],
        scope=CatalogScope(
            id=uuid4(),
            slug="faw",
            version=1,
            is_default=False,
        ),
    )

    with pytest.raises(
        ApplicationNotSubmittableError,
        match="доступен только автомобиль со склада витрины",
    ):
        await handle_create_application(command, db_session)


async def test_create_draft_generates_display_number_per_company_inn_and_day(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
) -> None:
    client_company.inn = "7701234567"
    await db_session.flush()

    first = await handle_create_draft(
        CreateDraftCommand(
            source_type="platform",
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=client_company.id,
            company_id=client_company.id,
            name="First",
            email="first@test.local",
            vehicles=[
                ApplicationVehiclePayload(
                    modification_id="MOD-A", custom_price=Decimal("100")
                )
            ],
        ),
        db_session,
    )
    second = await handle_create_draft(
        CreateDraftCommand(
            source_type="platform",
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=client_company.id,
            company_id=client_company.id,
            name="Second",
            email="second@test.local",
            vehicles=[
                ApplicationVehiclePayload(
                    modification_id="MOD-B", custom_price=Decimal("100")
                )
            ],
        ),
        db_session,
    )

    first_row = await db_session.get(LeasingApplication, first["application_id"])
    second_row = await db_session.get(LeasingApplication, second["application_id"])

    assert first_row is not None
    assert second_row is not None
    assert first_row.display_number is not None
    assert second_row.display_number is not None
    assert first_row.display_number.startswith("7701234567-")
    assert second_row.display_number.startswith("7701234567-")
    assert first_row.display_number.endswith("-001")
    assert second_row.display_number.endswith("-002")


async def test_build_display_number_full_format_for_fixed_date(
    db_session: AsyncSession,
) -> None:
    from application.commands.applications.display_number import build_display_number

    inn = "7701234567"
    fixed_date = date(2026, 9, 29)
    result = await build_display_number(
        db_session,
        inn=inn,
        created_on=fixed_date,
    )
    assert result == f"{inn}-290926-001"


async def test_display_number_increments_from_max_existing_sequence(
    db_session: AsyncSession,
    client_company: Company,
) -> None:
    from application.commands.applications.display_number import (
        assign_display_number_if_missing,
        build_display_number,
    )

    client_company.inn = "7709876543"
    fixed_date = date(2026, 9, 29)
    existing_app = LeasingApplication(
        company_id=client_company.id,
        display_number="7709876543-290926-002",
        status="active",
        created_at=datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
    )
    db_session.add(existing_app)
    await db_session.flush()

    next_num = await build_display_number(
        db_session,
        inn="7709876543",
        created_on=fixed_date,
    )
    assert next_num == "7709876543-290926-003"

    # Late assignment for an unnumbered app also gets -003 (incremental over -002 in DB)
    late_app = LeasingApplication(
        company_id=client_company.id,
        display_number=None,
        status="active",
        created_at=datetime(2026, 9, 29, 8, 0, tzinfo=UTC),
    )
    db_session.add(late_app)
    await db_session.flush()

    assigned = await assign_display_number_if_missing(
        db_session,
        application={"id": late_app.id, "company_id": client_company.id, "created_at": late_app.created_at},
    )
    assert assigned == "7709876543-290926-003"

    # Next app gets -004
    next_app = LeasingApplication(
        company_id=client_company.id,
        display_number=None,
        status="active",
        created_at=datetime(2026, 9, 29, 11, 0, tzinfo=UTC),
    )
    db_session.add(next_app)
    await db_session.flush()

    assigned_next = await assign_display_number_if_missing(
        db_session,
        application={"id": next_app.id, "company_id": client_company.id, "created_at": next_app.created_at},
    )
    assert assigned_next == "7709876543-290926-004"


async def test_create_draft_sequence_is_shared_across_creators_for_same_inn(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
) -> None:
    client_company.inn = "7707654321"
    second_dealer = User(
        phone="+76660003333",
        email="dealer-two@test.local",
        name="Dealer Two",
        role="dealer",
        is_active=True,
    )
    db_session.add(second_dealer)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=second_dealer.id,
            company_id=client_company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    await db_session.flush()

    first = await handle_create_draft(
        CreateDraftCommand(
            source_type="platform",
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=client_company.id,
            company_id=client_company.id,
            name="First Dealer",
            email="one@test.local",
            vehicles=[
                ApplicationVehiclePayload(
                    modification_id="MOD-A", custom_price=Decimal("100")
                )
            ],
        ),
        db_session,
    )
    second = await handle_create_draft(
        CreateDraftCommand(
            source_type="platform",
            actor_id=second_dealer.id,
            actor_role="dealer",
            actor_company_id=client_company.id,
            company_id=client_company.id,
            name="Second Dealer",
            email="two@test.local",
            vehicles=[
                ApplicationVehiclePayload(
                    modification_id="MOD-B", custom_price=Decimal("100")
                )
            ],
        ),
        db_session,
    )

    first_row = await db_session.get(LeasingApplication, first["application_id"])
    second_row = await db_session.get(LeasingApplication, second["application_id"])

    assert first_row is not None
    assert second_row is not None
    assert first_row.display_number is not None
    assert second_row.display_number is not None
    assert first_row.display_number.endswith("-001")
    assert second_row.display_number.endswith("-002")


async def test_employee_without_create_permission_cannot_create_draft(
    db_session: AsyncSession,
    client_company: Company,
) -> None:
    employee = User(
        phone="+76660004401",
        email="blocked-create@test.local",
        name="Blocked Create",
        role="client",
        company_id=client_company.id,
        is_active=True,
    )
    db_session.add(employee)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=employee.id,
            company_id=client_company.id,
            sub_role="employee",
            can_view_applications=True,
            can_create_applications=False,
        )
    )
    await db_session.flush()

    with pytest.raises(ServiceError) as exc_info:
        await handle_create_draft(
            CreateDraftCommand(
                source_type="platform",
                actor_id=employee.id,
                actor_role="client",
                actor_company_id=client_company.id,
                company_id=client_company.id,
                name="Blocked",
                email="blocked@test.local",
                vehicles=[
                    ApplicationVehiclePayload(
                        modification_id="MOD-BLOCKED",
                        custom_price=Decimal("100"),
                    )
                ],
            ),
            db_session,
        )
    assert "Создание заявок ограничено" in str(exc_info.value)


async def test_employee_with_create_permission_can_create_draft(
    db_session: AsyncSession,
    client_company: Company,
) -> None:
    employee = User(
        phone="+76660004402",
        email="allowed-create@test.local",
        name="Allowed Create",
        role="client",
        company_id=client_company.id,
        is_active=True,
    )
    db_session.add(employee)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=employee.id,
            company_id=client_company.id,
            sub_role="employee",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    await db_session.flush()

    result = await handle_create_draft(
        CreateDraftCommand(
            source_type="platform",
            actor_id=employee.id,
            actor_role="client",
            actor_company_id=client_company.id,
            company_id=client_company.id,
            name="Allowed",
            email="allowed@test.local",
            vehicles=[
                ApplicationVehiclePayload(
                    modification_id="MOD-ALLOWED",
                    custom_price=Decimal("100"),
                )
            ],
        ),
        db_session,
    )
    assert result["status"] == STATUS_ACTIVE
    application = await db_session.get(LeasingApplication, result["application_id"])
    assert application is not None
    assert application.source_type == "platform"


async def test_create_draft_unknown_company(
    db_session: AsyncSession, dealer: User
) -> None:
    cmd = CreateDraftCommand(
        source_type="platform",
        actor_id=dealer.id,
        actor_role="dealer",
        actor_company_id=uuid4(),
        company_id=uuid4(),
        vehicles=[ApplicationVehiclePayload(modification_id="MOD-A")],
    )
    with pytest.raises(CompanyNotFoundError):
        await handle_create_draft(cmd, db_session)


async def test_create_draft_no_vehicles(
    db_session: AsyncSession, dealer: User, client_company: Company
) -> None:
    cmd = CreateDraftCommand(
        source_type="platform",
        actor_id=dealer.id,
        actor_role="dealer",
        actor_company_id=client_company.id,
        company_id=client_company.id,
        vehicles=[],
    )
    with pytest.raises(ApplicationNotSubmittableError):
        await handle_create_draft(cmd, db_session)


async def test_create_application_with_lcs_becomes_active(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
    leasing_company: LeasingCompany,
) -> None:
    cmd = CreateApplicationCommand(
        source_type="platform",
        actor_id=dealer.id,
        actor_role="dealer",
        company_id=client_company.id,
        name="Test",
        email="test@test.local",
        vehicles=[
            ApplicationVehiclePayload(
                modification_id="MOD-X", quantity=1, custom_price=Decimal("50")
            )
        ],
        selected_leasing_companies=[leasing_company.id],
    )
    result = await handle_create_application(cmd, db_session)
    assert result["status"] == STATUS_ACTIVE
    assert result["vehiclesReserved"] == 1
    assert result["application_id"] is not None
    application = await db_session.get(LeasingApplication, result["application_id"])
    assert application is not None
    assert application.source_type == "platform"


async def test_create_application_without_lcs_becomes_active(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
) -> None:
    cmd = CreateApplicationCommand(
        source_type="platform",
        actor_id=dealer.id,
        actor_role="dealer",
        company_id=client_company.id,
        name="Test",
        email="test@test.local",
        vehicles=[
            ApplicationVehiclePayload(
                modification_id="MOD-X", quantity=1, custom_price=Decimal("50")
            )
        ],
    )
    result = await handle_create_application(cmd, db_session)
    assert result["status"] == STATUS_ACTIVE
    assert result["application_id"] is not None


async def test_create_application_with_create_draft_flag(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
    leasing_company: LeasingCompany,
) -> None:
    cmd = CreateApplicationCommand(
        source_type="platform",
        actor_id=dealer.id,
        actor_role="dealer",
        company_id=client_company.id,
        name="Test",
        email="test@test.local",
        vehicles=[ApplicationVehiclePayload(modification_id="MOD-X")],
        selected_leasing_companies=[leasing_company.id],
        create_draft=True,
    )
    result = await handle_create_application(cmd, db_session)
    assert result["status"] == STATUS_ACTIVE


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


async def _create_application_for_dealer(
    db_session: AsyncSession,
    dealer: User,
    company: Company,
    *,
    status: str,
    selected_leasing_companies: list[UUID] | None = None,
) -> dict[str, Any]:
    row = LeasingApplication(
        company_id=company.id,
        dealer_company_id=company.id,
        created_by=dealer.id,
        name="auto",
        email="auto@test.local",
        status=status,
        selected_leasing_companies=selected_leasing_companies,
    )
    db_session.add(row)
    await db_session.flush()
    return {"id": row.id, "status": row.status}


async def test_change_status_happy_path_active_to_rejected(
    db_session: AsyncSession, dealer: User, client_company: Company
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    result = await handle_change_status(
        ChangeStatusCommand(
            application_id=app["id"],
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=client_company.id,
            new_status=STATUS_REJECTED,
        ),
        db_session,
    )
    assert result["application"]["status"] == STATUS_REJECTED


async def test_change_status_happy_path_active_to_issued(
    db_session: AsyncSession, dealer: User, client_company: Company
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    result = await handle_change_status(
        ChangeStatusCommand(
            application_id=app["id"],
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=client_company.id,
            new_status=STATUS_ISSUED,
        ),
        db_session,
    )
    assert result["application"]["status"] == STATUS_ISSUED


async def test_change_status_happy_path_rejected_to_active(
    db_session: AsyncSession, dealer: User, client_company: Company
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_REJECTED
    )
    result = await handle_change_status(
        ChangeStatusCommand(
            application_id=app["id"],
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=client_company.id,
            new_status=STATUS_ACTIVE,
        ),
        db_session,
    )
    assert result["application"]["status"] == STATUS_ACTIVE


async def test_change_status_happy_path_issued_to_rejected(
    db_session: AsyncSession, dealer: User, client_company: Company
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ISSUED
    )
    result = await handle_change_status(
        ChangeStatusCommand(
            application_id=app["id"],
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=client_company.id,
            new_status=STATUS_REJECTED,
        ),
        db_session,
    )
    assert result["application"]["status"] == STATUS_REJECTED


async def test_change_status_illegitimate_transition_active_to_active(
    db_session: AsyncSession, dealer: User, client_company: Company
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    with pytest.raises(InvalidStatusTransitionError):
        await handle_change_status(
            ChangeStatusCommand(
                application_id=app["id"],
                actor_id=dealer.id,
                actor_role="dealer",
                actor_company_id=client_company.id,
                new_status=STATUS_ACTIVE,
            ),
            db_session,
        )


async def test_change_status_denied_for_other_dealer(
    db_session: AsyncSession, dealer: User, client_company: Company
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    with pytest.raises(ApplicationNotOwnedError):
        await handle_change_status(
            ChangeStatusCommand(
                application_id=app["id"],
                actor_id=uuid4(),
                actor_role="dealer",
                actor_company_id=None,
                new_status=STATUS_REJECTED,
            ),
            db_session,
        )


async def test_change_status_404_on_missing_application(
    db_session: AsyncSession, dealer: User
) -> None:
    with pytest.raises(ApplicationNotFoundError):
        await handle_change_status(
            ChangeStatusCommand(
                application_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                actor_id=dealer.id,
                actor_role="dealer",
                actor_company_id=None,
                new_status=STATUS_REJECTED,
            ),
            db_session,
        )


# ---------------------------------------------------------------------------
# VIN assignment (client-side)
# ---------------------------------------------------------------------------


async def test_assign_vin_happy_path(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
    available_vehicle: Vehicle,
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    av = ApplicationVehicle(
        application_id=app["id"],
        vehicle_id=None,
        modification_id="COMPL-A",
        quantity=1,
        unit_price=Decimal("100"),
        total_price=Decimal("100"),
        is_model_order=True,
    )
    db_session.add(av)
    await db_session.flush()
    result = await handle_assign_vin(
        AssignVinCommand(
            application_vehicle_id=av.id,
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=client_company.id,
            vehicle_id=available_vehicle.id,
        ),
        db_session,
    )
    assert result["assigned_vin"] == "HANDLERVIN00000001"


async def test_assign_vin_rejected_when_app_not_active(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
    available_vehicle: Vehicle,
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_REJECTED
    )
    av = ApplicationVehicle(
        application_id=app["id"],
        modification_id="COMPL-A",
        quantity=1,
        unit_price=Decimal("100"),
        total_price=Decimal("100"),
    )
    db_session.add(av)
    await db_session.flush()
    with pytest.raises(InvalidStatusTransitionError):
        await handle_assign_vin(
            AssignVinCommand(
                application_vehicle_id=av.id,
                actor_id=dealer.id,
                actor_role="dealer",
                actor_company_id=client_company.id,
                vehicle_id=available_vehicle.id,
            ),
            db_session,
        )


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


async def test_list_applications_employee_sees_all(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
    employee_user: User,
) -> None:
    for _ in range(3):
        await _create_application_for_dealer(
            db_session, dealer, client_company, status=STATUS_ACTIVE
        )
    result = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=employee_user.id,
            actor_role="carcraft_employee",
            actor_company_id=None,
        ),
        db_session,
    )
    assert result["total"] >= 3


async def test_list_applications_dealer_filter_by_dealer_id(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
) -> None:
    await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    # An application created by a different dealer (not visible).
    other_dealer = User(
        phone="+76660009999",
        email="otherdealer@test.local",
        role="dealer",
        is_active=True,
    )
    db_session.add(other_dealer)
    await db_session.flush()
    await _create_application_for_dealer(
        db_session,
        other_dealer,
        client_company,
        status=STATUS_ACTIVE,
    )
    result = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=None,
        ),
        db_session,
    )
    assert len(result["applications"]) > 0


async def test_list_applications_client_filters_by_company(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
    client_with_company: User,
) -> None:
    await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    other_company = Company(name="Other Co", company_type="other")
    db_session.add(other_company)
    await db_session.flush()
    await _create_application_for_dealer(
        db_session, dealer, other_company, status=STATUS_ACTIVE
    )
    result = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=client_with_company.id,
            actor_role="client",
            actor_company_id=client_company.id,
        ),
        db_session,
    )
    for app in result["applications"]:
        assert app["company_id"] == client_company.id


async def test_list_applications_includes_vehicle_totals_for_client_card(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
    client_with_company: User,
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    db_session.add(
        UserCompany(
            user_id=client_with_company.id,
            company_id=client_company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    db_session.add(
        ApplicationVehicle(
            application_id=app["id"],
            quantity=3,
            unit_price=Decimal("1538629.00"),
            total_price=Decimal("4800000.00"),
        )
    )
    await db_session.flush()

    result = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=client_with_company.id,
            actor_role="client",
            actor_company_id=client_company.id,
        ),
        db_session,
    )

    listed_app = next(
        app_item
        for app_item in result["applications"]
        if app_item["id"] == app["id"]
    )
    assert listed_app["total_vehicles_price"] == Decimal("4800000.00")
    assert listed_app["vehicles_count"] == 3


async def test_list_applications_vehicle_total_matches_detail_fallback(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
    client_with_company: User,
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    db_session.add(
        UserCompany(
            user_id=client_with_company.id,
            company_id=client_company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    db_session.add(
        ApplicationVehicle(
            application_id=app["id"],
            quantity=2,
            unit_price=Decimal("100000.00"),
            total_price=Decimal("0.00"),
        )
    )
    await db_session.flush()

    result = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=client_with_company.id,
            actor_role="client",
            actor_company_id=client_company.id,
        ),
        db_session,
    )

    listed_app = next(
        app_item
        for app_item in result["applications"]
        if app_item["id"] == app["id"]
    )
    assert listed_app["total_vehicles_price"] == Decimal("200000.00")
    assert listed_app["vehicles_count"] == 2


async def test_get_application_prefers_persisted_vehicle_total(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
    client_with_company: User,
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    db_session.add(
        UserCompany(
            user_id=client_with_company.id,
            company_id=client_company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    db_session.add(
        ApplicationVehicle(
            application_id=app["id"],
            quantity=2,
            unit_price=Decimal("100000.00"),
            total_price=Decimal("250000.00"),
        )
    )
    await db_session.flush()

    result = await handle_get_application(
        GetApplicationQuery(
            application_id=app["id"],
            actor_id=client_with_company.id,
            actor_role="client",
            actor_company_id=client_company.id,
        ),
        db_session,
    )

    assert result["total_vehicles_price"] == Decimal("250000.00")
    assert result["vehicles_count"] == 2


async def test_get_application_returns_creator_phone(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
    client_with_company: User,
) -> None:
    dealer.phone = "+79990000001"
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    db_session.add(
        UserCompany(
            user_id=client_with_company.id,
            company_id=client_company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    await db_session.flush()

    result = await handle_get_application(
        GetApplicationQuery(
            application_id=app["id"],
            actor_id=client_with_company.id,
            actor_role="client",
            actor_company_id=client_company.id,
        ),
        db_session,
    )

    assert result["phone"] == "+79990000001"
    assert result["owner"]["phone"] == "+79990000001"


async def test_employee_without_view_permission_gets_empty_list(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
) -> None:
    await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    employee = User(
        phone="+76660004403",
        email="blocked-view@test.local",
        name="Blocked View",
        role="client",
        company_id=client_company.id,
        is_active=True,
    )
    db_session.add(employee)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=employee.id,
            company_id=client_company.id,
            sub_role="employee",
            can_view_applications=False,
            can_create_applications=True,
        )
    )
    await db_session.flush()

    result = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=employee.id,
            actor_role="client",
            actor_company_id=client_company.id,
        ),
        db_session,
    )
    assert result["applications"] == []
    assert result["total"] == 0


async def test_employee_without_view_permission_cannot_get_application(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    employee = User(
        phone="+76660004404",
        email="blocked-detail@test.local",
        name="Blocked Detail",
        role="client",
        company_id=client_company.id,
        is_active=True,
    )
    db_session.add(employee)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=employee.id,
            company_id=client_company.id,
            sub_role="employee",
            can_view_applications=False,
            can_create_applications=True,
        )
    )
    await db_session.flush()

    with pytest.raises(ApplicationNotOwnedError):
        await handle_get_application(
            GetApplicationQuery(
                application_id=app["id"],
                actor_id=employee.id,
                actor_role="client",
                actor_company_id=client_company.id,
            ),
            db_session,
        )


async def test_employee_without_view_permission_can_get_own_created_application(
    db_session: AsyncSession,
    client_company: Company,
) -> None:
    employee = User(
        phone="+76660004405",
        email="own-draft-detail@test.local",
        name="Own Draft Detail",
        role="client",
        company_id=client_company.id,
        is_active=True,
    )
    db_session.add(employee)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=employee.id,
            company_id=client_company.id,
            sub_role="employee",
            can_view_applications=False,
            can_create_applications=True,
        )
    )
    await db_session.flush()

    draft = await handle_create_draft(
        CreateDraftCommand(
            source_type="platform",
            actor_id=employee.id,
            actor_role="client",
            actor_company_id=client_company.id,
            company_id=client_company.id,
            vehicles=[
                ApplicationVehiclePayload(
                    modification_id="MOD-OWN",
                    quantity=1,
                    custom_price=Decimal("100"),
                )
            ],
        ),
        db_session,
    )

    result = await handle_get_application(
        GetApplicationQuery(
            application_id=draft["application_id"],
            actor_id=employee.id,
            actor_role="client",
            actor_company_id=client_company.id,
        ),
        db_session,
    )
    assert result["id"] == draft["application_id"]
    assert result["created_by"] == employee.id


async def test_list_applications_leasing_company_filters_by_lc(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
    leasing_company: LeasingCompany,
) -> None:
    await _create_application_for_dealer(
        db_session,
        dealer,
        client_company,
        status=STATUS_ACTIVE,
        selected_leasing_companies=[leasing_company.id],
    )
    await _create_application_for_dealer(
        db_session,
        dealer,
        client_company,
        status=STATUS_ACTIVE,
        selected_leasing_companies=[uuid4()],
    )
    result = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=uuid4(),
            actor_role="leasing_company",
            actor_company_id=None,
            actor_leasing_company_id=leasing_company.id,
        ),
        db_session,
    )
    for app in result["applications"]:
        assert leasing_company.id in app["selected_leasing_companies"]


async def test_get_application_404(
    db_session: AsyncSession, employee_user: User
) -> None:
    with pytest.raises(ApplicationNotFoundError):
        await handle_get_application(
            GetApplicationQuery(
                application_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                actor_id=employee_user.id,
                actor_role="carcraft_employee",
                actor_company_id=None,
            ),
            db_session,
        )


async def test_get_application_ownership_check(
    db_session: AsyncSession, dealer: User, client_company: Company
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    with pytest.raises(ApplicationNotOwnedError):
        await handle_get_application(
            GetApplicationQuery(
                application_id=app["id"],
                actor_id=uuid4(),
                actor_role="dealer",
                actor_company_id=None,
            ),
            db_session,
        )


async def test_get_application_owner_without_company_relation_does_not_resolve_signers(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
) -> None:
    client_company.inn = "7700000001"
    client_company.director_inn = "7700000002"
    dealer.company_id = None
    await db_session.execute(
        delete(UserCompany).where(UserCompany.user_id == dealer.id)
    )
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )

    result = await handle_get_application(
        GetApplicationQuery(
            application_id=app["id"],
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=None,
        ),
        db_session,
    )

    assert "sopd_signer_candidates" not in result
    assert "sopd_signer_candidates" not in result["company"]


async def test_get_sopd_signer_candidates_authorized_owner_resolves_after_access(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
) -> None:
    client_company.inn = "7700000001"
    client_company.director_inn = "7700000002"
    dealer.company_id = None
    await db_session.execute(
        delete(UserCompany).where(UserCompany.user_id == dealer.id)
    )
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    provider = FakeCompanyLookupProvider(
        enrich_by_inn={
            "7700000002": {
                "name": {"short_with_opf": "ООО УК"},
                "management": {"name": "Управляев Устин", "inn": "500000000006"},
            }
        }
    )

    result = await handle_get_sopd_signer_candidates(
        GetSopdSignerCandidatesQuery(
            application_id=app["id"],
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=None,
            company_lookup_provider=provider,
        ),
        db_session,
    )

    assert provider.enrich_calls == ["7700000002"]
    assert result == {
        "candidates": [
            {
                "key": "500000000006",
                "role": "director_management_company",
                "role_label": "Директор управляющей компании",
                "full_name": "Управляев Устин",
                "inn": "500000000006",
                "share": None,
                "signing_method": "file",
                "source": "management_company_level_1",
                "sort_order": 1,
            }
        ]
    }


async def test_get_sopd_signer_candidates_provider_failure_is_not_empty_success(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
) -> None:
    client_company.inn = "7700000001"
    client_company.director_inn = "7700000002"
    dealer.company_id = None
    await db_session.execute(
        delete(UserCompany).where(UserCompany.user_id == dealer.id)
    )
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    provider = FakeCompanyLookupProvider()
    provider.raise_unavailable = True

    with pytest.raises(CompanyLookupUnavailableError):
        await handle_get_sopd_signer_candidates(
            GetSopdSignerCandidatesQuery(
                application_id=app["id"],
                actor_id=dealer.id,
                actor_role="dealer",
                actor_company_id=None,
                company_lookup_provider=provider,
            ),
            db_session,
        )

    assert provider.enrich_calls == ["7700000002"]


async def test_get_sopd_signer_candidates_denied_dealer_does_not_call_provider(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    provider = FakeCompanyLookupProvider()

    with pytest.raises(ApplicationNotOwnedError):
        await handle_get_sopd_signer_candidates(
            GetSopdSignerCandidatesQuery(
                application_id=app["id"],
                actor_id=uuid4(),
                actor_role="dealer",
                actor_company_id=None,
                company_lookup_provider=provider,
            ),
            db_session,
        )

    assert provider.enrich_calls == []


@pytest.mark.parametrize(
    ("actor_role", "actor_company_id"),
    [("dealer", None), ("carcraft_employee", None)],
)
async def test_get_sopd_signer_candidates_authorized_roles_receive_stable_empty_response(
    db_session: AsyncSession,
    dealer: User,
    employee_user: User,
    client_company: Company,
    actor_role: str,
    actor_company_id: UUID | None,
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    actor_id = dealer.id if actor_role == "dealer" else employee_user.id

    result = await handle_get_sopd_signer_candidates(
        GetSopdSignerCandidatesQuery(
            application_id=app["id"],
            actor_id=actor_id,
            actor_role=actor_role,
            actor_company_id=actor_company_id,
        ),
        db_session,
    )

    assert result == {"candidates": []}


def test_sopd_signer_candidates_have_separate_stable_schema() -> None:
    schema = ApplicationDetailResponse.model_json_schema()
    company = schema["properties"]["company"]
    company_ref = next(item["$ref"] for item in company["anyOf"] if "$ref" in item)
    company_schema = schema["$defs"][company_ref.rsplit("/", maxsplit=1)[-1]]

    assert "sopd_signer_candidates" not in company_schema["properties"]
    assert SopdSignerCandidatesResponse.model_validate({}).candidates == []


async def test_resolve_application_company_does_not_invent_missing_company(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_company_lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "application.queries.applications.get_application.company_repo.get_company_by_id",
        missing_company_lookup,
    )

    no_company = await _resolve_company(cast("AsyncSession", None), {})
    missing_company = await _resolve_company(
        cast("AsyncSession", None), {"company_id": uuid4()}
    )

    assert no_company is None
    assert missing_company is None
    missing_company_lookup.assert_awaited_once()


async def test_get_application_leasing_company_detail_omits_signer_candidates(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
    leasing_company: LeasingCompany,
) -> None:
    app = await _create_application_for_dealer(
        db_session,
        dealer,
        client_company,
        status=STATUS_ACTIVE,
        selected_leasing_companies=[leasing_company.id],
    )
    lc_reader = User(phone=f"+7{uuid4().int % 10**16:016d}", role="leasing_company",
                     company_id=leasing_company.company_id, is_active=True)
    db_session.add(lc_reader)
    db_session.add(LeasingCompanyApplication(
        application_id=app["id"], leasing_company_id=leasing_company.id, status="under_review",
    ))
    await db_session.flush()

    result = await handle_get_application(
        GetApplicationQuery(
            application_id=app["id"],
            actor_id=lc_reader.id,
            actor_role="leasing_company",
            actor_company_id=leasing_company.company_id,
            actor_leasing_company_id=leasing_company.id,
        ),
        db_session,
    )

    assert "sopd_signer_candidates" not in result["company"]


async def test_list_available_vins_requires_active(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
    available_vehicle: Vehicle,
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_REJECTED
    )
    av = ApplicationVehicle(
        application_id=app["id"],
        modification_id="COMPL-A",
        quantity=1,
        unit_price=Decimal("10"),
        total_price=Decimal("10"),
    )
    db_session.add(av)
    await db_session.flush()
    with pytest.raises(InvalidStatusTransitionError):
        await handle_list_available_vins(
            ListAvailableVinsQuery(
                application_vehicle_id=av.id,
                actor_id=dealer.id,
                actor_role="dealer",
                actor_company_id=client_company.id,
            ),
            db_session,
        )


async def test_list_available_vins_returns_matches_when_active(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
    available_vehicle: Vehicle,
) -> None:
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    av = ApplicationVehicle(
        application_id=app["id"],
        modification_id="COMPL-A",
        quantity=1,
        unit_price=Decimal("10"),
        total_price=Decimal("10"),
    )
    db_session.add(av)
    await db_session.flush()
    result = await handle_list_available_vins(
        ListAvailableVinsQuery(
            application_vehicle_id=av.id,
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=client_company.id,
        ),
        db_session,
    )
    assert any(v["id"] == available_vehicle.id for v in result["vehicles"])


# ---------------------------------------------------------------------------
# Tax system fallback from enriched company profile
# ---------------------------------------------------------------------------


async def test_list_applications_employee_sees_cross_company_only_here(
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    """Employees get scope across all companies without filters."""
    result = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=employee_user.id,
            actor_role="carcraft_employee",
            actor_company_id=None,
        ),
        db_session,
    )
    # Shape contract: always returns dict with "applications" and "total".
    assert "applications" in result
    assert "total" in result


async def test_distributor_application_scope_filters_list_and_hides_foreign_detail(
    db_session: AsyncSession,
) -> None:
    distributor_company = Company(name="Scope distributor", company_type="distributor")
    linked_dealer = Company(name="Linked dealer", company_type="dealer")
    foreign_dealer = Company(name="Foreign dealer", company_type="dealer")
    db_session.add_all([distributor_company, linked_dealer, foreign_dealer])
    await db_session.flush()
    distributor = User(
        phone="+76660112233",
        email="scope-distributor@test.local",
        role="distributor",
        company_id=distributor_company.id,
        is_active=True,
    )
    db_session.add_all(
        [
            distributor,
            DistributorDealerLink(
                distributor_company_id=distributor_company.id,
                dealer_company_id=linked_dealer.id,
            ),
        ]
    )
    mark = Mark(id="21864_SCOPE", name="Scope brand")
    db_session.add(mark)
    await db_session.flush()
    group = DealerGroup(distributor_company_id=distributor_company.id,
                        name="Scope group", created_by=distributor.id, is_active=True)
    linked_warehouse = Warehouse(company_id=linked_dealer.id, address="Linked stock", brand=mark.name)
    foreign_warehouse = Warehouse(company_id=foreign_dealer.id, address="Foreign stock", brand=mark.name)
    db_session.add_all([group, linked_warehouse, foreign_warehouse])
    await db_session.flush()
    db_session.add_all([
        DealerGroupMember(dealer_group_id=group.id, dealer_company_id=linked_dealer.id,
                          created_by=distributor.id),
        DistributorBrand(distributor_company_id=distributor_company.id,
                         brand_id=mark.id, is_active=True),
    ])
    linked_vehicle = Vehicle(
        mark_id=mark.id,
        vin="SCOPELINKED001",
        dealer_id=linked_dealer.id,
        status="available",
        is_available=True,
    )
    foreign_vehicle = Vehicle(
        mark_id=mark.id,
        vin="SCOPEFOREIGN01",
        dealer_id=foreign_dealer.id,
        status="available",
        is_available=True,
    )
    db_session.add_all([linked_vehicle, foreign_vehicle])
    await db_session.flush()
    db_session.add_all([
        VehicleWarehouse(vehicle_id=linked_vehicle.id, warehouse_id=linked_warehouse.id),
        VehicleWarehouse(vehicle_id=foreign_vehicle.id, warehouse_id=foreign_warehouse.id),
    ])
    linked_app = LeasingApplication(
        company_id=linked_dealer.id,
        dealer_company_id=linked_dealer.id,
        created_by=distributor.id,
        name="linked",
        email="linked@test.local",
        status=STATUS_ACTIVE,
    )
    foreign_app = LeasingApplication(
        company_id=foreign_dealer.id,
        dealer_company_id=foreign_dealer.id,
        created_by=distributor.id,
        name="foreign",
        email="foreign@test.local",
        status=STATUS_ACTIVE,
    )
    db_session.add_all([linked_app, foreign_app])
    await db_session.flush()
    db_session.add_all(
        [
            ApplicationVehicle(
                application_id=linked_app.id,
                vehicle_id=linked_vehicle.id,
                quantity=1,
                unit_price=Decimal("1"),
                total_price=Decimal("1"),
            ),
            ApplicationVehicle(
                application_id=foreign_app.id,
                vehicle_id=foreign_vehicle.id,
                quantity=1,
                unit_price=Decimal("1"),
                total_price=Decimal("1"),
            ),
        ]
    )
    await db_session.flush()

    listing = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=distributor.id,
            actor_role="distributor",
            actor_company_id=distributor_company.id,
        ),
        db_session,
    )
    assert listing["total"] == 1
    assert [app["id"] for app in listing["applications"]] == [linked_app.id]
    with pytest.raises(ApplicationNotFoundError):
        await handle_get_application(
            GetApplicationQuery(
                application_id=foreign_app.id,
                actor_id=distributor.id,
                actor_role="distributor",
                actor_company_id=distributor_company.id,
            ),
            db_session,
        )


# ---------------------------------------------------------------------------
# Tax system fallback from enriched company profile
# ---------------------------------------------------------------------------


async def test_get_application_falls_back_tax_system_from_company(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
) -> None:
    """When the questionnaire has no tax_system but the company row has one
    (from DaData enrichment), the value is injected into the response with
    a transient tax_system_auto flag.
    """
    client_company.tax_system = "УСН"
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    result = await handle_get_application(
        GetApplicationQuery(
            application_id=app["id"],
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=client_company.id,
        ),
        db_session,
    )
    assert result["questionnaire"] is not None
    assert result["questionnaire"]["tax_system"] == "УСН"
    assert result["questionnaire"]["tax_system_auto"] is True


async def test_get_application_does_not_override_existing_tax_system(
    db_session: AsyncSession,
    dealer: User,
    client_company: Company,
) -> None:
    """If the questionnaire already has a tax_system, the company value is
    ignored — user choice takes precedence.
    """
    from infrastructure.repositories import application_repository as app_repo

    client_company.tax_system = "УСН"
    app = await _create_application_for_dealer(
        db_session, dealer, client_company, status=STATUS_ACTIVE
    )
    await app_repo.upsert_questionnaire(
        db_session,
        application_id=app["id"],
        payload={"tax_system": "ОСН"},
    )
    result = await handle_get_application(
        GetApplicationQuery(
            application_id=app["id"],
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=client_company.id,
        ),
        db_session,
    )
    assert result["questionnaire"]["tax_system"] == "ОСН"
    assert "tax_system_auto" not in result["questionnaire"]
