"""Application repository — Phase 3 leasing applications domain.

Async, dict-only API. Owns ORM access for ``leasing_applications``,
``leasing_company_applications``, ``application_vehicles``,
``application_questionnaires``, ``leasing_application_calculations``,
``leasing_application_vehicle_calculations`` and
``leasing_application_comments``.

Returns plain dicts (or lists of dicts). ORM objects never escape this
module — handlers hydrate them into domain entities via ``from_dict``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from domain.leasing_purposes import selected_purposes
from domain.questionnaire import MANUAL_SOURCES, initial_values, merge_with_sources
from domain.questionnaire_people import (
    PEOPLE_FIELDS,
    normalize_incoming_people,
    normalize_stored_people,
)
from domain.special_equipment_commerce import (
    SPECIAL_EQUIPMENT_PUBLIC_DETAIL_SALE_STATUSES,
    SPECIAL_EQUIPMENT_PUBLICATION_PUBLISHED,
)
from domain.storefronts import CatalogScope
from infrastructure.models.applications import (
    AdditionalEquipment,
    AdditionalService,
    ApplicationQuestionnaire,
    ApplicationVehicle,
    ApplicationVehicleDealerActionDocument,
    ApplicationVehicleDealerDistribution,
    LeasingApplication,
    LeasingApplicationCalculation,
    LeasingApplicationComment,
    LeasingApplicationVehicleCalculation,
    LeasingCompanyApplication,
    LeasingPurpose,
    LeasingRegion,
)
from infrastructure.models.companies import Company, DistributorBrand, LeasingCompany
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
    SpecialEquipmentProductImage,
    SpecialEquipmentTrim,
)
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
    SpecialEquipmentPriceChangeLog,
)
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.models.users import User
from infrastructure.models.vehicles import City, Warehouse
from infrastructure.repositories.application_source_filters import (
    application_source_filters,
)
from infrastructure.repositories.catalog_scope import (
    special_equipment_visible_for_storefront,
    vehicle_visible_in,
)
from infrastructure.repositories.questionnaire_purpose_repository import (
    lock_purpose_application,
    sync_vehicle_purchase_purpose,
)
from infrastructure.repository_timing import timed_repository

_APPLICATION_STATUS_LABELS = {
    "active": "Активна",
    "deal": "Сделка",
    "closed": "Закрыта",
}
_CLOSING_LCA_STATUSES = {"closed", "rejected_prescoring", "rejected_approved"}


def _application_business_status(status: str | None) -> tuple[str, str]:
    if status == "closed":
        return "closed", _APPLICATION_STATUS_LABELS["closed"]
    if status == "deal":
        return "deal", _APPLICATION_STATUS_LABELS["deal"]
    return "active", _APPLICATION_STATUS_LABELS["active"]


def _group_business_status(lca_statuses: list[str]) -> tuple[str, str]:
    if any(status == "deal" for status in lca_statuses):
        return "deal", _APPLICATION_STATUS_LABELS["deal"]
    if lca_statuses and all(status in _CLOSING_LCA_STATUSES for status in lca_statuses):
        return "closed", _APPLICATION_STATUS_LABELS["closed"]
    return "active", _APPLICATION_STATUS_LABELS["active"]


def _attach_application_business_status(app: dict[str, Any]) -> None:
    status, label = _application_business_status(app.get("status"))
    app["application_status"] = status
    app["application_status_label"] = label
    app.setdefault("group_status", status)
    app.setdefault("group_status_label", label)


def _vehicle_dealer_company_id_expr() -> sa.ColumnElement[Any]:
    """Resolve the company owning a vehicle exactly like checkout routing."""

    from infrastructure.repositories.vehicle_ownership_repository import (
        resolved_vehicle_owner_expression,
    )

    return resolved_vehicle_owner_expression()


def _application_vehicle_dealer_company_id_expr() -> sa.ColumnElement[Any]:
    """Resolve the effective dealer owner of an application vehicle line.

    Concrete vehicles inherit the checkout ownership precedence from their
    current warehouse. Legacy model orders are identified by their missing
    ``vehicle_id`` and fall back to the dealer assigned on the application.
    """

    assigned_dealer_company_id = (
        select(LeasingApplication.dealer_company_id)
        .where(LeasingApplication.id == ApplicationVehicle.application_id)
        .correlate(ApplicationVehicle)
        .scalar_subquery()
    )
    return sa.case(
        (
            ApplicationVehicle.product_id.is_(None),
            assigned_dealer_company_id,
        ),
        else_=_vehicle_dealer_company_id_expr(),
    )


def _warehouse_company_id_expr() -> Any:
    return (
        select(Warehouse.owner_company_id)
        .select_from(SpecialEquipmentProduct)
        .join(Warehouse, Warehouse.id == SpecialEquipmentProduct.warehouse_id)
        .where(SpecialEquipmentProduct.id == ApplicationVehicle.product_id)
        .correlate(ApplicationVehicle)
        .scalar_subquery()
    )

def _distributor_vehicle_clause(company_id: UUID) -> sa.ColumnElement[bool]:
    """Own stock, or dealer stock in an active group with an active brand."""
    warehouse_company = _warehouse_company_id_expr()
    prod_col = getattr(ApplicationVehicle, "product_id", getattr(ApplicationVehicle, "vehicle_id", None))
    grouped_dealer = (
        select(DealerGroupMember.dealer_company_id)
        .join(DealerGroup, DealerGroup.id == DealerGroupMember.dealer_group_id)
        .join(Company, Company.id == DealerGroupMember.dealer_company_id)
        .where(
            DealerGroup.distributor_company_id == company_id,
            DealerGroup.is_active.is_(True),
            Company.company_type == "dealer",
            DealerGroupMember.dealer_company_id == warehouse_company,
        )
        .correlate(ApplicationVehicle)
        .exists()
    )
    active_brand = (
        select(DistributorBrand.brand_id)
        .select_from(SpecialEquipmentProduct)
        .where(SpecialEquipmentProduct.id == prod_col)
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .join(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .join(
            DistributorBrand,
            DistributorBrand.brand_id == SpecialEquipmentModel.mark_id,
        )
        .where(
            DistributorBrand.distributor_company_id == company_id,
            DistributorBrand.is_active.is_(True),
        )
        .correlate(ApplicationVehicle)
        .exists()
    )
    return sa.or_(warehouse_company == company_id, sa.and_(grouped_dealer, active_brand))


def _allocated_quantity_expr(dealer_filter: list[UUID]) -> Any:
    return func.coalesce(
        select(func.sum(ApplicationVehicleDealerDistribution.quantity))
        .where(
            ApplicationVehicleDealerDistribution.application_vehicle_id == ApplicationVehicle.id,
            ApplicationVehicleDealerDistribution.dealer_company_id.in_(dealer_filter),
        )
        .correlate(ApplicationVehicle)
        .scalar_subquery(),
        0,
    )


def _visible_vehicle_quantity_expr(
    dealer_filter: list[UUID] | None, distributor_company_id: UUID | None = None,
) -> Any:
    if dealer_filter is None or distributor_company_id is not None:
        return ApplicationVehicle.quantity
    # The warehouse owner and a legacy full-line assignee retain the whole row.
    return sa.case(
        (sa.or_(
            _application_vehicle_dealer_company_id_expr().in_(dealer_filter),
            ApplicationVehicle.dealer_company_id.in_(dealer_filter),
        ), ApplicationVehicle.quantity),
        else_=_allocated_quantity_expr(dealer_filter),
    )


def _visible_vehicle_total_expr(
    dealer_filter: list[UUID] | None, distributor_company_id: UUID | None = None,
    *, normalize_quantity: bool = False,
) -> Any:
    quantity = (sa.case((ApplicationVehicle.quantity > 0, ApplicationVehicle.quantity), else_=1)
                if normalize_quantity else ApplicationVehicle.quantity)
    whole_total = func.coalesce(
        func.nullif(ApplicationVehicle.total_price, 0),
        ApplicationVehicle.unit_price * quantity,
        0,
    )
    if dealer_filter is None or distributor_company_id is not None:
        return whole_total
    return func.round(whole_total * _visible_vehicle_quantity_expr(dealer_filter)
                      / func.greatest(ApplicationVehicle.quantity, 1), 2)


def _scope_vehicle_quantities(row: dict[str, Any], visible_quantity: int | None) -> None:
    """Project a dealer share without disclosing the other shares' totals."""
    whole_quantity = int(row.get("quantity") or 0)
    visible_quantity = int(visible_quantity or 0)
    row["can_manage_whole_vehicle"] = visible_quantity == whole_quantity
    if visible_quantity == whole_quantity:
        return
    row["quantity"] = visible_quantity
    if row.get("total_price") is not None:
        row["total_price"] = (
            Decimal(str(row["total_price"])) * visible_quantity / max(whole_quantity, 1)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    row["requested_quantity"] = visible_quantity
    row["confirmed_quantity"] = None
    for name in ("primary_employee_id", "additional_employee_id", "employees_assigned_by_id",
                 "employees_assigned_at", "vin", "assigned_vin", "vin_assigned_by", "vin_assigned_at"):
        row[name] = None
    row["dealer_action_documents"] = []


def _application_vehicle_dealer_filter_clause(
    dealer_filter: list[UUID] | None,
    distributor_company_id: UUID | None = None,
) -> sa.ColumnElement[bool]:
    """Allow the warehouse owner or assigned dealer of each vehicle line."""

    if distributor_company_id is not None:
        return _distributor_vehicle_clause(distributor_company_id)
    if dealer_filter is None:
        return sa.true()
    if not dealer_filter:
        return sa.false()
    return sa.or_(
        _application_vehicle_dealer_company_id_expr().in_(dealer_filter),
        ApplicationVehicle.dealer_company_id.in_(dealer_filter),
        _allocated_quantity_expr(dealer_filter) > 0,
    )


async def dealer_distribution_requires_scoped_read(
    session: AsyncSession, *, application_id: UUID, company_id: UUID,
) -> bool:
    """Whether a distribution recipient cannot see every application quantity.

    No new grants means unchanged legacy behavior. With a new grant, a whole
    line is insufficient if another vehicle or equipment line remains hidden.
    """
    has_distribution = (
        select(ApplicationVehicleDealerDistribution.id)
        .join(ApplicationVehicle,
              ApplicationVehicle.id == ApplicationVehicleDealerDistribution.application_vehicle_id)
        .where(ApplicationVehicle.application_id == application_id,
               ApplicationVehicleDealerDistribution.dealer_company_id == company_id)
        .exists()
    )
    hidden_vehicle_quantity = (
        select(ApplicationVehicle.id)
        .outerjoin(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
        )
        .where(
            ApplicationVehicle.application_id == application_id,
            sa.or_(
                ~func.coalesce(_application_vehicle_dealer_filter_clause([company_id]), False),
                func.coalesce(_visible_vehicle_quantity_expr([company_id]), 1)
                < func.coalesce(ApplicationVehicle.quantity, 1),
            ),
        )
        .exists()
    )
    hidden_equipment = (
        select(SpecialEquipmentApplicationItem.id)
        .where(
            SpecialEquipmentApplicationItem.application_id == application_id,
            ~func.coalesce(_special_equipment_dealer_filter_clause([company_id]), False),
        )
        .exists()
    )
    return bool(await session.scalar(select(sa.and_(
        has_distribution, sa.or_(hidden_vehicle_quantity, hidden_equipment),
    ))))


def _special_equipment_dealer_company_id_expr() -> sa.ColumnElement[Any]:
    """Resolve a special-equipment seller with a safe legacy fallback."""

    assigned_dealer_company_id = (
        select(LeasingApplication.dealer_company_id)
        .where(LeasingApplication.id == SpecialEquipmentApplicationItem.application_id)
        .correlate(SpecialEquipmentApplicationItem)
        .scalar_subquery()
    )
    return func.coalesce(
        SpecialEquipmentApplicationItem.seller_company_id,
        assigned_dealer_company_id,
    )


def _special_equipment_dealer_filter_clause(
    dealer_filter: list[UUID] | None,
) -> sa.ColumnElement[bool]:
    """Apply distributor scope to special-equipment application lines."""

    if dealer_filter is None:
        return sa.true()
    if not dealer_filter:
        return sa.false()
    return _special_equipment_dealer_company_id_expr().in_(dealer_filter)


def _vehicle_calculation_dealer_filter_clause(
    dealer_filter: list[UUID] | None,
    distributor_company_id: UUID | None = None,
) -> sa.ColumnElement[bool]:
    """Scope a persisted calculation through its application vehicle line."""

    if distributor_company_id is None:
        if dealer_filter is None:
            return sa.true()
        if not dealer_filter:
            return sa.false()

    return (
        select(ApplicationVehicle.id)
        .select_from(ApplicationVehicle)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
            isouter=True,
        )
        .where(
            ApplicationVehicle.application_id
            == LeasingApplicationVehicleCalculation.leasing_application_id,
            _application_vehicle_dealer_filter_clause(dealer_filter, distributor_company_id),
            _visible_vehicle_quantity_expr(dealer_filter, distributor_company_id) == ApplicationVehicle.quantity,
            sa.or_(
                sa.and_(
                    LeasingApplicationVehicleCalculation.vehicle_id.is_not(None),
                    ApplicationVehicle.product_id
                    == LeasingApplicationVehicleCalculation.vehicle_id,
                ),
                sa.and_(
                    LeasingApplicationVehicleCalculation.vehicle_id.is_(None),
                    ApplicationVehicle.product_id.is_(None),
                    sa.or_(
                        LeasingApplicationVehicleCalculation.modification_id.is_(None),
                        ApplicationVehicle.modification_id
                        == LeasingApplicationVehicleCalculation.modification_id,
                    ),
                ),
            ),
        )
        .correlate(LeasingApplicationVehicleCalculation)
        .exists()
    )


def dealer_child_ownership_clause(
    application_id: Any,
    company_id: Any,
) -> sa.ColumnElement[bool]:
    """True when a dealer owns at least one child line of an application."""

    owns_vehicle = (
        select(ApplicationVehicle.id)
        .select_from(ApplicationVehicle)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
            isouter=True,
        )
        .where(
            ApplicationVehicle.application_id == application_id,
            _application_vehicle_dealer_filter_clause([company_id]),
        )
        .correlate(LeasingApplication, Company)
        .exists()
    )
    owns_special_equipment = (
        select(SpecialEquipmentApplicationItem.id)
        .where(
            SpecialEquipmentApplicationItem.application_id == application_id,
            SpecialEquipmentApplicationItem.seller_company_id == company_id,
        )
        .correlate(LeasingApplication, Company)
        .exists()
    )
    return sa.or_(owns_vehicle, owns_special_equipment)


def distributor_child_ownership_clause(
    application_id: Any,
    dealer_ids: list[UUID] | None,
    distributor_company_id: UUID | None = None,
) -> sa.ColumnElement[bool]:
    """True when an application has a vehicle owned by a linked dealer."""

    if distributor_company_id is None:
        return sa.false()
    owns_linked_dealer_vehicle = (
        select(ApplicationVehicle.id)
        .select_from(ApplicationVehicle)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
            isouter=True,
        )
        .where(
            ApplicationVehicle.application_id == application_id,
            _distributor_vehicle_clause(distributor_company_id),
        )
        .correlate(LeasingApplication)
        .exists()
    )
    owns_special_equipment = (
        select(SpecialEquipmentApplicationItem.id)
        .where(
            SpecialEquipmentApplicationItem.application_id == application_id,
            _special_equipment_dealer_filter_clause(dealer_ids or []),
        )
        .correlate(LeasingApplication)
        .exists()
    )
    return sa.or_(owns_linked_dealer_vehicle, owns_special_equipment)


def _app_to_dict(row: LeasingApplication) -> dict[str, Any]:
    app = {
        "id": row.id,
        "storefront_id": row.storefront_id,
        "display_number": row.display_number,
        "source_type": row.source_type,
        "group_id": row.group_id,
        "group_number": row.display_number,
        "company_id": row.company_id,
        "dealer_company_id": row.dealer_company_id,
        "assigned_dealer_group_id": row.assigned_dealer_group_id,
        "dealer_assigned_by_id": row.dealer_assigned_by,
        "dealer_assigned_by": None,
        "dealer_assigned_at": row.dealer_assigned_at,
        "primary_employee_id": row.primary_employee_id,
        "additional_employee_id": row.additional_employee_id,
        "employees_assigned_by_id": row.employees_assigned_by,
        "employees_assigned_by": None,
        "employees_assigned_at": row.employees_assigned_at,
        "created_by": row.created_by,
        "vehicle_id": row.vehicle_id,
        "name": row.name,
        "email": row.email,
        "status": row.status,
        "total_amount": row.total_amount,
        "down_payment": row.down_payment,
        "down_payment_percent": row.down_payment_percent,
        "lease_term_months": row.lease_term_months,
        "monthly_payment": row.monthly_payment,
        "total_cost": row.total_cost,
        "markup": row.markup,
        "rate": row.rate,
        "total_interest": row.total_interest,
        "buyout_amount": row.buyout_amount,
        "vat_refund": row.vat_refund,
        "profit_tax_savings": row.profit_tax_savings,
        "total_savings": row.total_savings,
        "selected_leasing_companies": list(row.selected_leasing_companies)
        if row.selected_leasing_companies is not None
        else [],
        "leasing_company_comments": row.leasing_company_comments,
        "requested_documents": row.requested_documents,
        "comments_updated_at": row.comments_updated_at,
        "documents_requested_at": row.documents_requested_at,
        "client_visible_comment": row.client_visible_comment,
        "client_comment_updated_at": row.client_comment_updated_at,
        "questionnaire_completed": row.questionnaire_completed,
        "questionnaire_progress": row.questionnaire_progress,
        "current_stage": row.current_stage,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "deal_date": row.deal_date,
        "deal_documents": row.deal_documents if row.deal_documents is not None else [],
    }
    _attach_application_business_status(app)
    return app


def _special_equipment_application_item_to_dict(
    row: SpecialEquipmentApplicationItem,
) -> dict[str, Any]:
    return {
        column.key: getattr(row, column.key)
        for column in SpecialEquipmentApplicationItem.__table__.columns
    }


def _initial_requested_price_status(
    *, item_role: str, item_snapshot: dict[str, Any]
) -> str:
    if item_role != "component" and item_snapshot.get("price_on_request") is True:
        return "pending"
    return "none"


def _dealer_action_doc_to_dict(
    row: ApplicationVehicleDealerActionDocument,
) -> dict[str, Any]:
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


async def _dealer_action_docs_by_vehicle(
    session: AsyncSession, application_vehicle_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    if not application_vehicle_ids:
        return {}
    stmt = (
        select(ApplicationVehicleDealerActionDocument)
        .where(
            ApplicationVehicleDealerActionDocument.application_vehicle_id.in_(
                application_vehicle_ids
            )
        )
        .order_by(ApplicationVehicleDealerActionDocument.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    result: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(row.application_vehicle_id, []).append(
            _dealer_action_doc_to_dict(row)
        )
    return result


def _av_to_dict(
    row: ApplicationVehicle,
    *,
    dealer_action_documents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    prod_id = getattr(row, "product_id", getattr(row, "vehicle_id", None))
    return {
        "id": row.id,
        "application_id": row.application_id,
        "vehicle_id": prod_id,
        "product_id": prod_id,
        "dealer_company_id": row.dealer_company_id,
        "dealer_assigned_by_id": row.dealer_assigned_by,
        "dealer_assigned_at": row.dealer_assigned_at,
        "primary_employee_id": row.primary_employee_id,
        "additional_employee_id": row.additional_employee_id,
        "employees_assigned_by_id": row.employees_assigned_by,
        "employees_assigned_at": row.employees_assigned_at,
        "modification_id": row.modification_id,
        "quantity": row.quantity,
        "requested_quantity": row.requested_quantity,
        "confirmed_quantity": row.confirmed_quantity,
        "fulfillment_version": row.fulfillment_version,
        "unit_price": row.unit_price,
        "total_price": row.total_price,
        "comment": row.comment,
        "equipments": _with_nullable_option_comments(row.equipments),
        "services": _with_nullable_option_comments(row.services),
        "leasing_purpose": row.leasing_purpose,
        "leasing_purposes": selected_purposes(row.leasing_purposes, row.leasing_purpose),
        "regions": row.regions or [],
        "region": row.regions[0] if row.regions else None,
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


def _with_nullable_option_comments(
    items: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return [{**item, "comment": item.get("comment")} for item in items or []]


def _stable_application_vehicle_catalog_price(
    row: ApplicationVehicle, current_catalog_price: Any
) -> Any:
    unit_price = Decimal(str(row.unit_price)) if row.unit_price is not None else None
    if unit_price is not None and unit_price > 0:
        return unit_price
    return current_catalog_price


def _application_vehicle_correction_amount(
    catalog_price: Any, correction_type: Any, correction_value: Any
) -> Decimal | None:
    if catalog_price is None or correction_type is None or correction_value is None:
        return None
    base = Decimal(str(catalog_price))
    value = Decimal(str(correction_value))
    kind = str(correction_type)
    if kind in {"rubles_off", "rubles_up"}:
        amount = value
    elif kind in {"percent_off", "percent_up"}:
        amount = base * value / Decimal("100")
    elif kind == "fixed_price":
        amount = base - value
    else:
        return None
    return max(amount, Decimal("0")).quantize(Decimal("0.01"))


def _attach_application_vehicle_pricing(
    base: dict[str, Any],
    row: ApplicationVehicle,
    *,
    current_catalog_price: Any,
    catalog_price_to: Any,
) -> None:
    catalog_price = _stable_application_vehicle_catalog_price(
        row, current_catalog_price
    )
    base["catalog_price"] = catalog_price
    base["catalog_price_from"] = catalog_price
    base["catalog_price_to"] = catalog_price_to
    base["support"] = None
    base["discount"] = row.discount_value
    base["discount_amount"] = _application_vehicle_correction_amount(
        catalog_price,
        row.discount_type,
        row.discount_value,
    )
    base["markup_amount"] = _application_vehicle_correction_amount(
        catalog_price,
        row.markup_type,
        row.markup_value,
    )
    base["final_price"] = (
        row.final_price if row.final_price is not None else catalog_price
    )


def _lca_to_dict(row: LeasingCompanyApplication) -> dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "leasing_company_id": row.leasing_company_id,
        "status": row.status,
        "review_notes": row.review_notes,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _q_to_dict(row: ApplicationQuestionnaire) -> dict[str, Any]:
    return {
        column.key: getattr(row, column.key)
        for column in ApplicationQuestionnaire.__table__.columns
    }


def _coerce_questionnaire_payload(payload: dict[str, Any]) -> dict[str, Any]:
    columns = {
        column.key: column for column in ApplicationQuestionnaire.__table__.columns
    }
    result: dict[str, Any] = {}
    for key, value in payload.items():
        column = columns.get(key)
        if column is None:
            result[key] = value
            continue
        if isinstance(column.type, sa.Date) and not isinstance(
            column.type, sa.DateTime
        ):
            result[key] = _coerce_date_value(value)
            continue
        result[key] = value
    return result


def _coerce_date_value(value: Any) -> date | Any:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        for parser in (date.fromisoformat, _parse_dot_date):
            try:
                return parser(text[:10])
            except ValueError:
                continue
    return value


def _parse_dot_date(value: str) -> date:
    day, month, year = value.split(".", maxsplit=2)
    return date(int(year), int(month), int(day))


def _calc_to_dict(row: LeasingApplicationCalculation) -> dict[str, Any]:
    return {
        "leasing_application_id": row.leasing_application_id,
        "monthly_payment": row.monthly_payment,
        "rate": row.rate,
        "total_cost": row.total_cost,
        "total_interest": row.total_interest,
        "buyout_amount": row.buyout_amount,
        "vat_refund": row.vat_refund,
        "profit_tax_savings": row.profit_tax_savings,
        "total_savings": row.total_savings,
        "base_total": row.base_total,
        "vehicle_discount_support": row.vehicle_discount_support,
        "dealer_commission_support": row.dealer_commission_support,
        "down_payment_support": row.down_payment_support,
        "interest_support": row.interest_support,
        "effective_total": row.effective_total,
        "effective_down_payment": row.effective_down_payment,
        "selected_support": row.selected_support,
        "support_per_vehicle": row.support_per_vehicle,
        "support_per_program": row.support_per_program,
        "support_program_details": row.support_program_details,
        "calculations_per_vehicle": row.calculations_per_vehicle,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _vehicle_calc_to_dict(
    row: LeasingApplicationVehicleCalculation,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "leasing_application_id": row.leasing_application_id,
        "vehicle_id": row.vehicle_id,
        "modification_id": row.modification_id,
        "color": row.color,
        "quantity": row.quantity,
        "unit_price": row.unit_price,
        "total_amount": row.total_amount,
        "down_payment": row.down_payment,
        "down_payment_percent": row.down_payment_percent,
        "lease_term_months": row.lease_term_months,
        "buyout_amount": row.buyout_amount,
        "monthly_payment": row.monthly_payment,
        "rate": row.rate,
        "total_cost": row.total_cost,
        "total_interest": row.total_interest,
        "vat_refund": row.vat_refund,
        "profit_tax_savings": row.profit_tax_savings,
        "total_savings": row.total_savings,
        "sort_order": row.sort_order,
        "created_at": row.created_at,
    }


def _comment_to_dict(row: LeasingApplicationComment) -> dict[str, Any]:
    return {
        "id": row.id,
        "leasing_application_id": row.leasing_application_id,
        "comment_type": row.comment_type,
        "comment_text": row.comment_text,
        "created_by": row.created_by,
        "created_at": row.created_at,
    }


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@timed_repository
async def get_by_id(
    session: AsyncSession,
    application_id: uuid.UUID,
    *,
    dealer_filter: list[UUID] | None = None,
    distributor_company_id: UUID | None = None,
    for_update: bool = False,
) -> dict[str, Any] | None:
    row = await session.get(
        LeasingApplication, application_id,
        with_for_update=for_update, populate_existing=for_update,
    )
    if row is None:
        return None
    app = _app_to_dict(row)
    await _attach_group_statuses(session, [app])
    await _attach_commerce_totals(
        session,
        [app],
        dealer_filter=dealer_filter,
        distributor_company_id=distributor_company_id,
    )
    return app


@timed_repository
async def lock_application_price_state(
    session: AsyncSession,
    application_id: UUID,
) -> dict[str, Any] | None:
    """Lock one application and its current billable equipment rows.

    Dealer price updates and admin LC assignment share this primitive so the
    two transitions cannot pass their mutually exclusive guards concurrently.
    """

    application = (
        await session.execute(
            select(LeasingApplication)
            .where(LeasingApplication.id == application_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if application is None:
        return None
    items = (
        (
            await session.execute(
                select(SpecialEquipmentApplicationItem)
                .where(
                    SpecialEquipmentApplicationItem.application_id
                    == application_id,
                    SpecialEquipmentApplicationItem.item_status.in_(
                        ("active", "reserved")
                    ),
                    SpecialEquipmentApplicationItem.item_role != "component",
                )
                .order_by(SpecialEquipmentApplicationItem.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    return {
        "application": _app_to_dict(application),
        "items": [
            _special_equipment_application_item_to_dict(item) for item in items
        ],
    }


@timed_repository
async def get_special_equipment_application_item(
    session: AsyncSession,
    item_id: UUID,
) -> dict[str, Any] | None:
    item = await session.get(SpecialEquipmentApplicationItem, item_id)
    if item is None:
        return None
    return _special_equipment_application_item_to_dict(item)


@timed_repository
async def update_special_equipment_application_item_price(
    session: AsyncSession,
    *,
    item_id: UUID,
    unit_price: Decimal,
    total_price: Decimal,
    price_status: str,
    price_set_by: UUID,
    price_set_at: datetime,
) -> dict[str, Any]:
    item = (
        await session.execute(
            sa.update(SpecialEquipmentApplicationItem)
            .where(SpecialEquipmentApplicationItem.id == item_id)
            .values(
                unit_price=unit_price,
                total_price=total_price,
                price_status=price_status,
                price_set_by=price_set_by,
                price_set_at=price_set_at,
                updated_at=price_set_at,
            )
            .returning(SpecialEquipmentApplicationItem)
        )
    ).scalar_one()
    await session.flush()
    return _special_equipment_application_item_to_dict(item)


@timed_repository
async def append_special_equipment_price_change(
    session: AsyncSession,
    *,
    item_id: UUID,
    old_price: Decimal | None,
    new_price: Decimal,
    changed_by: UUID,
    changed_at: datetime,
    source: str,
) -> dict[str, Any]:
    row = SpecialEquipmentPriceChangeLog(
        item_id=item_id,
        old_price=old_price,
        new_price=new_price,
        changed_by=changed_by,
        changed_at=changed_at,
        source=source,
    )
    session.add(row)
    await session.flush()
    return {
        column.key: getattr(row, column.key)
        for column in SpecialEquipmentPriceChangeLog.__table__.columns
    }


@timed_repository
async def update_application_total_amount(
    session: AsyncSession,
    *,
    application_id: UUID,
    total_amount: Decimal,
) -> None:
    await session.execute(
        sa.update(LeasingApplication)
        .where(LeasingApplication.id == application_id)
        .values(total_amount=total_amount, updated_at=datetime.now(UTC))
    )
    await session.flush()


@timed_repository
async def count_pending_requested_price_items(
    session: AsyncSession,
    application_ids: list[UUID],
) -> dict[UUID, int]:
    if not application_ids:
        return {}
    rows = (
        await session.execute(
            select(
                SpecialEquipmentApplicationItem.application_id,
                func.count(SpecialEquipmentApplicationItem.id),
            )
            .where(
                SpecialEquipmentApplicationItem.application_id.in_(application_ids),
                SpecialEquipmentApplicationItem.item_status.in_(
                    ("active", "reserved")
                ),
                SpecialEquipmentApplicationItem.item_role != "component",
                SpecialEquipmentApplicationItem.price_status == "pending",
            )
            .group_by(SpecialEquipmentApplicationItem.application_id)
        )
    ).all()
    return {application_id: int(count) for application_id, count in rows}


@timed_repository
async def list_special_equipment_price_changes(
    session: AsyncSession,
    *,
    application_id: UUID,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    condition = (
        SpecialEquipmentApplicationItem.application_id == application_id
    )
    total = int(
        (
            await session.execute(
                select(func.count(SpecialEquipmentPriceChangeLog.id))
                .select_from(SpecialEquipmentPriceChangeLog)
                .join(
                    SpecialEquipmentApplicationItem,
                    SpecialEquipmentApplicationItem.id
                    == SpecialEquipmentPriceChangeLog.item_id,
                )
                .where(condition)
            )
        ).scalar_one()
    )
    rows = (
        await session.execute(
            select(
                SpecialEquipmentPriceChangeLog,
                User.name.label("changed_by_name"),
            )
            .join(
                SpecialEquipmentApplicationItem,
                SpecialEquipmentApplicationItem.id
                == SpecialEquipmentPriceChangeLog.item_id,
            )
            .join(User, User.id == SpecialEquipmentPriceChangeLog.changed_by)
            .where(condition)
            .order_by(
                SpecialEquipmentPriceChangeLog.changed_at.desc(),
                SpecialEquipmentPriceChangeLog.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items = []
    for change, changed_by_name in rows:
        item = {
            column.key: getattr(change, column.key)
            for column in SpecialEquipmentPriceChangeLog.__table__.columns
        }
        item["changed_by_name"] = changed_by_name
        items.append(item)
    return items, total


@timed_repository
async def list_for_user(  # noqa: PLR0912, PLR0915
    session: AsyncSession,
    *,
    user_id: UUID,
    role: str,
    company_id: UUID | None,
    leasing_company_id: UUID | None = None,
    dealer_filter: list[UUID] | None = None,
    can_view_company_applications: bool = True,
    include_authored_client_applications: bool = False,
    status: str | None = None,
    personal_clause: Any = None,
    source_types: tuple[str, ...] = (),
    search: str | None = None,
    page: int = 1,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Return applications visible to the given user, role-filtered.

    For ``client`` / ``dealer``: return the parent application even after
    admin dispatches it to LCs. Child LCA rows are shown only inside the
    application checkout flow.

    Returns a tuple of (items, total_count).
    """
    where_clause: Any = None
    status_filter = (status or "").strip() or None
    source_conditions = application_source_filters(source_types=source_types, search=search)

    if role == "carcraft_employee":
        pass
    elif role == "distributor":
        if dealer_filter is None:
            dealer_filter = [company_id] if company_id is not None else []
        where_clause = distributor_child_ownership_clause(
            LeasingApplication.id, dealer_filter, company_id
        )
    elif role == "leasing_company":
        lc_id = leasing_company_id if leasing_company_id is not None else company_id
        if lc_id is None:
            return [], 0
        # Use LCA table for filtering — single source of truth for LC visibility.
        count_stmt = (
            select(func.count(LeasingApplication.id))
            .join(
                LeasingCompanyApplication,
                LeasingCompanyApplication.application_id == LeasingApplication.id,
            )
            .where(LeasingCompanyApplication.leasing_company_id == lc_id)
        )
        if status_filter is not None:
            count_stmt = count_stmt.where(
                LeasingCompanyApplication.status == status_filter
            )
        count_stmt = count_stmt.where(*source_conditions)
        total = (await session.execute(count_stmt)).scalar() or 0

        sort_at = func.coalesce(
            LeasingCompanyApplication.updated_at,
            LeasingCompanyApplication.submitted_at,
            LeasingApplication.updated_at,
            LeasingApplication.created_at,
            LeasingCompanyApplication.created_at,
        )
        stmt = (
            select(LeasingApplication)
            .join(
                LeasingCompanyApplication,
                LeasingCompanyApplication.application_id == LeasingApplication.id,
            )
            .where(LeasingCompanyApplication.leasing_company_id == lc_id)
            .order_by(sort_at.desc(), LeasingApplication.created_at.desc())
        )
        if status_filter is not None:
            stmt = stmt.where(LeasingCompanyApplication.status == status_filter)
        stmt = stmt.where(*source_conditions)
        if limit is not None:
            stmt = stmt.offset((page - 1) * limit).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        apps = [_app_to_dict(r) for r in rows]
        await _attach_group_statuses(session, apps)
        await _attach_commerce_totals(session, apps)
        await _attach_company_info(session, apps)
        return apps, total
    elif role == "dealer":
        # Keep author visibility for legacy dealer accounts that do not have
        # a company yet. Company-linked dealers additionally see mixed
        # applications whenever they own at least one child item.
        dealer_clauses: list[Any] = [LeasingApplication.created_by == user_id]
        if company_id is not None:
            dealer_clauses.extend(
                (
                    LeasingApplication.dealer_company_id == company_id,
                    sa.and_(
                        LeasingApplication.dealer_company_id.is_(None),
                        LeasingApplication.company_id == company_id,
                    ),
                    dealer_child_ownership_clause(
                        LeasingApplication.id,
                        company_id,
                    ),
                )
            )
        where_clause = sa.or_(*dealer_clauses)
    elif role == "client":
        client_clauses: list[Any] = []
        if include_authored_client_applications:
            client_clauses.append(LeasingApplication.created_by == user_id)
        if company_id is not None and can_view_company_applications:
            client_clauses.append(LeasingApplication.company_id == company_id)
        if not client_clauses:
            return [], 0
        where_clause = sa.or_(*client_clauses)
    if personal_clause is not None:
        where_clause = sa.and_(where_clause, personal_clause) if where_clause is not None else personal_clause

    count_stmt = select(func.count(LeasingApplication.id))
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
    if status_filter is not None:
        count_stmt = count_stmt.where(LeasingApplication.status == status_filter)
    count_stmt = count_stmt.where(*source_conditions)
    total = (await session.execute(count_stmt)).scalar() or 0

    sort_at = func.coalesce(
        LeasingApplication.updated_at,
        LeasingApplication.created_at,
    )
    stmt = select(LeasingApplication).order_by(
        sort_at.desc(), LeasingApplication.created_at.desc()
    )
    if where_clause is not None:
        stmt = stmt.where(where_clause)
    if status_filter is not None:
        stmt = stmt.where(LeasingApplication.status == status_filter)
    stmt = stmt.where(*source_conditions)
    if limit is not None:
        stmt = stmt.offset((page - 1) * limit).limit(limit)

    rows = (await session.execute(stmt)).scalars().all()
    apps = [_app_to_dict(r) for r in rows]
    await _attach_group_statuses(session, apps)
    await _attach_commerce_totals(
        session,
        apps,
        dealer_filter=dealer_filter,
        distributor_company_id=company_id if role == "distributor" else None,
    )
    await _attach_company_info(session, apps)
    return apps, int(total)


async def distributor_can_view_application(
    session: AsyncSession,
    *,
    application_id: UUID,
    dealer_ids: list[UUID] | None,
    distributor_company_id: UUID | None = None,
) -> bool:
    """Return whether a linked dealer owns at least one application vehicle."""

    stmt = (
        select(LeasingApplication.id)
        .where(
            LeasingApplication.id == application_id,
            distributor_child_ownership_clause(LeasingApplication.id, dealer_ids, distributor_company_id),
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def distributor_can_view_application_vehicle(
    session: AsyncSession,
    *,
    application_vehicle_id: UUID,
    dealer_ids: list[UUID] | None,  # noqa: ARG001 - compatibility for existing callers
    distributor_company_id: UUID | None = None,
) -> bool:
    """Return whether a linked dealer owns the exact application vehicle row."""
    if distributor_company_id is None:
        return False
    stmt = (
        select(ApplicationVehicle.id)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
            isouter=True,
        )
        .where(
            ApplicationVehicle.id == application_vehicle_id,
            _distributor_vehicle_clause(distributor_company_id),
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


@timed_repository
async def dealer_company_owns_application_item(
    session: AsyncSession,
    *,
    application_id: UUID,
    company_id: UUID,
) -> bool:
    """Return whether ``company_id`` owns any persisted application child."""

    stmt = select(dealer_child_ownership_clause(application_id, company_id))
    return bool((await session.execute(stmt)).scalar_one())


@timed_repository
async def dealer_company_owns_application_vehicle(
    session: AsyncSession,
    *,
    application_vehicle_id: UUID,
    company_id: UUID,
) -> bool:
    """Return whether ``company_id`` owns the exact vehicle child row."""

    stmt = (
        select(ApplicationVehicle.id)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
            isouter=True,
        )
        .where(
            ApplicationVehicle.id == application_vehicle_id,
            _application_vehicle_dealer_filter_clause([company_id]),
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _attach_group_statuses(
    session: AsyncSession, applications: list[dict[str, Any]]
) -> None:
    if not applications:
        return

    application_ids = [app["id"] for app in applications]
    stmt = select(
        LeasingCompanyApplication.application_id,
        LeasingCompanyApplication.status,
    ).where(LeasingCompanyApplication.application_id.in_(application_ids))
    statuses_by_application: dict[UUID, list[str]] = {}
    for application_id, status in (await session.execute(stmt)).all():
        statuses_by_application.setdefault(application_id, []).append(str(status))

    for app in applications:
        group_statuses = statuses_by_application.get(app["id"], [])
        status, label = _group_business_status(group_statuses)
        app["group_status"] = status
        app["group_status_label"] = label


async def _attach_company_info(
    session: AsyncSession, applications: list[dict[str, Any]]
) -> None:
    if not applications:
        return

    company_ids = {
        company_id
        for app in applications
        for company_id in (
            app.get("company_id"),
            app.get("dealer_company_id"),
        )
        if company_id
    }
    if not company_ids:
        return

    stmt = select(Company.id, Company.name, Company.inn).where(
        Company.id.in_(company_ids)
    )
    companies = {
        row.id: {"name": row.name, "inn": row.inn}
        for row in (await session.execute(stmt)).all()
    }
    for app in applications:
        company = companies.get(app.get("company_id"))
        if company is None:
            app["company_name"] = None
            app["company_inn"] = None
        else:
            app["company_name"] = company["name"]
            app["company_inn"] = company["inn"]
        assigned_dealer = companies.get(app.get("dealer_company_id"))
        app["assigned_dealer"] = (
            {
                "id": app.get("dealer_company_id"),
                "name": assigned_dealer["name"],
                "inn": assigned_dealer["inn"],
            }
            if assigned_dealer is not None
            else None
        )


async def _attach_commerce_totals(
    session: AsyncSession,
    applications: list[dict[str, Any]],
    *,
    dealer_filter: list[UUID] | None = None,
    distributor_company_id: UUID | None = None,
) -> None:
    if not applications:
        return

    application_ids = [app["id"] for app in applications]
    vehicle_scope = _application_vehicle_dealer_filter_clause(dealer_filter, distributor_company_id)
    special_equipment_scope = _special_equipment_dealer_filter_clause(dealer_filter)
    visible_quantity = _visible_vehicle_quantity_expr(dealer_filter, distributor_company_id)
    visible_total = _visible_vehicle_total_expr(dealer_filter, distributor_company_id)
    stmt = (
        select(
            ApplicationVehicle.application_id,
            func.coalesce(func.sum(visible_total), 0),
            func.coalesce(func.sum(visible_quantity), 0),
        )
        .select_from(ApplicationVehicle)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
            isouter=True,
        )
        .where(
            ApplicationVehicle.application_id.in_(application_ids),
            vehicle_scope,
            ~sa.exists().where(
                SpecialEquipmentApplicationItem.application_id == ApplicationVehicle.application_id,
                SpecialEquipmentApplicationItem.product_id == ApplicationVehicle.product_id,
            ),
        )
        .group_by(ApplicationVehicle.application_id)
    )
    vehicle_totals = {
        application_id: {
            "total_vehicles_price": total_vehicles_price,
            "vehicles_count": int(vehicles_count or 0),
        }
        for application_id, total_vehicles_price, vehicles_count in (
            await session.execute(stmt)
        ).all()
    }

    effective_active_quantity = sa.case(
        (
            visible_quantity > 0,
            visible_quantity,
        ),
        else_=1,
    )
    active_vehicle_stmt = (
        select(
            ApplicationVehicle.application_id,
            func.coalesce(func.sum(_visible_vehicle_total_expr(
                dealer_filter, distributor_company_id, normalize_quantity=True,
            )), 0),
            func.coalesce(func.sum(effective_active_quantity), 0),
        )
        .where(
            ApplicationVehicle.application_id.in_(application_ids),
            ApplicationVehicle.car_status.in_(("active", "confirmed", "replacement")),
            vehicle_scope,
            ~sa.exists().where(
                SpecialEquipmentApplicationItem.application_id == ApplicationVehicle.application_id,
                SpecialEquipmentApplicationItem.product_id == ApplicationVehicle.product_id,
            ),
        )
        .select_from(ApplicationVehicle)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
            isouter=True,
        )
        .group_by(ApplicationVehicle.application_id)
    )
    active_vehicle_totals = {
        application_id: {
            "total_vehicles_price": total_vehicles_price,
            "vehicles_count": int(vehicles_count or 0),
        }
        for application_id, total_vehicles_price, vehicles_count in (
            await session.execute(active_vehicle_stmt)
        ).all()
    }

    special_equipment_stmt = (
        select(
            SpecialEquipmentApplicationItem.application_id,
            func.coalesce(
                func.sum(
                    func.coalesce(
                        func.nullif(
                            SpecialEquipmentApplicationItem.total_price,
                            0,
                        ),
                        func.nullif(
                            SpecialEquipmentApplicationItem.unit_price,
                            0,
                        ),
                        0,
                    )
                ),
                0,
            ),
            func.count(SpecialEquipmentApplicationItem.id),
            func.count(
                sa.case(
                    (
                        sa.and_(
                            SpecialEquipmentApplicationItem.item_role != "component",
                            SpecialEquipmentApplicationItem.total_price.is_(None),
                            SpecialEquipmentApplicationItem.unit_price.is_(None),
                        ),
                        1,
                    ),
                )
            ),
        )
        .where(
            SpecialEquipmentApplicationItem.application_id.in_(application_ids),
            SpecialEquipmentApplicationItem.item_status.in_(("active", "reserved")),
            special_equipment_scope,
        )
        .group_by(SpecialEquipmentApplicationItem.application_id)
    )
    special_equipment_totals = {
        application_id: {
            "total_special_equipment_price": (
                None if unknown_billable_count else total_price
            ),
            "special_equipment_count": int(items_count or 0),
        }
        for application_id, total_price, items_count, unknown_billable_count in (
            await session.execute(special_equipment_stmt)
        ).all()
    }

    for app in applications:
        app_id = app["id"]
        vehicle = vehicle_totals.get(app_id, {})
        active_vehicle = active_vehicle_totals.get(app_id, {})
        special_equipment = special_equipment_totals.get(app_id, {})
        vehicle_price = vehicle.get("total_vehicles_price", Decimal("0"))
        active_vehicle_price = active_vehicle.get(
            "total_vehicles_price",
            Decimal("0"),
        )
        special_equipment_price = special_equipment.get(
            "total_special_equipment_price",
            Decimal("0"),
        )
        vehicles_count = vehicle.get("vehicles_count", 0)
        active_vehicles_count = active_vehicle.get("vehicles_count", 0)
        special_equipment_count = special_equipment.get(
            "special_equipment_count",
            0,
        )

        # Keep the legacy vehicle-only fields stable. New callers use the
        # commerce totals, which cover both FK-correct persistence models.
        app["total_vehicles_price"] = vehicle_price
        app["vehicles_count"] = vehicles_count
        app["total_special_equipment_price"] = special_equipment_price
        app["special_equipment_count"] = special_equipment_count
        app["total_items_price"] = (
            None
            if special_equipment_price is None
            else active_vehicle_price + special_equipment_price
        )
        app["items_count"] = active_vehicles_count + special_equipment_count


def _lc_children_exist_subq() -> Any:
    """EXISTS sub-query: this application has at least one LC dispatch row."""
    return (
        select(LeasingCompanyApplication.id)
        .where(
            LeasingCompanyApplication.application_id == LeasingApplication.id,
            LeasingCompanyApplication.leasing_company_id.is_not(None),
        )
        .exists()
    )


@timed_repository
async def has_lc_children(session: AsyncSession, application_id: uuid.UUID) -> bool:
    """True if admin has already dispatched this application to any LC."""
    stmt = (
        select(LeasingCompanyApplication.id)
        .where(
            LeasingCompanyApplication.application_id == application_id,
            LeasingCompanyApplication.leasing_company_id.is_not(None),
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


@timed_repository
async def list_application_vehicles(
    session: AsyncSession,
    application_id: uuid.UUID,
    *,
    dealer_filter: list[UUID] | None = None,
    distributor_company_id: UUID | None = None,
) -> list[dict[str, Any]]:
    if distributor_company_id is None and dealer_filter is not None and not dealer_filter:
        return []
    stmt = (
        select(ApplicationVehicle)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
            isouter=True,
        )
        .where(
            ApplicationVehicle.application_id == application_id,
            _application_vehicle_dealer_filter_clause(dealer_filter, distributor_company_id),
        )
        .order_by(ApplicationVehicle.id)
    )
    rows = (await session.execute(stmt)).scalars().all()
    docs = await _dealer_action_docs_by_vehicle(session, [r.id for r in rows])
    items = [_av_to_dict(r, dealer_action_documents=docs.get(r.id, [])) for r in rows]
    from infrastructure.repositories import (
        vehicle_fulfillment_repository as fulfillment,
    )
    await fulfillment.enrich_line_composition(session, items)
    return items


@timed_repository
async def get_application_item_edit_rows(
    session: AsyncSession,
    application_id: UUID,
    line_ids: list[UUID],
) -> list[dict[str, Any]]:
    """Lock editable line identities in a stable order; never leak another application."""
    if not line_ids:
        return []
    result: list[dict[str, Any]] = []
    vehicle_rows = await session.execute(
        select(ApplicationVehicle.id.label("line_id"), sa.literal("vehicle").label("kind"), ApplicationVehicle.leasing_purpose, ApplicationVehicle.leasing_purposes)
        .where(ApplicationVehicle.application_id == application_id, ApplicationVehicle.id.in_(line_ids))
        .order_by(ApplicationVehicle.id)
        .with_for_update()
    )
    result.extend(dict(row) for row in vehicle_rows.mappings())

    line_ids_set = set(line_ids)
    se_rows = await session.execute(
        select(
            SpecialEquipmentApplicationItem.id,
            SpecialEquipmentApplicationItem.group_id,
            SpecialEquipmentApplicationItem.leasing_purpose,
            SpecialEquipmentApplicationItem.leasing_purposes,
        )
        .where(
            SpecialEquipmentApplicationItem.application_id == application_id,
            sa.or_(
                SpecialEquipmentApplicationItem.id.in_(line_ids),
                SpecialEquipmentApplicationItem.group_id.in_(line_ids),
            ),
        )
        .order_by(SpecialEquipmentApplicationItem.id)
        .with_for_update()
    )
    seen_se_lines: set[UUID] = set()
    for item_id, group_id, legacy, purposes in se_rows.all():
        if item_id in line_ids_set and item_id not in seen_se_lines:
            seen_se_lines.add(item_id)
            result.append({"line_id": item_id, "kind": "special_equipment", "leasing_purpose": legacy, "leasing_purposes": purposes})
        if group_id in line_ids_set and group_id not in seen_se_lines:
            seen_se_lines.add(group_id)
            result.append({"line_id": group_id, "kind": "special_equipment", "leasing_purpose": legacy, "leasing_purposes": purposes})
    return result


@timed_repository
async def update_application_item_fields(
    session: AsyncSession,
    application_id: UUID,
    items: list[dict[str, Any]],
) -> None:
    """Apply the complete, validated edit batch in the caller's transaction."""
    await lock_purpose_application(session, application_id)
    for item in items:
        if item["kind"] == "special_equipment":
            group_subq = (
                select(SpecialEquipmentApplicationItem.group_id)
                .where(
                    SpecialEquipmentApplicationItem.application_id == application_id,
                    SpecialEquipmentApplicationItem.id == item["line_id"],
                )
                .scalar_subquery()
            )
            updated = await session.execute(
                sa.update(SpecialEquipmentApplicationItem)
                .where(
                    SpecialEquipmentApplicationItem.application_id == application_id,
                    sa.or_(
                        SpecialEquipmentApplicationItem.id == item["line_id"],
                        SpecialEquipmentApplicationItem.group_id == item["line_id"],
                        sa.and_(
                            SpecialEquipmentApplicationItem.group_id == group_subq,
                            SpecialEquipmentApplicationItem.group_id.is_not(None),
                        ),
                    ),
                )
                .values(
                    leasing_purpose=item["leasing_purpose"],
                    leasing_purposes=item["leasing_purposes"],
                    regions=item["regions"],
                    comment=item["comment"],
                ).returning(SpecialEquipmentApplicationItem.product_id)
            )
            product_ids = list(updated.scalars())
            await session.execute(sa.update(ApplicationVehicle).where(
                ApplicationVehicle.application_id == application_id,
                ApplicationVehicle.product_id.in_(product_ids),
            ).values(leasing_purpose=item["leasing_purpose"], leasing_purposes=item["leasing_purposes"]))
        else:
            await session.execute(
                sa.update(ApplicationVehicle)
                .where(
                    ApplicationVehicle.application_id == application_id,
                    ApplicationVehicle.id == item["line_id"],
                )
                .values(
                    leasing_purpose=item["leasing_purpose"],
                    leasing_purposes=item["leasing_purposes"],
                    regions=item["regions"],
                    comment=item["comment"],
                )
            )
    await session.flush()
    await sync_vehicle_purchase_purpose(session, application_id)



@timed_repository
async def list_vehicle_distribution_context(
    session: AsyncSession, application_vehicle_ids: list[UUID],
) -> dict[UUID, dict[str, Any]]:
    """Batch stock owner and legacy full assignments for already scoped lines."""
    if not application_vehicle_ids:
        return {}
    owner = aliased(Company, name="distribution_stock_owner")
    legacy = aliased(Company, name="distribution_legacy_dealer")
    rows = (await session.execute(
        select(
            ApplicationVehicle.id, ApplicationVehicle.quantity,
            Warehouse.company_id.label("stock_owner_id"),
            owner.name.label("stock_owner_name"), owner.inn.label("stock_owner_inn"),
            owner.company_type.label("stock_owner_type"),
            legacy.id.label("legacy_dealer_id"), legacy.name.label("legacy_dealer_name"),
            legacy.inn.label("legacy_dealer_inn"),
        )
        .select_from(ApplicationVehicle)
        .outerjoin(SpecialEquipmentProduct, SpecialEquipmentProduct.id == ApplicationVehicle.product_id)
        .outerjoin(Warehouse, Warehouse.id == SpecialEquipmentProduct.warehouse_id)
        .outerjoin(owner, owner.id == Warehouse.company_id)
        .outerjoin(legacy, sa.and_(legacy.id == ApplicationVehicle.dealer_company_id,
                                  legacy.company_type == "dealer"))
        .where(ApplicationVehicle.id.in_(application_vehicle_ids))
    )).mappings().all()
    return {row["id"]: dict(row) for row in rows}


@timed_repository
async def list_application_vehicle_item_rows(
    session: AsyncSession,
    application_ids: list[UUID],
    *,
    dealer_filter: list[UUID] | None = None,
    distributor_company_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Return the minimal vehicle data used by the unified item projection."""
    if not application_ids or (distributor_company_id is None and dealer_filter is not None and not dealer_filter):
        return []

    stmt = (
        select(
            ApplicationVehicle.id,
            ApplicationVehicle.application_id,
            ApplicationVehicle.product_id.label("product_id"),
            ApplicationVehicle.product_id.label("vehicle_id"),
            ApplicationVehicle.modification_id,
            _visible_vehicle_quantity_expr(dealer_filter, distributor_company_id).label("quantity"),
            ApplicationVehicle.quantity.label("whole_quantity"),
            ApplicationVehicle.unit_price,
            _visible_vehicle_total_expr(dealer_filter, distributor_company_id).label("total_price"),
            ApplicationVehicle.comment,
            ApplicationVehicle.leasing_purpose,
            ApplicationVehicle.leasing_purposes,
            ApplicationVehicle.regions,
            ApplicationVehicle.dealer_comment,
            ApplicationVehicle.discount_type,
            ApplicationVehicle.discount_value,
            ApplicationVehicle.discount_show_catalog_price,
            ApplicationVehicle.markup_type,
            ApplicationVehicle.markup_value,
            ApplicationVehicle.markup_show_catalog_price,
            ApplicationVehicle.final_price,
            ApplicationVehicle.car_status.label("status"),
            ApplicationVehicle.created_at,
            sa.cast(None, sa.dialects.postgresql.JSONB).label("images"),
            SpecialEquipmentProduct.vin,
            SpecialEquipmentProduct.manufacture_year.label("year"),
            SpecialEquipmentMark.name.label("mark_name"),
            SpecialEquipmentMark.name.label("mark_cyrillic_name"),
            SpecialEquipmentModel.name.label("model_name"),
            SpecialEquipmentModel.name.label("model_cyrillic_name"),
            SpecialEquipmentModification.name.label("modification_name"),
            SpecialEquipmentProduct.superstructure_name,
            SpecialEquipmentProduct.superstructure_manufacturer,
            SpecialEquipmentProduct.price.label("catalog_price_from"),
            SpecialEquipmentMark.name.label("fallback_mark_name"),
            SpecialEquipmentMark.name.label("fallback_mark_cyrillic_name"),
            SpecialEquipmentModel.name.label("fallback_model_name"),
            SpecialEquipmentModel.name.label("fallback_model_cyrillic_name"),
            SpecialEquipmentModification.name.label("fallback_modification_name"),
            SpecialEquipmentProduct.price.label("fallback_catalog_price_from"),
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
        .where(
            ApplicationVehicle.application_id.in_(application_ids),
            _application_vehicle_dealer_filter_clause(dealer_filter, distributor_company_id),
        )
        .order_by(ApplicationVehicle.application_id, ApplicationVehicle.id)
    )
    result = await session.execute(stmt)
    return [dict(row) for row in result.mappings().all()]


@timed_repository
async def list_application_special_equipment_item_rows(
    session: AsyncSession,
    application_ids: list[UUID],
    *,
    dealer_filter: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    """Return all special-equipment lines with snapshot-safe display data.

    Removed/replaced/rejected rows remain part of the immutable application
    history and are therefore present in the read model. Commerce totals are
    calculated separately and include only current active/reserved lines.
    """

    if not application_ids or (dealer_filter is not None and not dealer_filter):
        return []

    primary_image_id = (
        select(SpecialEquipmentProductImage.id)
        .where(SpecialEquipmentProductImage.product_id == SpecialEquipmentProduct.id)
        .order_by(
            SpecialEquipmentProductImage.is_primary.desc(),
            SpecialEquipmentProductImage.sort_order,
            SpecialEquipmentProductImage.id,
        )
        .limit(1)
        .correlate(SpecialEquipmentProduct)
        .scalar_subquery()
    )
    composite_product = aliased(
        SpecialEquipmentProduct,
        name="application_item_composite_product",
    )
    offer_detail_is_public = sa.and_(
        SpecialEquipmentApplicationItem.item_role == "offer",
        SpecialEquipmentProduct.publication_status
        == SPECIAL_EQUIPMENT_PUBLICATION_PUBLISHED,
        SpecialEquipmentProduct.sale_status.in_(
            SPECIAL_EQUIPMENT_PUBLIC_DETAIL_SALE_STATUSES
        ),
        special_equipment_visible_for_storefront(
            LeasingApplication.storefront_id,
        ),
    )
    component_detail_is_public = sa.and_(
        SpecialEquipmentApplicationItem.item_role == "component",
        SpecialEquipmentApplicationItem.item_snapshot["is_base"].astext
        == "true",
        composite_product.publication_status
        == SPECIAL_EQUIPMENT_PUBLICATION_PUBLISHED,
        composite_product.sale_status.in_(
            SPECIAL_EQUIPMENT_PUBLIC_DETAIL_SALE_STATUSES
        ),
        special_equipment_visible_for_storefront(
            LeasingApplication.storefront_id,
            product=composite_product,
        ),
    )
    detail_product_id = sa.case(
        (
            offer_detail_is_public,
            SpecialEquipmentProduct.id,
        ),
        (
            component_detail_is_public,
            composite_product.id,
        ),
        else_=None,
    ).label("detail_product_id")
    detail_product_slug = sa.case(
        (
            offer_detail_is_public,
            SpecialEquipmentProduct.slug,
        ),
        (
            component_detail_is_public,
            composite_product.slug,
        ),
        else_=None,
    ).label("detail_product_slug")
    stmt = (
        select(
            SpecialEquipmentApplicationItem.id,
            SpecialEquipmentApplicationItem.application_id,
            SpecialEquipmentApplicationItem.product_id,
            SpecialEquipmentApplicationItem.group_id,
            SpecialEquipmentApplicationItem.parent_group_id,
            SpecialEquipmentApplicationItem.source_cart_item_id,
            SpecialEquipmentApplicationItem.seller_company_id,
            SpecialEquipmentApplicationItem.unit_price,
            SpecialEquipmentApplicationItem.total_price,
            SpecialEquipmentApplicationItem.currency_code,
            SpecialEquipmentApplicationItem.item_status.label("status"),
            SpecialEquipmentApplicationItem.item_role,
            SpecialEquipmentApplicationItem.price_status,
            SpecialEquipmentApplicationItem.price_set_by,
            SpecialEquipmentApplicationItem.price_set_at,
            SpecialEquipmentApplicationItem.item_snapshot,
            SpecialEquipmentApplicationItem.comment,
            SpecialEquipmentApplicationItem.leasing_purpose,
            SpecialEquipmentApplicationItem.leasing_purposes,
            SpecialEquipmentApplicationItem.regions,
            SpecialEquipmentApplicationItem.overstock_requested_quantity,
            SpecialEquipmentApplicationItem.created_at,
            SpecialEquipmentModification.name.label("modification_name"),
            SpecialEquipmentProduct.superstructure_name,
            SpecialEquipmentProduct.superstructure_manufacturer,
            SpecialEquipmentModel.name.label("model_name"),
            SpecialEquipmentProduct.manufacture_year,
            SpecialEquipmentProduct.vin,
            SpecialEquipmentMark.name.label("mark_name"),
            primary_image_id.label("primary_image_id"),
            detail_product_id,
            detail_product_slug,
        )
        .select_from(SpecialEquipmentApplicationItem)
        .join(
            LeasingApplication,
            LeasingApplication.id
            == SpecialEquipmentApplicationItem.application_id,
        )
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == SpecialEquipmentApplicationItem.product_id,
        )
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .join(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .join(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
        .join(
            composite_product,
            sa.cast(composite_product.id, sa.String)
            == SpecialEquipmentApplicationItem.item_snapshot[
                "composite_product_id"
            ].astext,
            isouter=True,
        )
        .where(
            SpecialEquipmentApplicationItem.application_id.in_(application_ids),
            _special_equipment_dealer_filter_clause(dealer_filter),
        )
        .order_by(
            SpecialEquipmentApplicationItem.application_id,
            SpecialEquipmentApplicationItem.id,
        )
    )
    result = await session.execute(stmt)
    return [dict(row) for row in result.mappings().all()]


@timed_repository
async def list_application_vehicles_with_catalog(  # noqa: PLR0915
    session: AsyncSession,
    application_id: uuid.UUID,
    *,
    dealer_filter: list[UUID] | None = None,
    distributor_company_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Same as :func:`list_application_vehicles` + mark/model/color/year.

    Catalog fields are resolved via two parallel chains:
    * Reserved units: ``application_vehicles.vehicle_id → vehicles``, then
      ``vehicles.mark_id/model_id/complectation_id``.
    * Model orders (no ``vehicle_id``): fall back to
      ``application_vehicles.modification_id → modification → configuration →
      generation → model → mark``.

    Both chains are `LEFT JOIN`-ed so rows without catalog data still come
    back — just with null ``mark_name`` / ``model_name``.
    """
    if distributor_company_id is None and dealer_filter is not None and not dealer_filter:
        return []

    # Aliases for the fallback chain (model-order rows).
    mod_fb = aliased(SpecialEquipmentModification, name="mod_fb")
    mdl_fb = aliased(SpecialEquipmentModel, name="mdl_fb")
    mrk_fb = aliased(SpecialEquipmentMark, name="mrk_fb")
    warehouse_company = aliased(Company, name="warehouse_owner_company")
    effective_dealer_company = aliased(
        Company,
        name="effective_dealer_company",
    )
    effective_dealer_company_id = _application_vehicle_dealer_company_id_expr()

    stmt = (
        select(
            ApplicationVehicle,
            _visible_vehicle_quantity_expr(dealer_filter, distributor_company_id).label("visible_quantity"),
            sa.null().label("v_color"),
            SpecialEquipmentProduct.manufacture_year.label("v_year"),
            SpecialEquipmentProduct.vin.label("vehicle_vin"),
            sa.null().label("v_images"),
            SpecialEquipmentMark.name.label("mark_name"),
            SpecialEquipmentMark.name.label("mark_cyr"),
            SpecialEquipmentModel.name.label("model_name"),
            SpecialEquipmentModel.name.label("model_cyr"),
            sa.func.coalesce(
                SpecialEquipmentModification.name, mod_fb.name,
            ).label("modification_name"),
            sa.func.coalesce(
                SpecialEquipmentModification.name,
                SpecialEquipmentProduct.superstructure_name,
            ).label("group_name"),
            SpecialEquipmentTrim.name.label("catalog_trim_name"),
            SpecialEquipmentProduct.superstructure_name,
            SpecialEquipmentProduct.superstructure_manufacturer,
            SpecialEquipmentProduct.price.label("catalog_price_from"),
            SpecialEquipmentProduct.price.label("catalog_price_to"),
            sa.null().label("engine_type"),
            sa.null().label("transmission"),
            sa.null().label("drive"),
            mrk_fb.name.label("fb_mark_name"),
            mrk_fb.name.label("fb_mark_cyr"),
            mdl_fb.name.label("fb_model_name"),
            mdl_fb.name.label("fb_model_cyr"),
            mod_fb.name.label("fb_group_name"),
            sa.null().label("fb_catalog_price_from"),
            sa.null().label("fb_catalog_price_to"),
            effective_dealer_company.name.label("dealer_name"),
            effective_dealer_company.inn.label("stock_dealer_inn"),
            effective_dealer_company.company_type.label("stock_owner_type"),
            effective_dealer_company_id.label("dealer_id"),
            Warehouse.id.label("warehouse_id"),
            Warehouse.address.label("warehouse_address"),
            Warehouse.brand.label("warehouse_brand"),
            City.name.label("warehouse_city"),
            Warehouse.company_id.label("warehouse_company_id"),
            warehouse_company.name.label("warehouse_company_name"),
        )
        .select_from(ApplicationVehicle)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
            isouter=True,
        )
        .join(
            SpecialEquipmentTrim,
            SpecialEquipmentTrim.id == SpecialEquipmentProduct.trim_id,
            isouter=True,
        )
        .join(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
            isouter=True,
        )
        .join(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
            isouter=True,
        )
        .join(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
            isouter=True,
        )
        .join(
            mod_fb,
            sa.cast(mod_fb.id, sa.String) == ApplicationVehicle.modification_id,
            isouter=True,
        )
        .join(mdl_fb, mdl_fb.id == mod_fb.model_id, isouter=True)
        .join(mrk_fb, mrk_fb.id == mdl_fb.mark_id, isouter=True)
        .join(Warehouse, Warehouse.id == SpecialEquipmentProduct.warehouse_id, isouter=True)
        .join(City, City.id == Warehouse.city_id, isouter=True)
        .join(
            warehouse_company,
            warehouse_company.id == Warehouse.company_id,
            isouter=True,
        )
        .join(
            effective_dealer_company,
            effective_dealer_company.id == effective_dealer_company_id,
            isouter=True,
        )
        .where(
            ApplicationVehicle.application_id == application_id,
            _application_vehicle_dealer_filter_clause(dealer_filter, distributor_company_id),
        )
        .order_by(ApplicationVehicle.id)
    )
    result = (await session.execute(stmt)).all()
    vehicle_ids = [row.ApplicationVehicle.id for row in result]
    docs = await _dealer_action_docs_by_vehicle(session, vehicle_ids)
    items: list[dict[str, Any]] = []
    for row in result:
        base = _av_to_dict(
            row.ApplicationVehicle,
            dealer_action_documents=docs.get(row.ApplicationVehicle.id, []),
        )
        group_name = row.group_name or row.fb_group_name
        mark_cyrillic = row.mark_cyr or row.fb_mark_cyr
        model_cyrillic = row.model_cyr or row.fb_model_cyr
        base["assigned_vin"] = row.ApplicationVehicle.vin
        base["vehicle_vin"] = row.vehicle_vin
        base["color"] = row.v_color
        base["year"] = row.v_year
        base["vehicle_year"] = row.v_year
        base["images"] = row.v_images
        base["mark_name"] = row.mark_name or row.fb_mark_name
        base["mark_cyrillic"] = mark_cyrillic
        base["mark_cyrillic_name"] = mark_cyrillic
        base["model_name"] = row.model_name or row.fb_model_name
        base["model_cyrillic"] = model_cyrillic
        base["model_cyrillic_name"] = model_cyrillic
        base["modification_name"] = row.modification_name
        base["catalog_trim_name"] = row.catalog_trim_name
        base["group_name"] = group_name
        base["complectation_name"] = group_name
        base["engine"] = row.engine_type
        base["engine_type"] = row.engine_type
        base["transmission"] = row.transmission
        base["drive"] = row.drive
        _attach_application_vehicle_pricing(
            base,
            row.ApplicationVehicle,
            current_catalog_price=row.catalog_price_from
            if row.catalog_price_from is not None
            else row.fb_catalog_price_from,
            catalog_price_to=row.catalog_price_to or row.fb_catalog_price_to,
        )
        base["dealer_id"] = row.dealer_id
        base["dealer_name"] = row.dealer_name
        base["stock_dealer"] = (
            {"id": row.dealer_id, "name": row.dealer_name, "inn": row.stock_dealer_inn}
            if row.dealer_id is not None and row.stock_owner_type == "dealer"
            else None
        )
        base["warehouse"] = (
            {
                "id": row.warehouse_id,
                "address": row.warehouse_address,
                "brand": row.warehouse_brand,
                "city": row.warehouse_city,
                "company_id": row.warehouse_company_id,
                "company_name": row.warehouse_company_name,
            }
            if row.warehouse_id
            else None
        )
        base["warehouse_id"] = row.warehouse_id
        base["warehouse_address"] = row.warehouse_address
        _scope_vehicle_quantities(base, row.visible_quantity)
        items.append(base)
    from infrastructure.repositories import (
        vehicle_fulfillment_repository as fulfillment,
    )
    await fulfillment.enrich_line_composition(session, items)
    for item in items:
        if not item.get("can_manage_whole_vehicle", True):
            item["allocations"] = []
            item["allocated_vehicle_ids"] = []
            item["allocated_vins"] = []
            item["vin"] = None
            item["assigned_vin"] = None
            item["vehicle_vin"] = None
    return items


@timed_repository
async def get_questionnaire(
    session: AsyncSession, application_id: uuid.UUID, *, for_update: bool = False
) -> dict[str, Any] | None:
    stmt = select(ApplicationQuestionnaire).where(
        ApplicationQuestionnaire.application_id == application_id
    )
    if for_update:
        # Every questionnaire writer takes the parent first, including callers
        # that read for validation before upsert_questionnaire acquires its locks.
        await session.execute(
            select(LeasingApplication.id)
            .where(LeasingApplication.id == application_id)
            .with_for_update()
        )
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _q_to_dict(row)


@timed_repository
async def get_calculation(
    session: AsyncSession, application_id: uuid.UUID
) -> dict[str, Any] | None:
    row = await session.get(LeasingApplicationCalculation, application_id)
    if row is None:
        return None
    return _calc_to_dict(row)


@timed_repository
async def list_vehicle_calculations(
    session: AsyncSession,
    application_id: uuid.UUID,
    *,
    dealer_filter: list[UUID] | None = None,
    distributor_company_id: UUID | None = None,
) -> list[dict[str, Any]]:
    if distributor_company_id is None and dealer_filter is not None and not dealer_filter:
        return []
    stmt = (
        select(LeasingApplicationVehicleCalculation)
        .where(
            LeasingApplicationVehicleCalculation.leasing_application_id
            == application_id,
            _vehicle_calculation_dealer_filter_clause(dealer_filter, distributor_company_id),
        )
        .order_by(LeasingApplicationVehicleCalculation.sort_order)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_vehicle_calc_to_dict(r) for r in rows]


@timed_repository
async def list_lc_links(
    session: AsyncSession, application_id: uuid.UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(LeasingCompanyApplication)
        .where(LeasingCompanyApplication.application_id == application_id)
        .order_by(LeasingCompanyApplication.id)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_lca_to_dict(r) for r in rows]


@timed_repository
async def list_comments(
    session: AsyncSession, application_id: uuid.UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(LeasingApplicationComment)
        .where(LeasingApplicationComment.leasing_application_id == application_id)
        .order_by(LeasingApplicationComment.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_comment_to_dict(r) for r in rows]


@timed_repository
async def list_companies_info(
    session: AsyncSession, leasing_company_ids: list[UUID]
) -> list[dict[str, Any]]:
    """Resolve display names for a list of leasing-company-table ids."""
    if not leasing_company_ids:
        return []
    stmt = (
        select(LeasingCompany.id, Company.name)
        .join(Company, Company.id == LeasingCompany.company_id, isouter=True)
        .where(LeasingCompany.id.in_(leasing_company_ids))
    )
    result = await session.execute(stmt)
    return [{"company_id": row.id, "company_name": row.name} for row in result.all()]


# ---------------------------------------------------------------------------
# Writes — applications
# ---------------------------------------------------------------------------


@timed_repository
async def all_vehicles_visible_in_scope(
    session: AsyncSession,
    vehicle_ids: list[UUID],
    scope: CatalogScope,
) -> bool:
    unique_ids = set(vehicle_ids)
    if not unique_ids:
        return True
    count = await session.scalar(
        select(func.count(SpecialEquipmentProduct.id)).where(
            SpecialEquipmentProduct.id.in_(unique_ids),
            SpecialEquipmentProduct.publication_status == "published",
            SpecialEquipmentProduct.sale_status == "available",
            vehicle_visible_in(scope),
        )
    )
    return int(count or 0) == len(unique_ids)


@timed_repository
async def create_application(
    session: AsyncSession, *, payload: dict[str, Any]
) -> uuid.UUID:
    """Insert a leasing_applications row and return its UUID id.

    ``payload`` is filtered against the model columns to ignore unknown keys.
    """
    allowed = {c.key for c in LeasingApplication.__table__.columns}
    safe = {k: v for k, v in payload.items() if k in allowed}
    row = LeasingApplication(**safe)
    session.add(row)
    await session.flush()
    await upsert_questionnaire(session, application_id=row.id, payload=initial_values(), source="system")
    company = await session.get(Company, row.company_id) if row.company_id else None
    if company is not None:
        from domain.questionnaire_sources import company_values
        from infrastructure.repositories.company_repository import _company_to_dict
        await upsert_questionnaire(
            session, application_id=row.id,
            payload=company_values(dict(_company_to_dict(company)), row.id), source="company",
        )
    return row.id


@timed_repository
async def max_daily_display_sequence(
    session: AsyncSession,
    *,
    company_inn: str,
    created_on: date | None = None,
) -> int:
    """Return the maximum numeric suffix (-NNN) among display numbers issued
    today for this company INN. Used to calculate the next sequence number.
    """
    target_date = created_on or datetime.now(UTC).date()
    seq_expr = sa.cast(
        sa.func.substring(LeasingApplication.display_number, r"-(\d{3})$"),
        sa.Integer,
    )
    stmt = (
        select(sa.func.coalesce(sa.func.max(seq_expr), 0))
        .select_from(LeasingApplication)
        .join(Company, Company.id == LeasingApplication.company_id)
        .where(
            Company.inn == company_inn,
            func.date(LeasingApplication.created_at) == target_date,
            LeasingApplication.display_number.is_not(None),
        )
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


@timed_repository
async def get_company_inn(session: AsyncSession, *, company_id: UUID) -> str | None:
    from infrastructure.models.companies import Company

    stmt = select(Company.inn).where(Company.id == company_id)
    row = (await session.execute(stmt)).first()
    return str(row[0]) if row is not None and row[0] is not None else None


@timed_repository
async def update_display_number(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    display_number: str,
) -> None:
    row = await session.get(LeasingApplication, application_id)
    if row is None:
        return
    row.display_number = display_number
    await session.flush()


@timed_repository
async def update_application_status(
    session: AsyncSession,
    application_id: uuid.UUID,
    *,
    new_status: str,
    changed_by: UUID | None = None,
) -> bool:
    row = await session.scalar(select(LeasingApplication).where(LeasingApplication.id == application_id)
        .with_for_update().execution_options(populate_existing=True))
    if row is None:
        return False
    from infrastructure.repositories import (
        vehicle_fulfillment_repository as fulfillment,
    )
    if new_status == "issued":
        await fulfillment.complete_application(session, application_id)
    elif new_status == "rejected":
        await fulfillment.release_application(session, application_id, reason="Заявка завершена отказом")
    row.status = new_status
    cast("Any", row).updated_at = datetime.now(UTC)
    if new_status == "closed":
        lca_stmt = select(LeasingCompanyApplication).where(
            LeasingCompanyApplication.application_id == application_id
        )
        lca_rows = (await session.execute(lca_stmt)).scalars().all()
        for lca in lca_rows:
            old_lca_status = lca.status
            if old_lca_status == "closed":
                continue
            lca.status = "closed"
            cast("Any", lca).updated_at = datetime.now(UTC)
            await session.flush()
            from infrastructure.repositories import (
                status_history_repository as history_repo,
            )

            await history_repo.append_lca_status_history(
                session,
                lca_id=lca.id,
                application_id=application_id,
                old_status=old_lca_status,
                new_status="closed",
                changed_by=changed_by,
                reason="Родительская заявка закрыта",
            )
    await session.flush()
    return True


@timed_repository
async def delete_application_vehicles(
    session: AsyncSession, application_id: uuid.UUID
) -> None:
    await lock_purpose_application(session, application_id)
    stmt = select(ApplicationVehicle).where(
        ApplicationVehicle.application_id == application_id
    )
    rows = (await session.execute(stmt)).scalars().all()
    for row in rows:
        await session.delete(row)
    await session.flush()
    await sync_vehicle_purchase_purpose(session, application_id)



@timed_repository
async def delete_vehicle_calculations(
    session: AsyncSession, application_id: uuid.UUID
) -> None:
    stmt = select(LeasingApplicationVehicleCalculation).where(
        LeasingApplicationVehicleCalculation.leasing_application_id == application_id
    )
    rows = (await session.execute(stmt)).scalars().all()
    for row in rows:
        await session.delete(row)
    await session.flush()


@timed_repository
async def replace_selected_leasing_companies(
    session: AsyncSession,
    application_id: uuid.UUID,
    *,
    leasing_company_ids: list[UUID],
) -> bool:
    row = await session.get(LeasingApplication, application_id)
    if row is None:
        return False
    row.selected_leasing_companies = list(leasing_company_ids)
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True


@timed_repository
async def update_requested_documents(
    session: AsyncSession,
    application_id: uuid.UUID,
    *,
    requested_documents: Any,
) -> bool:
    row = await session.get(LeasingApplication, application_id)
    if row is None:
        return False
    row.requested_documents = requested_documents
    cast("Any", row).documents_requested_at = datetime.now(UTC)
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True


@timed_repository
async def list_leasing_purposes(session: AsyncSession) -> list[dict[str, Any]]:
    stmt = select(LeasingPurpose).order_by(LeasingPurpose.purpose_name)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "purpose_name": row.purpose_name,
            "purpose_display_name": row.purpose_display_name,
        }
        for row in rows
    ]


@timed_repository
async def list_leasing_regions(
    session: AsyncSession, *, q: str | None = None
) -> list[dict[str, Any]]:
    stmt = select(LeasingRegion)
    query = (q or "").strip()
    if query:
        pattern = f"%{query}%"
        stmt = stmt.where(
            or_(
                LeasingRegion.region_display_name.ilike(pattern),
                LeasingRegion.region_number.ilike(pattern),
            )
        )
    stmt = stmt.order_by(LeasingRegion.region_number.asc())
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "region_name": row.region_name,
            "region_display_name": row.region_display_name,
            "region_number": row.region_number,
        }
        for row in rows
    ]


@timed_repository
async def list_additional_equipments(session: AsyncSession) -> list[dict[str, Any]]:
    stmt = (
        select(AdditionalEquipment)
        .where(AdditionalEquipment.is_active.is_(True))
        .order_by(
            AdditionalEquipment.sort_order.asc(),
            AdditionalEquipment.equipment_display_name.asc(),
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "equipment_code": row.equipment_code,
            "equipment_display_name": row.equipment_display_name,
        }
        for row in rows
    ]


@timed_repository
async def list_additional_services(session: AsyncSession) -> list[dict[str, Any]]:
    stmt = (
        select(AdditionalService)
        .where(AdditionalService.is_active.is_(True))
        .order_by(
            AdditionalService.sort_order.asc(),
            AdditionalService.service_display_name.asc(),
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "service_code": row.service_code,
            "service_display_name": row.service_display_name,
        }
        for row in rows
    ]


@timed_repository
async def get_additional_option_catalog_membership(
    session: AsyncSession, codes: list[str]
) -> dict[str, list[str]]:
    unique_codes = set(codes)
    if not unique_codes:
        return {"equipment_codes": [], "service_codes": []}
    equipment_codes = (
        await session.execute(
            select(AdditionalEquipment.equipment_code).where(
                AdditionalEquipment.equipment_code.in_(unique_codes)
            )
        )
    ).scalars()
    service_codes = (
        await session.execute(
            select(AdditionalService.service_code).where(
                AdditionalService.service_code.in_(unique_codes)
            )
        )
    ).scalars()
    return {
        "equipment_codes": list(equipment_codes),
        "service_codes": list(service_codes),
    }


# ---------------------------------------------------------------------------
# Writes — application vehicles
# ---------------------------------------------------------------------------


async def _initial_application_vehicle_assignment(
    session: AsyncSession,
    *,
    application_id: UUID,
    vehicle_id: UUID | None,
) -> dict[str, Any]:
    """Build the initial assignment from the concrete vehicle warehouse.

    Application-level assignments are a legacy fallback only for model-order
    rows without a concrete ``vehicle_id``.  A real vehicle must start with
    the dealer that owns its current warehouse and without copied employees.
    """

    if vehicle_id is not None:
        dealer_company_id = (
            await session.execute(
                select(_vehicle_dealer_company_id_expr())
                .select_from(SpecialEquipmentProduct)
                .where(SpecialEquipmentProduct.id == vehicle_id)
            )
        ).scalar_one_or_none()
        return {
            "dealer_company_id": dealer_company_id,
            "dealer_assigned_by": None,
            "dealer_assigned_at": None,
            "primary_employee_id": None,
            "additional_employee_id": None,
            "employees_assigned_by": None,
            "employees_assigned_at": None,
        }

    application = await session.get(LeasingApplication, application_id)
    return {
        "dealer_company_id": application.dealer_company_id if application else None,
        "dealer_assigned_by": application.dealer_assigned_by if application else None,
        "dealer_assigned_at": application.dealer_assigned_at if application else None,
        "primary_employee_id": application.primary_employee_id if application else None,
        "additional_employee_id": application.additional_employee_id if application else None,
        "employees_assigned_by": application.employees_assigned_by if application else None,
        "employees_assigned_at": application.employees_assigned_at if application else None,
    }


@timed_repository
async def create_application_vehicle(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    vehicle_id: UUID | None,
    modification_id: str | None,
    quantity: int,
    unit_price: Decimal,
    total_price: Decimal,
    is_model_order: bool,
    comment: str | None = None,
    equipments: list[dict[str, Any]] | None = None,
    services: list[dict[str, Any]] | None = None,
    leasing_purpose: str | None = None,
    leasing_purposes: list[str] | None = None,
    regions: list[str] | None = None,
    requested_quantity: int | None = None,
) -> UUID:
    await lock_purpose_application(session, application_id)
    assignment = await _initial_application_vehicle_assignment(
        session,
        application_id=application_id,
        vehicle_id=vehicle_id,
    )
    row = ApplicationVehicle(
        application_id=application_id,
        product_id=vehicle_id,
        **assignment,
        modification_id=modification_id,
        quantity=quantity,
        requested_quantity=quantity if requested_quantity is None else requested_quantity,
        unit_price=unit_price,
        total_price=total_price,
        is_model_order=is_model_order,
        comment=comment,
        equipments=equipments or [],
        services=services or [],
        leasing_purpose=next(iter(selected_purposes(leasing_purposes, leasing_purpose)), None),
        leasing_purposes=selected_purposes(leasing_purposes, leasing_purpose),
        regions=regions or [],
    )
    session.add(row)
    await session.flush()
    await sync_vehicle_purchase_purpose(session, application_id)
    return row.id


@timed_repository
async def create_special_equipment_application_item(
    session: AsyncSession,
    *,
    application_id: UUID,
    product_id: UUID,
    seller_company_id: UUID | None,
    unit_price: Decimal | None,
    total_price: Decimal | None,
    currency_code: str,
    item_snapshot: dict[str, Any],
    comment: str | None = None,
    equipments: list[dict[str, Any]] | None = None,
    services: list[dict[str, Any]] | None = None,
    leasing_purpose: str | None = None,
    leasing_purposes: list[str] | None = None,
    regions: list[str] | None = None,
    source_cart_item_id: UUID | None = None,
    group_id: UUID | None = None,
    parent_group_id: UUID | None = None,
    item_role: str = "offer",
    overstock_requested_quantity: int = 0,
) -> UUID:
    """Append one FK-correct special-equipment line to a common application."""

    await lock_purpose_application(session, application_id)
    row = SpecialEquipmentApplicationItem(
        application_id=application_id,
        product_id=product_id,
        seller_company_id=seller_company_id,
        unit_price=unit_price,
        total_price=total_price,
        currency_code=currency_code,
        item_snapshot=item_snapshot,
        comment=comment,
        equipments=equipments or [],
        services=services or [],
        leasing_purpose=next(iter(selected_purposes(leasing_purposes, leasing_purpose)), None),
        leasing_purposes=selected_purposes(leasing_purposes, leasing_purpose),
        regions=regions or [],
        source_cart_item_id=source_cart_item_id,
        group_id=group_id or uuid.uuid4(),
        parent_group_id=parent_group_id,
        item_role=item_role,
        overstock_requested_quantity=overstock_requested_quantity,
        item_status="active",
        price_status=_initial_requested_price_status(
            item_role=item_role,
            item_snapshot=item_snapshot,
        ),
    )
    session.add(row)
    if item_role == "offer":
        existing_vehicle = await session.scalar(
            select(ApplicationVehicle).where(
                ApplicationVehicle.application_id == application_id,
                ApplicationVehicle.product_id == product_id,
            )
        )
        if existing_vehicle is None:
            session.add(
                ApplicationVehicle(
                    id=row.id,
                    application_id=application_id,
                    product_id=product_id,
                    dealer_company_id=seller_company_id,
                    quantity=1,
                    requested_quantity=1,
                    unit_price=unit_price,
                    total_price=total_price,
                    comment=comment,
                    equipments=equipments or [],
                    services=services or [],
                    leasing_purpose=next(iter(selected_purposes(leasing_purposes, leasing_purpose)), None),
        leasing_purposes=selected_purposes(leasing_purposes, leasing_purpose),
                    regions=regions or [],
                    car_status="active",
                )
            )
    await session.flush()
    await sync_vehicle_purchase_purpose(session, application_id)
    return row.id


@timed_repository
async def get_application_vehicle(
    session: AsyncSession, application_vehicle_id: UUID
) -> dict[str, Any] | None:
    row = await session.get(ApplicationVehicle, application_vehicle_id)
    if row is None:
        return None
    return _av_to_dict(row)


@timed_repository
async def update_application_vehicle_additional_options(
    session: AsyncSession,
    *,
    application_id: UUID,
    application_vehicle_id: UUID,
    equipments: list[dict[str, Any]],
    services: list[dict[str, Any]],
) -> dict[str, Any] | None:
    row = await session.get(ApplicationVehicle, application_vehicle_id)
    if row is None or row.application_id != application_id:
        return None
    row.equipments = equipments
    row.services = services
    options_total = _sum_option_prices(equipments) + _sum_option_prices(services)
    qty = row.quantity if row.quantity and row.quantity > 0 else 1
    effective_unit_price = Decimal(
        str(row.final_price if row.final_price is not None else row.unit_price or 0)
    )
    total_price = (effective_unit_price + options_total) * Decimal(qty)
    cast("Any", row).total_price = total_price
    if row.product_id is not None:
        se_item = await session.scalar(
            select(SpecialEquipmentApplicationItem).where(
                SpecialEquipmentApplicationItem.application_id == application_id,
                SpecialEquipmentApplicationItem.product_id == row.product_id,
            )
        )
        if se_item is not None:
            se_item.equipments = equipments
            se_item.services = services
            se_item.total_price = total_price
    await session.flush()
    return _av_to_dict(row)


def _sum_option_prices(items: list[dict[str, Any]]) -> Decimal:
    total = Decimal("0")
    for item in items:
        try:
            total += Decimal(str(item.get("price") or 0))
        except (ValueError, ArithmeticError, TypeError):
            continue
    return total


@timed_repository
async def assign_vin_to_application_vehicle(
    session: AsyncSession,
    application_vehicle_id: UUID,
    *,
    vehicle_id: UUID,
    vin: str,
    assigned_by: UUID,
) -> bool:
    """Set the application_vehicles row to point at a real vehicle + VIN."""
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
async def list_available_vins_for_application_vehicle(
    session: AsyncSession,
    *,
    modification_id: str | None,
    color: str | None = None,  # noqa: ARG001
    dealer_filter: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    """Vehicles of the matching modification still in `available`."""
    if not modification_id:
        return []
    try:
        mod_uuid = UUID(str(modification_id))
    except (ValueError, TypeError):
        return []

    stmt = (
        select(SpecialEquipmentProduct)
        .where(
            SpecialEquipmentProduct.modification_id == mod_uuid,
            SpecialEquipmentProduct.sale_status == "available",
            SpecialEquipmentProduct.vin.is_not(None),
            SpecialEquipmentProduct.vin != "",
        )
        .order_by(SpecialEquipmentProduct.id.desc())
    )
    if dealer_filter is not None:
        if not dealer_filter:
            return []
        stmt = stmt.where(SpecialEquipmentProduct.seller_company_id.in_(dealer_filter))
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "vin": r.vin,
            "color": None,
            "year": r.manufacture_year,
            "base_price": r.price,
            "discount_price": r.special_price,
            "status": r.sale_status,
            "complectation_id": str(r.modification_id),
            "modification_id": str(r.modification_id),
            "model_id": None,
            "mark_id": None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Writes — questionnaire / calculations / LC links
# ---------------------------------------------------------------------------

_QUESTIONNAIRE_READONLY_FIELDS = frozenset(
    {"id", "application_id", "created_at", "updated_at", "field_sources", "people_identity_map"}
)


@timed_repository
async def create_questionnaire(
    session: AsyncSession, *, application_id: uuid.UUID, payload: dict[str, Any],
) -> UUID:
    return await upsert_questionnaire(session, application_id=application_id, payload=payload)


@timed_repository
async def upsert_questionnaire(
    session: AsyncSession, *, application_id: uuid.UUID, payload: dict[str, Any],
    source: str = "manual",
) -> UUID:
    """One row per application; atomic merge with explicit user-input precedence."""
    allowed = {column.key for column in ApplicationQuestionnaire.__table__.columns}
    safe = _coerce_questionnaire_payload({
        key: value for key, value in payload.items()
        if key in allowed and key not in _QUESTIONNAIRE_READONLY_FIELDS
    })
    await session.execute(select(LeasingApplication.id).where(LeasingApplication.id == application_id).with_for_update())
    await session.execute(
        pg_insert(ApplicationQuestionnaire)
        .values(id=uuid.uuid4(), application_id=application_id)
        .on_conflict_do_nothing(index_elements=["application_id"])
    )
    stmt = select(ApplicationQuestionnaire).where(
        ApplicationQuestionnaire.application_id == application_id
    ).with_for_update().execution_options(populate_existing=True)
    existing = (await session.execute(stmt)).scalar_one()
    original = _q_to_dict(existing)
    current = normalize_stored_people(original, application_id)
    existing_sources = current.get("field_sources") or {}
    missing_defaults = {
        key: value for key, value in initial_values().items()
        if current.get(key) is None and not any(
            origin in MANUAL_SOURCES and (path == key or path.startswith(f"{key}."))
            for path, origin in existing_sources.items()
        )
    }
    default_updates, default_sources = merge_with_sources(current, missing_defaults, "system")
    current.update(default_updates)
    current["field_sources"] = default_sources
    safe, identities = normalize_incoming_people(current, safe, explicit=source in MANUAL_SOURCES)
    updates, sources = merge_with_sources(current, safe, source)
    updates = default_updates | updates
    for field in PEOPLE_FIELDS:
        if current.get(field) != original.get(field) and field not in updates:
            updates[field] = current[field]
    existing.people_identity_map = identities
    if updates.get("postal_address_matches_legal", existing.postal_address_matches_legal) is True:
        updates["postal_address"] = updates.get("legal_address", existing.legal_address)
    for key, value in updates.items():
        setattr(existing, key, value)
    existing.field_sources = sources
    cast("Any", existing).updated_at = datetime.now(UTC)
    await session.flush()
    return existing.id


@timed_repository
async def upsert_calculation(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    existing = await session.get(LeasingApplicationCalculation, application_id)
    allowed = {c.key for c in LeasingApplicationCalculation.__table__.columns}
    safe = {k: v for k, v in payload.items() if k in allowed}
    safe.pop("leasing_application_id", None)
    if existing is None:
        row = LeasingApplicationCalculation(
            leasing_application_id=application_id, **safe
        )
        session.add(row)
    else:
        for k, v in safe.items():
            setattr(existing, k, v)
        cast("Any", existing).updated_at = datetime.now(UTC)
    await session.flush()


@timed_repository
async def add_vehicle_calculation(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    payload: dict[str, Any],
) -> UUID:
    allowed = {c.key for c in LeasingApplicationVehicleCalculation.__table__.columns}
    safe = {k: v for k, v in payload.items() if k in allowed and k != "id"}
    safe["leasing_application_id"] = application_id
    row = LeasingApplicationVehicleCalculation(**safe)
    session.add(row)
    await session.flush()
    return row.id


@timed_repository
async def upsert_lc_links(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    leasing_company_ids: list[UUID],
    changed_by: UUID | None = None,
) -> int:
    """Make sure leasing_company_applications has an entry per LC.

    Inserts only missing rows. Returns count of newly inserted rows.
    """
    if not leasing_company_ids:
        return 0
    existing_stmt = select(LeasingCompanyApplication.leasing_company_id).where(
        LeasingCompanyApplication.application_id == application_id
    )
    existing = {row[0] for row in (await session.execute(existing_stmt)).all()}
    inserted_rows: list[LeasingCompanyApplication] = []
    for lc_id in leasing_company_ids:
        if lc_id in existing:
            continue
        row = LeasingCompanyApplication(
            application_id=application_id,
            leasing_company_id=lc_id,
            status="submitted",
        )
        session.add(row)
        inserted_rows.append(row)
    if inserted_rows:
        await session.flush()
        from infrastructure.repositories import (
            status_history_repository as history_repo,
        )

        for row in inserted_rows:
            await history_repo.append_lca_status_history(
                session,
                lca_id=row.id,
                application_id=application_id,
                old_status=None,
                new_status="submitted",
                changed_by=changed_by,
            )
    return len(inserted_rows)


# ---------------------------------------------------------------------------
# Reference checks
# ---------------------------------------------------------------------------


@timed_repository
async def vehicle_exists(session: AsyncSession, vehicle_id: UUID) -> bool:
    row = await session.get(SpecialEquipmentProduct, vehicle_id)
    return row is not None


@timed_repository
async def get_vehicle(session: AsyncSession, vehicle_id: UUID) -> dict[str, Any] | None:
    row = await session.get(SpecialEquipmentProduct, vehicle_id)
    if row is None:
        return None
    return {
        "id": row.id,
        "product_id": row.id,
        "vehicle_id": row.id,
        "vin": row.vin,
        "status": row.sale_status,
        "complectation_id": str(row.modification_id),
        "modification_id": str(row.modification_id),
        "color": None,
        "discount_price": row.special_price,
        "base_price": row.price,
        "dealer_id": row.seller_company_id,
        "seller_company_id": row.seller_company_id,
        "warehouse_id": row.warehouse_id,
        "mark_id": None,
        "model_id": None,
        "is_available": row.sale_status == "available",
    }


@timed_repository
async def update_vehicle_status(
    session: AsyncSession,
    vehicle_id: UUID,
    *,
    status: str,
) -> bool:
    row = await session.get(SpecialEquipmentProduct, vehicle_id)
    if row is None:
        return False
    row.sale_status = status
    await session.flush()
    return True


@timed_repository
async def user_exists(session: AsyncSession, user_id: UUID) -> bool:
    row = await session.get(User, user_id)
    return row is not None


@timed_repository
async def company_exists(session: AsyncSession, company_id: UUID) -> bool:
    row = await session.get(Company, company_id)
    return row is not None


@timed_repository
async def leasing_company_exists(
    session: AsyncSession, leasing_company_id: UUID
) -> bool:
    row = await session.get(LeasingCompany, leasing_company_id)
    return row is not None


@timed_repository
async def get_lc_summary(
    session: AsyncSession, application_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Return LCA summary for an application (status per LC).

    Returns a list of dicts with keys: leasing_company_id, status, company_name.
    """
    from infrastructure.models.companies import Company

    stmt = (
        select(
            LeasingCompanyApplication.leasing_company_id,
            LeasingCompanyApplication.status,
            Company.name.label("company_name"),
        )
        .join(
            LeasingCompany,
            LeasingCompany.id == LeasingCompanyApplication.leasing_company_id,
        )
        .join(
            Company,
            Company.id == LeasingCompany.company_id,
        )
        .where(LeasingCompanyApplication.application_id == application_id)
        .order_by(LeasingCompanyApplication.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "leasing_company_id": r.leasing_company_id,
            "status": r.status,
            "company_name": r.company_name,
        }
        for r in rows
    ]


@timed_repository
async def resolve_leasing_company_id(
    session: AsyncSession, company_id: UUID | None
) -> UUID | None:
    """Return the ``leasing_companies.id`` associated with ``company_id``.

    The user table stores ``company_id`` pointing to ``companies``; the
    ``selected_leasing_companies`` ARRAY on ``leasing_applications`` stores
    ``leasing_companies.id`` values. This helper resolves one into the other
    so role-filter logic can match them.
    """
    if company_id is None:
        return None
    stmt = select(LeasingCompany.id).where(LeasingCompany.company_id == company_id)
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        return None
    return row[0]


# ---------------------------------------------------------------------------
# Helpers used by the requested-documents endpoint
# ---------------------------------------------------------------------------


def parse_requested_documents(value: Any) -> list[str]:
    """Best-effort conversion of the ``requested_documents`` JSONB field.

    The Express implementation accepts either a list, a JSON-string list or
    a comma-separated string. We mirror that behaviour so the new and
    legacy data shapes coexist during migration.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, dict):
        items = value.get("items")
        if isinstance(items, list):
            return [str(x).strip() for x in items if str(x).strip()]
        return []
    if isinstance(value, str):
        return _parse_requested_documents_string(value)
    return []


def _parse_requested_documents_string(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        import json

        try:
            parsed = json.loads(stripped)
        except ValueError:
            parsed = None
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    return [chunk.strip() for chunk in stripped.split(",") if chunk.strip()]


# ---------------------------------------------------------------------------
# Counts used for application-group hydration
# ---------------------------------------------------------------------------


@timed_repository
async def count_application_vehicles(
    session: AsyncSession, application_id: uuid.UUID
) -> int:
    stmt = select(func.count(ApplicationVehicle.id)).where(
        ApplicationVehicle.application_id == application_id
    )
    return int((await session.execute(stmt)).scalar() or 0)


@timed_repository
async def sum_application_vehicles_total(
    session: AsyncSession, application_id: uuid.UUID
) -> Decimal:
    stmt = select(func.coalesce(func.sum(ApplicationVehicle.total_price), 0)).where(
        ApplicationVehicle.application_id == application_id
    )
    raw = (await session.execute(stmt)).scalar() or 0
    if isinstance(raw, Decimal):
        return raw
    return Decimal(str(raw))


@timed_repository
async def sum_active_application_items_total(
    session: AsyncSession, application_id: uuid.UUID
) -> Decimal | None:
    """Return the current vehicle + special-equipment commerce total."""

    vehicle_stmt = select(
        func.coalesce(func.sum(ApplicationVehicle.total_price), 0)
    ).where(
        ApplicationVehicle.application_id == application_id,
        ApplicationVehicle.car_status.in_(("active", "confirmed", "replacement")),
        ~sa.exists().where(
            SpecialEquipmentApplicationItem.application_id == ApplicationVehicle.application_id,
            SpecialEquipmentApplicationItem.product_id == ApplicationVehicle.product_id,
        ),
    )
    vehicle_raw = (await session.execute(vehicle_stmt)).scalar() or 0

    equipment_stmt = select(
        func.coalesce(
            func.sum(
                func.coalesce(
                    SpecialEquipmentApplicationItem.total_price,
                    SpecialEquipmentApplicationItem.unit_price,
                    0,
                )
            ),
            0,
        ),
        func.count(
            sa.case(
                (
                    sa.and_(
                        SpecialEquipmentApplicationItem.item_role != "component",
                        SpecialEquipmentApplicationItem.total_price.is_(None),
                        SpecialEquipmentApplicationItem.unit_price.is_(None),
                    ),
                    1,
                )
            )
        ),
    ).where(
        SpecialEquipmentApplicationItem.application_id == application_id,
        SpecialEquipmentApplicationItem.item_status.in_(("active", "reserved")),
    )
    equipment_raw, unknown_count = (await session.execute(equipment_stmt)).one()
    if unknown_count:
        return None
    return Decimal(str(vehicle_raw)) + Decimal(str(equipment_raw or 0))


@timed_repository
async def ensure_application_vehicles_for_special_equipment(
    session: AsyncSession,
    application_id: UUID,
) -> bool:
    """Ensure ApplicationVehicle rows exist for special equipment offer items."""
    await lock_purpose_application(session, application_id)
    stmt = select(SpecialEquipmentApplicationItem).where(
        SpecialEquipmentApplicationItem.application_id == application_id,
        SpecialEquipmentApplicationItem.item_role == "offer",
    )
    items = (await session.execute(stmt)).scalars().all()
    created = False
    for item in items:
        if not item.product_id:
            continue
        existing = await session.scalar(
            select(ApplicationVehicle).where(
                ApplicationVehicle.application_id == application_id,
                ApplicationVehicle.product_id == item.product_id,
            )
        )
        if existing is None:
            session.add(
                ApplicationVehicle(
                    id=item.id,
                    application_id=application_id,
                    product_id=item.product_id,
                    dealer_company_id=item.seller_company_id,
                    quantity=1,
                    requested_quantity=1,
                    unit_price=item.unit_price,
                    total_price=item.total_price,
                    comment=item.comment,
                    equipments=item.equipments or [],
                    services=item.services or [],
                    leasing_purpose=item.leasing_purpose,
                    leasing_purposes=item.leasing_purposes,
                    regions=item.regions or [],
                    car_status="active",
                )
            )
            created = True
    if created:
        await session.flush()
    await sync_vehicle_purchase_purpose(session, application_id)
    return created


# ---------------------------------------------------------------------------
# LC-scoped application listing (Phase 5 E3 / LC create-side)
# ---------------------------------------------------------------------------


@timed_repository
async def update_application_fields(
    session: AsyncSession,
    application_id: uuid.UUID,
    *,
    fields: dict[str, Any],
) -> bool:
    """Apply a partial update to ``leasing_applications``.

    Only known columns are written; the row's ``updated_at`` is bumped to
    the current time in UTC.
    """
    row = await session.get(LeasingApplication, application_id)
    if row is None:
        return False
    allowed = {c.key for c in LeasingApplication.__table__.columns}
    touched = False
    for key, value in fields.items():
        if key not in allowed or key in {"id", "created_at"}:
            continue
        setattr(row, key, value)
        touched = True
    if not touched:
        return False
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True


@timed_repository
async def save_deal_confirmation(
    session: AsyncSession,
    application_id: uuid.UUID,
    *,
    deal_date: date,
    deal_documents: list[dict[str, Any]],
) -> bool:
    row = await session.scalar(
        select(LeasingApplication)
        .where(LeasingApplication.id == application_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        return False
    row.deal_date = deal_date
    row.deal_documents = deal_documents
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True


@timed_repository
async def update_application_vehicles_vins(
    session: AsyncSession,
    application_id: uuid.UUID,
    vehicles_vin_data: list[dict[str, Any]],
    *,
    actor_id: UUID,
) -> None:
    for item in vehicles_vin_data:
        v_id = item["vehicle_id"]
        vin = item["vin"]
        row = await session.scalar(
            select(ApplicationVehicle).where(
                ApplicationVehicle.application_id == application_id,
                or_(
                    ApplicationVehicle.id == v_id,
                    ApplicationVehicle.product_id == v_id,
                ),
            )
        )
        if row is not None:
            row.vin = vin
            row.vin_assigned_by = actor_id
            cast("Any", row).vin_assigned_at = datetime.now(UTC)
    await session.flush()


__all__ = [
    "add_vehicle_calculation",
    "assign_vin_to_application_vehicle",
    "company_exists",
    "count_application_vehicles",
    "create_application",
    "create_application_vehicle",
    "create_questionnaire",
    "dealer_child_ownership_clause",
    "dealer_company_owns_application_item",
    "dealer_company_owns_application_vehicle",
    "ensure_application_vehicles_for_special_equipment",
    "get_additional_option_catalog_membership",
    "get_application_vehicle",
    "get_by_id",
    "get_calculation",
    "get_company_inn",
    "get_lc_summary",
    "get_questionnaire",
    "get_vehicle",
    "leasing_company_exists",
    "list_additional_equipments",
    "list_additional_services",
    "list_application_special_equipment_item_rows",
    "list_application_vehicle_item_rows",
    "list_application_vehicles",
    "list_application_vehicles_with_catalog",
    "list_available_vins_for_application_vehicle",
    "list_comments",
    "list_companies_info",
    "list_for_user",
    "list_lc_links",
    "list_leasing_purposes",
    "list_leasing_regions",
    "list_vehicle_calculations",
    "max_daily_display_sequence",
    "parse_requested_documents",
    "resolve_leasing_company_id",
    "save_deal_confirmation",
    "sum_active_application_items_total",
    "sum_application_vehicles_total",
    "update_application_fields",
    "update_application_status",
    "update_application_vehicle_additional_options",
    "update_application_vehicles_vins",
    "update_display_number",
    "update_requested_documents",
    "update_vehicle_status",
    "upsert_calculation",
    "upsert_lc_links",
    "upsert_questionnaire",
    "user_exists",
    "vehicle_exists",
]
