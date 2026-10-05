
"""Physical allocation invariants exercised against PostgreSQL, not mock locks."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from application.commands.application_vehicles.fulfillment import (
    FulfillmentCommand,
    get_fulfillment,
    save_fulfillment,
)
from application.errors import ServiceError
from domain.errors import (
    ApplicationVehicleAssignmentError,
    ApplicationVehicleFulfillmentRequiredError,
    VehicleNotAvailableError,
)
from infrastructure.models.applications import (
    ApplicationVehicle,
    ApplicationVehicleAllocation,
    LeasingApplication,
)
from infrastructure.models.companies import Company
from infrastructure.models.users import User
from infrastructure.repositories import vehicle_fulfillment_repository as repo
from tests.legacy_compat import Vehicle, VehicleWarehouse


async def seed(db: AsyncSession, actor: User) -> tuple[LeasingApplication, ApplicationVehicle, list[Vehicle], FulfillmentCommand]:
    company = Company(name="Fulfillment client", company_type="dealer", inn="1234567890")
    db.add(company)
    await db.flush()
    app = LeasingApplication(status="active", company_id=company.id, created_by=actor.id)
    db.add(app)
    await db.flush()
    line = ApplicationVehicle(application_id=app.id, requested_quantity=4, quantity=4,
        unit_price=Decimal("100"), total_price=Decimal("400"), car_status="active")
    cars = [Vehicle(status="available", is_available=True, vin=str(uuid4())[:17], base_price=999) for _ in range(2)]
    db.add_all([line, *cars])
    await db.flush()
    cmd = FulfillmentCommand(application_vehicle_id=line.id, actor_id=actor.id,
        actor_role="carcraft_employee", actor_company_id=None, confirmed_quantity=3,
        vehicle_ids=[cars[0].id], reserve_expires_at=(datetime.now(UTC) + timedelta(days=2)).date())
    return app, line, cars, cmd


async def test_save_reprices_quantity_preserves_requested_and_agreed_unit_price(db_session: AsyncSession, employee_user: User) -> None:
    _app, _line, cars, cmd = await seed(db_session, employee_user)
    result = await save_fulfillment(cmd, db_session)
    assert (result["requested_quantity"], result["confirmed_quantity"], result["remaining_quantity"]) == (4, 3, 2)
    assert result["allocations"][0]["unit_price"] == Decimal("100")
    assert result["application_totals"]["total_amount"] == Decimal("300")
    await db_session.refresh(cars[0])
    assert cars[0].status == "reserved"
    assert result["version"] == 1
    with pytest.raises(ServiceError, match="уже изменён"):
        await save_fulfillment(cmd, db_session)


async def test_replace_requires_reason_and_releases_only_removed_machine(db_session: AsyncSession, employee_user: User) -> None:
    _app, _line, cars, cmd = await seed(db_session, employee_user)
    await save_fulfillment(cmd, db_session)
    replacement = replace(cmd, version=1, vehicle_ids=[cars[1].id])
    with pytest.raises(ApplicationVehicleAssignmentError, match="причину"):
        await save_fulfillment(replacement, db_session)
    result = await save_fulfillment(replace(replacement, comment="Замена цвета"), db_session)
    assert len(result["allocations"]) == 2
    assert sum(a["released_at"] is None for a in result["allocations"]) == 1
    await db_session.refresh(cars[0])
    await db_session.refresh(cars[1])
    assert (cars[0].status, cars[1].status) == ("available", "reserved")
    assert result["application_totals"]["total_amount"] == Decimal("300")


async def test_preview_transaction_rolls_back_stock_line_and_history(db_session: AsyncSession, employee_user: User) -> None:
    _app, line, cars, cmd = await seed(db_session, employee_user)
    lid, car_id = line.id, cars[0].id
    tx = await db_session.begin_nested()
    result = await save_fulfillment(cmd, db_session)
    assert result["version"] == 1
    await tx.rollback()
    unchanged = await get_fulfillment(replace(cmd, application_vehicle_id=lid), db_session)
    assert unchanged["version"] == 0 and unchanged["quantity"] == 4
    assert unchanged["allocations"] == [] and unchanged["history"] == []
    assert (await repo.stock(db_session, [car_id]))[0]["status"] == "available"


async def test_unique_active_claim_rejects_same_physical_unit(db_session: AsyncSession, employee_user: User) -> None:
    app, _line, cars, cmd = await seed(db_session, employee_user)
    await save_fulfillment(cmd, db_session)
    other = ApplicationVehicle(application_id=app.id, quantity=1, unit_price=100)
    db_session.add(other)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(ApplicationVehicleAllocation(application_vehicle_id=other.id,
                vehicle_id=cars[0].id, unit_price=100,
                reserved_until=datetime.now(UTC)+timedelta(days=1), created_by=employee_user.id))
            await db_session.flush()
    assert len((await db_session.scalars(select(ApplicationVehicleAllocation))).all()) == 1


async def test_claim_conflict_preserves_previous_selection(db_session: AsyncSession, employee_user: User) -> None:
    _app, line, cars, cmd = await seed(db_session, employee_user)
    await save_fulfillment(cmd, db_session)
    cars[1].status = "sold"
    await db_session.flush()
    with pytest.raises(VehicleNotAvailableError):
        await save_fulfillment(replace(cmd, version=1, vehicle_ids=[cars[1].id], comment="Замена"), db_session)
    active = await repo.allocations(db_session, line.id, active_only=True)
    assert [a["vehicle_id"] for a in active] == [cars[0].id]


async def test_quantity_change_recalculates_saved_financing_and_options(db_session: AsyncSession, employee_user: User) -> None:
    app, line, _cars, cmd = await seed(db_session, employee_user)
    app.lease_term_months = 36
    cast("Any", app).down_payment_percent = Decimal("20")
    cast("Any", app).rate = Decimal("12")
    cast("Any", app).total_cost = Decimal("2400000")
    cast("Any", app).vat_refund = Decimal("400000")
    cast("Any", app).profit_tax_savings = Decimal("400000")
    line.quantity = 2
    line.requested_quantity = 2
    cast("Any", line).unit_price = Decimal("1000000")
    line.equipments = [{"price": 10000}]
    cast("Any", line).total_price = Decimal("2020000")
    await db_session.flush()
    result = await save_fulfillment(cmd, db_session)
    assert result["application_totals"]["total_amount"] == Decimal("3030000")
    assert result["application_totals"]["down_payment"] == Decimal("606000")
    assert result["application_totals"]["monthly_payment"] > 0
    assert result["calculation"]["total_cost"] == result["application_totals"]["total_cost"]
    assert result["requested_quantity"] == 2 and result["quantity"] == 3


async def test_concurrent_allocations_have_one_winner(_engine: AsyncEngine) -> None:
    import asyncio

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import AsyncSession

    from infrastructure.models.applications import ApplicationVehicleFulfillmentHistory
    from infrastructure.models.users import User

    uid = uuid4()
    async with AsyncSession(_engine, expire_on_commit=False) as session:
        actor = User(id=uid, phone=f"+7{str(uid.int)[0:10]}", role="carcraft_employee", is_active=True)
        session.add(actor)
        await session.flush()
        app, first, cars, _cmd = await seed(session, actor)
        second = ApplicationVehicle(application_id=app.id, quantity=4, unit_price=100, total_price=400)
        session.add(second)
        await session.flush()
        app_id, company_id = app.id, app.company_id
        line_ids, vehicle_ids = [first.id, second.id], [v.id for v in cars]
        await session.commit()
    async def attempt(line_id: UUID) -> bool:
        async with AsyncSession(_engine) as session:
            await repo.line(session, line_id, lock=True)
            locked = await repo.stock(session, [vehicle_ids[0]], lock=True)
            if locked[0]["status"] != "available":
                return False
            await repo.save(session, line_id=line_id, actor_id=uid, quantity=3,
                vehicle_ids=[vehicle_ids[0]], expires_at=datetime.now(UTC)+timedelta(days=1), comment=None)
            await session.commit()
            return True
    try:
        winners = await asyncio.gather(*(attempt(line_id) for line_id in line_ids))
        assert sorted(winners) == [False, True]
    finally:
        async with AsyncSession(_engine) as cleanup:
            for model in (ApplicationVehicleFulfillmentHistory, ApplicationVehicleAllocation):
                await cleanup.execute(delete(model).where(model.application_vehicle_id.in_(line_ids)))
            await cleanup.execute(delete(ApplicationVehicle).where(ApplicationVehicle.id.in_(line_ids)))
            await cleanup.execute(delete(LeasingApplication).where(LeasingApplication.id == app_id))
            await cleanup.execute(delete(Vehicle).where(Vehicle.id.in_(vehicle_ids)))
            await cleanup.execute(delete(Company).where(Company.id == company_id))
            await cleanup.execute(delete(User).where(User.id == uid))
            await cleanup.commit()


async def test_deal_completion_sells_selected_stock_and_rejection_does_not_release_it(db_session: AsyncSession, employee_user: User) -> None:
    from infrastructure.repositories import application_repository
    from infrastructure.repositories.vehicle_stock_status_repository import (
        enrich_stock_status,
    )
    app, _line, cars, cmd = await seed(db_session, employee_user)
    await save_fulfillment(replace(cmd, confirmed_quantity=1), db_session)
    await application_repository.update_application_status(db_session, app.id, new_status="issued")
    await db_session.refresh(cars[0])
    assert cars[0].status == "sold"
    active = await repo.allocations(db_session, cmd.application_vehicle_id, active_only=True)
    assert active[0]["completed_at"] is not None
    await application_repository.update_application_status(db_session, app.id, new_status="rejected")
    await db_session.refresh(cars[0])
    assert cars[0].status == "sold"
    rows: list[dict[str, Any]] = [{"id": cars[0].id}]
    await enrich_stock_status(db_session, rows)
    assert rows[0]["sale_completed"] is True and rows[0]["reserved_until"] is None


async def test_incomplete_fulfillment_cannot_complete_deal(db_session: AsyncSession, employee_user: User) -> None:
    from domain.errors import ApplicationVehicleAssignmentError
    from infrastructure.repositories import application_repository
    app, _line, cars, cmd = await seed(db_session, employee_user)
    await save_fulfillment(cmd, db_session)
    with pytest.raises(ApplicationVehicleAssignmentError, match="подберите все"):
        await application_repository.update_application_status(db_session, app.id, new_status="issued")
    await db_session.refresh(app)
    await db_session.refresh(cars[0])
    assert app.status == "active" and cars[0].status == "reserved"


async def test_legacy_reserved_vin_is_adopted_and_replaced_atomically(db_session: AsyncSession, employee_user: User) -> None:
    _app, line, cars, cmd = await seed(db_session, employee_user)
    line.vehicle_id = cars[0].id
    line.vin = cars[0].vin
    line.is_model_order = True
    cars[0].status = "reserved"
    await db_session.flush()
    before = await get_fulfillment(cmd, db_session)
    assert before["allocated_quantity"] == 1 and before["allocations"][0]["legacy"]
    from infrastructure.repositories.application_repository import (
        list_application_vehicles_with_catalog,
    )
    projection = (await list_application_vehicles_with_catalog(db_session, line.application_id))[0]
    assert projection["allocated_vehicle_ids"] == [cars[0].id]
    assert projection["allocated_vins"] == [cars[0].vin]
    assert projection["allocations"][0]["legacy"] is True
    assert projection["confirmed_quantity"] is None
    assert await repo.allocations(db_session, line.id) == []
    result = await save_fulfillment(replace(cmd, vehicle_ids=[cars[1].id], comment="Замена существующей брони"), db_session)
    assert len(result["allocations"]) == 2
    await db_session.refresh(cars[0])
    await db_session.refresh(cars[1])
    assert cars[0].status == "available" and cars[1].status == "reserved"


async def test_financing_requires_complete_and_keeps_reserved_stock_past_deadline(db_session: AsyncSession, employee_user: User) -> None:
    from infrastructure.models.applications import LeasingCompanyApplication
    from infrastructure.models.companies import LeasingCompany
    from infrastructure.repositories.application_vehicle_repository import (
        claim_expired_reservations,
    )
    app, _line, cars, cmd = await seed(db_session, employee_user)
    await save_fulfillment(cmd, db_session)
    with pytest.raises(ApplicationVehicleAssignmentError, match="Перед передачей"):
        await repo.require_complete_for_financing(db_session, app.id)
    await save_fulfillment(replace(cmd, version=1, confirmed_quantity=1), db_session)
    await repo.require_complete_for_financing(db_session, app.id)
    company = Company(name="LC", company_type="leasing_company", inn="1234567891")
    db_session.add(company)
    await db_session.flush()
    lc = LeasingCompany(company_id=company.id, is_active=True)
    db_session.add(lc)
    await db_session.flush()
    db_session.add(LeasingCompanyApplication(application_id=app.id, leasing_company_id=lc.id, status="submitted"))
    await db_session.flush()
    assert await claim_expired_reservations(db_session, (datetime.now(UTC)+timedelta(days=5)).date()) == []
    await db_session.refresh(cars[0])
    assert cars[0].status == "reserved"
    result = await get_fulfillment(cmd, db_session)
    assert result["reservation_fixed"] is True and result["editable"] is False


async def test_legacy_dealer_actions_cannot_bypass_managed_pick(db_session: AsyncSession, employee_user: User) -> None:
    from application.commands.application_vehicles.dealer_action import (
        DealerVehicleActionCommand,
        handle_dealer_vehicle_action,
    )
    _app, _line, _cars, cmd = await seed(db_session, employee_user)
    await save_fulfillment(cmd, db_session)
    for action in ("replace_vin", "reserve"):
        async with db_session.begin_nested() as savepoint:
            with pytest.raises((ApplicationVehicleAssignmentError, ApplicationVehicleFulfillmentRequiredError), match="подбор"):
                await handle_dealer_vehicle_action(DealerVehicleActionCommand(
                    application_vehicle_id=cmd.application_vehicle_id, actor_id=cmd.actor_id,
                    actor_role="carcraft_employee", actor_company_id=None,
                    action=cast("Any", action), vin="NEWVIN00000000001", reserve_expires_at=cmd.reserve_expires_at), db_session)
            await savepoint.rollback()


async def test_main_application_projection_contains_new_vin_and_preserves_price_anchor(db_session: AsyncSession, employee_user: User) -> None:
    from infrastructure.repositories.application_repository import (
        list_application_vehicles_with_catalog,
    )
    app, line, cars, cmd = await seed(db_session, employee_user)
    line.vehicle_id = cars[0].id
    line.vin = cars[0].vin
    await db_session.flush()
    await save_fulfillment(replace(cmd, vehicle_ids=[cars[1].id]), db_session)
    projection = (await list_application_vehicles_with_catalog(db_session, app.id))[0]
    assert projection["vehicle_id"] == cars[0].id
    assert projection["vin"] == projection["vehicle_vin"] == projection["assigned_vin"] == cars[1].vin
    assert projection["allocated_vehicle_ids"] == [cars[1].id]


def test_supplier_quantity_schema_rejects_postgres_integer_overflow() -> None:
    from pydantic import ValidationError

    from presentation.schemas.application_vehicles import FulfillmentRequest
    with pytest.raises(ValidationError):
        FulfillmentRequest(version=0, confirmed_quantity=2147483648,
            reserve_expires_at=datetime.now(UTC).date())


async def test_dwh_snapshot_serializes_reservation_date_before_publish(db_session: AsyncSession, employee_user: User, monkeypatch: pytest.MonkeyPatch) -> None:
    from application.commands.application_vehicles.fulfillment import (
        fulfillment_event_snapshot,
        publish_fulfillment_snapshot,
    )
    from infrastructure.messaging import dwh_events
    _app, _line, _cars, cmd = await seed(db_session, employee_user)
    await save_fulfillment(cmd, db_session)
    snapshot = await fulfillment_event_snapshot(cmd, db_session)
    assert cmd.reserve_expires_at is not None
    assert snapshot["line"]["reserve_expires_at"] == cmd.reserve_expires_at.isoformat()
    emitted: list[dict[str, Any]] = []
    monkeypatch.setattr(dwh_events, "emit_app_vehicle_changed", emitted.append)
    monkeypatch.setattr(dwh_events, "emit_leasing_application_changed", emitted.append)
    monkeypatch.setattr(dwh_events, "emit_vehicle_changed", emitted.append)
    publish_fulfillment_snapshot(snapshot)
    assert len(emitted) == 3


@pytest.mark.parametrize("action", ["reject", "replace"])
@pytest.mark.parametrize("phase", ["financing", "issued"])
async def test_managed_dealer_actions_cannot_release_fixed_or_purchased_stock(db_session: AsyncSession, employee_user: User, action: str, phase: str) -> None:
    from application.commands.application_vehicles.dealer_action import (
        DealerVehicleActionCommand,
        handle_dealer_vehicle_action,
    )
    from infrastructure.models.applications import LeasingCompanyApplication
    from infrastructure.models.companies import LeasingCompany
    from infrastructure.repositories import application_repository
    app, line, cars, cmd = await seed(db_session, employee_user)
    await save_fulfillment(replace(cmd, confirmed_quantity=1), db_session)
    if phase == "financing":
        company = Company(name="Fixed LC", company_type="leasing_company", inn="1234567892")
        db_session.add(company)
        await db_session.flush()
        lc = LeasingCompany(company_id=company.id, is_active=True)
        db_session.add(lc)
        await db_session.flush()
        db_session.add(LeasingCompanyApplication(application_id=app.id, leasing_company_id=lc.id, status="submitted"))
        await db_session.flush()
    else:
        await application_repository.update_application_status(db_session, app.id, new_status="issued")
    with pytest.raises(ServiceError) as error:
        await handle_dealer_vehicle_action(DealerVehicleActionCommand(
            application_vehicle_id=cmd.application_vehicle_id, actor_id=cmd.actor_id,
            actor_role="carcraft_employee", actor_company_id=None, action=cast("Any", action)), db_session)
    assert error.value.status_code == 409
    await db_session.refresh(cars[0])
    await db_session.refresh(line)
    assert cars[0].status == ("reserved" if phase == "financing" else "sold")
    assert line.car_status == "confirmed" and line.fulfillment_version == 1
    assert len(await repo.allocations(db_session, line.id, active_only=True)) == 1


async def test_nonanchor_allocation_blocks_delete_preflight_and_warehouse_unlink(db_session: AsyncSession, employee_user: User) -> None:
    from application.commands.vehicles.admin_deletion import (
        VehicleDeletionError,
        handle_admin_delete_vehicle,
        handle_unbind_all_warehouse_vehicles,
    )
    from infrastructure.models.vehicles import Warehouse
    from infrastructure.repositories import vehicle_deletion_repository as deletion
    from infrastructure.repositories import warehouse_repository as warehouses
    _app, _line, cars, cmd = await seed(db_session, employee_user)
    await save_fulfillment(cmd, db_session)
    warehouse = Warehouse(address="Reserved vehicle test", brand="Test")
    db_session.add(warehouse)
    await db_session.flush()
    db_session.add(VehicleWarehouse(vehicle_id=cars[0].id, warehouse_id=warehouse.id))
    await db_session.flush()
    reasons = (await deletion.blocking_reasons(db_session, [cars[0].id]))[cars[0].id]
    assert {reason["type"] for reason in reasons} == {"application_vehicle_allocations"}
    with pytest.raises(VehicleDeletionError) as error:
        await handle_admin_delete_vehicle(db_session, cars[0].id, "УДАЛИТЬ")
    assert error.value.status_code == 409
    assert error.value.blocking_reasons == reasons
    with pytest.raises(ApplicationVehicleAssignmentError, match="отвязать"):
        await warehouses.delete_binding(db_session, warehouse_id=warehouse.id, vehicle_id=cars[0].id)
    with pytest.raises(VehicleDeletionError, match="отвязать"):
        await handle_unbind_all_warehouse_vehicles(db_session, warehouse.id, True)
    assert await warehouses.get_binding(db_session, cars[0].id) is not None
    await repo.release_line(db_session, cmd.application_vehicle_id, reason="Отмена")
    assert (await deletion.blocking_reasons(db_session, [cars[0].id]))[cars[0].id][0]["type"] == "application_vehicle_allocations"
    assert await warehouses.delete_binding(db_session, warehouse_id=warehouse.id, vehicle_id=cars[0].id)
