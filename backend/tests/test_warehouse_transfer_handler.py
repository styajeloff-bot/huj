"""Regression tests for warehouse vehicle transfer history and scoped queries."""
from __future__ import annotations

from typing import cast

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.warehouse_transfers import (
    TransferVehiclesCommand,
    handle_transfer_vehicles,
)
from application.queries.warehouse_transfers import (
    ListAvailableWarehousesQuery,
    ListSourceVehiclesQuery,
    handle_list_available_warehouses,
    handle_list_source_vehicles,
)
from infrastructure.models.companies import Company, DistributorDealerLink
from infrastructure.models.users import User
from infrastructure.models.vehicles import (
    VehicleWarehouseTransfer,
    Warehouse,
)
from tests.legacy_compat import Vehicle, VehicleWarehouse


def test_vehicle_warehouse_transfer_keeps_auditable_references() -> None:
    """History must preserve a transfer without cascading warehouse deletion."""
    table = cast("sa.Table", VehicleWarehouseTransfer.__table__)

    assert table.name == "vehicle_warehouse_transfers"
    assert table.c.vehicle_id.nullable is False
    assert table.c.source_warehouse_id.nullable is False
    assert table.c.destination_warehouse_id.nullable is False
    assert table.c.actor_user_id.nullable is True
    assert table.c.created_at.server_default is not None

    foreign_keys = {fk.parent.name: fk.ondelete for fk in table.foreign_keys}
    assert foreign_keys["vehicle_id"] != "CASCADE"
    assert foreign_keys["source_warehouse_id"] != "CASCADE"
    assert foreign_keys["destination_warehouse_id"] != "CASCADE"
    assert foreign_keys["actor_user_id"] == "SET NULL"

    checks = [
        constraint.sqltext
        for constraint in table.constraints
        if isinstance(constraint, sa.CheckConstraint)
    ]
    assert any(
        "source_warehouse_id" in str(check)
        and "destination_warehouse_id" in str(check)
        for check in checks
    )


@pytest.mark.asyncio
async def test_distributor_sees_only_linked_legacy_warehouse_and_source_vehicle(
    db_session: AsyncSession,
) -> None:
    distributor_company = Company(
        name="Transfer distributor",
        company_type="distributor",
        is_active=True,
    )
    linked_dealer = Company(
        name="Transfer linked dealer",
        company_type="dealer",
        is_active=True,
    )
    foreign_dealer = Company(
        name="Transfer foreign dealer",
        company_type="dealer",
        is_active=True,
    )
    db_session.add_all([distributor_company, linked_dealer, foreign_dealer])
    await db_session.flush()

    distributor_user = User(
        phone="+766****4455",
        email="transfer-distributor@test.local",
        name="Transfer distributor user",
        role="distributor",
        is_active=True,
        company_id=distributor_company.id,
    )
    db_session.add_all(
        [
            distributor_user,
            DistributorDealerLink(
                distributor_company_id=distributor_company.id,
                dealer_company_id=linked_dealer.id,
            ),
        ]
    )
    await db_session.flush()

    source = Warehouse(
        address="Linked legacy source",
        brand="BMW",
        company_id=linked_dealer.id,
    )
    other_linked_warehouse = Warehouse(
        address="Linked dealer warehouse",
        brand="BMW",
        dealer_id=linked_dealer.id,
    )
    foreign_warehouse = Warehouse(
        address="Foreign warehouse",
        brand="BMW",
        dealer_id=foreign_dealer.id,
    )
    db_session.add_all([source, other_linked_warehouse, foreign_warehouse])
    await db_session.flush()

    in_scope_source_vehicle = Vehicle(
        vin="TRANSFER_SCOPE_OK",
        dealer_id=linked_dealer.id,
        year=2025,
        color="Белый",
        status="available",
        is_available=True,
    )
    foreign_vehicle_in_same_source = Vehicle(
        vin="SCOPE_FOREIGN",
        dealer_id=foreign_dealer.id,
        status="available",
        is_available=True,
    )
    linked_vehicle_in_other_source = Vehicle(
        vin="SCOPE_OTHER_WH",
        dealer_id=linked_dealer.id,
        status="available",
        is_available=True,
    )
    db_session.add_all(
        [
            in_scope_source_vehicle,
            foreign_vehicle_in_same_source,
            linked_vehicle_in_other_source,
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            VehicleWarehouse(
                vehicle_id=in_scope_source_vehicle.id,
                warehouse_id=source.id,
            ),
            VehicleWarehouse(
                vehicle_id=foreign_vehicle_in_same_source.id,
                warehouse_id=source.id,
            ),
            VehicleWarehouse(
                vehicle_id=linked_vehicle_in_other_source.id,
                warehouse_id=other_linked_warehouse.id,
            ),
        ]
    )
    await db_session.flush()

    warehouses = await handle_list_available_warehouses(
        ListAvailableWarehousesQuery(
            actor_id=distributor_user.id,
            actor_role="distributor",
            company_id=distributor_company.id,
        ),
        db_session,
    )
    assert {item["id"] for item in warehouses["warehouses"]} == {
        source.id,
        other_linked_warehouse.id,
    }

    result = await handle_list_source_vehicles(
        ListSourceVehiclesQuery(
            actor_id=distributor_user.id,
            actor_role="distributor",
            company_id=distributor_company.id,
            source_warehouse_id=source.id,
            page=1,
            limit=20,
        ),
        db_session,
    )

    assert result["pagination"] == {"page": 1, "limit": 20, "total": 1, "pages": 1}
    assert [item["id"] for item in result["vehicles"]] == [in_scope_source_vehicle.id]

    filtered = await handle_list_source_vehicles(
        ListSourceVehiclesQuery(
            actor_id=distributor_user.id,
            actor_role="distributor",
            company_id=distributor_company.id,
            source_warehouse_id=source.id,
            page=1,
            limit=20,
            vin="SCOPE",
            years=[2025],
            colors=["Белый"],
        ),
        db_session,
    )
    assert [item["id"] for item in filtered["vehicles"]] == [
        in_scope_source_vehicle.id
    ]
    assert filtered["facets"]["years"] == [2025]
    assert filtered["facets"]["colors"] == ["Белый"]


@pytest.mark.asyncio
async def test_transfer_updates_binding_and_appends_one_audit_record(
    db_session: AsyncSession,
) -> None:
    actor = User(
        phone="+7660001000",
        email="transfer-employee@test.local",
        name="Transfer employee",
        role="carcraft_employee",
        is_active=True,
    )
    source = Warehouse(address="Transfer source", brand="BMW")
    destination = Warehouse(address="Transfer destination", brand="BMW")
    vehicle = Vehicle(
        vin="TRANSFER_OK",
        status="available",
        is_available=True,
    )
    db_session.add_all([actor, source, destination, vehicle])
    await db_session.flush()
    db_session.add(VehicleWarehouse(vehicle_id=vehicle.id, warehouse_id=source.id))
    await db_session.flush()

    result = await handle_transfer_vehicles(
        TransferVehiclesCommand(
            actor_id=actor.id,
            actor_role="carcraft_employee",
            source_warehouse_id=source.id,
            destination_warehouse_id=destination.id,
            vehicle_ids=[vehicle.id],
        ),
        db_session,
    )

    assert result["transferred_count"] == 1
    assert result["failed_count"] == 0
    binding = await db_session.scalar(
        sa.select(VehicleWarehouse).where(VehicleWarehouse.vehicle_id == vehicle.id)
    )
    assert binding is not None
    assert binding.warehouse_id == destination.id
    history = (
        await db_session.scalars(
            sa.select(VehicleWarehouseTransfer).where(
                VehicleWarehouseTransfer.vehicle_id == vehicle.id
            )
        )
    ).all()
    assert len(history) == 1
    assert history[0].source_warehouse_id == source.id
    assert history[0].destination_warehouse_id == destination.id
    assert history[0].actor_user_id == actor.id

    all_filtered_vehicle = Vehicle(
        vin="TRANSFER_ALL",
        status="available",
        is_available=True,
    )
    db_session.add(all_filtered_vehicle)
    await db_session.flush()
    db_session.add(
        VehicleWarehouse(
            vehicle_id=all_filtered_vehicle.id,
            warehouse_id=source.id,
        )
    )
    await db_session.flush()

    all_filtered_result = await handle_transfer_vehicles(
        TransferVehiclesCommand(
            actor_id=actor.id,
            actor_role="carcraft_employee",
            source_warehouse_id=source.id,
            destination_warehouse_id=destination.id,
            vehicle_ids=[],
            all_filtered=True,
        ),
        db_session,
    )
    assert all_filtered_result["transferred_count"] == 1
    all_filtered_binding = await db_session.scalar(
        sa.select(VehicleWarehouse).where(
            VehicleWarehouse.vehicle_id == all_filtered_vehicle.id
        )
    )
    assert all_filtered_binding is not None
    assert all_filtered_binding.warehouse_id == destination.id


@pytest.mark.asyncio
async def test_distributor_without_dealers_cannot_transfer_explicit_vehicle_id(
    db_session: AsyncSession,
) -> None:
    distributor = Company(
        name="Unlinked transfer distributor",
        company_type="distributor",
        is_active=True,
    )
    actor = User(
        phone="+7660002000",
        email="unlinked-transfer@test.local",
        name="Unlinked distributor",
        role="distributor",
        is_active=True,
        company_id=distributor.id,
    )
    source = Warehouse(address="Foreign source", brand="BMW")
    destination = Warehouse(address="Foreign destination", brand="BMW")
    vehicle = Vehicle(vin="FOREIGN_MOVE", status="available", is_available=True)
    db_session.add_all([distributor, actor, source, destination, vehicle])
    await db_session.flush()
    db_session.add(VehicleWarehouse(vehicle_id=vehicle.id, warehouse_id=source.id))
    await db_session.flush()

    result = await handle_transfer_vehicles(
        TransferVehiclesCommand(
            actor_id=actor.id,
            actor_role="distributor",
            company_id=distributor.id,
            source_warehouse_id=source.id,
            destination_warehouse_id=destination.id,
            vehicle_ids=[vehicle.id],
        ),
        db_session,
    )

    assert result["transferred_count"] == 0
    assert result["results"] == [{"vehicle_id": vehicle.id, "status": "unavailable"}]
    binding = await db_session.scalar(
        sa.select(VehicleWarehouse).where(VehicleWarehouse.vehicle_id == vehicle.id)
    )
    assert binding is not None
    assert binding.warehouse_id == source.id
