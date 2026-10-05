"""SQL clauses and validation helpers for personal access rules in leasing applications."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from infrastructure.models.applications import ApplicationVehicle, LeasingApplication
from infrastructure.models.special_equipment import (
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
)
from infrastructure.models.vehicles import Warehouse
from infrastructure.repositories import user_company_access_repository as access_repo
from infrastructure.repositories.user_company_access_repository import (
    PersonalAccessRules,
)


def _build_warehouse_fails_expr(  # noqa: PLR0911
    personal_rules: PersonalAccessRules,
    role: str,
    company_id: UUID,
    warehouse_table: Any,
    product_table: Any,
) -> sa.ColumnElement[bool] | None:
    """Return condition indicating that the vehicle's warehouse FAILS personal rules.

    Returns None if no warehouse restriction is active.
    """
    if role == "dealer":
        mode = personal_rules.warehouse_mode
        if mode == "none":
            return sa.true()
        if mode == "selected":
            if not personal_rules.warehouse_ids:
                return sa.true()
            return sa.or_(
                product_table.warehouse_id.is_(None),
                product_table.warehouse_id.not_in_(list(personal_rules.warehouse_ids)),
            )
        if mode == "except_selected":
            if not personal_rules.warehouse_ids:
                return sa.false()
            return sa.or_(
                product_table.warehouse_id.is_(None),
                product_table.warehouse_id.in_(list(personal_rules.warehouse_ids)),
            )
        return None

    # Distributor
    dist_mode = personal_rules.warehouse_mode
    dlr_mode = personal_rules.dealer_warehouse_mode

    has_dist_restriction = dist_mode in ("selected", "except_selected", "none")
    has_dlr_restriction = dlr_mode in ("selected", "except_selected", "none")

    if not has_dist_restriction and not has_dlr_restriction:
        return None

    if dist_mode == "none" and dlr_mode == "none":
        return sa.true()

    # Pass conditions for distributor stock vs dealer stock
    def _dist_passes() -> sa.ColumnElement[bool]:
        if dist_mode == "none":
            return sa.false()
        if dist_mode == "selected":
            return product_table.warehouse_id.in_(list(personal_rules.warehouse_ids))
        if dist_mode == "except_selected":
            return product_table.warehouse_id.not_in_(list(personal_rules.warehouse_ids))
        return sa.true()

    def _dlr_passes() -> sa.ColumnElement[bool]:
        if dlr_mode == "none":
            return sa.false()
        if dlr_mode == "selected":
            return product_table.warehouse_id.in_(list(personal_rules.dealer_warehouse_ids))
        if dlr_mode == "except_selected":
            return product_table.warehouse_id.not_in_(list(personal_rules.dealer_warehouse_ids))
        return sa.true()

    passes_cond = or_(
        sa.and_(warehouse_table.company_id == company_id, _dist_passes()),
        sa.and_(warehouse_table.company_id != company_id, _dlr_passes()),
    )
    return sa.or_(
        product_table.warehouse_id.is_(None),
        warehouse_table.company_id.is_(None),
        sa.not_(passes_cond),
    )


def _build_brand_fails_expr(
    personal_rules: PersonalAccessRules,
    mark_model_table: Any,
) -> sa.ColumnElement[bool] | None:
    """Return condition indicating that the vehicle's brand FAILS personal rules.

    Returns None if no brand restriction is active.
    """
    mode = personal_rules.brand_mode
    if mode == "none":
        return sa.true()
    if mode == "selected":
        if not personal_rules.brand_ids:
            return sa.true()
        return sa.or_(
            mark_model_table.mark_id.is_(None),
            mark_model_table.mark_id.not_in_(list(personal_rules.brand_ids)),
        )
    if mode == "except_selected":
        if not personal_rules.brand_ids:
            return sa.false()
        return sa.or_(
            mark_model_table.mark_id.is_(None),
            mark_model_table.mark_id.in_(list(personal_rules.brand_ids)),
        )
    return None


def build_personal_application_clause(  # noqa: PLR0911, PLR0912
    personal_rules: PersonalAccessRules,
    role: str,
    company_id: UUID,
) -> sa.ColumnElement[bool]:
    """Build SQL WHERE element enforcing personal rules on leasing applications."""
    if not personal_rules.has_rules:
        return sa.true()

    # 1. Application creator restriction
    if personal_rules.application_creator_mode == "none":
        return sa.false()

    clauses: list[sa.ColumnElement[bool]] = []
    if personal_rules.application_creator_mode == "selected":
        if not personal_rules.application_creator_ids:
            return sa.false()
        clauses.append(LeasingApplication.created_by.in_(list(personal_rules.application_creator_ids)))
    elif personal_rules.application_creator_mode == "except_selected" and personal_rules.application_creator_ids:
        clauses.append(LeasingApplication.created_by.not_in_(list(personal_rules.application_creator_ids)))

    # 2. Dealer restriction (for distributor)
    if role == "distributor":
        if personal_rules.dealer_mode == "none":
            return sa.false()
        if personal_rules.dealer_mode == "selected":
            if not personal_rules.dealer_ids:
                return sa.false()
            clauses.append(LeasingApplication.dealer_company_id.in_(list(personal_rules.dealer_ids)))

    # 3. Warehouse and Brand restrictions on all vehicles
    wh_fails_av = _build_warehouse_fails_expr(
        personal_rules, role, company_id, Warehouse, SpecialEquipmentProduct
    )
    brand_fails_av = _build_brand_fails_expr(personal_rules, SpecialEquipmentModel)

    has_wh_restriction = wh_fails_av is not None
    has_brand_restriction = brand_fails_av is not None

    if not has_wh_restriction and not has_brand_restriction:
        return sa.and_(*clauses) if clauses else sa.true()

    # Combine vehicle failure checks
    failing_conditions: list[sa.ColumnElement[bool]] = []
    if wh_fails_av is not None:
        failing_conditions.append(wh_fails_av)
    if brand_fails_av is not None:
        failing_conditions.append(brand_fails_av)

    av_vehicle_fails = or_(*failing_conditions)

    # Subquery: does there exist any vehicle in application_vehicles that FAILS?
    failing_av_subquery = (
        select(ApplicationVehicle.id)
        .select_from(ApplicationVehicle)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
            isouter=True,
        )
        .join(
            Warehouse,
            Warehouse.id == SpecialEquipmentProduct.warehouse_id,
            isouter=True,
        )
        .join(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == func.coalesce(
                SpecialEquipmentProduct.modification_id,
                ApplicationVehicle.modification_id,
            ),
            isouter=True,
        )
        .join(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
            isouter=True,
        )
        .where(
            ApplicationVehicle.application_id == LeasingApplication.id,
            av_vehicle_fails,
        )
        .correlate(LeasingApplication)
        .exists()
    )

    has_av_subquery = (
        select(ApplicationVehicle.id)
        .where(ApplicationVehicle.application_id == LeasingApplication.id)
        .correlate(LeasingApplication)
        .exists()
    )

    # Fallback vehicle check for applications without child application_vehicles rows
    fb_prod = aliased(SpecialEquipmentProduct, name="fb_prod")
    fb_wh = aliased(Warehouse, name="fb_wh")
    fb_mod = aliased(SpecialEquipmentModification, name="fb_mod")
    fb_mdl = aliased(SpecialEquipmentModel, name="fb_mdl")

    fb_wh_fails = _build_warehouse_fails_expr(
        personal_rules, role, company_id, fb_wh, fb_prod
    )
    fb_brand_fails = _build_brand_fails_expr(personal_rules, fb_mdl)
    fb_failing_conditions: list[sa.ColumnElement[bool]] = []
    if fb_wh_fails is not None:
        fb_failing_conditions.append(fb_wh_fails)
    if fb_brand_fails is not None:
        fb_failing_conditions.append(fb_brand_fails)
    fb_vehicle_fails = or_(*fb_failing_conditions)

    fallback_passes_subquery = (
        select(fb_prod.id)
        .select_from(fb_prod)
        .join(fb_wh, fb_wh.id == fb_prod.warehouse_id, isouter=True)
        .join(fb_mod, fb_mod.id == fb_prod.modification_id, isouter=True)
        .join(fb_mdl, fb_mdl.id == fb_mod.model_id, isouter=True)
        .where(
            fb_prod.id == LeasingApplication.vehicle_id,
            sa.not_(fb_vehicle_fails),
        )
        .correlate(LeasingApplication)
        .exists()
    )

    # All vehicles must pass. If no vehicles exist when restriction is active, application is hidden.
    vehicle_match_clause = sa.case(
        (has_av_subquery, sa.not_(failing_av_subquery)),
        (LeasingApplication.vehicle_id.is_not(None), fallback_passes_subquery),
        else_=sa.false(),
    )

    clauses.append(vehicle_match_clause)
    return sa.and_(*clauses)


async def check_application_personal_access(  # noqa: PLR0911, PLR0912, PLR0915
    session: AsyncSession,
    *,
    application_id: UUID,
    user_id: UUID,
    company_id: UUID,
    role: str,
) -> bool:
    """Validate whether an application is accessible to actor under active personal rules."""
    personal_rules = await access_repo.get_actor_personal_access_rules(
        session, user_id, company_id
    )
    if not personal_rules.has_rules:
        return True

    # 1. Creator check
    if personal_rules.application_creator_mode == "none":
        return False

    app_row = await session.execute(
        select(
            LeasingApplication.created_by,
            LeasingApplication.dealer_company_id,
            LeasingApplication.vehicle_id,
        ).where(LeasingApplication.id == application_id)
    )
    app = app_row.first()
    if app is None:
        return False

    creator_id = app.created_by
    if personal_rules.application_creator_mode == "selected":
        if not creator_id or creator_id not in personal_rules.application_creator_ids:
            return False
    elif (
        personal_rules.application_creator_mode == "except_selected"
        and creator_id
        and creator_id in personal_rules.application_creator_ids
    ):
        return False

    # 2. Dealer check (for distributor)
    if role == "distributor":
        if personal_rules.dealer_mode == "none":
            return False
        if personal_rules.dealer_mode == "selected":
            dealer_id = app.dealer_company_id
            if not dealer_id or dealer_id not in personal_rules.dealer_ids:
                return False

    # 3. Warehouse and Brand check
    has_wh_restriction = (
        personal_rules.warehouse_mode in ("selected", "except_selected", "none")
        or (role == "distributor" and personal_rules.dealer_warehouse_mode in ("selected", "except_selected", "none"))
    )
    has_brand_restriction = personal_rules.brand_mode in ("selected", "except_selected", "none")

    if not has_wh_restriction and not has_brand_restriction:
        return True

    # Query vehicle details for this application
    av_rows = (
        await session.execute(
            select(
                ApplicationVehicle.id,
                SpecialEquipmentProduct.warehouse_id,
                Warehouse.company_id.label("warehouse_company_id"),
                SpecialEquipmentModel.mark_id,
            )
            .select_from(ApplicationVehicle)
            .join(
                SpecialEquipmentProduct,
                SpecialEquipmentProduct.id == ApplicationVehicle.product_id,
                isouter=True,
            )
            .join(
                Warehouse,
                Warehouse.id == SpecialEquipmentProduct.warehouse_id,
                isouter=True,
            )
            .join(
                SpecialEquipmentModification,
                SpecialEquipmentModification.id == func.coalesce(
                    SpecialEquipmentProduct.modification_id,
                    ApplicationVehicle.modification_id,
                ),
                isouter=True,
            )
            .join(
                SpecialEquipmentModel,
                SpecialEquipmentModel.id
                == func.coalesce(
                    SpecialEquipmentModification.model_id,
                    SpecialEquipmentProduct.model_id,
                ),
                isouter=True,
            )
            .where(ApplicationVehicle.application_id == application_id)
        )
    ).all()

    vehicles_to_check: list[Any] = list(av_rows)
    if not vehicles_to_check:
        # Check fallback vehicle
        if not app.vehicle_id:
            # Cannot determine warehouse or brand when restriction is active
            return False
        fb_row = (
            await session.execute(
                select(
                    SpecialEquipmentProduct.id,
                    SpecialEquipmentProduct.warehouse_id,
                    Warehouse.company_id.label("warehouse_company_id"),
                    SpecialEquipmentModel.mark_id,
                )
                .select_from(SpecialEquipmentProduct)
                .join(
                    Warehouse,
                    Warehouse.id == SpecialEquipmentProduct.warehouse_id,
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
                    == func.coalesce(
                        SpecialEquipmentModification.model_id,
                        SpecialEquipmentProduct.model_id,
                    ),
                    isouter=True,
                )
                .where(SpecialEquipmentProduct.id == app.vehicle_id)
            )
        ).first()
        if fb_row is None:
            return False
        vehicles_to_check = [fb_row]

    # Every vehicle MUST pass warehouse and brand rules
    for v in vehicles_to_check:
        wh_id = v.warehouse_id
        wh_comp_id = v.warehouse_company_id
        mark_id = v.mark_id

        # Warehouse validation
        if has_wh_restriction:
            if wh_id is None:
                return False
            if role == "dealer":
                mode = personal_rules.warehouse_mode
                if mode == "none":
                    return False
                if mode == "selected" and wh_id not in personal_rules.warehouse_ids:
                    return False
                if mode == "except_selected" and wh_id in personal_rules.warehouse_ids:
                    return False
            elif role == "distributor":
                if wh_comp_id == company_id:
                    # Distributor's own warehouse
                    mode = personal_rules.warehouse_mode
                    if mode == "none":
                        return False
                    if mode == "selected" and wh_id not in personal_rules.warehouse_ids:
                        return False
                    if mode == "except_selected" and wh_id in personal_rules.warehouse_ids:
                        return False
                else:
                    # Dealer's warehouse
                    mode = personal_rules.dealer_warehouse_mode
                    if mode == "none":
                        return False
                    if mode == "selected" and wh_id not in personal_rules.dealer_warehouse_ids:
                        return False
                    if mode == "except_selected" and wh_id in personal_rules.dealer_warehouse_ids:
                        return False

        # Brand validation
        if has_brand_restriction:
            if mark_id is None:
                return False
            mode = personal_rules.brand_mode
            if mode == "none":
                return False
            if mode == "selected" and mark_id not in personal_rules.brand_ids:
                return False
            if mode == "except_selected" and mark_id in personal_rules.brand_ids:
                return False

    return True
