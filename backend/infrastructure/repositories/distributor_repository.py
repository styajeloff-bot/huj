"""Distributor repository — async, dict-only API.

Owns ORM access for distributor-scoped queries:

- vehicles within the distributor's scope (filter by ``dealer_id``)
- summary counters (total / available / reserved / sold + total amount)
- applications routed to the distributor (via ``application_vehicles`` join)
- bulk insert of vehicles parsed from an xlsx import
- catalog lookup by name (for resolving xlsx mark/model strings to FK ids)

The Express schema referenced ``vehicles.distributor_id`` directly; in the
current FastAPI ORM that column does not exist (verified against Alembic
heads ``001..014``). Per the B3 brief we use the trivial mapping
"distributor scope == vehicles whose ``dealer_id`` IS the distributor
user's id". When a distributor↔dealer-set bridge table is introduced in
a future phase this module is the only place that needs to change.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
)
from infrastructure.models.companies import Company, Distributor
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
)
from infrastructure.models.users import User
from infrastructure.models.vehicles import Warehouse
from infrastructure.repositories import support_repository as support_repo
from infrastructure.repositories.questionnaire_purpose_repository import (
    lock_purpose_application,
    sync_vehicle_purchase_purpose,
)
from infrastructure.repositories.vehicle_stock_status_repository import (
    enrich_stock_status,
)
from infrastructure.repository_timing import timed_repository


def _vehicle_to_dict(row: SpecialEquipmentProduct) -> dict[str, Any]:
    return {
        "id": row.id,
        "product_id": row.id,
        "vehicle_id": row.id,
        "vin": row.vin,
        "dealer_id": row.seller_company_id,
        "seller_company_id": row.seller_company_id,
        "warehouse_id": row.warehouse_id,
        "mark_id": None,
        "model_id": None,
        "generation_id": None,
        "configuration_id": None,
        "complectation_id": str(row.modification_id) if row.modification_id else None,
        "modification_id": str(row.modification_id) if row.modification_id else None,
        "year": row.manufacture_year,
        "base_price": row.price,
        "special_price": row.special_price,
        "dealer_cost": None,
        "discount_price": row.special_price,
        "color": None,
        "color_inter": None,
        "images": [],
        "status": row.sale_status,
        "is_available": row.sale_status == "available",
        "created_at": getattr(row, "created_at", None),
        "updated_at": getattr(row, "updated_at", None),
    }


# ---------------------------------------------------------------------------
# Distributor identity / lookup
# ---------------------------------------------------------------------------


@timed_repository
async def get_distributor_for_user(
    session: AsyncSession, user_id: UUID
) -> dict[str, Any] | None:
    """Resolve the user's distributor row via ``users.company_id`` →
    ``distributors.company_id`` (one-to-one).

    Returns ``None`` if the user does not exist or is not bound to a
    distributor company.
    """
    stmt = (
        select(Distributor)
        .join(User, User.company_id == Distributor.company_id)
        .where(User.id == user_id)
    )
    result = await session.execute(stmt)
    row = result.scalars().first()
    if row is None:
        return None
    return {
        "id": row.id,
        "company_id": row.company_id,
        "regions": row.regions,
        "brands": row.brands,
        "is_active": row.is_active,
    }


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

_ALLOWED_SORT: dict[str, Any] = {
    "created_at": SpecialEquipmentProduct.id,
    "updated_at": SpecialEquipmentProduct.id,
    "base_price": SpecialEquipmentProduct.price,
    "year": SpecialEquipmentProduct.manufacture_year,
    "vin": SpecialEquipmentProduct.vin,
    "mark_name": SpecialEquipmentMark.name,
    "model_name": SpecialEquipmentModel.name,
}


def _vehicle_dealer_company_id_expr() -> sa.ColumnElement[Any]:
    """Resolve vehicle ownership through its warehouse, then seller_company_id."""
    warehouse_dealer_company_id = (
        select(Warehouse.company_id)
        .where(Warehouse.id == SpecialEquipmentProduct.warehouse_id)
        .limit(1)
        .correlate(SpecialEquipmentProduct)
        .scalar_subquery()
    )
    return func.coalesce(warehouse_dealer_company_id, SpecialEquipmentProduct.seller_company_id)


async def _resolve_vehicle_dealer_company_id(
    session: AsyncSession,
    vehicle_id: UUID,
) -> UUID | None:
    return (
        await session.execute(
            select(_vehicle_dealer_company_id_expr())
            .select_from(SpecialEquipmentProduct)
            .where(SpecialEquipmentProduct.id == vehicle_id)
        )
    ).scalar_one_or_none()


def _scope_conditions(dealer_filter: list[UUID] | None) -> list[Any]:
    """Build the WHERE clause that pins the query to a distributor's dealers.

    Ownership comes from a vehicle's linked dealer warehouse when present,
    with ``seller_company_id`` retained for inventory rows. Employees
    pass ``None`` to get the unfiltered query.
    """
    if dealer_filter is None:
        return []
    if not dealer_filter:
        return [sa.false()]
    return [_vehicle_dealer_company_id_expr().in_(dealer_filter)]


@timed_repository
async def list_distributor_vehicles(
    session: AsyncSession,
    *,
    dealer_filter: list[UUID] | None,
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
    search: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[dict[str, Any]], int]:
    """Paginated vehicles list within the distributor's scope."""
    conditions: list[Any] = _scope_conditions(dealer_filter)
    if status:
        conditions.append(SpecialEquipmentProduct.sale_status == status)
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                SpecialEquipmentProduct.vin.ilike(pattern),
                SpecialEquipmentMark.name.ilike(pattern),
                SpecialEquipmentModel.name.ilike(pattern),
            )
        )

    where_clause = and_(*conditions) if conditions else None
    sort_col = _ALLOWED_SORT.get(sort_by, SpecialEquipmentProduct.id)
    sort_expr = sort_col.asc() if sort_order.lower() == "asc" else sort_col.desc()

    base = (
        select(
            SpecialEquipmentProduct,
            SpecialEquipmentMark.name.label("mark_name"),
            SpecialEquipmentModel.name.label("model_name"),
        )
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .outerjoin(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
    )
    if where_clause is not None:
        base = base.where(where_clause)

    list_stmt = base.order_by(sort_expr).offset((page - 1) * limit).limit(limit)
    count_stmt = (
        select(func.count(SpecialEquipmentProduct.id))
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .outerjoin(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
    )
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)

    rows = (await session.execute(list_stmt)).all()
    total = (await session.execute(count_stmt)).scalar() or 0

    items: list[dict[str, Any]] = []
    for r in rows:
        payload = _vehicle_to_dict(r[0])
        payload["mark_name"] = r.mark_name
        payload["model_name"] = r.model_name
        items.append(payload)
    await enrich_stock_status(session, items)
    return items, int(total)


@timed_repository
async def get_distributor_vehicle(
    session: AsyncSession, vehicle_id: UUID
) -> dict[str, Any] | None:
    """Single vehicle row hydrated with mark/model display names."""
    stmt = (
        select(
            SpecialEquipmentProduct,
            SpecialEquipmentMark.name.label("mark_name"),
            SpecialEquipmentModel.name.label("model_name"),
        )
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .outerjoin(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
        .where(SpecialEquipmentProduct.id == vehicle_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    payload = _vehicle_to_dict(row[0])
    payload["mark_name"] = row.mark_name
    payload["model_name"] = row.model_name
    await enrich_stock_status(session, [payload])
    return payload


@timed_repository
async def list_distributor_brand_options(
    session: AsyncSession, *, dealer_filter: list[UUID]
) -> list[dict[str, str]]:
    """Return catalog IDs and names present in the linked dealers' inventory."""
    stmt = (
        select(SpecialEquipmentMark.id, SpecialEquipmentMark.name)
        .join(SpecialEquipmentModel, SpecialEquipmentModel.mark_id == SpecialEquipmentMark.id)
        .join(
            SpecialEquipmentModification,
            SpecialEquipmentModification.model_id == SpecialEquipmentModel.id,
        )
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.modification_id == SpecialEquipmentModification.id,
        )
        .where(
            SpecialEquipmentMark.name.is_not(None),
            SpecialEquipmentMark.name != "",
            *_scope_conditions(dealer_filter),
        )
        .group_by(SpecialEquipmentMark.id, SpecialEquipmentMark.name)
        .order_by(SpecialEquipmentMark.name, SpecialEquipmentMark.id)
    )
    return [
        {"id": str(row.id), "name": row.name}
        for row in (await session.execute(stmt)).all()
    ]


@timed_repository
async def list_distributor_brand_names(
    session: AsyncSession, *, dealer_filter: list[UUID] | None
) -> list[str]:
    """Return distinct mark display names present in the distributor's scope.

    Sorted alphabetically. Used by the inventory UI's brand picker which
    only needs a flat list of strings rather than ``{id, name}`` pairs.
    """
    conditions = _scope_conditions(dealer_filter)
    stmt = (
        select(SpecialEquipmentMark.name)
        .join(SpecialEquipmentModel, SpecialEquipmentModel.mark_id == SpecialEquipmentMark.id)
        .join(
            SpecialEquipmentModification,
            SpecialEquipmentModification.model_id == SpecialEquipmentModel.id,
        )
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.modification_id == SpecialEquipmentModification.id,
        )
        .where(SpecialEquipmentMark.name.is_not(None))
    )
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.group_by(SpecialEquipmentMark.name).order_by(SpecialEquipmentMark.name)
    return [r[0] for r in (await session.execute(stmt)).all() if r[0]]


# ---------------------------------------------------------------------------
# Summary counters
# ---------------------------------------------------------------------------


@timed_repository
async def get_distributor_summary(
    session: AsyncSession,
    *,
    dealer_filter: list[UUID] | None,
) -> dict[str, Any]:
    """Counts and aggregate amount of vehicles in scope."""
    conditions = _scope_conditions(dealer_filter)
    where = and_(*conditions) if conditions else None

    base = select(
        func.count(SpecialEquipmentProduct.id).label("total"),
        func.count(SpecialEquipmentProduct.id)
        .filter(SpecialEquipmentProduct.sale_status == "available")
        .label("available"),
        func.count(SpecialEquipmentProduct.id)
        .filter(SpecialEquipmentProduct.sale_status == "reserved")
        .label("reserved"),
        func.count(SpecialEquipmentProduct.id)
        .filter(SpecialEquipmentProduct.sale_status == "sold")
        .label("sold"),
        func.coalesce(
            func.sum(func.coalesce(SpecialEquipmentProduct.special_price, SpecialEquipmentProduct.price)),
            0,
        ).label("total_amount"),
    )
    if where is not None:
        base = base.where(where)
    row = (await session.execute(base)).one()
    total_amount = row.total_amount or 0
    return {
        "total": int(row.total or 0),
        "available": int(row.available or 0),
        "reserved": int(row.reserved or 0),
        "sold": int(row.sold or 0),
        "total_amount": float(total_amount),
    }


# ---------------------------------------------------------------------------
# Applications listing (read-only — distributor view of leasing apps that
# include at least one vehicle in scope).
# ---------------------------------------------------------------------------


@timed_repository
async def list_distributor_applications(
    session: AsyncSession,
    *,
    dealer_filter: list[UUID] | None,
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """List leasing applications that touch at least one in-scope vehicle.

    The Express analogue joined ``leasing_application_calculations`` and
    aggregated vehicles into a JSONB column. Here we keep the response
    minimal — top-level application fields plus the count of in-scope
    vehicles per application — to avoid pulling in too many tables before
    the applications domain is migrated in Phase 3.
    """
    base_join = (
        select(
            LeasingApplication.id,
            LeasingApplication.status,
            LeasingApplication.total_amount,
            LeasingApplication.created_at,
            LeasingApplication.updated_at,
            LeasingApplication.company_id,
            func.count(ApplicationVehicle.id).label("vehicles_count"),
        )
        .join(
            ApplicationVehicle,
            ApplicationVehicle.application_id == LeasingApplication.id,
        )
        .join(SpecialEquipmentProduct, SpecialEquipmentProduct.id == ApplicationVehicle.product_id)
    )
    conditions = _scope_conditions(dealer_filter)
    if status:
        conditions.append(LeasingApplication.status == status)
    if conditions:
        base_join = base_join.where(and_(*conditions))

    base_join = base_join.group_by(LeasingApplication.id)

    sort_at = func.coalesce(
        LeasingApplication.updated_at,
        LeasingApplication.created_at,
    )
    list_stmt = (
        base_join.order_by(sort_at.desc(), LeasingApplication.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    rows = (await session.execute(list_stmt)).all()

    # Count distinct applications matching the filter — separate query.
    count_stmt = (
        select(func.count(func.distinct(LeasingApplication.id)))
        .select_from(LeasingApplication)
        .join(
            ApplicationVehicle,
            ApplicationVehicle.application_id == LeasingApplication.id,
        )
        .join(SpecialEquipmentProduct, SpecialEquipmentProduct.id == ApplicationVehicle.product_id)
    )
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total = (await session.execute(count_stmt)).scalar() or 0

    items = [
        {
            "id": r.id,
            "status": r.status,
            "total_amount": (
                float(r.total_amount) if r.total_amount is not None else None
            ),
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "company_id": r.company_id,
            "vehicles_count": int(r.vehicles_count or 0),
        }
        for r in rows
    ]
    return items, int(total)


# ---------------------------------------------------------------------------
# Single-row CRUD (in-scope writes)
# ---------------------------------------------------------------------------


@timed_repository
async def create_vehicle_in_scope(
    session: AsyncSession, *, payload: dict[str, Any]
) -> UUID:
    """Create a vehicle/product. Caller is responsible for setting dealer_id."""
    raw_id = payload.get("id") or uuid.uuid4()
    mod_id = payload.get("modification_id") or payload.get("complectation_id")
    if mod_id:
        try:
            mod_uuid = UUID(str(mod_id))
        except (ValueError, TypeError):
            mod_uuid = uuid.uuid4()
    else:
        mod_uuid = uuid.uuid4()

    product_payload: dict[str, Any] = {
        "id": raw_id,
        "code": payload.get("code") or f"prod-{raw_id}",
        "slug": payload.get("slug") or f"prod-{raw_id}",
        "modification_id": mod_uuid,
        "seller_company_id": payload.get("dealer_id") or payload.get("seller_company_id"),
        "warehouse_id": payload.get("warehouse_id"),
        "price": payload.get("base_price") or payload.get("price"),
        "special_price": payload.get("special_price") or payload.get("discount_price"),
        "sale_status": payload.get("status") or payload.get("sale_status") or "available",
        "publication_status": payload.get("publication_status") or "published",
        "vin": payload.get("vin"),
        "manufacture_year": payload.get("year") or payload.get("manufacture_year"),
    }
    clean = {k: v for k, v in product_payload.items() if v is not None or k in ("warehouse_id", "vin")}
    row = SpecialEquipmentProduct(**clean)
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise
    return row.id


@timed_repository
async def update_vehicle_in_scope(
    session: AsyncSession,
    *,
    vehicle_id: UUID,
    dealer_filter: list[UUID] | None,
    fields: dict[str, Any],
) -> bool:
    """Apply a partial update only when the row matches the scope.

    Returns False when the row is missing or out of scope.
    """
    row = await session.get(SpecialEquipmentProduct, vehicle_id)
    if row is None:
        return False
    if dealer_filter is not None and row.seller_company_id not in dealer_filter:
        return False
    field_mappings = {
        "base_price": "price",
        "special_price": "special_price",
        "discount_price": "special_price",
        "year": "manufacture_year",
        "status": "sale_status",
        "dealer_id": "seller_company_id",
    }
    for key, value in fields.items():
        attr = field_mappings.get(key, key)
        if hasattr(row, attr):
            setattr(row, attr, value)
    await session.flush()
    return True


@timed_repository
async def assign_vin_in_scope(
    session: AsyncSession,
    *,
    vehicle_id: UUID,
    dealer_filter: list[UUID] | None,
    vin: str,
) -> bool:
    """Assign / overwrite VIN on a single vehicle within scope."""
    row = await session.get(SpecialEquipmentProduct, vehicle_id)
    if row is None:
        return False
    if dealer_filter is not None and row.seller_company_id not in dealer_filter:
        return False
    row.vin = vin
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise
    return True


# ---------------------------------------------------------------------------
# Bulk update — atomic update of price/status/availability across an id set
# ---------------------------------------------------------------------------


@timed_repository
async def bulk_update_in_scope(
    session: AsyncSession,
    *,
    vehicle_ids: list[UUID],
    dealer_filter: list[UUID] | None,
    updates: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[UUID]]:
    """Apply ``updates`` atomically to every id in scope.

    Returns ``(updated_rows, missing_or_out_of_scope_ids)`` so the caller
    can raise an appropriate domain error on partial mismatches before
    committing. The handler validates first; this function just performs
    the database side-effect.
    """
    if not vehicle_ids:
        return [], []

    fetch_stmt = select(SpecialEquipmentProduct).where(SpecialEquipmentProduct.id.in_(vehicle_ids))
    fetched = (await session.execute(fetch_stmt)).scalars().all()
    fetched_by_id = {r.id: r for r in fetched}

    missing: list[UUID] = []
    in_scope: list[SpecialEquipmentProduct] = []
    for vid in vehicle_ids:
        row = fetched_by_id.get(vid)
        if row is None:
            missing.append(vid)
            continue
        if dealer_filter is not None and row.seller_company_id not in dealer_filter:
            missing.append(vid)
            continue
        in_scope.append(row)

    if not in_scope:
        return [], missing

    field_mappings = {
        "base_price": "price",
        "special_price": "special_price",
        "discount_price": "special_price",
        "year": "manufacture_year",
        "status": "sale_status",
        "dealer_id": "seller_company_id",
    }
    for row in in_scope:
        for key, value in updates.items():
            attr = field_mappings.get(key, key)
            if hasattr(row, attr):
                setattr(row, attr, value)
    await session.flush()
    return [_vehicle_to_dict(r) for r in in_scope], missing


# ---------------------------------------------------------------------------
# Catalog lookup (used by xlsx import to resolve names → ids)
# ---------------------------------------------------------------------------


@timed_repository
async def find_mark_id_by_name(session: AsyncSession, name: str) -> str | None:
    stmt = select(SpecialEquipmentMark.id).where(SpecialEquipmentMark.name.ilike(name)).limit(1)
    res = (await session.execute(stmt)).scalar_one_or_none()
    return str(res) if res else None


@timed_repository
async def find_model_id_by_name(
    session: AsyncSession, *, name: str, mark_id: str
) -> str | None:
    try:
        m_uuid = UUID(mark_id)
    except (ValueError, TypeError):
        return None
    stmt = (
        select(SpecialEquipmentModel.id)
        .where(SpecialEquipmentModel.name.ilike(name), SpecialEquipmentModel.mark_id == m_uuid)
        .limit(1)
    )
    res = (await session.execute(stmt)).scalar_one_or_none()
    return str(res) if res else None


@timed_repository
async def find_generation_id_by_name(
    session: AsyncSession, *, name: str, model_id: str
) -> str | None:
    try:
        m_uuid = UUID(model_id)
    except (ValueError, TypeError):
        return None
    stmt = (
        select(SpecialEquipmentModification.id)
        .where(SpecialEquipmentModification.name.ilike(name), SpecialEquipmentModification.model_id == m_uuid)
        .limit(1)
    )
    res = (await session.execute(stmt)).scalar_one_or_none()
    return str(res) if res else None


@timed_repository
async def mark_exists(session: AsyncSession, mark_id: Any) -> bool:
    try:
        m_uuid = mark_id if isinstance(mark_id, UUID) else UUID(str(mark_id))
    except (ValueError, TypeError):
        return False
    stmt = select(SpecialEquipmentMark.id).where(SpecialEquipmentMark.id == m_uuid)
    return (await session.execute(stmt)).first() is not None


@timed_repository
async def model_exists(session: AsyncSession, model_id: Any) -> bool:
    try:
        m_uuid = model_id if isinstance(model_id, UUID) else UUID(str(model_id))
    except (ValueError, TypeError):
        return False
    stmt = select(SpecialEquipmentModel.id).where(SpecialEquipmentModel.id == m_uuid)
    return (await session.execute(stmt)).first() is not None


@timed_repository
async def vin_exists(
    session: AsyncSession,
    vin: str,
    *,
    exclude_id: UUID | None = None,
) -> bool:
    stmt = select(SpecialEquipmentProduct.id).where(SpecialEquipmentProduct.vin == vin)
    if exclude_id is not None:
        stmt = stmt.where(SpecialEquipmentProduct.id != exclude_id)
    return (await session.execute(stmt)).first() is not None


@timed_repository
async def existing_vins(session: AsyncSession, vins: list[str]) -> set[str]:
    """Return the subset of ``vins`` already present in the vehicles table."""
    if not vins:
        return set()
    stmt = select(SpecialEquipmentProduct.vin).where(SpecialEquipmentProduct.vin.in_(vins))
    rows = (await session.execute(stmt)).scalars().all()
    return {v for v in rows if v is not None}


# ---------------------------------------------------------------------------
# Bulk insert (xlsx import)
# ---------------------------------------------------------------------------


@timed_repository
async def bulk_create_vehicles(
    session: AsyncSession, *, payloads: list[dict[str, Any]]
) -> int:
    """Insert a batch of vehicle rows. Returns the count of inserted rows."""
    if not payloads:
        return 0
    count = 0
    for p in payloads:
        await create_vehicle_in_scope(session, payload=p)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Profile (user + company + distributor extension)
# ---------------------------------------------------------------------------


@timed_repository
async def get_distributor_profile(
    session: AsyncSession, user_id: UUID
) -> dict[str, Any] | None:
    """Compose a distributor profile: user row, company, distributor extension.

    Returns ``None`` when the user doesn't exist. The company/distributor
    blocks are ``None`` when the user is not bound to one (e.g. an employee
    viewing themselves).
    """
    user = await session.get(User, user_id)
    if user is None:
        return None
    company: dict[str, Any] | None = None
    distributor: dict[str, Any] | None = None
    if user.company_id is not None:
        company_row = await session.get(Company, user.company_id)
        if company_row is not None:
            company = {
                "id": company_row.id,
                "name": company_row.name,
                "inn": company_row.inn,
                "company_type": company_row.company_type,
                "phone": company_row.phone,
                "email": company_row.email,
                "website": company_row.website,
                "is_active": (
                    bool(company_row.is_active)
                    if company_row.is_active is not None
                    else True
                ),
            }
        dist_stmt = select(Distributor).where(Distributor.company_id == user.company_id)
        dist_row = (await session.execute(dist_stmt)).scalars().first()
        if dist_row is not None:
            distributor = {
                "id": dist_row.id,
                "company_id": dist_row.company_id,
                "regions": dist_row.regions,
                "brands": dist_row.brands,
                "is_active": (
                    bool(dist_row.is_active) if dist_row.is_active is not None else True
                ),
            }
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "phone": user.phone,
            "role": user.role,
            "company_id": user.company_id,
        },
        "company": company,
        "distributor": distributor,
    }


# ---------------------------------------------------------------------------
# Stats / analytics / filters
# ---------------------------------------------------------------------------


@timed_repository
async def get_distributor_stats(
    session: AsyncSession, *, dealer_filter: list[UUID] | None
) -> dict[str, Any]:
    """Counts of vehicles and applications in scope."""
    summary = await get_distributor_summary(session, dealer_filter=dealer_filter)

    # Count applications touching in-scope vehicles, broken out by status.
    conditions = _scope_conditions(dealer_filter)

    apps_stmt = (
        select(
            LeasingApplication.status,
            func.count(func.distinct(LeasingApplication.id)).label("n"),
        )
        .join(
            ApplicationVehicle,
            ApplicationVehicle.application_id == LeasingApplication.id,
        )
        .join(SpecialEquipmentProduct, SpecialEquipmentProduct.id == ApplicationVehicle.product_id)
    )
    if conditions:
        apps_stmt = apps_stmt.where(and_(*conditions))
    apps_stmt = apps_stmt.group_by(LeasingApplication.status)

    by_status: dict[str, int] = {}
    applications_total = 0
    for row in (await session.execute(apps_stmt)).all():
        key = str(row.status) if row.status is not None else "unknown"
        n = int(row.n or 0)
        by_status[key] = n
        applications_total += n

    return {
        "vehicles": summary,
        "applications": {
            "total": applications_total,
            "by_status": by_status,
        },
    }


@timed_repository
async def get_distributor_analytics(
    session: AsyncSession,
    *,
    dealer_filter: list[UUID] | None,
) -> dict[str, Any]:
    """Simple breakdown / timeline over the current distributor scope.

    The Express analogue produced an ad-hoc monthly bucketing. Here we
    return a compact shape: counts grouped by status plus a monthly
    timeline of created_at over the last 12 months.
    """
    conditions = _scope_conditions(dealer_filter)
    where = and_(*conditions) if conditions else None

    # By status
    status_stmt = select(
        SpecialEquipmentProduct.sale_status.label("status"),
        func.count(SpecialEquipmentProduct.id).label("n"),
    )
    if where is not None:
        status_stmt = status_stmt.where(where)
    status_stmt = status_stmt.group_by(SpecialEquipmentProduct.sale_status)
    by_status: dict[str, int] = {}
    for row in (await session.execute(status_stmt)).all():
        key = str(row.status) if row.status is not None else "unknown"
        by_status[key] = int(row.n or 0)

    # By mark
    mark_stmt = (
        select(
            SpecialEquipmentMark.name.label("mark_name"),
            func.count(SpecialEquipmentProduct.id).label("n"),
        )
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .outerjoin(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
    )
    if where is not None:
        mark_stmt = mark_stmt.where(where)
    mark_stmt = (
        mark_stmt.group_by(SpecialEquipmentMark.name)
        .order_by(func.count(SpecialEquipmentProduct.id).desc())
        .limit(20)
    )
    by_mark = [
        {"mark": (row.mark_name or "—"), "count": int(row.n or 0)}
        for row in (await session.execute(mark_stmt)).all()
    ]

    # Monthly timeline (last 12 months)
    created_expr = func.coalesce(SpecialEquipmentProduct.published_at, func.now())
    bucket = func.date_trunc("month", created_expr).label("bucket")
    timeline_stmt = select(
        bucket,
        func.count(SpecialEquipmentProduct.id).label("n"),
    )
    if where is not None:
        timeline_stmt = timeline_stmt.where(where)
    timeline_stmt = timeline_stmt.group_by(bucket).order_by(bucket.asc())
    timeline = [
        {
            "period": (row.bucket.isoformat() if row.bucket is not None else None),
            "count": int(row.n or 0),
        }
        for row in (await session.execute(timeline_stmt)).all()
    ]

    return {
        "by_status": by_status,
        "by_mark": by_mark,
        "timeline": timeline,
    }


@timed_repository
async def get_distributor_warehouse_analytics(
    session: AsyncSession,
    *,
    dealer_filter: list[UUID] | None,
) -> dict[str, Any]:
    """Rich warehouse analytics for the distributor scope.

    Breakdown by status, mark, dealer, city plus financial aggregates
    and a monthly timeline of vehicle additions.
    """
    conditions = _scope_conditions(dealer_filter)
    where = and_(*conditions) if conditions else None

    price_col = func.coalesce(SpecialEquipmentProduct.special_price, SpecialEquipmentProduct.price, 0)

    # Total vehicles & value
    total_stmt = select(
        func.count(SpecialEquipmentProduct.id).label("n"),
        func.sum(price_col).label("v"),
    )
    if where is not None:
        total_stmt = total_stmt.where(where)
    total_row = (await session.execute(total_stmt)).one_or_none()
    total_vehicles = int(total_row.n or 0) if total_row else 0
    total_value = float(total_row.v or 0) if total_row else 0.0

    # By status
    status_stmt = select(
        SpecialEquipmentProduct.sale_status.label("status"),
        func.count(SpecialEquipmentProduct.id).label("n"),
        func.sum(price_col).label("v"),
    )
    if where is not None:
        status_stmt = status_stmt.where(where)
    status_stmt = status_stmt.group_by(SpecialEquipmentProduct.sale_status)
    by_status = [
        {
            "status": str(row.status) if row.status is not None else "unknown",
            "count": int(row.n or 0),
            "value": float(row.v or 0),
        }
        for row in (await session.execute(status_stmt)).all()
    ]

    # By mark
    mark_stmt = (
        select(
            SpecialEquipmentMark.name.label("mark_name"),
            func.count(SpecialEquipmentProduct.id).label("n"),
            func.sum(price_col).label("v"),
        )
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .outerjoin(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
    )
    if where is not None:
        mark_stmt = mark_stmt.where(where)
    mark_stmt = mark_stmt.group_by(SpecialEquipmentMark.name).order_by(func.count(SpecialEquipmentProduct.id).desc())
    by_mark = [
        {
            "mark": (row.mark_name or "—"),
            "count": int(row.n or 0),
            "value": float(row.v or 0),
        }
        for row in (await session.execute(mark_stmt)).all()
    ]

    # By dealer (join Company for name)
    dealer_stmt = (
        select(
            Company.id.label("dealer_id"),
            Company.name.label("dealer_name"),
            func.count(SpecialEquipmentProduct.id).label("n"),
            func.sum(price_col).label("v"),
        )
        .join(Company, Company.id == SpecialEquipmentProduct.seller_company_id)
    )
    if where is not None:
        dealer_stmt = dealer_stmt.where(where)
    dealer_stmt = (
        dealer_stmt.group_by(Company.id, Company.name)
        .order_by(func.count(SpecialEquipmentProduct.id).desc())
        .limit(100)
    )
    by_dealer = [
        {
            "dealer_id": row.dealer_id,
            "dealer_name": row.dealer_name or "—",
            "count": int(row.n or 0),
            "value": float(row.v or 0),
        }
        for row in (await session.execute(dealer_stmt)).all()
    ]

    # By city (join Company)
    city_stmt = (
        select(
            Company.city.label("city"),
            func.count(SpecialEquipmentProduct.id).label("n"),
            func.sum(price_col).label("v"),
        )
        .join(Company, Company.id == SpecialEquipmentProduct.seller_company_id)
    )
    if where is not None:
        city_stmt = city_stmt.where(where)
    city_stmt = (
        city_stmt.where(Company.city.is_not(None))
        .group_by(Company.city)
        .order_by(func.count(SpecialEquipmentProduct.id).desc())
        .limit(100)
    )
    by_city = [
        {
            "city": row.city or "—",
            "count": int(row.n or 0),
            "value": float(row.v or 0),
        }
        for row in (await session.execute(city_stmt)).all()
    ]

    # Total dealers in scope
    dealers_count_stmt = select(func.count(func.distinct(SpecialEquipmentProduct.seller_company_id)))
    if where is not None:
        dealers_count_stmt = dealers_count_stmt.where(where)
    total_dealers = int((await session.execute(dealers_count_stmt)).scalar() or 0)

    # Monthly timeline (added vehicles by month + status)
    created_expr = func.coalesce(SpecialEquipmentProduct.published_at, func.now())
    bucket = func.date_trunc("month", created_expr).label("bucket")
    timeline_stmt = select(
        bucket,
        SpecialEquipmentProduct.sale_status.label("status"),
        func.count(SpecialEquipmentProduct.id).label("n"),
    )
    if where is not None:
        timeline_stmt = timeline_stmt.where(where)
    timeline_stmt = (
        timeline_stmt.group_by(bucket, SpecialEquipmentProduct.sale_status).order_by(bucket.asc()).limit(36)
    )
    timeline = [
        {
            "period": (row.bucket.isoformat() if row.bucket is not None else None),
            "status": str(row.status) if row.status is not None else "unknown",
            "count": int(row.n or 0),
        }
        for row in (await session.execute(timeline_stmt)).all()
    ]

    return {
        "total_vehicles": total_vehicles,
        "total_value": total_value,
        "total_dealers": total_dealers,
        "by_status": by_status,
        "by_mark": by_mark,
        "by_dealer": by_dealer,
        "by_city": by_city,
        "timeline": timeline,
    }


@timed_repository
async def get_distributor_filters(
    session: AsyncSession, *, dealer_filter: list[UUID] | None
) -> dict[str, Any]:
    """Return distinct filter values available to the distributor.

    Distributors rarely have more than a handful of marks / models, so
    just SELECT DISTINCT with a capped LIMIT; this keeps the query cheap
    and bounded.
    """
    conditions = _scope_conditions(dealer_filter)
    where = and_(*conditions) if conditions else None

    # Marks in scope
    mark_stmt = (
        select(SpecialEquipmentMark.id, SpecialEquipmentMark.name)
        .join(SpecialEquipmentModel, SpecialEquipmentModel.mark_id == SpecialEquipmentMark.id)
        .join(
            SpecialEquipmentModification,
            SpecialEquipmentModification.model_id == SpecialEquipmentModel.id,
        )
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.modification_id == SpecialEquipmentModification.id,
        )
    )
    if where is not None:
        mark_stmt = mark_stmt.where(where)
    mark_stmt = mark_stmt.group_by(SpecialEquipmentMark.id, SpecialEquipmentMark.name).order_by(SpecialEquipmentMark.name).limit(200)
    marks = [
        {"id": str(r.id), "name": r.name} for r in (await session.execute(mark_stmt)).all()
    ]

    # Models in scope
    model_stmt = (
        select(SpecialEquipmentModel.id, SpecialEquipmentModel.name, SpecialEquipmentModel.mark_id)
        .join(
            SpecialEquipmentModification,
            SpecialEquipmentModification.model_id == SpecialEquipmentModel.id,
        )
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.modification_id == SpecialEquipmentModification.id,
        )
    )
    if where is not None:
        model_stmt = model_stmt.where(where)
    model_stmt = (
        model_stmt.group_by(SpecialEquipmentModel.id, SpecialEquipmentModel.name, SpecialEquipmentModel.mark_id)
        .order_by(SpecialEquipmentModel.name)
        .limit(500)
    )
    models = [
        {"id": str(r.id), "name": r.name, "mark_id": str(r.mark_id)}
        for r in (await session.execute(model_stmt)).all()
    ]

    # Years in scope
    year_stmt = select(SpecialEquipmentProduct.manufacture_year)
    if where is not None:
        year_stmt = year_stmt.where(where)
    year_stmt = (
        year_stmt.where(SpecialEquipmentProduct.manufacture_year.is_not(None))
        .group_by(SpecialEquipmentProduct.manufacture_year)
        .order_by(SpecialEquipmentProduct.manufacture_year.desc())
    )
    years = [r[0] for r in (await session.execute(year_stmt)).all() if r[0] is not None]

    # Warehouses (distributors own warehouses by dealer_id or company_id)
    warehouse_stmt = select(Warehouse.id, Warehouse.address, Warehouse.brand)
    if dealer_filter is not None:
        warehouse_stmt = warehouse_stmt.where(
            or_(
                Warehouse.company_id.in_(dealer_filter),
                Warehouse.dealer_id.in_(dealer_filter),
            )
        )
    warehouse_stmt = warehouse_stmt.order_by(Warehouse.address).limit(200)
    warehouses = [
        {"id": r.id, "address": r.address, "brand": r.brand}
        for r in (await session.execute(warehouse_stmt)).all()
    ]

    # Statuses
    statuses = ["available", "reserved", "sold"]

    return {
        "marks": marks,
        "models": models,
        "years": years,
        "warehouses": warehouses,
        "statuses": statuses,
    }


# ---------------------------------------------------------------------------
# Dealers in scope
# ---------------------------------------------------------------------------


@timed_repository
async def list_distributor_dealers(
    session: AsyncSession,
    *,
    dealer_filter: list[UUID] | None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List dealer companies within the distributor's scope.

    ``dealer_filter=None`` (employee) returns all dealer companies;
    ``dealer_filter=[...]`` returns only the matching companies.
    """
    if dealer_filter is None:
        # Employee — return all dealer companies.
        count_stmt = select(func.count(Company.id)).where(
            Company.company_type == "dealer"
        )
        total = int((await session.execute(count_stmt)).scalar() or 0)

        rows_stmt = (
            select(Company.id, Company.name, Company.company_type)
            .where(Company.company_type == "dealer")
            .order_by(Company.name.nullslast(), Company.id)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = (await session.execute(rows_stmt)).all()
        items = [
            {"id": r.id, "name": r.name, "company_type": r.company_type} for r in rows
        ]
        return items, total

    if not dealer_filter:
        # Distributor with no linked dealers — empty result.
        return [], 0

    count_stmt = select(func.count(Company.id)).where(
        Company.id.in_(dealer_filter), Company.company_type == "dealer"
    )
    total = int((await session.execute(count_stmt)).scalar() or 0)

    rows_stmt = (
        select(Company.id, Company.name, Company.company_type)
        .where(Company.id.in_(dealer_filter), Company.company_type == "dealer")
        .order_by(Company.name.nullslast(), Company.id)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    rows = (await session.execute(rows_stmt)).all()
    items = [{"id": r.id, "name": r.name, "company_type": r.company_type} for r in rows]
    return items, total


# ---------------------------------------------------------------------------
# Support programs in scope
# ---------------------------------------------------------------------------


@timed_repository
async def list_distributor_support_programs(
    session: AsyncSession,
    *,
    dealer_filter: list[UUID] | None,
    actor_user_id: UUID,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """Return support programs visible to the distributor.

    Filtering rule mirrors Express:
    - Distributors see programs linked to their company id.
    - Employees see everything (no filter).
    """
    distributor_id: UUID | None = None
    if dealer_filter is not None:
        distributor_id = (
            await session.execute(
                select(User.company_id).where(
                    User.id == actor_user_id,
                    User.role == "distributor",
                    User.company_id.is_not(None),
                )
            )
        ).scalar_one_or_none()
        if distributor_id is None:
            return [], 0

    return await support_repo.list_programs(
        session,
        page=page,
        limit=limit,
        distributor_id=distributor_id,
    )


# ---------------------------------------------------------------------------
# Applications grouped
# ---------------------------------------------------------------------------


@timed_repository
async def list_distributor_applications_grouped(
    session: AsyncSession,
    *,
    dealer_filter: list[UUID] | None,
    page: int = 1,
    limit: int = 500,
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """Return applications bucketed by status."""
    conditions = _scope_conditions(dealer_filter)

    base = (
        select(
            LeasingApplication.id,
            LeasingApplication.status,
            LeasingApplication.total_amount,
            LeasingApplication.created_at,
            LeasingApplication.updated_at,
            LeasingApplication.company_id,
            func.count(ApplicationVehicle.id).label("vehicles_count"),
        )
        .join(
            ApplicationVehicle,
            ApplicationVehicle.application_id == LeasingApplication.id,
        )
        .join(SpecialEquipmentProduct, SpecialEquipmentProduct.id == ApplicationVehicle.product_id)
    )
    if conditions:
        base = base.where(and_(*conditions))

    sort_at = func.coalesce(
        LeasingApplication.updated_at,
        LeasingApplication.created_at,
    )
    list_stmt = (
        base.group_by(LeasingApplication.id)
        .order_by(sort_at.desc(), LeasingApplication.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    rows = (await session.execute(list_stmt)).all()

    count_stmt = (
        select(func.count(func.distinct(LeasingApplication.id)))
        .select_from(LeasingApplication)
        .join(
            ApplicationVehicle,
            ApplicationVehicle.application_id == LeasingApplication.id,
        )
        .join(SpecialEquipmentProduct, SpecialEquipmentProduct.id == ApplicationVehicle.product_id)
    )
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total = (await session.execute(count_stmt)).scalar() or 0

    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        key = str(r.status) if r.status is not None else "unknown"
        grouped.setdefault(key, []).append(
            {
                "id": r.id,
                "status": r.status,
                "total_amount": (
                    float(r.total_amount) if r.total_amount is not None else None
                ),
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "company_id": r.company_id,
                "vehicles_count": int(r.vehicles_count or 0),
            }
        )
    return grouped, int(total)


# ---------------------------------------------------------------------------
# Application vehicles management
# ---------------------------------------------------------------------------


@timed_repository
async def list_vehicles_for_application(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    dealer_filter: list[UUID] | None,
    distributor_company_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Return vehicles attached to an application restricted to scope."""
    stmt = (
        select(
            ApplicationVehicle.id.label("av_id"),
            ApplicationVehicle.application_id,
            ApplicationVehicle.product_id.label("product_id"),
            ApplicationVehicle.quantity,
            ApplicationVehicle.total_price,
            ApplicationVehicle.unit_price,
            ApplicationVehicle.vin.label("av_vin"),
            ApplicationVehicle.is_model_order,
            SpecialEquipmentProduct.id.label("v_id"),
            SpecialEquipmentProduct.vin.label("v_vin"),
            SpecialEquipmentProduct.sale_status.label("status"),
            SpecialEquipmentProduct.seller_company_id.label("dealer_id"),
            SpecialEquipmentProduct.price.label("base_price"),
            SpecialEquipmentProduct.special_price.label("discount_price"),
            SpecialEquipmentMark.id.label("mark_id"),
            SpecialEquipmentModel.id.label("model_id"),
            SpecialEquipmentMark.name.label("mark_name"),
            SpecialEquipmentModel.name.label("model_name"),
        )
        .select_from(ApplicationVehicle)
        .outerjoin(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
        )
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .outerjoin(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
        .where(ApplicationVehicle.application_id == application_id)
    )
    if distributor_company_id is not None:
        from infrastructure.repositories.application_repository import (
            _distributor_vehicle_clause,
        )

        stmt = stmt.where(_distributor_vehicle_clause(distributor_company_id))
    elif dealer_filter is not None:
        stmt = stmt.where(_vehicle_dealer_company_id_expr().in_(dealer_filter))
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": r.av_id,
            "application_id": r.application_id,
            "vehicle_id": r.product_id,
            "product_id": r.product_id,
            "quantity": r.quantity,
            "total_price": (
                float(r.total_price) if r.total_price is not None else None
            ),
            "unit_price": (float(r.unit_price) if r.unit_price is not None else None),
            "vin": r.av_vin or r.v_vin,
            "is_model_order": bool(r.is_model_order)
            if r.is_model_order is not None
            else False,
            "vehicle": {
                "id": r.v_id,
                "vin": r.v_vin,
                "status": r.status,
                "dealer_id": r.dealer_id,
                "base_price": (
                    float(r.base_price) if r.base_price is not None else None
                ),
                "discount_price": (
                    float(r.discount_price) if r.discount_price is not None else None
                ),
                "mark_id": str(r.mark_id) if r.mark_id else None,
                "model_id": str(r.model_id) if r.model_id else None,
                "mark_name": r.mark_name,
                "model_name": r.model_name,
            }
            if r.v_id is not None
            else None,
        }
        for r in rows
    ]


@timed_repository
async def get_application_vehicle_with_scope(
    session: AsyncSession,
    *,
    application_vehicle_id: UUID,
    dealer_filter: list[UUID] | None,
) -> dict[str, Any] | None:
    """Return an application_vehicles row only if its vehicle is in scope."""
    stmt = (
        select(ApplicationVehicle, SpecialEquipmentProduct.seller_company_id)
        .outerjoin(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
        )
        .where(ApplicationVehicle.id == application_vehicle_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    av = row[0]
    vehicle_dealer_id = row[1]
    if dealer_filter is not None and vehicle_dealer_id not in dealer_filter:
        return None
    prod_id = getattr(av, "product_id", getattr(av, "vehicle_id", None))
    return {
        "id": av.id,
        "application_id": av.application_id,
        "vehicle_id": prod_id,
        "product_id": prod_id,
        "quantity": av.quantity,
        "unit_price": av.unit_price,
        "total_price": av.total_price,
        "vin": av.vin,
        "is_model_order": av.is_model_order,
    }


@timed_repository
async def add_vehicle_to_application(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    vehicle_id: UUID,
    quantity: int,
    unit_price: Any,
    total_price: Any,
) -> UUID:
    """Insert an application_vehicles row. Returns the new id."""
    await lock_purpose_application(session, application_id)
    dealer_company_id = await _resolve_vehicle_dealer_company_id(session, vehicle_id)
    row = ApplicationVehicle(
        application_id=application_id,
        product_id=vehicle_id,
        dealer_company_id=dealer_company_id,
        quantity=quantity,
        unit_price=unit_price,
        total_price=total_price,
    )
    session.add(row)
    await session.flush()
    await sync_vehicle_purchase_purpose(session, row.application_id)
    return row.id


@timed_repository
async def replace_application_vehicle_link(
    session: AsyncSession,
    *,
    application_vehicle_id: UUID,
    new_vehicle_id: UUID,
) -> bool:
    """Swap the vehicle_id on an existing application_vehicles row."""
    row = await session.get(ApplicationVehicle, application_vehicle_id)
    if row is None:
        return False
    dealer_company_id = await _resolve_vehicle_dealer_company_id(session, new_vehicle_id)
    row.product_id = new_vehicle_id
    row.dealer_company_id = dealer_company_id
    row.dealer_assigned_by = None
    row.dealer_assigned_at = None
    row.primary_employee_id = None
    row.additional_employee_id = None
    row.employees_assigned_by = None
    row.employees_assigned_at = None
    await session.flush()
    await sync_vehicle_purchase_purpose(session, row.application_id)
    return True


@timed_repository
async def delete_application_vehicle(
    session: AsyncSession, *, application_vehicle_id: UUID
) -> bool:
    row = await session.get(ApplicationVehicle, application_vehicle_id)
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    await sync_vehicle_purchase_purpose(session, row.application_id)
    return True


@timed_repository
async def set_vehicle_status(
    session: AsyncSession, *, vehicle_id: UUID, status: str
) -> bool:
    row = await session.get(SpecialEquipmentProduct, vehicle_id)
    if row is None:
        return False
    row.sale_status = status
    await session.flush()
    return True


@timed_repository
async def delete_vehicle_in_scope(
    session: AsyncSession,
    *,
    vehicle_id: UUID,
    dealer_filter: list[UUID] | None,
) -> bool:
    """Delete a vehicle only when it belongs to the distributor's scope."""
    row = await session.get(SpecialEquipmentProduct, vehicle_id)
    if row is None:
        return False
    if dealer_filter is not None and row.seller_company_id not in dealer_filter:
        return False
    await session.delete(row)
    await session.flush()
    return True


# ---------------------------------------------------------------------------
# Model orders (application_vehicles where is_model_order=true or product_id NULL)
# ---------------------------------------------------------------------------


@timed_repository
async def list_model_orders(
    session: AsyncSession,
    *,
    dealer_filter: list[UUID] | None,
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """List application_vehicles rows that are model-orders (no VIN yet).

    Scope filter: application_vehicles linked (via any existing vehicle on
    the same application) to a vehicle in the distributor's scope are
    considered "belonging" to the distributor. Employees see everything.
    """
    subq_conditions: list[Any] = []
    if dealer_filter is not None:
        subq_conditions.append(SpecialEquipmentProduct.seller_company_id.in_(dealer_filter))

    in_scope_app_ids = select(ApplicationVehicle.application_id).join(
        SpecialEquipmentProduct,
        SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
    )
    if subq_conditions:
        in_scope_app_ids = in_scope_app_ids.where(and_(*subq_conditions))
    in_scope_app_ids = in_scope_app_ids.group_by(ApplicationVehicle.application_id)

    conditions: list[Any] = [
        or_(
            ApplicationVehicle.is_model_order.is_(True),
            ApplicationVehicle.product_id.is_(None),
        )
    ]
    if dealer_filter is not None:
        conditions.append(ApplicationVehicle.application_id.in_(in_scope_app_ids))
    if status == "pending":
        conditions.append(ApplicationVehicle.vin.is_(None))
    elif status == "assigned":
        conditions.append(ApplicationVehicle.vin.is_not(None))

    count_stmt = select(func.count(ApplicationVehicle.id)).where(and_(*conditions))
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = (
        select(ApplicationVehicle)
        .where(and_(*conditions))
        .order_by(ApplicationVehicle.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    items = [
        {
            "id": r.id,
            "application_id": r.application_id,
            "vehicle_id": getattr(r, "product_id", getattr(r, "vehicle_id", None)),
            "product_id": getattr(r, "product_id", getattr(r, "vehicle_id", None)),
            "modification_id": r.modification_id,
            "quantity": r.quantity,
            "vin": r.vin,
            "is_model_order": r.is_model_order,
            "vin_assigned_by": r.vin_assigned_by,
            "vin_assigned_at": r.vin_assigned_at,
            "created_at": r.created_at,
        }
        for r in rows
    ]
    return items, int(total)


@timed_repository
async def count_model_orders_by_status(
    session: AsyncSession, *, dealer_filter: list[UUID] | None
) -> dict[str, int]:
    """Return counts of pending vs assigned model orders."""
    _, pending_total = await list_model_orders(
        session, dealer_filter=dealer_filter, page=1, limit=1, status="pending"
    )
    _, assigned_total = await list_model_orders(
        session, dealer_filter=dealer_filter, page=1, limit=1, status="assigned"
    )
    return {
        "pending": pending_total,
        "assigned": assigned_total,
        "total": pending_total + assigned_total,
    }


@timed_repository
async def assign_vin_to_model_order(
    session: AsyncSession,
    *,
    application_vehicle_id: UUID,
    dealer_filter: list[UUID] | None,
    vin: str,
    assigned_by: UUID,
) -> dict[str, Any] | None:
    """Write the VIN on an application_vehicles row, scoped."""
    scoped = await get_application_vehicle_with_scope(
        session,
        application_vehicle_id=application_vehicle_id,
        dealer_filter=dealer_filter,
    )
    if scoped is None:
        return None
    row = await session.get(ApplicationVehicle, application_vehicle_id)
    if row is None:
        return None
    row.vin = vin
    row.vin_assigned_by = assigned_by
    cast("Any", row).vin_assigned_at = datetime.now(UTC)
    await session.flush()
    return {
        "id": row.id,
        "application_id": row.application_id,
        "vin": row.vin,
        "vin_assigned_by": row.vin_assigned_by,
        "vin_assigned_at": row.vin_assigned_at,
    }


# ---------------------------------------------------------------------------
# Available vehicles for application assignment
# ---------------------------------------------------------------------------


@timed_repository
async def list_available_vehicles_for_app(
    session: AsyncSession,
    *,
    dealer_filter: list[UUID] | None,
    mark_id: str | None = None,
    model_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return vehicles available to attach to a leasing application."""
    conditions: list[Any] = [SpecialEquipmentProduct.sale_status == "available"]
    if dealer_filter is not None:
        conditions.append(SpecialEquipmentProduct.seller_company_id.in_(dealer_filter))
    if mark_id:
        try:
            m_uuid = UUID(mark_id)
            conditions.append(SpecialEquipmentMark.id == m_uuid)
        except (ValueError, TypeError):
            pass
    if model_id:
        try:
            m_uuid = UUID(model_id)
            conditions.append(SpecialEquipmentModel.id == m_uuid)
        except (ValueError, TypeError):
            pass

    stmt = (
        select(
            SpecialEquipmentProduct,
            SpecialEquipmentMark.name.label("mark_name"),
            SpecialEquipmentModel.name.label("model_name"),
        )
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .outerjoin(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
        .where(and_(*conditions))
        .order_by(SpecialEquipmentProduct.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    items: list[dict[str, Any]] = []
    for r in rows:
        payload = _vehicle_to_dict(r[0])
        payload["mark_name"] = r.mark_name
        payload["model_name"] = r.model_name
        items.append(payload)
    return items


# ---------------------------------------------------------------------------
# Vehicles export data (for xlsx / csv)
# ---------------------------------------------------------------------------


@timed_repository
async def list_vehicles_for_export(
    session: AsyncSession,
    *,
    dealer_filter: list[UUID] | None,
    status: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """Return a flat list of vehicles in scope for export purposes."""
    items, _ = await list_distributor_vehicles(
        session,
        dealer_filter=dealer_filter,
        page=1,
        limit=100_000,
        status=status,
        search=search,
    )
    return items
