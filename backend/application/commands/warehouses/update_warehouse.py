"""Update warehouse command."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.warehouses.status_events import (
    WarehouseMutationResult,
    WarehouseStatusEvent,
)
from application.commands.warehouses.validate_form import (
    validate_warehouse_form_selection,
)
from domain.errors import (
    CityNotFoundError,
    CompanyNotFoundError,
    InvalidWarehouseError,
    WarehouseNotFoundError,
)
from domain.values import WarehouseStatus
from infrastructure.repositories import warehouse_repository as repo
from infrastructure.repositories.special_equipment_management_repository import (
    lock_catalog_for_mutation,
)


@dataclass
class UpdateWarehouseCommand:
    warehouse_id: UUID
    name: str | None = None
    owner_company_id: UUID | None = None
    owner_company_type: str | None = None
    address: str | None = None
    brand_ids: list[UUID] = field(default_factory=list)
    category_id: UUID | None = None
    city_id: UUID | None = None
    is_active: bool | None = None
    update_city: bool = False
    update_brands: bool = False
    update_category: bool = False
    update_owner_company: bool = False
    actor_role: str | None = None
    actor_company_ids: list[UUID] | None = None
    # Backward compatibility
    brand: str | None = None
    dealer_id: UUID | None = None
    company_id: UUID | None = None
    status: WarehouseStatus | None = None
    update_dealer: bool = False
    update_company: bool = False


def _check_permissions(cmd: UpdateWarehouseCommand, existing: dict[str, Any]) -> None:
    if cmd.actor_role == "carcraft_employee" or cmd.actor_company_ids is None:
        return
    existing_owner = existing.get("owner_company_id")
    if existing_owner is None or UUID(str(existing_owner)) not in cmd.actor_company_ids:
        raise InvalidWarehouseError("У вас нет прав на редактирование этого склада")
    if (
        cmd.update_owner_company
        and cmd.owner_company_id is not None
        and cmd.owner_company_id not in cmd.actor_company_ids
    ):
        raise InvalidWarehouseError("Вы можете передавать склад только своей компании")


async def _validate_payload(
    cmd: UpdateWarehouseCommand,
    session: AsyncSession,
    new_owner: UUID | None,
) -> None:
    if cmd.name is not None:
        name = cmd.name.strip()
        if not name or len(name) > 255:
            raise InvalidWarehouseError("Название склада обязательно и не должно превышать 255 символов")

    if cmd.address is not None:
        address = cmd.address.strip()
        if not address or len(address) > 500:
            raise InvalidWarehouseError("Адрес склада обязателен и не должен превышать 500 символов")

    if cmd.update_city and cmd.city_id is not None and not await repo.city_exists(session, cmd.city_id):
        raise CityNotFoundError(cmd.city_id)


    if (
        (cmd.update_owner_company or cmd.update_company or cmd.update_dealer)
        and new_owner is not None
        and not await repo.company_exists(
            session, new_owner, allowed_types=("dealer", "distributor")
        )
    ):
        raise CompanyNotFoundError(str(new_owner))


def _build_status_events(
    warehouse_id: UUID,
    existing: dict[str, Any],
    eff_is_active: bool | None,
    new_owner: UUID | None,
) -> list[WarehouseStatusEvent]:
    events: list[WarehouseStatusEvent] = []
    if eff_is_active is not None and existing.get("is_active") != eff_is_active:
        events.append(
            {
                "warehouse_id": warehouse_id,
                "old_status": "active" if existing.get("is_active") else "inactive",
                "new_status": "active" if eff_is_active else "inactive",
                "company_id": new_owner or (UUID(str(existing["owner_company_id"])) if existing.get("owner_company_id") else None),
            }
        )
    if new_owner is not None and existing.get("owner_company_id") != str(new_owner):
        events.append(
            {
                "warehouse_id": warehouse_id,
                "old_status": "active" if existing.get("is_active") else "inactive",
                "new_status": "active" if (eff_is_active if eff_is_active is not None else existing.get("is_active")) else "inactive",
                "company_id": new_owner,
                "payload": {
                    "company_id_changed": {
                        "old": existing.get("owner_company_id"),
                        "new": str(new_owner),
                    }
                },
            }
        )
    return events


async def handle_update_warehouse(
    cmd: UpdateWarehouseCommand, session: AsyncSession
) -> WarehouseMutationResult:
    await lock_catalog_for_mutation(session)
    await repo.lock_warehouse_for_update(session, cmd.warehouse_id)
    existing = await repo.get_by_id(session, cmd.warehouse_id, is_admin=True)
    if existing is None:
        raise WarehouseNotFoundError(cmd.warehouse_id)

    _check_permissions(cmd, existing)

    new_owner = cmd.owner_company_id if cmd.update_owner_company else (
        cmd.company_id if cmd.update_company else (cmd.dealer_id if cmd.update_dealer else None)
    )
    await _validate_payload(cmd, session, new_owner)
    if cmd.update_brands or cmd.update_category:
        brand_ids = cmd.brand_ids if cmd.update_brands else [UUID(str(value)) for value in existing["brand_ids"]]
        category_id = cmd.category_id if cmd.update_category else existing["category_id"]
        await validate_warehouse_form_selection(session, brand_ids, category_id)

    eff_is_active = cmd.is_active
    if eff_is_active is None and cmd.status is not None:
        eff_is_active = (cmd.status == WarehouseStatus.ACTIVE)

    await repo.update_warehouse(
        session,
        cmd.warehouse_id,
        name=cmd.name.strip() if cmd.name is not None else None,
        address=cmd.address.strip() if cmd.address is not None else None,
        city_id=cmd.city_id if cmd.update_city else None,
        brand_ids=cmd.brand_ids,
        category_id=cmd.category_id,
        owner_company_id=new_owner,
        owner_company_type=cmd.owner_company_type,
        is_active=eff_is_active,
        update_city=cmd.update_city,
        update_brands=cmd.update_brands,
        update_category=cmd.update_category,
        update_owner_company=(cmd.update_owner_company or cmd.update_company or cmd.update_dealer),
    )

    events = _build_status_events(cmd.warehouse_id, existing, eff_is_active, new_owner)
    saved = await repo.get_by_id(session, cmd.warehouse_id, is_admin=True)
    assert saved is not None
    return {"warehouse": saved, "status_events": events}
