"""Unit / handler tests for LC-side leasing applications (Phase 5 E3)."""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.applications import ApplicationVehiclePayload
from application.commands.leasing_applications_lc import (
    CreateLcApplicationCommand,
    SubmitLcApplicationCommand,
    UpdateLcApplicationCommand,
    handle_create_lc_application,
    handle_submit_lc_application,
    handle_update_lc_application,
)
from application.queries.leasing_applications_lc import (
    ListLcApplicationsOverviewQuery,
    handle_list_lc_applications_overview,
)
from domain.entities.leasing_application import STATUS_ACTIVE
from domain.errors import (
    ApplicationNotEditableError,
    ApplicationNotOwnedError,
    LeasingCompanyBindingNotConfiguredError,
)
from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.notification_delivery import NotificationEventOutbox
from infrastructure.models.users import User


@pytest_asyncio.fixture
async def lc_client_company(db_session: AsyncSession) -> Company:
    c = Company(name="LC Test Co", company_type="other")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def lc_provider_company(db_session: AsyncSession) -> Company:
    c = Company(name="LC Provider", company_type="leasing_company")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def lc_entity(
    db_session: AsyncSession, lc_provider_company: Company
) -> LeasingCompany:
    lc = LeasingCompany(
        company_id=lc_provider_company.id, is_active=True
    )
    db_session.add(lc)
    await db_session.flush()
    return lc


@pytest_asyncio.fixture
async def lc_user(
    db_session: AsyncSession, lc_provider_company: Company
) -> User:
    u = User(
        phone="+76660000001",
        email="lcuser@test.local",
        name="LC User",
        role="leasing_company",
        is_active=True,
        company_id=lc_provider_company.id,
    )
    db_session.add(u)
    await db_session.flush()
    await db_session.refresh(u)
    return u


# ---------------------------------------------------------------------------
# create_lc_application
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_lc_application_active_and_adds_self(
    db_session: AsyncSession,
    lc_user: User,
    lc_client_company: Company,
    lc_entity: LeasingCompany,
) -> None:
    cmd = CreateLcApplicationCommand(
        source_type="platform",
        actor_id=lc_user.id,
        actor_role="leasing_company",
        actor_leasing_company_id=lc_entity.id,
        company_id=lc_client_company.id,
        name="Client",
        email="c@test.local",
        vehicles=[
            ApplicationVehiclePayload(
                modification_id="MOD-LC",
                quantity=1,
                custom_price=Decimal("100"),
            )
        ],
        selected_leasing_companies=[],
    )
    result = await handle_create_lc_application(cmd, db_session)
    assert result["status"] == STATUS_ACTIVE
    app_id = result["application_id"]

    row = await db_session.get(LeasingApplication, app_id)
    assert row is not None
    assert lc_entity.id in (row.selected_leasing_companies or [])
    events = (await db_session.scalars(sa.select(NotificationEventOutbox).where(
        NotificationEventOutbox.aggregate_id == app_id,
    ).order_by(NotificationEventOutbox.sequence))).all()
    assert [event.event_type for event in events] == [
        "leasing.application_created", "leasing.company_assigned",
    ]
    # No INN in this fixture: the established numbering policy cannot assign
    # a display number, so the event uses the complete opaque UUID.
    assert events[0].payload["request_number"] == str(row.id)


@pytest.mark.asyncio
async def test_create_lc_application_without_binding_errors(
    db_session: AsyncSession,
    lc_user: User,
    lc_client_company: Company,
) -> None:
    cmd = CreateLcApplicationCommand(
        source_type="platform",
        actor_id=lc_user.id,
        actor_role="leasing_company",
        actor_leasing_company_id=None,
        company_id=lc_client_company.id,
        vehicles=[
            ApplicationVehiclePayload(
                modification_id="MOD-LC", custom_price=Decimal("10")
            )
        ],
    )
    with pytest.raises(LeasingCompanyBindingNotConfiguredError):
        await handle_create_lc_application(cmd, db_session)


# ---------------------------------------------------------------------------
# update_lc_application
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_lc_application_active_happy_path(
    db_session: AsyncSession,
    lc_user: User,
    lc_client_company: Company,
    lc_entity: LeasingCompany,
) -> None:
    app = LeasingApplication(
        company_id=lc_client_company.id,
        email="active@test.local",
        status=STATUS_ACTIVE,
        selected_leasing_companies=[lc_entity.id],
    )
    db_session.add(app)
    await db_session.flush()
    await db_session.refresh(app)

    cmd = UpdateLcApplicationCommand(
        application_id=app.id,
        actor_id=lc_user.id,
        actor_role="leasing_company",
        actor_company_id=lc_user.company_id,
        actor_leasing_company_id=lc_entity.id,
        fields_set={"name", "total_amount"},
        name="Updated Name",
        total_amount=Decimal("500000"),
    )
    result = await handle_update_lc_application(cmd, db_session)
    assert result["application"]["name"] == "Updated Name"
    assert Decimal(str(result["application"]["total_amount"])) == Decimal("500000")


@pytest.mark.asyncio
async def test_update_lc_application_with_lc_children_rejected(
    db_session: AsyncSession,
    lc_user: User,
    lc_client_company: Company,
    lc_entity: LeasingCompany,
) -> None:
    app = LeasingApplication(
        company_id=lc_client_company.id,
        email="x@test.local",
        status=STATUS_ACTIVE,
        selected_leasing_companies=[lc_entity.id],
    )
    db_session.add(app)
    await db_session.flush()
    await db_session.refresh(app)

    child = LeasingCompanyApplication(
        application_id=app.id,
        leasing_company_id=lc_entity.id,
    )
    db_session.add(child)
    await db_session.flush()

    cmd = UpdateLcApplicationCommand(
        application_id=app.id,
        actor_id=lc_user.id,
        actor_role="leasing_company",
        actor_company_id=lc_user.company_id,
        actor_leasing_company_id=lc_entity.id,
        fields_set={"name"},
        name="X",
    )
    with pytest.raises(ApplicationNotEditableError):
        await handle_update_lc_application(cmd, db_session)


@pytest.mark.asyncio
async def test_update_lc_application_foreign_lc_denied(
    db_session: AsyncSession,
    lc_user: User,
    lc_client_company: Company,
    lc_entity: LeasingCompany,
) -> None:
    # Application belongs to some other LC id.
    app = LeasingApplication(
        company_id=lc_client_company.id,
        email="x@test.local",
        status=STATUS_ACTIVE,
        selected_leasing_companies=[uuid4()],
    )
    db_session.add(app)
    await db_session.flush()
    await db_session.refresh(app)

    cmd = UpdateLcApplicationCommand(
        application_id=app.id,
        actor_id=lc_user.id,
        actor_role="leasing_company",
        actor_company_id=lc_user.company_id,
        actor_leasing_company_id=lc_entity.id,
        fields_set={"name"},
        name="X",
    )
    with pytest.raises(ApplicationNotOwnedError):
        await handle_update_lc_application(cmd, db_session)


# ---------------------------------------------------------------------------
# submit_lc_application
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_lc_application_active_no_op(
    db_session: AsyncSession,
    lc_user: User,
    lc_client_company: Company,
    lc_entity: LeasingCompany,
) -> None:
    app = LeasingApplication(
        company_id=lc_client_company.id,
        email="submit@test.local",
        status=STATUS_ACTIVE,
        selected_leasing_companies=[lc_entity.id],
    )
    db_session.add(app)
    await db_session.flush()
    await db_session.refresh(app)

    cmd = SubmitLcApplicationCommand(
        application_id=app.id,
        actor_id=lc_user.id,
        actor_role="leasing_company",
        actor_company_id=lc_user.company_id,
        actor_leasing_company_id=lc_entity.id,
    )
    result = await handle_submit_lc_application(cmd, db_session)
    assert result["application"]["status"] == STATUS_ACTIVE


# ---------------------------------------------------------------------------
# list + stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_lc_applications_overview_filters_by_lc(
    db_session: AsyncSession,
    lc_user: User,
    lc_client_company: Company,
    lc_entity: LeasingCompany,
) -> None:
    in_scope = LeasingApplication(
        company_id=lc_client_company.id,
        email="a@test.local",
        status=STATUS_ACTIVE,
        selected_leasing_companies=[lc_entity.id],
    )
    out_of_scope = LeasingApplication(
        company_id=lc_client_company.id,
        email="b@test.local",
        status=STATUS_ACTIVE,
        selected_leasing_companies=[uuid4()],
    )
    db_session.add_all([in_scope, out_of_scope])
    await db_session.flush()

    # Create LCA for in_scope so LC can see it
    lca_in_scope = LeasingCompanyApplication(
        application_id=in_scope.id,
        leasing_company_id=lc_entity.id,
        status="submitted",
    )
    db_session.add(lca_in_scope)
    await db_session.flush()

    result = await handle_list_lc_applications_overview(
        ListLcApplicationsOverviewQuery(
            actor_user_id=lc_user.id,
            actor_role="leasing_company",
            actor_leasing_company_id=lc_entity.id,
        ),
        db_session,
    )
    ids = [a["application"]["id"] for a in result["applications"]]
    assert in_scope.id in ids
    assert out_of_scope.id not in ids


# Phase 15 H3 — handle_get_lc_applications_stats deleted with /stats/overview.
