"""Unit tests for admin_applications command/query handlers."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.admin_applications import (
    AssignLeasingCompaniesToApplicationCommand,
    handle_assign_leasing_companies_to_application,
)
from application.queries.admin_applications import (
    GetAdminApplicationDetailQuery,
    ListAdminApplicationsQuery,
    handle_get_admin_application_detail,
    handle_list_admin_applications,
)
from domain.entities.leasing_application import (
    STATUS_ACTIVE,
    STATUS_ISSUED,
    STATUS_REJECTED,
)
from domain.errors import (
    ApplicationLcAssignmentNotAllowedError,
    ApplicationNotFoundError,
    LeasingCompanyNotFoundError,
)
from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
    LeasingCompanyApplication,
    LeasingProposal,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.compensations import (
    CompensationModel,
    CompensationTemplateModel,
)
from infrastructure.models.support import (
    ApplicationAppliedSupport,
    SupportProgram,
)
from infrastructure.repositories import (
    admin_applications_repository as admin_repo,
)
from presentation.schemas.admin import AdminApplicationDetailResponse
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


async def _make_company(db: AsyncSession, inn: str) -> Company:
    company = Company(
        name=f"Company {inn}",
        inn=inn,
        company_type="dealer",
        is_active=True,
    )
    db.add(company)
    await db.flush()
    return company


async def _make_leasing_company(
    db: AsyncSession, *, inn: str = "7700001000", name: str = "LC Co"
) -> LeasingCompany:
    company = Company(
        name=name,
        inn=inn,
        company_type="leasing_company",
        is_active=True,
    )
    db.add(company)
    await db.flush()
    lc = LeasingCompany(company_id=company.id, is_active=True)
    db.add(lc)
    await db.flush()
    return lc


async def _make_application(
    db: AsyncSession, *, company_id: UUID, status: str = STATUS_ACTIVE
) -> LeasingApplication:
    app = LeasingApplication(
        company_id=company_id,
        name="Test App",
        email="app@test.local",
        status=status,
        selected_leasing_companies=[],
    )
    db.add(app)
    await db.flush()
    return app


async def test_list_admin_applications_empty_total(
    db_session: AsyncSession,
) -> None:
    result = await handle_list_admin_applications(
        ListAdminApplicationsQuery(page=1, limit=10), db_session
    )
    assert "applications" in result
    assert "pagination" in result


async def test_list_admin_applications_filters_by_status(
    db_session: AsyncSession,
) -> None:
    company = await _make_company(db_session, "7700100001")
    await _make_application(db_session, company_id=company.id, status=STATUS_ACTIVE)
    await _make_application(db_session, company_id=company.id, status=STATUS_REJECTED)

    result = await handle_list_admin_applications(
        ListAdminApplicationsQuery(status=STATUS_ACTIVE), db_session
    )
    assert all(a["status"] == STATUS_ACTIVE for a in result["applications"])


async def test_list_admin_applications_returns_display_number(
    db_session: AsyncSession,
) -> None:
    company = await _make_company(db_session, "7700100007")
    app = LeasingApplication(
        company_id=company.id,
        name="Display Number App",
        email="display@test.local",
        status=STATUS_ACTIVE,
        selected_leasing_companies=[],
        display_number="7700100007-2904-001",
    )
    db_session.add(app)
    await db_session.flush()

    result = await handle_list_admin_applications(
        ListAdminApplicationsQuery(page=1, limit=10), db_session
    )
    item = next(a for a in result["applications"] if a["id"] == app.id)
    assert item["display_number"] == "7700100007-2904-001"


async def test_list_admin_applications_prefers_persisted_vehicle_total(
    db_session: AsyncSession,
) -> None:
    company = await _make_company(db_session, "7700100008")
    app = await _make_application(
        db_session, company_id=company.id, status=STATUS_ACTIVE
    )
    db_session.add(
        ApplicationVehicle(
            application_id=app.id,
            quantity=2,
            unit_price=Decimal("100000.00"),
            total_price=Decimal("250000.00"),
        )
    )
    await db_session.flush()

    result = await handle_list_admin_applications(
        ListAdminApplicationsQuery(page=1, limit=10), db_session
    )

    item = next(a for a in result["applications"] if a["id"] == app.id)
    assert item["total_vehicles_price"] == Decimal("250000.00")


async def test_get_admin_application_detail_projects_price_adjustments(
    db_session: AsyncSession,
) -> None:
    company = await _make_company(db_session, "7700100013")
    app = await _make_application(
        db_session, company_id=company.id, status=STATUS_ACTIVE
    )
    vehicle_line = ApplicationVehicle(
        application_id=app.id,
        quantity=2,
        unit_price=Decimal("1000000.00"),
        total_price=Decimal("1900000.00"),
        discount_type="percent_off",
        discount_value=Decimal("10.00"),
        markup_type="rubles_up",
        markup_value=Decimal("50000.00"),
        discount_show_catalog_price=False,
        markup_show_catalog_price=True,
        final_price=Decimal("950000.00"),
        dealer_comment="Итоговое предложение дилера",
    )
    db_session.add(vehicle_line)
    await db_session.flush()

    result = await handle_get_admin_application_detail(
        GetAdminApplicationDetailQuery(application_id=app.id),
        db_session,
    )

    application = result["application"]
    assert application["items_count"] == 2
    assert application["total_items_price"] == Decimal("1900000.00")
    assert len(application["vehicle_price_items"]) == 1

    item = application["vehicle_price_items"][0]
    assert item["type"] == "vehicle"
    assert item["title"] == "Автомобиль"
    assert item["unit_price"] == Decimal("1000000.00")
    assert item["catalog_price"] == Decimal("1000000.00")
    assert item["discount_type"] == "percent_off"
    assert item["discount_value"] == Decimal("10.00")
    assert item["discount_amount"] == Decimal("100000.00")
    assert item["markup_type"] == "rubles_up"
    assert item["markup_value"] == Decimal("50000.00")
    assert item["markup_amount"] == Decimal("50000.00")
    assert item["final_price"] == Decimal("950000.00")
    assert item["total_price"] == Decimal("1900000.00")
    assert item["dealer_comment"] == "Итоговое предложение дилера"
    assert item["show_catalog_price"] is False

    validated = AdminApplicationDetailResponse.model_validate(result)
    assert validated.application.vehicle_price_items[0].show_catalog_price is False


async def test_get_admin_application_detail_returns_lca_with_proposals(
    db_session: AsyncSession,
) -> None:
    company = await _make_company(db_session, "7700100012")
    lc = await _make_leasing_company(db_session, inn="7700003001", name="Detail LC")
    app = await _make_application(
        db_session, company_id=company.id, status=STATUS_ACTIVE
    )
    object.__setattr__(app, "display_number", "7700100012-0907-001")
    object.__setattr__(app, "total_amount", Decimal("1200000.00"))
    await db_session.flush()

    lca = LeasingCompanyApplication(
        application_id=app.id,
        leasing_company_id=lc.id,
        status="approved_scoring",
        decision_comment="approved",
    )
    db_session.add(lca)
    await db_session.flush()

    proposal = LeasingProposal(
        leasing_company_application_id=lca.id,
        kind="preliminary",
        position=2,
        total_amount=Decimal("1190000.00"),
        monthly_payment=Decimal("53000.00"),
    )
    db_session.add(proposal)
    await db_session.flush()

    result = await handle_get_admin_application_detail(
        GetAdminApplicationDetailQuery(application_id=app.id),
        db_session,
    )

    assert result["application"]["id"] == app.id
    assert result["application"]["display_number"] == "7700100012-0907-001"
    assert result["application"]["company_name"] == company.name

    links = result["leasing_company_applications"]
    assert len(links) == 1
    assert links[0]["id"] == lca.id
    assert links[0]["leasing_company"]["name"] == "Detail LC"
    assert links[0]["proposals"] == [
        {
            **links[0]["proposals"][0],
            "id": proposal.id,
            "leasing_company_application_id": lca.id,
            "kind": "preliminary",
            "position": 2,
            "total_amount": Decimal("1190000.00"),
            "monthly_payment": Decimal("53000.00"),
        }
    ]


async def test_get_admin_application_detail_batches_proposals_for_all_lcas(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    application_id = uuid4()
    lca_ids = [uuid4(), uuid4(), uuid4()]
    lca_items = [{"id": lca_id} for lca_id in lca_ids]
    proposals = [
        {
            "id": uuid4(),
            "leasing_company_application_id": lca_ids[0],
            "kind": "final",
        },
        {
            "id": uuid4(),
            "leasing_company_application_id": lca_ids[0],
            "kind": "preliminary",
        },
        {
            "id": uuid4(),
            "leasing_company_application_id": lca_ids[2],
            "kind": "preliminary",
        },
    ]
    get_detail_base = AsyncMock(return_value={"id": application_id})
    list_lca_details = AsyncMock(return_value=lca_items)
    list_proposals_by_lca_ids = AsyncMock(return_value=proposals)
    monkeypatch.setattr(admin_repo, "get_detail_base", get_detail_base)
    monkeypatch.setattr(admin_repo, "list_lca_details", list_lca_details)
    monkeypatch.setattr(
        admin_repo,
        "list_proposals_by_lca_ids",
        list_proposals_by_lca_ids,
    )

    result = await handle_get_admin_application_detail(
        GetAdminApplicationDetailQuery(application_id=application_id),
        db_session,
    )

    list_proposals_by_lca_ids.assert_awaited_once_with(db_session, lca_ids)
    links = result["leasing_company_applications"]
    assert links[0]["proposals"] == proposals[:2]
    assert links[1]["proposals"] == []
    assert links[2]["proposals"] == proposals[2:]


async def test_assign_leasing_companies_happy_path(
    db_session: AsyncSession,
) -> None:
    company = await _make_company(db_session, "7700100003")
    lc = await _make_leasing_company(db_session)
    app = await _make_application(
        db_session, company_id=company.id, status=STATUS_ACTIVE
    )

    result = await handle_assign_leasing_companies_to_application(
        AssignLeasingCompaniesToApplicationCommand(
            application_id=app.id, leasing_company_ids=[lc.id]
        ),
        db_session,
    )
    assert result["assigned_count"] == 1
    assert result["new_links_count"] == 1
    assert result["leasing_company_ids"] == [lc.id]


async def test_assign_leasing_companies_unknown_lc_raises(
    db_session: AsyncSession,
) -> None:
    company = await _make_company(db_session, "7700100004")
    app = await _make_application(
        db_session, company_id=company.id, status=STATUS_ACTIVE
    )

    with pytest.raises(LeasingCompanyNotFoundError):
        await handle_assign_leasing_companies_to_application(
            AssignLeasingCompaniesToApplicationCommand(
                application_id=app.id, leasing_company_ids=[uuid4()]
            ),
            db_session,
        )


async def test_assign_leasing_companies_wrong_status_raises(
    db_session: AsyncSession,
) -> None:
    company = await _make_company(db_session, "7700100005")
    lc = await _make_leasing_company(db_session)
    app = await _make_application(
        db_session, company_id=company.id, status=STATUS_ISSUED
    )

    with pytest.raises(ApplicationLcAssignmentNotAllowedError):
        await handle_assign_leasing_companies_to_application(
            AssignLeasingCompaniesToApplicationCommand(
                application_id=app.id, leasing_company_ids=[lc.id]
            ),
            db_session,
        )


async def test_assign_missing_application_raises(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(ApplicationNotFoundError):
        await handle_assign_leasing_companies_to_application(
            AssignLeasingCompaniesToApplicationCommand(
                application_id=uuid.uuid4(), leasing_company_ids=[uuid4()]
            ),
            db_session,
        )


async def test_assign_fans_out_active_into_one_application_per_lc(
    db_session: AsyncSession,
) -> None:
    from infrastructure.repositories import (
        application_repository as app_repo,
    )

    company = await _make_company(db_session, "7700100010")
    lc1 = await _make_leasing_company(db_session, inn="7700002001", name="LC One")
    lc2 = await _make_leasing_company(db_session, inn="7700002002", name="LC Two")
    app = await _make_application(
        db_session,
        company_id=company.id,
        status=STATUS_ACTIVE,
    )
    # Fan-out decision is based on has_lc_children, not status.
    assert not await app_repo.has_lc_children(db_session, app.id)

    # vehicles — the application itself is the group root (group_id=NULL).
    await app_repo.create_application_vehicle(
        db_session,
        application_id=app.id,
        vehicle_id=None,
        modification_id="mod-a",
        quantity=1,
        unit_price=0,  # type: ignore[arg-type]
        total_price=0,  # type: ignore[arg-type]
        is_model_order=True,
    )

    result = await handle_assign_leasing_companies_to_application(
        AssignLeasingCompaniesToApplicationCommand(
            application_id=app.id, leasing_company_ids=[lc1.id, lc2.id]
        ),
        db_session,
    )

    # No clones created; original LA stays active with LCA records.
    assert result["status"] == STATUS_ACTIVE

    original = await app_repo.get_by_id(db_session, app.id)
    assert original is not None
    assert original["status"] == STATUS_ACTIVE
    assert original["selected_leasing_companies"] == [lc1.id, lc2.id]

    # LCA records created for each LC.
    lc_links = await app_repo.list_lc_links(db_session, app.id)
    assert len(lc_links) == 2
    link_lcs = {link["leasing_company_id"] for link in lc_links}
    assert link_lcs == {lc1.id, lc2.id}
    assert all(link["status"] == "submitted" for link in lc_links)

    # Original application keeps its vehicles (not cloned).
    original_vehicles_stmt = select(ApplicationVehicle).where(
        ApplicationVehicle.application_id == app.id
    )
    original_vehicles = (
        (await db_session.execute(original_vehicles_stmt)).scalars().all()
    )
    assert len(original_vehicles) == 1


async def test_assign_leasing_companies_keeps_display_number(
    db_session: AsyncSession,
) -> None:
    """When the source application already has a display_number, it is
    preserved after LC assignment — the original LA is the single source
    of truth."""
    company = await _make_company(db_session, "7700100008")
    lc = await _make_leasing_company(db_session)
    app = await _make_application(
        db_session, company_id=company.id, status=STATUS_ACTIVE
    )
    # Manually set a display_number as if the application had been created
    # through the normal checkout flow.
    from infrastructure.repositories import application_repository as repo

    await repo.update_display_number(
        db_session,
        application_id=app.id,
        display_number="7700100008-0505-042",
    )

    result = await handle_assign_leasing_companies_to_application(
        AssignLeasingCompaniesToApplicationCommand(
            application_id=app.id, leasing_company_ids=[lc.id]
        ),
        db_session,
    )

    from infrastructure.repositories import application_repository as repo

    original = await repo.get_by_id(db_session, result["application_id"])
    assert original is not None
    assert original["display_number"] == "7700100008-0505-042"
    assert original["status"] == STATUS_ACTIVE
    assert result["new_links_count"] == 1


async def test_assign_leasing_companies_finalizes_selected_supports(
    db_session: AsyncSession,
) -> None:
    from infrastructure.repositories import application_repository as app_repo

    company = await _make_company(db_session, "7700100011")
    lc = await _make_leasing_company(db_session)
    vehicle = Vehicle(
        status="available",
        is_available=True,
        base_price=Decimal("1000000"),
    )
    program = SupportProgram(
        name="Down payment support",
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 100000},
        is_active=True,
    )
    db_session.add_all([vehicle, program])
    await db_session.flush()
    db_session.add(
        CompensationTemplateModel(
            support_program_id=program.id,
            payer="carcraft",
            recipient="client",
            calculation_base="support_amount",
            value_type="percent",
            value=100,
            payment_schedule_value="1",
        )
    )
    await db_session.flush()

    app = await _make_application(
        db_session, company_id=company.id, status=STATUS_ACTIVE
    )
    object.__setattr__(app, "total_amount", Decimal("1000000"))
    object.__setattr__(app, "down_payment", Decimal("200000"))
    object.__setattr__(app, "down_payment_percent", 20)
    object.__setattr__(app, "lease_term_months", 24)
    await db_session.flush()

    await app_repo.create_application_vehicle(
        db_session,
        application_id=app.id,
        vehicle_id=vehicle.id,
        modification_id=None,
        quantity=1,
        unit_price=Decimal("1000000"),
        total_price=Decimal("1000000"),
        is_model_order=False,
    )
    await app_repo.upsert_calculation(
        db_session,
        application_id=app.id,
        payload={
            "total_amount": 1000000,
            "down_payment": 200000,
            "down_payment_percent": 20,
            "lease_term_months": 24,
            "selected_support": {str(vehicle.id): [str(program.id)]},
        },
    )

    result = await handle_assign_leasing_companies_to_application(
        AssignLeasingCompaniesToApplicationCommand(
            application_id=app.id,
            leasing_company_ids=[lc.id],
        ),
        db_session,
    )

    assert result["status"] == STATUS_ACTIVE

    applied_support = (
        await db_session.execute(
            select(ApplicationAppliedSupport).where(
                ApplicationAppliedSupport.application_id == app.id
            )
        )
    ).scalar_one()
    assert applied_support.support_program_id == program.id
    assert applied_support.vehicle_id == vehicle.id
    assert applied_support.support_amount == 100000

    compensation = (
        await db_session.execute(
            select(CompensationModel).where(
                CompensationModel.applied_support_id == applied_support.id
            )
        )
    ).scalar_one()
    assert compensation.application_id == app.id
    assert compensation.vehicle_id == vehicle.id
    assert compensation.payer == "carcraft"
    assert compensation.recipient == "client"
    assert compensation.amount == 100000
