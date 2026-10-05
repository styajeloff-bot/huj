"""Locked persistence and batched reads for quantity-based dealer assignments."""

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    ApplicationDealerDistributionRequest,
    ApplicationVehicle,
    ApplicationVehicleDealerDistribution,
    LeasingApplication,
)
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.vehicles import Warehouse


async def lock_application(session: AsyncSession, application_id: UUID) -> bool:
    result = await session.scalar(
        sa.select(LeasingApplication.id)
        .where(LeasingApplication.id == application_id)
        .with_for_update()
    )
    return result is not None


async def distributor_is_active(session: AsyncSession, company_id: UUID) -> bool:
    return bool(
        await session.scalar(
            sa.select(
                sa.exists().where(
                    Company.id == company_id,
                    Company.company_type == "distributor",
                    Company.is_active.is_(True),
                )
            )
        )
    )


async def get_request(
    session: AsyncSession,
    *,
    application_id: UUID,
    company_id: UUID,
    request_id: UUID,
) -> dict[str, Any] | None:
    row = await session.scalar(
        sa.select(ApplicationDealerDistributionRequest).where(
            ApplicationDealerDistributionRequest.application_id == application_id,
            ApplicationDealerDistributionRequest.distributor_company_id == company_id,
            ApplicationDealerDistributionRequest.client_request_id == request_id,
        )
    )
    if row is None:
        return None
    ids = list(
        (
            await session.scalars(
                sa.select(ApplicationVehicleDealerDistribution.application_vehicle_id)
                .where(
                    ApplicationVehicleDealerDistribution.request_id == row.id,
                )
                .order_by(ApplicationVehicleDealerDistribution.application_vehicle_id)
            )
        ).all()
    )
    return {"payload_hash": row.payload_hash, "application_vehicle_ids": ids}


async def lock_distribution_lines(
    session: AsyncSession,
    *,
    application_id: UUID,
    application_vehicle_ids: list[UUID],
) -> dict[UUID, dict[str, Any]]:
    rows = list(
        (
            await session.scalars(
                sa.select(ApplicationVehicle)
                .where(
                    ApplicationVehicle.application_id == application_id,
                    ApplicationVehicle.id.in_(application_vehicle_ids),
                )
                .order_by(ApplicationVehicle.id)
                .with_for_update()
            )
        ).all()
    )
    product_ids = sorted({row.product_id for row in rows if row.product_id is not None})
    # Transfers lock inventory items too; preserve that ownership while assigning.
    await session.execute(
        sa.select(SpecialEquipmentProduct.id)
        .where(SpecialEquipmentProduct.id.in_(product_ids))
        .order_by(SpecialEquipmentProduct.id)
        .with_for_update()
    )
    links = list(
        (
            await session.execute(
                sa.select(SpecialEquipmentProduct.id, SpecialEquipmentProduct.warehouse_id)
                .where(SpecialEquipmentProduct.id.in_(product_ids), SpecialEquipmentProduct.warehouse_id.is_not(None))
                .order_by(SpecialEquipmentProduct.id)
                .with_for_update()
            )
        ).all()
    )
    warehouse_ids = sorted({row.warehouse_id for row in links if row.warehouse_id is not None})
    warehouses = list(
        (
            await session.scalars(
                sa.select(Warehouse)
                .where(Warehouse.id.in_(warehouse_ids))
                .order_by(Warehouse.id)
                .with_for_update()
            )
        ).all()
    )
    owner_by_warehouse = {row.id: row.company_id for row in warehouses}
    owners_by_vehicle: dict[UUID, set[UUID | None]] = {}
    for link in links:
        owners_by_vehicle.setdefault(link.id, set()).add(
            owner_by_warehouse.get(link.warehouse_id)
        )
    legacy_ids = {
        row.dealer_company_id for row in rows if row.dealer_company_id is not None
    }
    legacy_dealers = set(
        (
            await session.scalars(
                sa.select(Company.id).where(
                    Company.id.in_(legacy_ids),
                    Company.company_type == "dealer",
                )
            )
        ).all()
    )
    total_rows = (
        await session.execute(
            sa.select(
                ApplicationVehicleDealerDistribution.application_vehicle_id,
                sa.func.sum(ApplicationVehicleDealerDistribution.quantity),
            )
            .where(
                ApplicationVehicleDealerDistribution.application_vehicle_id.in_(
                    application_vehicle_ids
                )
            )
            .group_by(ApplicationVehicleDealerDistribution.application_vehicle_id)
        )
    ).all()
    totals = {row[0]: row[1] for row in total_rows}
    result = {}
    for row in rows:
        owners = (
            owners_by_vehicle.get(row.product_id, set()) if row.product_id else set()
        )
        result[row.id] = {
            "quantity": row.quantity,
            "stock_owner_id": next(iter(owners)) if len(owners) == 1 else None,
            "legacy_dealer_assigned": row.dealer_company_id in legacy_dealers,
            "distributed_quantity": int(totals.get(row.id, 0)),
            "status": row.car_status,
        }
    return result


async def save_distribution(
    session: AsyncSession,
    *,
    application_id: UUID,
    company_id: UUID,
    actor_id: UUID,
    request_id: UUID,
    payload_hash: str,
    dealer_id: UUID,
    items: list[tuple[UUID, int]],
) -> None:
    request = ApplicationDealerDistributionRequest(
        application_id=application_id,
        distributor_company_id=company_id,
        actor_id=actor_id,
        client_request_id=request_id,
        payload_hash=payload_hash,
    )
    session.add(request)
    await session.flush()
    session.add_all(
        [
            ApplicationVehicleDealerDistribution(
                application_vehicle_id=line_id,
                dealer_company_id=dealer_id,
                quantity=quantity,
                request_id=request.id,
            )
            for line_id, quantity in items
        ]
    )
    await session.flush()


async def list_distributions(
    session: AsyncSession,
    application_vehicle_ids: list[UUID],
) -> dict[UUID, list[dict[str, Any]]]:
    if not application_vehicle_ids:
        return {}
    rows = (
        await session.execute(
            sa.select(
                ApplicationVehicleDealerDistribution.application_vehicle_id,
                Company.id.label("dealer_id"),
                Company.name,
                Company.inn,
                sa.func.sum(ApplicationVehicleDealerDistribution.quantity).label(
                    "quantity"
                ),
            )
            .join(
                Company,
                Company.id == ApplicationVehicleDealerDistribution.dealer_company_id,
            )
            .where(
                ApplicationVehicleDealerDistribution.application_vehicle_id.in_(
                    application_vehicle_ids
                )
            )
            .group_by(
                ApplicationVehicleDealerDistribution.application_vehicle_id,
                Company.id,
                Company.name,
                Company.inn,
            )
            .order_by(
                ApplicationVehicleDealerDistribution.application_vehicle_id,
                Company.name,
                Company.id,
            )
        )
    ).all()
    result: dict[UUID, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(row.application_vehicle_id, []).append(
            {
                "dealer": {"id": row.dealer_id, "name": row.name, "inn": row.inn},
                "quantity": int(row.quantity),
            }
        )
    return result
