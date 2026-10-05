"""Create warehouse command."""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.warehouses.status_events import WarehouseMutationResult
from application.commands.warehouses.validate_form import (
    validate_warehouse_form_selection,
)
from domain.entities.warehouse import Warehouse
from domain.errors import (
    CityNotFoundError,
    CompanyNotFoundError,
    InvalidWarehouseError,
)
from infrastructure.repositories import warehouse_repository as repo
from infrastructure.repositories.special_equipment_management_repository import (
    lock_catalog_for_mutation,
)


@dataclass
class CreateWarehouseCommand:
    name: str = ""
    owner_company_id: UUID | None = None
    owner_company_type: str = "dealer"
    address: str = ""
    city_id: UUID | None = None
    brand_ids: list[UUID] = field(default_factory=list)
    category_id: UUID | None = None
    is_active: bool = True
    actor_role: str | None = None
    actor_company_ids: list[UUID] | None = None
    # Backward compatibility
    brand: str | None = None
    dealer_id: UUID | None = None
    company_id: UUID | None = None


async def handle_create_warehouse(
    cmd: CreateWarehouseCommand, session: AsyncSession
) -> WarehouseMutationResult:
    await lock_catalog_for_mutation(session)
    eff_owner_id = cmd.owner_company_id or cmd.company_id or cmd.dealer_id
    if eff_owner_id is None:
        raise InvalidWarehouseError("Компания-владелец склада обязательна")

    # Role validation: non-admin can only create warehouse for their own company
    if (
        cmd.actor_role != "carcraft_employee"
        and cmd.actor_company_ids is not None
        and eff_owner_id not in cmd.actor_company_ids
    ):
        raise InvalidWarehouseError("Вы можете создавать склады только для своих компаний")

    eff_name = (cmd.name or "").strip()
    if not eff_name:
        if cmd.brand:
            eff_name = f"Склад {cmd.brand}"
        elif cmd.address:
            eff_name = f"Склад {cmd.address.strip()[:30]}"
        else:
            eff_name = "Склад"

    await validate_warehouse_form_selection(session, cmd.brand_ids, cmd.category_id)

    warehouse = Warehouse(
        warehouse_id=None,
        name=eff_name,
        owner_company_id=eff_owner_id,
        owner_company_type=cmd.owner_company_type,
        address=cmd.address,
        city_id=cmd.city_id,
        brand_ids=cmd.brand_ids,
        category_id=cmd.category_id,
        is_active=cmd.is_active,
    )
    warehouse.ensure_valid()

    if warehouse.city_id is not None and not await repo.city_exists(
        session, warehouse.city_id
    ):
        raise CityNotFoundError(warehouse.city_id)

    if not await repo.company_exists(
        session, warehouse.owner_company_id, allowed_types=("dealer", "distributor")
    ):
        raise CompanyNotFoundError(str(warehouse.owner_company_id))

    warehouse_id = await repo.create_warehouse(
        session,
        name=warehouse.name,
        owner_company_id=warehouse.owner_company_id,
        owner_company_type=warehouse.owner_company_type,
        address=warehouse.address,
        city_id=warehouse.city_id,
        brand_ids=warehouse.brand_ids,
        category_id=warehouse.category_id,
        is_active=warehouse.is_active,
    )
    saved = await repo.get_by_id(session, warehouse_id, is_admin=True)
    assert saved is not None
    return {
        "warehouse": saved,
        "status_events": [{
            "warehouse_id": warehouse_id,
            "old_status": None,
            "new_status": "active" if warehouse.is_active else "inactive",
            "company_id": warehouse.owner_company_id,
            "payload": {"address": warehouse.address, "name": warehouse.name},
        }],
    }

