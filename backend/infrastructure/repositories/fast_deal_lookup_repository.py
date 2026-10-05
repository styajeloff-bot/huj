"""Read-only lookups behind the fast deal forms: parties, directories, stock search.

Nothing here writes. Who may search which stock is decided by the caller and arrives
as plain arguments: ``own_stock_of`` is the company whose warehouses are searched (a
dealer), ``None`` means every published unit (a leasing company). The one rule for
the physical owner of a unit is ``resolved_vehicle_owner_expression``: the owner of
its warehouse, else its seller.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from infrastructure.models.applications import (
    AdditionalEquipment,
    AdditionalService,
    ApplicationVehicleAllocation,
    LeasingPurpose,
    LeasingRegion,
)
from infrastructure.models.companies import Company, DistributorDealerLink
from infrastructure.models.payments import PurchaseOrder
from infrastructure.models.special_equipment import (
    SpecialEquipmentCategory,
    SpecialEquipmentCategoryRelation,
    SpecialEquipmentColor,
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentModificationCategory,
    SpecialEquipmentProduct,
    SpecialEquipmentTrim,
)
from infrastructure.models.vehicles import City, Warehouse
from infrastructure.repositories.vehicle_ownership_repository import (
    resolved_vehicle_owner_expression,
)
from infrastructure.repository_timing import timed_repository

Record = dict[str, Any]


def _contains(column: Any, text: str) -> sa.ColumnElement[bool]:
    """Case-insensitive substring match; LIKE wildcards in ``text`` stay literal."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    clause: sa.ColumnElement[bool] = column.ilike(f"%{escaped}%", escape="\\")
    return clause


async def _rows(session: AsyncSession, stmt: sa.Select[Any]) -> list[Record]:
    return [dict(row) for row in (await session.execute(stmt)).mappings().all()]


async def _attach_category_names(session: AsyncSession, rows: Iterable[Record]) -> None:
    """Add ``category_name`` next to every ``category_id`` with one extra query."""
    items = list(rows)
    ids = {row["category_id"] for row in items if row.get("category_id") is not None}
    names: dict[UUID, str] = {}
    if ids:
        found = await session.execute(
            sa.select(SpecialEquipmentCategory.id, SpecialEquipmentCategory.name).where(
                SpecialEquipmentCategory.id.in_(ids)
            )
        )
        names = {row.id: row.name for row in found.all()}
    for row in items:
        category_id = row.get("category_id")
        row["category_name"] = names.get(category_id) if category_id is not None else None


# ------------------------------------------------------------------------ companies

def _company_search(q: str | None) -> list[sa.ColumnElement[bool]]:
    if not q:
        return []
    return [sa.or_(_contains(Company.name, q), _contains(Company.inn, q))]


@timed_repository
async def list_leasing_companies(
    session: AsyncSession, *, q: str | None, limit: int
) -> list[Record]:
    """Active companies of type ``leasing_company``; the id is the company id."""
    stmt = (
        sa.select(Company.id, Company.name, Company.inn)
        .where(
            Company.company_type == "leasing_company",
            Company.is_active.is_not(False),
            *_company_search(q),
        )
        .order_by(Company.name, Company.id)
        .limit(limit)
    )
    return await _rows(session, stmt)


@timed_repository
async def list_dealers(
    session: AsyncSession,
    *,
    q: str | None,
    limit: int,
    distributor_company_id: UUID | None = None,
) -> list[Record]:
    """Active dealer companies; a distributor sees only the dealers linked to it."""
    stmt = (
        sa.select(Company.id, Company.name, Company.inn)
        .where(
            Company.company_type == "dealer",
            Company.is_active.is_not(False),
            *_company_search(q),
        )
        .order_by(Company.name, Company.id)
        .limit(limit)
    )
    if distributor_company_id is not None:
        stmt = stmt.where(
            Company.id.in_(
                sa.select(DistributorDealerLink.dealer_company_id).where(
                    DistributorDealerLink.distributor_company_id
                    == distributor_company_id
                )
            )
        )
    return await _rows(session, stmt)


@timed_repository
async def list_warehouses(
    session: AsyncSession,
    *,
    own_stock_of: UUID | None,
    q: str | None,
    limit: int,
) -> list[Record]:
    """Active warehouses for the stock filter.

    A dealer gets its own; with ``own_stock_of=None`` (a leasing company) every
    warehouse that holds at least one published unit.
    """
    owner = aliased(Company)
    stmt = (
        sa.select(
            Warehouse.id,
            Warehouse.name,
            Warehouse.address,
            City.name.label("city_name"),
            Warehouse.owner_company_id.label("owner_company_id"),
            owner.name.label("owner_company_name"),
        )
        .select_from(Warehouse)
        .join(owner, owner.id == Warehouse.owner_company_id)
        .outerjoin(City, City.id == Warehouse.city_id)
        .where(Warehouse.is_active.is_(True))
        .order_by(Warehouse.name, Warehouse.id)
        .limit(limit)
    )
    if own_stock_of is not None:
        stmt = stmt.where(Warehouse.owner_company_id == own_stock_of)
    else:
        stmt = stmt.where(
            sa.exists()
            .where(
                SpecialEquipmentProduct.warehouse_id == Warehouse.id,
                SpecialEquipmentProduct.publication_status == "published",
            )
            .correlate(Warehouse)
        )
    if q:
        stmt = stmt.where(
            sa.or_(
                _contains(Warehouse.name, q),
                _contains(Warehouse.address, q),
                _contains(City.name, q),
            )
        )
    return await _rows(session, stmt)


# ----------------------------------------------------------------------- directories

@timed_repository
async def list_categories(
    session: AsyncSession, *, q: str | None, limit: int
) -> list[Record]:
    """Active categories shown in the catalog; ``is_leaf`` marks the end of a branch."""
    active_child = aliased(SpecialEquipmentCategory)
    has_child = (
        sa.exists()
        .where(
            SpecialEquipmentCategoryRelation.parent_id == SpecialEquipmentCategory.id,
            active_child.id == SpecialEquipmentCategoryRelation.child_id,
            active_child.is_active.is_(True),
            active_child.is_visible_in_catalog.is_(True),
        )
        .correlate(SpecialEquipmentCategory)
    )
    stmt = (
        sa.select(
            SpecialEquipmentCategory.id,
            SpecialEquipmentCategory.code,
            SpecialEquipmentCategory.name,
            SpecialEquipmentCategory.is_attachment_category,
            sa.not_(has_child).label("is_leaf"),
        )
        .where(
            SpecialEquipmentCategory.is_active.is_(True),
            SpecialEquipmentCategory.is_visible_in_catalog.is_(True),
        )
        .order_by(
            SpecialEquipmentCategory.sort_order,
            SpecialEquipmentCategory.name,
            SpecialEquipmentCategory.id,
        )
        .limit(limit)
    )
    if q:
        stmt = stmt.where(_contains(SpecialEquipmentCategory.name, q))
    return await _rows(session, stmt)


def _model_in_category(category_id: UUID) -> sa.ColumnElement[bool]:
    """A model belongs to a category itself or through one of its modifications."""
    via_modification = (
        sa.select(SpecialEquipmentModification.model_id)
        .join(
            SpecialEquipmentModificationCategory,
            SpecialEquipmentModificationCategory.modification_id
            == SpecialEquipmentModification.id,
        )
        .where(SpecialEquipmentModificationCategory.category_id == category_id)
    )
    return sa.or_(
        SpecialEquipmentModel.category_id == category_id,
        SpecialEquipmentModel.id.in_(via_modification),
    )


def _model_category_id() -> sa.ColumnElement[Any]:
    """The model's own category, else the primary one of one of its modifications."""
    primary = (
        sa.select(SpecialEquipmentModificationCategory.category_id)
        .join(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id
            == SpecialEquipmentModificationCategory.modification_id,
        )
        .where(
            SpecialEquipmentModification.model_id == SpecialEquipmentModel.id,
            SpecialEquipmentModificationCategory.is_primary.is_(True),
        )
        .order_by(
            SpecialEquipmentModification.name,
            SpecialEquipmentModificationCategory.sort_order,
        )
        .limit(1)
        .correlate(SpecialEquipmentModel)
        .scalar_subquery()
    )
    return sa.func.coalesce(SpecialEquipmentModel.category_id, primary)


@timed_repository
async def list_marks(
    session: AsyncSession,
    *,
    q: str | None,
    category_id: UUID | None,
    limit: int,
) -> list[Record]:
    stmt = (
        sa.select(
            SpecialEquipmentMark.id, SpecialEquipmentMark.name, SpecialEquipmentMark.code
        )
        .where(SpecialEquipmentMark.is_active.is_(True))
        .order_by(SpecialEquipmentMark.name, SpecialEquipmentMark.id)
        .limit(limit)
    )
    if q:
        stmt = stmt.where(_contains(SpecialEquipmentMark.name, q))
    if category_id is not None:
        stmt = stmt.where(
            SpecialEquipmentMark.id.in_(
                sa.select(SpecialEquipmentModel.mark_id).where(
                    SpecialEquipmentModel.is_active.is_(True),
                    _model_in_category(category_id),
                )
            )
        )
    return await _rows(session, stmt)


@timed_repository
async def list_models(
    session: AsyncSession,
    *,
    q: str | None,
    mark_id: UUID | None,
    category_id: UUID | None,
    limit: int,
) -> list[Record]:
    stmt = (
        sa.select(
            SpecialEquipmentModel.id,
            SpecialEquipmentModel.name,
            SpecialEquipmentModel.code,
            SpecialEquipmentModel.mark_id,
            SpecialEquipmentMark.name.label("mark_name"),
            _model_category_id().label("category_id"),
        )
        .join(
            SpecialEquipmentMark, SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id
        )
        .where(
            SpecialEquipmentModel.is_active.is_(True),
            SpecialEquipmentMark.is_active.is_(True),
        )
        .order_by(SpecialEquipmentModel.name, SpecialEquipmentModel.id)
        .limit(limit)
    )
    if q:
        stmt = stmt.where(_contains(SpecialEquipmentModel.name, q))
    if mark_id is not None:
        stmt = stmt.where(SpecialEquipmentModel.mark_id == mark_id)
    if category_id is not None:
        stmt = stmt.where(_model_in_category(category_id))
    rows = await _rows(session, stmt)
    await _attach_category_names(session, rows)
    return rows


@timed_repository
async def list_modifications(
    session: AsyncSession,
    *,
    q: str | None,
    model_id: UUID | None,
    category_id: UUID | None,
    limit: int,
) -> list[Record]:
    """Modifications with the category they suggest (primary, else the model's)."""
    modification = SpecialEquipmentModification
    modification_category = SpecialEquipmentModificationCategory
    primary = (
        sa.select(modification_category.category_id)
        .where(
            modification_category.modification_id == modification.id,
            modification_category.is_primary.is_(True),
        )
        .order_by(modification_category.sort_order)
        .limit(1)
        .correlate(modification)
        .scalar_subquery()
    )
    stmt = (
        sa.select(
            modification.id,
            modification.name,
            modification.code,
            modification.model_id,
            modification.year_from,
            modification.year_to,
            sa.func.coalesce(primary, SpecialEquipmentModel.category_id).label(
                "category_id"
            ),
        )
        .select_from(modification)
        .join(SpecialEquipmentModel, SpecialEquipmentModel.id == modification.model_id)
        .where(
            modification.is_active.is_(True),
            SpecialEquipmentModel.is_active.is_(True),
        )
        .order_by(modification.name, modification.id)
        .limit(limit)
    )
    if q:
        stmt = stmt.where(_contains(modification.name, q))
    if model_id is not None:
        stmt = stmt.where(modification.model_id == model_id)
    if category_id is not None:
        stmt = stmt.where(
            sa.or_(
                modification.id.in_(
                    sa.select(modification_category.modification_id).where(
                        modification_category.category_id == category_id
                    )
                ),
                SpecialEquipmentModel.category_id == category_id,
            )
        )
    rows = await _rows(session, stmt)
    await _attach_category_names(session, rows)
    return rows


@timed_repository
async def list_trims(
    session: AsyncSession,
    *,
    q: str | None,
    modification_id: UUID | None,
    limit: int,
) -> list[Record]:
    stmt = (
        sa.select(
            SpecialEquipmentTrim.id,
            SpecialEquipmentTrim.name,
            SpecialEquipmentTrim.code,
            SpecialEquipmentTrim.modification_id,
        )
        .where(SpecialEquipmentTrim.is_active.is_(True))
        .order_by(
            SpecialEquipmentTrim.sort_order,
            SpecialEquipmentTrim.name,
            SpecialEquipmentTrim.id,
        )
        .limit(limit)
    )
    if q:
        stmt = stmt.where(_contains(SpecialEquipmentTrim.name, q))
    if modification_id is not None:
        stmt = stmt.where(SpecialEquipmentTrim.modification_id == modification_id)
    return await _rows(session, stmt)


@timed_repository
async def list_colors(
    session: AsyncSession, *, q: str | None, applicability: str, limit: int
) -> list[Record]:
    """Active colors usable for ``applicability`` (``body`` or ``interior``)."""
    stmt = (
        sa.select(
            SpecialEquipmentColor.id,
            SpecialEquipmentColor.name,
            SpecialEquipmentColor.code,
            SpecialEquipmentColor.applicability,
        )
        .where(
            SpecialEquipmentColor.is_active.is_(True),
            SpecialEquipmentColor.applicability.in_((applicability, "both")),
        )
        .order_by(sa.func.lower(SpecialEquipmentColor.name), SpecialEquipmentColor.id)
        .limit(limit)
    )
    if q:
        stmt = stmt.where(_contains(SpecialEquipmentColor.name, q))
    return await _rows(session, stmt)


@timed_repository
async def list_model_candidates(
    session: AsyncSession,
    *,
    mark_id: UUID | None,
    fragments: Sequence[str],
    limit: int,
) -> list[Record]:
    """Active models to rank by similarity to a typed name.

    Within one mark every model is a candidate (a mark has few). Across marks a
    model is a candidate only when its name contains one of the typed ``fragments``,
    which keeps the ranked set small.
    """
    if mark_id is None and not fragments:
        return []
    stmt = (
        sa.select(
            SpecialEquipmentModel.id,
            SpecialEquipmentModel.name,
            SpecialEquipmentModel.mark_id,
            SpecialEquipmentMark.name.label("mark_name"),
            _model_category_id().label("category_id"),
        )
        .join(
            SpecialEquipmentMark, SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id
        )
        .where(
            SpecialEquipmentModel.is_active.is_(True),
            SpecialEquipmentMark.is_active.is_(True),
        )
        .order_by(SpecialEquipmentModel.name, SpecialEquipmentModel.id)
        .limit(limit)
    )
    if mark_id is not None:
        stmt = stmt.where(SpecialEquipmentModel.mark_id == mark_id)
    else:
        stmt = stmt.where(
            sa.or_(*(_contains(SpecialEquipmentModel.name, item) for item in fragments))
        )
    rows = await _rows(session, stmt)
    await _attach_category_names(session, rows)
    return rows


# -------------------------------------------------- equipment, services, purposes, regions

@timed_repository
async def list_equipments(
    session: AsyncSession, *, q: str | None, limit: int
) -> list[Record]:
    stmt = (
        sa.select(
            AdditionalEquipment.equipment_code.label("code"),
            AdditionalEquipment.equipment_display_name.label("name"),
        )
        .where(AdditionalEquipment.is_active.is_(True))
        .order_by(
            AdditionalEquipment.sort_order,
            AdditionalEquipment.equipment_display_name,
            AdditionalEquipment.equipment_code,
        )
        .limit(limit)
    )
    if q:
        stmt = stmt.where(_contains(AdditionalEquipment.equipment_display_name, q))
    return await _rows(session, stmt)


@timed_repository
async def list_services(
    session: AsyncSession, *, q: str | None, limit: int
) -> list[Record]:
    stmt = (
        sa.select(
            AdditionalService.service_code.label("code"),
            AdditionalService.service_display_name.label("name"),
        )
        .where(AdditionalService.is_active.is_(True))
        .order_by(
            AdditionalService.sort_order,
            AdditionalService.service_display_name,
            AdditionalService.service_code,
        )
        .limit(limit)
    )
    if q:
        stmt = stmt.where(_contains(AdditionalService.service_display_name, q))
    return await _rows(session, stmt)


@timed_repository
async def list_purposes(
    session: AsyncSession, *, q: str | None, limit: int
) -> list[Record]:
    stmt = (
        sa.select(
            LeasingPurpose.purpose_name.label("code"),
            LeasingPurpose.purpose_display_name.label("name"),
        )
        .order_by(LeasingPurpose.purpose_display_name, LeasingPurpose.purpose_name)
        .limit(limit)
    )
    if q:
        stmt = stmt.where(_contains(LeasingPurpose.purpose_display_name, q))
    return await _rows(session, stmt)


@timed_repository
async def list_regions(
    session: AsyncSession, *, q: str | None, limit: int
) -> list[Record]:
    stmt = (
        sa.select(
            LeasingRegion.region_name.label("code"),
            LeasingRegion.region_display_name.label("name"),
            LeasingRegion.region_number.label("number"),
        )
        .order_by(LeasingRegion.region_number)
        .limit(limit)
    )
    if q:
        stmt = stmt.where(
            sa.or_(
                _contains(LeasingRegion.region_display_name, q),
                _contains(LeasingRegion.region_number, q),
            )
        )
    return await _rows(session, stmt)


# ----------------------------------------------------------------------------- stock

def _claimed() -> sa.ColumnElement[bool]:
    """Held by something: a reserved/sold status, an active allocation or a purchase.

    Allocations of every source count (ordinary application, exchange, fast deal),
    and so does a purchase order that is not cancelled.
    """
    product = SpecialEquipmentProduct
    allocation = (
        sa.exists()
        .where(
            ApplicationVehicleAllocation.product_id == product.id,
            ApplicationVehicleAllocation.released_at.is_(None),
        )
        .correlate(product)
    )
    purchase = (
        sa.exists()
        .where(PurchaseOrder.product_id == product.id, PurchaseOrder.status != "cancelled")
        .correlate(product)
    )
    return sa.or_(product.sale_status.in_(("reserved", "sold")), allocation, purchase)


def _unit_category_id() -> sa.ColumnElement[Any]:
    """Primary category of the unit's modification, else its model's category."""
    product = SpecialEquipmentProduct
    primary = (
        sa.select(SpecialEquipmentModificationCategory.category_id)
        .where(
            SpecialEquipmentModificationCategory.modification_id
            == product.modification_id,
            SpecialEquipmentModificationCategory.is_primary.is_(True),
        )
        .order_by(SpecialEquipmentModificationCategory.sort_order)
        .limit(1)
        .correlate(product)
        .scalar_subquery()
    )
    return sa.func.coalesce(primary, SpecialEquipmentModel.category_id)


class _Units:
    """Aliases and the join skeleton shared by the VIN lookup, the list and the count.

    A unit has a modification (a chassis or a kit) or, for a custom superstructure,
    its own model: the model is whichever of the two is present, exactly as the
    public catalog resolves it.
    """

    def __init__(self) -> None:
        self.trim = aliased(SpecialEquipmentTrim)
        self.color = aliased(SpecialEquipmentColor)
        self.warehouse = aliased(Warehouse)
        self.city = aliased(City)
        self.owner = aliased(Company)
        self.owner_id = resolved_vehicle_owner_expression()

    def query(self, *columns: Any) -> sa.Select[Any]:
        product = SpecialEquipmentProduct
        return (
            sa.select(*columns)
            .select_from(product)
            .outerjoin(
                SpecialEquipmentModification,
                SpecialEquipmentModification.id == product.modification_id,
            )
            .join(
                SpecialEquipmentModel,
                SpecialEquipmentModel.id
                == sa.func.coalesce(SpecialEquipmentModification.model_id, product.model_id),
            )
            .join(
                SpecialEquipmentMark,
                SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
            )
            .outerjoin(self.trim, self.trim.id == product.trim_id)
            .outerjoin(self.color, self.color.id == product.body_color_id)
            .outerjoin(self.warehouse, self.warehouse.id == product.warehouse_id)
            .outerjoin(self.city, self.city.id == self.warehouse.city_id)
            .outerjoin(self.owner, self.owner.id == self.owner_id)
        )

    def columns(self) -> list[Any]:
        product = SpecialEquipmentProduct
        return [
            product.id,
            product.code,
            product.vin,
            product.no_vin,
            product.condition,
            product.manufacture_year,
            product.mileage_km,
            product.engine_hours,
            product.publication_status,
            product.sale_status,
            product.price,
            product.special_price,
            product.price_on_request,
            product.price_from,
            product.warehouse_id,
            self.warehouse.name.label("warehouse_name"),
            self.city.name.label("warehouse_city"),
            self.owner_id.label("owner_company_id"),
            self.owner.name.label("owner_company_name"),
            SpecialEquipmentMark.id.label("mark_id"),
            SpecialEquipmentMark.name.label("mark_name"),
            SpecialEquipmentModel.id.label("model_id"),
            SpecialEquipmentModel.name.label("model_name"),
            SpecialEquipmentModification.id.label("modification_id"),
            SpecialEquipmentModification.name.label("modification_name"),
            self.trim.id.label("trim_id"),
            self.trim.name.label("trim_name"),
            self.color.id.label("body_color_id"),
            self.color.name.label("body_color_name"),
            _unit_category_id().label("category_id"),
            _claimed().label("claimed"),
        ]

    def scope(self, own_stock_of: UUID | None) -> list[sa.ColumnElement[bool]]:
        """Own warehouses (archived listings are out of the catalog) or all published."""
        product = SpecialEquipmentProduct
        if own_stock_of is not None:
            return [
                self.owner_id == own_stock_of,
                product.publication_status != "archived",
            ]
        return [product.publication_status == "published"]


@timed_repository
async def find_unit_by_vin(
    session: AsyncSession, *, vin: str, own_stock_of: UUID | None
) -> Record | None:
    """The unit with this (already normalised) VIN inside the searched stock."""
    units = _Units()
    stmt = (
        units.query(*units.columns())
        .where(
            sa.func.upper(SpecialEquipmentProduct.vin) == vin,
            *units.scope(own_stock_of),
        )
        .limit(1)
    )
    row = (await session.execute(stmt)).mappings().first()
    if row is None:
        return None
    result = dict(row)
    await _attach_category_names(session, [result])
    return result


@timed_repository
async def list_units(
    session: AsyncSession,
    *,
    own_stock_of: UUID | None,
    vin: str | None,
    warehouse_id: UUID | None,
    mark_id: UUID | None,
    model_id: UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[Record], int]:
    """One page of units of the searched stock, newest listing first, and the total.

    Nothing is hidden by state: reserved, sold and unpublished units of an own stock
    are returned with their ``claimed`` flag so that the caller can explain them.
    """
    units = _Units()
    product = SpecialEquipmentProduct
    clauses = units.scope(own_stock_of)
    if vin:
        clauses.append(_contains(product.vin, vin))
    if warehouse_id is not None:
        clauses.append(product.warehouse_id == warehouse_id)
    if mark_id is not None:
        clauses.append(SpecialEquipmentMark.id == mark_id)
    if model_id is not None:
        clauses.append(SpecialEquipmentModel.id == model_id)
    total = await session.scalar(units.query(sa.func.count()).where(*clauses))
    stmt = (
        units.query(*units.columns())
        .where(*clauses)
        .order_by(product.published_at.desc().nulls_last(), product.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = await _rows(session, stmt)
    await _attach_category_names(session, rows)
    return rows, int(total or 0)
