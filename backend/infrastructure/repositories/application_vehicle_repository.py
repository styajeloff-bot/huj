"""ApplicationVehicle repository — admin scope, async, dict-only API.

Covers VIN / vehicle assignment workflow on `application_vehicles` rows.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    ApplicationVehicle,
    ApplicationVehicleDealerActionDocument,
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
)
from infrastructure.repositories.questionnaire_purpose_repository import (
    sync_vehicle_purchase_purpose,
)
from infrastructure.repository_timing import timed_repository


def _doc_to_dict(row: ApplicationVehicleDealerActionDocument) -> dict[str, Any]:
    return {
        "id": row.id,
        "application_vehicle_id": row.application_vehicle_id,
        "action": row.action,
        "file_url": row.file_url,
        "file_key": row.file_key,
        "file_name": row.file_name,
        "file_type": row.file_type,
        "uploaded_by": row.uploaded_by,
        "created_at": row.created_at,
    }


async def _list_dealer_action_documents(
    session: AsyncSession, application_vehicle_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(ApplicationVehicleDealerActionDocument)
        .where(
            ApplicationVehicleDealerActionDocument.application_vehicle_id
            == application_vehicle_id
        )
        .order_by(ApplicationVehicleDealerActionDocument.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_doc_to_dict(row) for row in rows]


def _row_to_dict(
    row: ApplicationVehicle,
    *,
    dealer_action_documents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    prod_id = getattr(row, "product_id", getattr(row, "vehicle_id", None))
    return {
        "id": row.id,
        "application_id": row.application_id,
        "product_id": prod_id,
        "vehicle_id": prod_id,
        "modification_id": row.modification_id,
        "quantity": row.quantity,
        "requested_quantity": row.requested_quantity,
        "confirmed_quantity": row.confirmed_quantity,
        "fulfillment_version": row.fulfillment_version,
        "equipments": row.equipments or [],
        "services": row.services or [],
        "unit_price": row.unit_price,
        "total_price": row.total_price,
        "comment": row.comment,
        "status": row.car_status,
        "car_status": row.car_status,
        "dealer_comment": row.dealer_comment,
        "reserve_expires_at": row.reserve_expires_at,
        "discount_type": row.discount_type,
        "discount_value": row.discount_value,
        "discount_show_catalog_price": row.discount_show_catalog_price,
        "markup_type": row.markup_type,
        "markup_value": row.markup_value,
        "markup_show_catalog_price": row.markup_show_catalog_price,
        "final_price": row.final_price,
        "show_catalog_price": (
            row.discount_show_catalog_price
            and row.markup_show_catalog_price
        ),
        "vin": row.vin,
        "vin_assigned_by": row.vin_assigned_by,
        "vin_assigned_at": row.vin_assigned_at,
        "is_model_order": row.is_model_order,
        "created_at": row.created_at,
        "dealer_action_documents": dealer_action_documents or [],
    }


def _apply_catalog_price_visibility(
    row: ApplicationVehicle,
    *,
    discount: bool | None,
    markup: bool | None,
) -> None:
    if discount is not None:
        row.discount_show_catalog_price = discount
    if markup is not None:
        row.markup_show_catalog_price = markup


@timed_repository
async def get_by_id(
    session: AsyncSession, application_vehicle_id: UUID
) -> dict[str, Any] | None:
    row = await session.get(ApplicationVehicle, application_vehicle_id)
    if row is None:
        return None
    docs = await _list_dealer_action_documents(session, application_vehicle_id)
    return _row_to_dict(row, dealer_action_documents=docs)


@timed_repository
async def claim_expired_reservations(
    session: AsyncSession, before_date: date, *, limit: int = 100,
) -> list[dict[str, Any]]:
    """Claim parent then vehicle, exactly like interactive business commands.

    Candidate lookup deliberately has no locks. Every condition is rechecked
    after acquiring the locks; concurrent sweep/interactive work is skipped.
    """
    candidates = (await session.execute(
        select(ApplicationVehicle.id, ApplicationVehicle.application_id)
        .join(LeasingApplication, LeasingApplication.id == ApplicationVehicle.application_id)
        .where(
            LeasingApplication.status == "active",
            ApplicationVehicle.car_status == "confirmed",
            ApplicationVehicle.reserve_expires_at < before_date,
            ~select(LeasingCompanyApplication.id).where(
                LeasingCompanyApplication.application_id == ApplicationVehicle.application_id,
                ApplicationVehicle.fulfillment_version > 0,
            ).exists(),
        )
        .order_by(ApplicationVehicle.reserve_expires_at, ApplicationVehicle.id)
        .limit(limit)
    )).all()
    claimed: list[dict[str, Any]] = []
    for candidate in candidates:
        parent = await session.scalar(select(LeasingApplication).where(
            LeasingApplication.id == candidate.application_id,
            LeasingApplication.status == "active",
        ).with_for_update(skip_locked=True).execution_options(populate_existing=True))
        if parent is None:
            continue
        row = await session.scalar(select(ApplicationVehicle).where(
            ApplicationVehicle.id == candidate.id,
            ApplicationVehicle.car_status == "confirmed",
            ApplicationVehicle.reserve_expires_at < before_date,
            ~select(LeasingCompanyApplication.id).where(
                LeasingCompanyApplication.application_id == ApplicationVehicle.application_id,
                ApplicationVehicle.fulfillment_version > 0,
            ).exists(),
        ).with_for_update(skip_locked=True).execution_options(populate_existing=True))
        if row is not None:
            claimed.append({**_row_to_dict(row), "application_status": parent.status,
                            "display_number": parent.display_number})
    return claimed


@timed_repository
async def release_expired_reservation(
    session: AsyncSession, application_vehicle_id: UUID,
) -> None:
    """Called for a locked due row after the domain expiry guard succeeds."""
    row = await session.get(ApplicationVehicle, application_vehicle_id)
    if row is None:
        raise ValueError("Locked reservation no longer exists")
    from infrastructure.repositories import (
        vehicle_fulfillment_repository as fulfillment,
    )
    await fulfillment.release_line(session, application_vehicle_id, reason="Истёк срок бронирования")
    row.car_status = "active"
    row.reserve_expires_at = None
    await session.flush()
    await sync_vehicle_purchase_purpose(session, row.application_id)


@timed_repository
async def get_pricing_context(
    session: AsyncSession, application_vehicle_id: UUID
) -> dict[str, Any] | None:
    """Load the persisted catalog base and existing independent corrections."""
    prod_col = getattr(ApplicationVehicle, "product_id", getattr(ApplicationVehicle, "vehicle_id", None))
    stmt = (
        select(
            ApplicationVehicle,
            func.coalesce(
                func.nullif(ApplicationVehicle.unit_price, 0),
                SpecialEquipmentProduct.price,
                0,
            ).label("catalog_unit_price"),
        )
        .select_from(ApplicationVehicle)
        .outerjoin(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == prod_col,
        )
        .where(ApplicationVehicle.id == application_vehicle_id)
    )
    result = (await session.execute(stmt)).first()
    if result is None:
        return None
    row = result.ApplicationVehicle
    return {
        **_row_to_dict(row),
        "catalog_unit_price": result.catalog_unit_price,
        "equipments": row.equipments or [],
        "services": row.services or [],
    }


@timed_repository
async def lock_parent_application(session: AsyncSession, application_vehicle_id: UUID) -> None:
    """Same parent-first lock order as LC decisions and the deadline sweep."""
    await session.execute(
        select(LeasingApplication.id)
        .join(ApplicationVehicle, ApplicationVehicle.application_id == LeasingApplication.id)
        .where(ApplicationVehicle.id == application_vehicle_id)
        .with_for_update(of=LeasingApplication)
    )


@timed_repository
async def update_vehicle_ref(
    session: AsyncSession,
    application_vehicle_id: UUID,
    *,
    vehicle_id: UUID,
    vin: str | None,
    assigned_by: UUID,
) -> bool:
    row = await session.get(ApplicationVehicle, application_vehicle_id)
    if row is None:
        return False
    row.product_id = vehicle_id
    row.vin = vin
    row.vin_assigned_by = assigned_by
    cast("Any", row).vin_assigned_at = datetime.now(UTC)
    await session.flush()
    await sync_vehicle_purchase_purpose(session, row.application_id)
    return True

@timed_repository
async def update_vin(
    session: AsyncSession,
    application_vehicle_id: UUID,
    *,
    vin: str | None,
    assigned_by: UUID,
) -> bool:
    row = await session.get(ApplicationVehicle, application_vehicle_id)
    if row is None:
        return False
    row.vin = vin
    row.vin_assigned_by = assigned_by
    cast("Any", row).vin_assigned_at = datetime.now(UTC)
    await session.flush()
    return True

async def _sync_dealer_action_to_se_item(
    session: AsyncSession,
    row: ApplicationVehicle,
    *,
    total_price: Any | None,
    status: str | None,
) -> None:
    if row.product_id is None:
        return
    se_item = await session.scalar(
        select(SpecialEquipmentApplicationItem).where(
            SpecialEquipmentApplicationItem.application_id == row.application_id,
            SpecialEquipmentApplicationItem.product_id == row.product_id,
        )
    )
    if se_item is None:
        return
    if total_price is not None:
        se_item.total_price = total_price
    if status == "rejected":
        se_item.item_status = "rejected"
    elif status in {"confirmed", "replacement"}:
        se_item.item_status = "reserved"


@timed_repository
async def update_dealer_action(
    session: AsyncSession,
    application_vehicle_id: UUID,
    *,
    status: str | None,
    dealer_comment: str | None = None,
    reserve_expires_at: Any | None = None,
    discount_type: str | None = None,
    discount_value: Any | None = None,
    markup_type: str | None = None,
    markup_value: Any | None = None,
    discount_show_catalog_price: bool | None = None,
    markup_show_catalog_price: bool | None = None,
    final_price: Any | None = None,
    total_price: Any | None = None,
    vin: str | None = None,
    vin_assigned_by: UUID | None = None,
) -> dict[str, Any] | None:
    row = await session.get(ApplicationVehicle, application_vehicle_id)
    if row is None:
        return None
    if status is not None:
        row.car_status = status
    if dealer_comment is not None:
        row.dealer_comment = dealer_comment
    if reserve_expires_at is not None:
        row.reserve_expires_at = reserve_expires_at
    if discount_type is not None:
        row.discount_type = discount_type
    if discount_value is not None:
        row.discount_value = discount_value
    if markup_type is not None:
        row.markup_type = markup_type
    if markup_value is not None:
        row.markup_value = markup_value
    _apply_catalog_price_visibility(
        row,
        discount=discount_show_catalog_price,
        markup=markup_show_catalog_price,
    )
    if final_price is not None:
        row.final_price = final_price
    if total_price is not None:
        row.total_price = total_price
    if vin is not None:
        row.vin = vin
        row.vin_assigned_by = vin_assigned_by
        cast("Any", row).vin_assigned_at = datetime.now(UTC)
    await _sync_dealer_action_to_se_item(
        session,
        row,
        total_price=total_price,
        status=status,
    )
    await session.flush()
    await sync_vehicle_purchase_purpose(session, row.application_id)
    docs = await _list_dealer_action_documents(session, application_vehicle_id)
    return _row_to_dict(row, dealer_action_documents=docs)


@timed_repository
async def add_dealer_action_documents(
    session: AsyncSession,
    application_vehicle_id: UUID,
    *,
    action: str,
    uploaded_by: UUID,
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[ApplicationVehicleDealerActionDocument] = []
    for document in documents:
        row = ApplicationVehicleDealerActionDocument(
            application_vehicle_id=application_vehicle_id,
            action=action,
            file_url=str(document["file_url"]),
            file_key=str(document["file_key"]),
            file_name=str(document["file_name"]),
            file_type=document.get("file_type"),
            uploaded_by=uploaded_by,
        )
        rows.append(row)
        session.add(row)
    await session.flush()
    return [_doc_to_dict(row) for row in rows]

@timed_repository
async def vin_used_on_other(
    session: AsyncSession,
    *,
    vin: str,
    exclude_id: UUID,
) -> bool:
    """True iff some OTHER application_vehicle row already has this VIN."""
    from infrastructure.models.applications import ApplicationVehicleAllocation
    allocation = select(ApplicationVehicleAllocation.id).where(
        ApplicationVehicleAllocation.vin == vin,
        # NULL for a fast-deal claim: ``!=`` would skip it and hide the used VIN.
        ApplicationVehicleAllocation.application_vehicle_id.is_distinct_from(exclude_id),
        ApplicationVehicleAllocation.released_at.is_(None),
    )
    if (await session.execute(allocation)).first() is not None:
        return True
    stmt = select(ApplicationVehicle.id).where(
        ApplicationVehicle.vin == vin,
        ApplicationVehicle.id != exclude_id,
    )
    return (await session.execute(stmt)).first() is not None

@timed_repository
async def update_vehicle_dealer(
    session: AsyncSession,
    vehicle_id: UUID,
    *,
    dealer_id: UUID | None,
) -> bool:
    row = await session.get(SpecialEquipmentProduct, vehicle_id)
    if row is None:
        return False
    if dealer_id is not None:
        row.seller_company_id = dealer_id
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def list_available_vins_for_application_vehicle(
    session: AsyncSession,
    *,
    complectation_id: str | None,
    color: str | None = None,
) -> list[dict[str, Any]]:
    """Products of the matching modification that are still in `available`."""
    del color
    if not complectation_id:
        return []
    try:
        mod_id = UUID(str(complectation_id))
    except (ValueError, TypeError):
        return []
    stmt = (
        select(SpecialEquipmentProduct)
        .where(
            SpecialEquipmentProduct.modification_id == mod_id,
            SpecialEquipmentProduct.sale_status == "available",
            SpecialEquipmentProduct.vin.is_not(None),
            SpecialEquipmentProduct.vin != "",
        )
        .order_by(SpecialEquipmentProduct.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "product_id": r.id,
            "vehicle_id": r.id,
            "vin": r.vin,
            "color": None,
            "year": r.manufacture_year,
            "base_price": r.price,
            "discount_price": r.special_price,
            "status": r.sale_status,
            "complectation_id": r.modification_id,
            "model_id": None,
            "mark_id": None,
        }
        for r in rows
    ]
