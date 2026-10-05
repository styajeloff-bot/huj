"""Distribution recipients cannot mutate the rest of a commercial line."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.application_vehicles.dealer_action import (
    DealerVehicleActionCommand,
    handle_dealer_vehicle_action,
)
from application.commands.application_vehicles.fulfillment import (
    FulfillmentCommand,
    save_fulfillment,
)
from application.dealer_distribution_access import ensure_whole_vehicle_write_allowed
from domain.dealer_distribution import DealerDistributionConflictError
from domain.errors import ApplicationNotOwnedError
from infrastructure.models.applications import (
    ApplicationDealerDistributionRequest,
    ApplicationVehicle,
    ApplicationVehicleDealerDistribution,
    LeasingApplication,
)
from infrastructure.models.companies import Company
from infrastructure.models.users import User
from infrastructure.models.vehicles import City, Warehouse
from infrastructure.repositories.dealer_distribution_access_repository import (
    application_has_distributions,
)
from tests.legacy_compat import Vehicle, VehicleWarehouse

type DistributionGraph = tuple[
    Company, Company, User, LeasingApplication, ApplicationVehicle, ApplicationVehicleDealerDistribution,
]


@pytest_asyncio.fixture
async def distributed_line(db_session: AsyncSession) -> DistributionGraph:
    owner = Company(name="21864 distributor", company_type="distributor", is_active=True)
    dealer = Company(name="21864 dealer", company_type="dealer", is_active=True)
    db_session.add_all([owner, dealer])
    await db_session.flush()
    actor = User(name="21864 distributor", role="distributor", phone="+70002186499", company_id=owner.id)
    city = City(name="21864 guard city")
    db_session.add_all([actor, city])
    await db_session.flush()
    warehouse = Warehouse(company_id=owner.id, dealer_id=owner.id, city_id=city.id, brand="FAW", address="21864", status="active")
    vehicle = Vehicle(dealer_id=owner.id, vin="GUARD21864", status="available", base_price=Decimal("100"))
    application = LeasingApplication(company_id=owner.id, name="21864 guard", status="active")
    db_session.add_all([warehouse, vehicle, application])
    await db_session.flush()
    db_session.add(VehicleWarehouse(vehicle_id=vehicle.id, warehouse_id=warehouse.id))
    line = ApplicationVehicle(application_id=application.id, vehicle_id=vehicle.id, quantity=5,
                              unit_price=Decimal("100"), total_price=Decimal("500"))
    request = ApplicationDealerDistributionRequest(application_id=application.id, distributor_company_id=owner.id,
        actor_id=actor.id, client_request_id=uuid4(), payload_hash="0" * 64)
    db_session.add_all([line, request])
    await db_session.flush()
    allocation = ApplicationVehicleDealerDistribution(application_vehicle_id=line.id,
        dealer_company_id=dealer.id, quantity=2, request_id=request.id)
    db_session.add(allocation)
    await db_session.flush()
    return owner, dealer, actor, application, line, allocation


async def test_partial_dealer_cannot_change_whole_position_price(
    db_session: AsyncSession, distributed_line: DistributionGraph,
) -> None:
    _, dealer, actor, _, line, _ = distributed_line
    with pytest.raises(ApplicationNotOwnedError):
        await handle_dealer_vehicle_action(DealerVehicleActionCommand(
            application_vehicle_id=line.id, actor_id=actor.id, actor_role="dealer",
            actor_company_id=dealer.id, action="discount", discount_type="rubles_off",
            discount_value=Decimal("10")), db_session)
    await db_session.refresh(line)
    assert line.total_price == Decimal("500")
    assert line.quantity == 5
    assert line.final_price is None


async def test_entire_quantity_recipient_keeps_whole_position_access(
    db_session: AsyncSession, distributed_line: DistributionGraph,
) -> None:
    _, dealer, _, _, line, allocation = distributed_line
    allocation.quantity = 5
    await db_session.flush()
    scope = await ensure_whole_vehicle_write_allowed(db_session,
        application_vehicle_id=line.id, actor_role="dealer", actor_company_id=dealer.id)
    assert scope["actor_quantity"] == 5
    assert scope["sole_dealer_id"] == dealer.id


async def test_stock_owner_cannot_reduce_below_distributed_quantity(
    db_session: AsyncSession, distributed_line: DistributionGraph,
) -> None:
    owner, _, actor, _, line, _ = distributed_line
    with pytest.raises(DealerDistributionConflictError):
        await save_fulfillment(FulfillmentCommand(application_vehicle_id=line.id,
            actor_id=actor.id, actor_role="distributor", actor_company_id=owner.id,
            confirmed_quantity=1, reserve_expires_at=(datetime.now(UTC) + timedelta(days=1)).date()), db_session)
    await db_session.refresh(line)
    assert line.quantity == 5
    assert line.total_price == Decimal("500")


async def test_stock_owner_and_admin_keep_access_and_parent_detects_assignments(
    db_session: AsyncSession, distributed_line: DistributionGraph,
) -> None:
    owner, _, _, application, line, _ = distributed_line
    assert await application_has_distributions(db_session, application.id)
    assert not await application_has_distributions(db_session, uuid4())
    for role, company_id in (("distributor", owner.id), ("carcraft_employee", None)):
        scope = await ensure_whole_vehicle_write_allowed(db_session,
            application_vehicle_id=line.id, actor_role=role, actor_company_id=company_id)
        assert scope["distributed_quantity"] == 2
        assert scope["quantity"] == 5


@pytest.mark.parametrize("quantity", [2, 5])
async def test_employee_assignment_respects_distribution_and_keeps_dealer_identity(
    db_session: AsyncSession, distributed_line: DistributionGraph, quantity: int,
) -> None:
    from application.commands.application_vehicles.assign_employees import (
        AssignApplicationVehicleEmployeesCommand,
        handle_assign_application_vehicle_employees,
    )

    _, dealer, _, application, line, allocation = distributed_line
    employee = User(name="21864 dealer employee", role="dealer", phone="+70002186498",
                    company_id=dealer.id, is_active=True)
    allocation.quantity = quantity
    db_session.add(employee)
    await db_session.flush()
    command = AssignApplicationVehicleEmployeesCommand(
        application_id=application.id, application_vehicle_id=line.id,
        actor_id=employee.id, actor_role="dealer", actor_company_id=dealer.id,
        update_primary=True, primary_employee_id=employee.id,
    )
    assert line.quantity is not None
    if quantity < line.quantity:
        with pytest.raises(ApplicationNotOwnedError):
            await handle_assign_application_vehicle_employees(command, db_session)
        await db_session.refresh(line)
        assert line.primary_employee_id is None
        return
    result = await handle_assign_application_vehicle_employees(command, db_session)
    assert result["application_vehicle"]["assigned_dealer"]["id"] == dealer.id
    assert result["application_vehicle"]["primary_employee"]["id"] == employee.id
    await db_session.refresh(line)
    assert line.primary_employee_id == employee.id
    assert line.dealer_company_id is None
