from dataclasses import replace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.application_vehicles.dealer_action import (
    DealerVehicleActionCommand,
    handle_dealer_vehicle_action,
)
from application.commands.application_vehicles.fulfillment import (
    FulfillmentCommand,
    get_fulfillment,
    save_fulfillment,
)
from application.errors import ServiceError
from domain.errors import (
    ApplicationVehicleAssignmentError,
    ApplicationVehicleFulfillmentRequiredError,
)
from infrastructure.models.applications import ApplicationVehicle, LeasingApplication
from infrastructure.models.users import User
from infrastructure.models.vehicles import Warehouse
from infrastructure.repositories import application_repository as apps
from infrastructure.repositories import vehicle_fulfillment_repository as fulfillment
from tests.legacy_compat import Vehicle, VehicleWarehouse
from tests.test_vehicle_fulfillment import seed


async def warehouse_owned(db: AsyncSession, actor: User) -> tuple[LeasingApplication, ApplicationVehicle, list[Vehicle], FulfillmentCommand]:
    app, line, cars, cmd = await seed(db, actor)
    line.vehicle_id = cars[0].id
    cars[0].complectation_id = "matching"
    cars[1].complectation_id = "other"
    warehouse = Warehouse(address="21924 repro", brand="Test", company_id=app.company_id)
    db.add(warehouse)
    await db.flush()
    db.add_all([VehicleWarehouse(vehicle_id=car.id, warehouse_id=warehouse.id) for car in cars])
    await db.flush()
    assert await apps.dealer_company_owns_application_vehicle(db, application_vehicle_id=line.id, company_id=app.company_id)
    return app, line, cars, replace(cmd, actor_role="dealer", actor_company_id=app.company_id)

async def test_old_reserve_rejects_before_mutation(db_session: AsyncSession, employee_user: User) -> None:
    app, line, cars, cmd = await warehouse_owned(db_session, employee_user)
    with pytest.raises(ApplicationVehicleFulfillmentRequiredError, match="Подберите автомобили"):
        await handle_dealer_vehicle_action(DealerVehicleActionCommand(application_vehicle_id=line.id,
            actor_id=employee_user.id, actor_role="dealer", actor_company_id=app.company_id,
            action="reserve", reserve_expires_at=cmd.reserve_expires_at), db_session)
    await db_session.refresh(line)
    await db_session.refresh(cars[0])
    assert line.car_status == "active" and line.confirmed_quantity is None and line.fulfillment_version == 0
    assert cars[0].status == "available" and line.reserve_expires_at is None

async def test_warehouse_owned_candidate_is_visible(db_session: AsyncSession, employee_user: User) -> None:
    _app, _line, cars, cmd = await warehouse_owned(db_session, employee_user)
    view = await get_fulfillment(cmd, db_session)
    assert [v["id"] for v in view["available_vehicles"]] == [cars[0].id]

async def test_warehouse_owned_candidate_can_be_saved(db_session: AsyncSession, employee_user: User) -> None:
    _app, _line, cars, cmd = await warehouse_owned(db_session, employee_user)
    result = await save_fulfillment(cmd, db_session)
    assert result["confirmed_quantity"] == 3
    await db_session.refresh(cars[0])
    assert cars[0].status == "reserved"

async def test_missing_snapshot_uses_anchor_trim(db_session: AsyncSession, employee_user: User) -> None:
    _app, line, cars, cmd = await warehouse_owned(db_session, employee_user)
    assert line.modification_id is None
    with pytest.raises(ApplicationVehicleAssignmentError):
        await save_fulfillment(replace(cmd, vehicle_ids=[cars[1].id]), db_session)
    assert await fulfillment.allocations(db_session, line.id) == []

async def test_actual_warehouse_owner_overrides_stale_vehicle_owner(db_session: AsyncSession, employee_user: User) -> None:
    from infrastructure.models.companies import Company
    _app, _line, cars, cmd = await warehouse_owned(db_session, employee_user)
    other = Company(name="Other dealer", company_type="dealer", inn="9999999999")
    db_session.add(other)
    await db_session.flush()
    cars[0].dealer_id = other.id
    await db_session.flush()
    assert await fulfillment.available_stock(db_session, dealer_ids=[other.id], complectation_id=None) == []
    await save_fulfillment(cmd, db_session)

async def test_foreign_warehouse_cannot_be_selected_with_stale_dealer_id(db_session: AsyncSession, employee_user: User) -> None:
    from sqlalchemy import update

    from infrastructure.models.companies import Company
    app, line, cars, cmd = await warehouse_owned(db_session, employee_user)
    other = Company(name="Other dealer", company_type="dealer", inn="9999999999")
    db_session.add(other)
    await db_session.flush()
    foreign = Warehouse(address="Foreign", brand="Test", company_id=other.id)
    db_session.add(foreign)
    await db_session.flush()
    cars[1].dealer_id = app.company_id
    cars[1].complectation_id = cars[0].complectation_id
    await db_session.execute(update(VehicleWarehouse).where(VehicleWarehouse.vehicle_id == cars[1].id).values(warehouse_id=foreign.id))
    await db_session.flush()
    with pytest.raises(ServiceError) as error:
        await save_fulfillment(replace(cmd, vehicle_ids=[cars[1].id]), db_session)
    assert error.value.status_code == 404
    assert await fulfillment.allocations(db_session, line.id) == []
