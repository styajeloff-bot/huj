"""Read authoritative origin rows inside the source transition transaction."""

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyApplication,
    LeasingProposal,
)
from infrastructure.models.companies import (
    Company,
    DistributorDealerLink,
    LeasingCompany,
)
from infrastructure.models.exchange import ExchangeBid, ExchangeRequest
from infrastructure.models.fast_deals import FastDeal, FastDealVehicle
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
    SpecialEquipmentTrim,
)
from infrastructure.models.support import (
    ApplicationAppliedSupport,
    DealerGroup,
    DealerGroupMember,
)
from infrastructure.repositories import application_repository

Record = dict[str, Any]


async def _row(session: AsyncSession, table: sa.FromClause, row_id: UUID) -> Record:
    value = (
        (await session.execute(sa.select(table).where(table.c.id == row_id)))
        .mappings()
        .first()
    )
    return dict(value) if value is not None else {}


async def _company_exists(session: AsyncSession, company_id: Any, kind: str) -> bool:
    if company_id is None:
        return False
    return bool(
        await session.scalar(
            sa.select(Company.id).where(
                Company.id == company_id, Company.company_type == kind
            )
        )
    )


async def _leasing_company(session: AsyncSession, leasing_id: Any) -> Any:
    return await session.scalar(
        sa.select(LeasingCompany.id)
        .join(Company, Company.id == LeasingCompany.company_id)
        .where(
            LeasingCompany.id == leasing_id, Company.company_type == "leasing_company"
        )
    )


async def _participants(session: AsyncSession, dealer_id: Any, group_id: Any) -> Record:
    result: Record = {
        "dealer_company_id": dealer_id,
        "dealer_group_id": group_id,
        "distributor_company_id": None,
    }
    if not await _company_exists(session, dealer_id, "dealer"):
        result["dealer_company_id"] = None
        return result
    linked = await session.scalar(
        sa.select(DistributorDealerLink.distributor_company_id).where(
            DistributorDealerLink.dealer_company_id == dealer_id
        )
    )
    if group_id is not None:
        assigned = await session.scalar(
            sa.select(DealerGroup.distributor_company_id)
            .join(
                DealerGroupMember, DealerGroupMember.dealer_group_id == DealerGroup.id
            )
            .where(
                DealerGroup.id == group_id,
                DealerGroupMember.dealer_company_id == dealer_id,
            )
        )
        if assigned is None or (linked is not None and assigned != linked):
            result["participant_conflict"] = True
            return result
        linked = assigned
    if linked is not None and await _company_exists(session, linked, "distributor"):
        result["distributor_company_id"] = linked
    return result


async def _supports(session: AsyncSession, field: str, origin: UUID) -> list[Record]:
    table = ApplicationAppliedSupport.__table__
    rows = (
        await session.execute(sa.select(table).where(table.c[field] == origin))
    ).mappings()
    return [dict(row) for row in rows]


async def _vehicle_catalog(
    session: AsyncSession, vehicle_ids: list[UUID]
) -> dict[UUID, Record]:
    if not vehicle_ids:
        return {}
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentProduct.id.label("vehicle_id"),
                SpecialEquipmentProduct.vin,
                SpecialEquipmentProduct.seller_company_id.label("stock_dealer_company_id"),
                SpecialEquipmentMark.name.label("brand"),
                SpecialEquipmentModel.name.label("model"),
                SpecialEquipmentModification.name.label("modification"),
                sa.func.coalesce(
                    SpecialEquipmentModification.name,
                    SpecialEquipmentProduct.superstructure_name,
                ).label("legacy_trim"),
                SpecialEquipmentTrim.name.label("trim"),
            )
            .select_from(SpecialEquipmentProduct)
            .outerjoin(
                SpecialEquipmentTrim,
                SpecialEquipmentTrim.id == SpecialEquipmentProduct.trim_id,
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
            .where(SpecialEquipmentProduct.id.in_(vehicle_ids))
        )
    ).mappings()
    return {row["vehicle_id"]: dict(row) for row in rows}


async def _application_vehicles(
    session: AsyncSession, lines: list[Record]
) -> list[Record]:
    # The fulfillment reader includes only active allocations. Its synthetic
    # legacy reservation remains represented by the original commercial line.
    allocations = [
        allocation
        for line in lines
        for allocation in line.get("allocations", [])
        if not allocation.get("legacy")
    ]
    catalog = await _vehicle_catalog(
        session, [allocation["vehicle_id"] for allocation in allocations]
    )
    result: list[Record] = []
    for line in lines:
        active = [
            item for item in line.get("allocations", []) if not item.get("legacy")
        ]
        if active:
            result.extend(
                {
                    **catalog.get(allocation["vehicle_id"], {}),
                    "vehicle_id": allocation["vehicle_id"],
                    "application_vehicle_id": line["id"],
                    "allocation_id": allocation["id"],
                    "vin": allocation["vin"], "quantity": 1,
                    "dealer_company_id": line.get("dealer_company_id"),
                } for allocation in active
            )
        else:
            result.append(
                {
                    "vehicle_id": line.get("vehicle_id"),
                    "application_vehicle_id": line["id"],
                    "brand": line.get("mark_name"),
                    "model": line.get("model_name"),
                    "modification": line.get("modification_name"),
                    "trim": line.get("catalog_trim_name"),
                    "legacy_trim": line.get("group_name"),
                    "vin": line.get("assigned_vin") or line.get("vehicle_vin"),
                    "quantity": line.get("quantity"),
                    "dealer_company_id": line.get("dealer_company_id"),
                }
            )
    return result


async def lca_source(session: AsyncSession, link_id: UUID) -> Record:
    """A final proposal supplies the amount; parent totals are deliberately absent."""
    link = await _row(session, LeasingCompanyApplication.__table__, link_id)
    result: Record = {
        "leasing_company_application_id": link_id,
        "source_status": link.get("status"),
    }
    if not link.get("application_id"):
        return result
    app = await _row(session, LeasingApplication.__table__, link["application_id"])
    result.update(
        application_id=link["application_id"],
        source_type=app.get("source_type"),
        application_number=app.get("display_number"),
        client_company_id=app.get("company_id"),
        leasing_company_id=await _leasing_company(
            session, link.get("leasing_company_id")
        ),
    )
    result.update(
        await _participants(
            session, app.get("dealer_company_id"), app.get("assigned_dealer_group_id")
        )
    )
    proposal = (
        (
            await session.execute(
                sa.select(LeasingProposal.__table__).where(
                    LeasingProposal.leasing_company_application_id == link_id,
                    LeasingProposal.kind == "final",
                )
            )
        )
        .mappings()
        .first()
    )
    if proposal is not None:
        result.update(
            final_proposal_id=proposal["id"],
            final_amount=proposal["total_amount"],
            final_client_decision=proposal["client_decision_action"],
        )
    lines = await application_repository.list_application_vehicles_with_catalog(
        session, link["application_id"]
    )
    lines = [line for line in lines if line.get("car_status") != "not_confirmed"]
    result["vehicles"] = await _application_vehicles(session, lines)
    if any(
        line.get("dealer_company_id") is not None
        and line["dealer_company_id"] != result["dealer_company_id"]
        for line in lines
    ):
        result["participant_conflict"] = True
    result["supports"] = await _supports(
        session, "application_id", link["application_id"]
    )
    return result


async def exchange_source(session: AsyncSession, request_id: UUID) -> Record:
    request = await _row(session, ExchangeRequest.__table__, request_id)
    result: Record = {
        "exchange_request_id": request_id,
        "source_type": "exchange",
        "source_status": request.get("status"),
    }
    if not request.get("accepted_bid_id"):
        return result
    bid = await _row(session, ExchangeBid.__table__, request["accepted_bid_id"])
    if bid.get("request_id") != request_id:
        return result
    leasing = (
        await session.scalars(
            sa.select(LeasingCompany.id)
            .join(Company, Company.id == LeasingCompany.company_id)
            .where(
                LeasingCompany.company_id == request.get("lc_company_id"),
                Company.company_type == "leasing_company",
            )
        )
    ).all()
    dealer = bid.get("dealer_company_id")
    distributor = bid.get("distributor_id")
    if distributor is None:
        # A dealer's own bid need not carry a distributor. Resolve the explicit
        # company relationship at acceptance, as for ordinary leasing deals.
        participants = await _participants(session, dealer, None)
        distributor = participants["distributor_company_id"]
    result.update(
        leasing_company_id=leasing[0] if len(leasing) == 1 else None,
        dealer_company_id=dealer
        if await _company_exists(session, dealer, "dealer")
        else None,
        distributor_company_id=distributor
        if await _company_exists(session, distributor, "distributor")
        else None,
        accepted_bid_id=bid["id"],
        bid_is_accepted=bid["is_accepted"],
        bid_price=bid["price"],
        bid_quantity=bid["quantity"],
        request_quantity=request["quantity"],
        discount_type=request["discount_type"],
        discount_value=request["discount_value"],
    )
    if (
        request.get("batch_number") is not None
        and request.get("batch_index") is not None
    ):
        result["application_number"] = (
            f"{request['batch_number']}-{request['batch_index']}"
        )
    req_prod_id = request.get("product_id") or request.get("vehicle_id")
    vehicle = (
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentProduct.id.label("vehicle_id"),
                    SpecialEquipmentProduct.vin,
                    SpecialEquipmentMark.name.label("brand"),
                    SpecialEquipmentModel.name.label("model"),
                    SpecialEquipmentModification.name.label("modification"),
                    SpecialEquipmentModification.name.label("legacy_trim"),
                    SpecialEquipmentTrim.name.label("trim"),
                )
                .select_from(SpecialEquipmentProduct)
                .outerjoin(
                    SpecialEquipmentTrim,
                    SpecialEquipmentTrim.id == SpecialEquipmentProduct.trim_id,
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
                .where(SpecialEquipmentProduct.id == req_prod_id)
            )
        )
        .mappings()
        .first()
    ) if req_prod_id is not None else None
    result["vehicles"] = (
        [dict(vehicle, quantity=bid["quantity"])] if vehicle is not None else []
    )
    result["supports"] = await _supports(session, "exchange_request_id", request_id)
    return result


async def _leasing_extension_ids(session: AsyncSession, company_id: Any) -> list[Any]:
    """``leasing_companies.id`` rows of a leasing *company*.

    A fast deal stores ``companies.id`` while monetization programs and deals use the
    leasing extension id: two different UUID contracts that are joined here only.
    """
    if company_id is None:
        return []
    rows = await session.scalars(
        sa.select(LeasingCompany.id)
        .join(Company, Company.id == LeasingCompany.company_id)
        .where(
            LeasingCompany.company_id == company_id,
            Company.company_type == "leasing_company",
        )
    )
    return list(rows.all())


def _fast_deal_vehicle(row: Record) -> Record:
    """Position snapshot used to match vehicle filters of monetization programs."""
    return {
        "vehicle_id": row["product_id"],
        "fast_deal_vehicle_id": row["id"],
        "brand": row["mark_name"],
        "model": row["model_name"],
        "modification": row["modification_name"],
        "trim": row["trim_name"],
        "legacy_trim": row["modification_name"],
        "vin": row["vin"],
        "quantity": 1,
        "dealer_company_id": row["dealer_company_id"],
        "final_price": row["final_price"],
    }


async def fast_deal_source(session: AsyncSession, deal_id: UUID) -> Record:
    """Facts of one fast deal; each split DL part is an independent source.

    ``group_id`` is never a key. The leasing company is resolved explicitly through
    ``LeasingCompany.company_id``: no match, or several, leaves it undefined for the
    existing capture-failure path instead of guessing a company.
    """
    deal = await _row(session, FastDeal.__table__, deal_id)
    result: Record = {"fast_deal_id": deal_id}
    if not deal:
        return result
    dealer_id = (
        deal["initiator_company_id"]
        if deal["source_type"] == "dealer_to_leasing"
        else deal["dealer_company_id"]
    )
    leasing = await _leasing_extension_ids(session, deal["leasing_company_id"])
    result.update(
        source_type=deal["source_type"],
        source_status="deal" if deal["status"] == "confirmed" else deal["status"],
        application_number=deal["display_number"],
        client_company_id=deal["client_company_id"],
        confirmed_amount=deal["confirmed_amount"],
        leasing_company_id=leasing[0] if len(leasing) == 1 else None,
    )
    result.update(await _participants(session, dealer_id, None))
    positions = FastDealVehicle.__table__
    rows = [
        dict(row)
        for row in (
            await session.execute(
                sa.select(positions)
                .where(
                    positions.c.fast_deal_id == deal_id,
                    positions.c.item_status == "active",
                )
                .order_by(positions.c.position, positions.c.id)
            )
        ).mappings()
    ]
    if len(leasing) > 1 or any(
        row["dealer_company_id"] is not None and row["dealer_company_id"] != dealer_id
        for row in rows
    ):
        result["participant_conflict"] = True
    result["vehicles"] = [_fast_deal_vehicle(row) for row in rows]
    active = {row["id"] for row in rows}
    # The applied-support row stores the catalog unit as ``product_id``; program
    # matching reads it as ``vehicle_id``. Supports of removed positions do not count.
    result["supports"] = [
        dict(support, vehicle_id=support["product_id"])
        for support in await _supports(session, "fast_deal_id", deal_id)
        if support["fast_deal_vehicle_id"] in active
    ]
    return result
