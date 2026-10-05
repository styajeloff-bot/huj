
"""Real database coverage for distributor scope and quantity share reads."""
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.applications import (
    GetApplicationQuery,
    ListApplicationsQuery,
    handle_get_application,
    handle_list_applications,
)
from application.queries.distributor.list_distributor_applications import (
    ListDistributorApplicationsQuery,
    handle_list_distributor_applications,
)
from application.queries.distributor.list_distributor_applications_grouped import (
    ListDistributorApplicationsGroupedQuery,
    handle_list_distributor_applications_grouped,
)
from domain.errors import ApplicationNotFoundError
from infrastructure.models.applications import (
    ApplicationDealerDistributionRequest,
    ApplicationVehicle,
    ApplicationVehicleDealerDistribution,
    LeasingApplication,
)
from infrastructure.models.companies import DistributorBrand, DistributorDealerLink
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.repositories import application_repository as repo
from tests import test_distributor_dealer_assignment as assignment_fixtures
from tests.legacy_compat import Mark

assignment_graph = assignment_fixtures.assignment_graph

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("active_group,active_brand", [(True, True), (True, False), (False, True), (False, False)])
async def test_dealer_application_requires_active_group_and_brand(
    db_session: AsyncSession, assignment_graph: assignment_fixtures.AssignmentGraph,
    active_group: bool, active_brand: bool,
) -> None:
    graph = assignment_graph
    db_session.add(Mark(id="21864_BRAND", name="Scoped brand"))
    await db_session.flush()
    graph.dealer_two_vehicle.mark_id = "21864_BRAND"
    graph.group.is_active = active_group
    db_session.add(DistributorBrand(distributor_company_id=graph.distributor_company.id,
                                    brand_id="21864_BRAND", is_active=active_brand))
    # A direct link and parent dealer must never bypass either condition.
    db_session.add(DistributorDealerLink(distributor_company_id=graph.distributor_company.id,
                                        dealer_company_id=graph.dealer_two.id))
    app = LeasingApplication(company_id=graph.client_company.id, dealer_company_id=graph.dealer_two.id,
                             status="active", name="Dealer stock")
    db_session.add(app)
    await db_session.flush()
    line = ApplicationVehicle(application_id=app.id, vehicle_id=graph.dealer_two_vehicle.id,
                              dealer_company_id=graph.dealer_two.id, quantity=2,
                              unit_price=Decimal("100"), total_price=Decimal("200"))
    db_session.add(line)
    await db_session.flush()
    result = await handle_list_applications(ListApplicationsQuery(
        actor_id=graph.distributor_user.id, actor_role="distributor",
        actor_company_id=graph.distributor_company.id), db_session)
    expected = active_group and active_brand
    assert (app.id in {item["id"] for item in result["applications"]}) is expected
    alternate = await handle_list_distributor_applications(ListDistributorApplicationsQuery(
        actor_id=graph.distributor_user.id, actor_role="distributor", company_id=graph.distributor_company.id), db_session)
    grouped = await handle_list_distributor_applications_grouped(ListDistributorApplicationsGroupedQuery(
        actor_id=graph.distributor_user.id, actor_role="distributor", company_id=graph.distributor_company.id), db_session)
    assert alternate["applications"] == result["applications"]
    assert (app.id in {item["id"] for rows in grouped["applications"].values() for item in rows}) is expected
    detail_query = GetApplicationQuery(application_id=app.id, actor_id=graph.distributor_user.id,
                                      actor_role="distributor", actor_company_id=graph.distributor_company.id)
    if expected:
        detail = await handle_get_application(detail_query, db_session)
        assert [item["id"] for item in detail["items"]] == [line.id]
        assert detail["items_count"] == 2
    else:
        with pytest.raises(ApplicationNotFoundError):
            await handle_get_application(detail_query, db_session)


async def test_mixed_own_stock_is_visible_and_out_of_brand_line_is_hidden(
    db_session: AsyncSession, assignment_graph: assignment_fixtures.AssignmentGraph,
) -> None:
    graph = assignment_graph
    hidden = ApplicationVehicle(application_id=graph.application.id, vehicle_id=graph.dealer_two_vehicle.id,
                                quantity=3, unit_price=Decimal("100"), total_price=Decimal("300"))
    db_session.add(hidden)
    await db_session.flush()
    result = await handle_get_application(GetApplicationQuery(application_id=graph.application.id,
        actor_id=graph.distributor_user.id, actor_role="distributor",
        actor_company_id=graph.distributor_company.id), db_session)
    assert len(result["vehicles"]) == len(result["dealer_distribution"]) == 1
    assert result["vehicles"][0]["vehicle_id"] == graph.distributor_vehicle.id
    assert result["total_items_price"] == Decimal("1000000")
    assert result["items_count"] == 1
    assert result["dealer_distribution"][0]["can_assign_dealer"] is True
    assert not await repo.distributor_can_view_application(db_session,
        application_id=graph.application.id, dealer_ids=[graph.dealer_two.id],
        distributor_company_id=uuid4())
    admin = await handle_get_application(GetApplicationQuery(application_id=graph.application.id,
        actor_id=graph.carcraft_user.id, actor_role="carcraft_employee", actor_company_id=None), db_session)
    assert len(admin["vehicles"]) == 2


async def test_multiple_groups_do_not_duplicate_application_or_totals(
    db_session: AsyncSession, assignment_graph: assignment_fixtures.AssignmentGraph,
) -> None:
    graph = assignment_graph
    db_session.add(Mark(id="21864_BRAND", name="Scoped brand"))
    await db_session.flush()
    graph.dealer_two_vehicle.mark_id = "21864_BRAND"
    db_session.add(DistributorBrand(distributor_company_id=graph.distributor_company.id, brand_id="21864_BRAND"))
    second = DealerGroup(distributor_company_id=graph.distributor_company.id, name="Second group",
                         is_active=True, created_by=graph.distributor_user.id)
    db_session.add(second)
    await db_session.flush()
    db_session.add(DealerGroupMember(dealer_group_id=second.id, dealer_company_id=graph.dealer_two.id,
                                    created_by=graph.distributor_user.id))
    db_session.add(ApplicationVehicle(application_id=graph.application.id, vehicle_id=graph.dealer_two_vehicle.id,
                                      quantity=2, unit_price=Decimal("100"), total_price=Decimal("200")))
    await db_session.flush()
    result = await handle_list_applications(ListApplicationsQuery(actor_id=graph.distributor_user.id,
        actor_role="distributor", actor_company_id=graph.distributor_company.id), db_session)
    assert result["total"] == 1
    assert result["applications"][0]["items_count"] == 3


async def test_dealer_reads_only_allocated_quantity_and_amount(
    db_session: AsyncSession, assignment_graph: assignment_fixtures.AssignmentGraph,
) -> None:
    graph = assignment_graph
    line = await db_session.scalar(sa.select(ApplicationVehicle).where(ApplicationVehicle.application_id == graph.application.id))
    assert line is not None
    line.quantity = 5
    line.requested_quantity = 5
    cast("Any", line).unit_price = Decimal("100")
    cast("Any", line).total_price = Decimal("600")  # Includes unit options: the share must preserve them.
    for company, quantity in [(graph.dealer_one, 2), (graph.dealer_two, 1)]:
        journal = ApplicationDealerDistributionRequest(application_id=graph.application.id,
            distributor_company_id=graph.distributor_company.id, actor_id=graph.distributor_user.id,
            client_request_id=uuid4(), payload_hash="share-test")
        db_session.add(journal)
        await db_session.flush()
        db_session.add(ApplicationVehicleDealerDistribution(application_vehicle_id=line.id,
            dealer_company_id=company.id, quantity=quantity, request_id=journal.id))
    await db_session.flush()
    for company, actor, quantity in [(graph.dealer_one, graph.dealer_one_user, 2),
                                      (graph.dealer_two, graph.dealer_two_user, 1)]:
        listed = await handle_list_applications(ListApplicationsQuery(actor_id=actor.id, actor_role="dealer",
            actor_company_id=company.id), db_session)
        assert listed["total"] == 1
        summary = listed["applications"][0]
        assert summary["items_count"] == quantity
        assert summary["total_items_price"] == Decimal("120") * quantity
        detail = await handle_get_application(GetApplicationQuery(application_id=graph.application.id,
            actor_id=actor.id, actor_role="dealer", actor_company_id=company.id), db_session)
        assert detail["vehicles"][0]["quantity"] == quantity
        assert detail["vehicles"][0]["total_price"] == Decimal("120") * quantity
        assert detail["vehicles"][0]["can_manage_whole_vehicle"] is False
        assert detail["vehicles"][0]["assigned_dealer"] == {"id": company.id, "name": company.name, "inn": company.inn}
        assert detail["vehicles"][0]["dealer_company_id"] == company.id
        assert detail["total_amount"] == Decimal("120") * quantity
        allocation = detail["dealer_distribution"][0]
        assert allocation["unassigned_quantity"] == 0
        assert allocation["dealer_allocations"] == [{"dealer": {"id": company.id,
            "name": company.name, "inn": company.inn}, "quantity": quantity}]
    owner = await handle_get_application(GetApplicationQuery(application_id=graph.application.id,
        actor_id=graph.distributor_user.id, actor_role="distributor",
        actor_company_id=graph.distributor_company.id), db_session)
    assert owner["items_count"] == 5
    assert owner["total_items_price"] == Decimal("600")
    assert owner["dealer_distribution"][0]["unassigned_quantity"] == 2
    assert len(owner["dealer_distribution"][0]["dealer_allocations"]) == 2


@pytest.mark.parametrize("owner_as_legacy_dealer", [True, False])
async def test_legacy_full_assignment_counts_only_a_dealer_company(
    db_session: AsyncSession, assignment_graph: assignment_fixtures.AssignmentGraph,
    owner_as_legacy_dealer: bool,
) -> None:
    graph = assignment_graph
    line = await db_session.scalar(sa.select(ApplicationVehicle).where(ApplicationVehicle.application_id == graph.application.id))
    assert line is not None
    line.quantity = 5
    line.dealer_company_id = graph.distributor_company.id if owner_as_legacy_dealer else graph.dealer_one.id
    await db_session.flush()
    result = await handle_get_application(GetApplicationQuery(application_id=graph.application.id,
        actor_id=graph.distributor_user.id, actor_role="distributor",
        actor_company_id=graph.distributor_company.id), db_session)
    distribution = result["dealer_distribution"][0]
    assert distribution["unassigned_quantity"] == (5 if owner_as_legacy_dealer else 0)
    assert distribution["can_assign_dealer"] is owner_as_legacy_dealer
    assert len(distribution["dealer_allocations"]) == (0 if owner_as_legacy_dealer else 1)


async def test_special_equipment_keeps_existing_dealer_scope(
    db_session: AsyncSession, assignment_graph: assignment_fixtures.AssignmentGraph,
) -> None:
    from tests.test_application_commerce_projection import _seed_mixed_application

    graph = assignment_graph
    app, _vehicle, equipment, _removed = await _seed_mixed_application(db_session)
    equipment.seller_company_id = graph.dealer_two.id
    await db_session.flush()
    detail = await handle_get_application(GetApplicationQuery(application_id=app.id,
        actor_id=graph.distributor_user.id, actor_role="distributor",
        actor_company_id=graph.distributor_company.id), db_session)
    assert {item["id"] for item in detail["items"]} == {equipment.id}
    assert detail["vehicles"] == []


async def test_shared_assignment_reads_resolve_new_full_recipient(
    db_session: AsyncSession, assignment_graph: assignment_fixtures.AssignmentGraph,
) -> None:
    from infrastructure.repositories import (
        application_vehicle_assignment_repository as assignments,
    )

    graph = assignment_graph
    line = await db_session.scalar(sa.select(ApplicationVehicle).where(ApplicationVehicle.application_id == graph.application.id))
    assert line is not None
    line.dealer_company_id = graph.distributor_company.id  # Historical owner value is not a dealer assignment.
    journal = ApplicationDealerDistributionRequest(application_id=graph.application.id,
        distributor_company_id=graph.distributor_company.id, actor_id=graph.distributor_user.id,
        client_request_id=uuid4(), payload_hash="full-read-test")
    db_session.add(journal)
    await db_session.flush()
    db_session.add(ApplicationVehicleDealerDistribution(application_vehicle_id=line.id,
        dealer_company_id=graph.dealer_one.id, quantity=1, request_id=journal.id))
    await db_session.flush()
    assignment = await assignments.get_assignment(db_session, application_id=graph.application.id,
                                                 application_vehicle_id=line.id)
    assert assignment is not None
    assert assignment["dealer_company_id"] == graph.dealer_one.id
    details = await assignments.get_assignment_details(db_session, application_vehicle_id=line.id)
    assert details["assigned_dealer"] == {"id": graph.dealer_one.id, "name": graph.dealer_one.name, "inn": graph.dealer_one.inn}
    await db_session.refresh(line)
    assert line.dealer_company_id == graph.distributor_company.id
