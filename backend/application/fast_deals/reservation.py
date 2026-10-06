"""Global reserve of catalog units for fast deals.

Contract used by every flow:

* ``reserve_deal`` runs under the deal lock inside the send transaction. It locks all
  reservable products in a stable order, validates every claim (allocations of other
  deals/applications, purchases, other fast deals) and inserts one allocation per
  position with ``reserved_until = NULL``. Any failure raises
  ``FastDealReserveConflictError`` and the whole send is rolled back.
* ``release_*`` frees allocations in the same transaction as the status change.
* ``complete_deal`` completes allocations and marks products sold at confirmation.
* ``lock_products`` lets a flow that reserves several deals in one transaction take
  every product lock up front, in one id order.

Only a real catalog unit with its original VIN and a proven owner is reserved. The
owner is the dealer of the deal (DD: the initiator) or of the position (DL). Manual
positions and manually typed VINs never reach the catalog.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.actor import Actor
from domain.fast_deals.catalog_rules import is_reservable_unit
from domain.fast_deals.errors import FastDealReserveConflictError, FastDealStateError
from domain.fast_deals.values import ItemStatus, SourceType
from domain.fast_deals.vin import normalize_vin
from infrastructure.repositories import fast_deal_claims_repository as claims
from infrastructure.repositories import fast_deal_repository as repo
from infrastructure.repositories.fast_deal_access_repository import Scope

Record = dict[str, Any]


def _reservable(vehicles: list[Record]) -> list[Record]:
    """Active positions flagged by the server as reservable, in lock order."""
    return sorted(
        (
            item
            for item in vehicles
            if item["is_reservable"] and item["item_status"] == ItemStatus.ACTIVE
        ),
        key=lambda item: item["product_id"] or UUID(int=0),
    )


def _expected_owner(deal: Record, position: Record) -> UUID | None:
    """DD: the initiating dealer owns every unit. DL: the dealer of the position."""
    if deal["source_type"] == SourceType.DEALER_TO_LEASING:
        owner: UUID | None = deal["initiator_company_id"]
        return owner
    dealer: UUID | None = position["dealer_company_id"]
    return dealer


def _visible_to(actor: Actor) -> Scope:
    return Scope(
        role=actor.role,
        company_id=actor.company_id,
        user_id=actor.user_id,
        is_company_admin=actor.is_company_admin,
    )


def _conflict(message: str, position: Record, number: str | None = None) -> FastDealReserveConflictError:
    return FastDealReserveConflictError(message, vin=position["vin"], source_number=number)


def _foreign_claim(position: Record, claim: Record) -> FastDealReserveConflictError:
    """Name the competing source only when it is a fast deal the actor may see."""
    vin = position["vin"]
    if claim["fast_deal_id"] is None:
        return _conflict(f"Техника с VIN {vin} уже закреплена за другой заявкой или покупкой", position)
    number = claim["fast_deal_number"]
    if number is None:
        return _conflict(f"Техника с VIN {vin} уже закреплена за другой сделкой", position)
    return _conflict(f"Техника с VIN {vin} уже закреплена за сделкой {number}", position, number)


def _availability_problem(position: Record, product: Record | None) -> str | None:
    vin = position["vin"]
    if product is None:
        return f"Техника с VIN {vin} больше не найдена в каталоге"
    if product["publication_status"] != "published":
        return f"Объявление техники с VIN {vin} снято с публикации"
    if product["sale_status"] != "available":
        return (
            f"Техника с VIN {vin} недоступна: она уже зарезервирована, "
            "продана или снята с продажи"
        )
    if normalize_vin(product["vin"]) != normalize_vin(vin):
        return f"VIN в каталоге изменился: техника с VIN {vin} больше не соответствует позиции"
    return None


def _ownership_and_price_problem(deal: Record, position: Record, product: Record) -> str | None:
    vin = position["vin"]
    if not is_reservable_unit(
        product,
        owner_company_id=product["owner_company_id"],
        expected_owner_id=_expected_owner(deal, position),
        vin_entered_manually=position["vin_entered_manually"],
    ):
        return (
            f"Принадлежность техники с VIN {vin} не подтверждена: "
            "резервировать можно только технику дилера-владельца"
        )
    if not product["price_on_request"] and product["price"] is None:
        return f"У техники с VIN {vin} не задана цена, резерв невозможен"
    has_price_from = (product["price_from"] or 0) > 0
    if product["price_on_request"] and not has_price_from and position["final_price"] <= 0:
        return (
            f"Для техники с VIN {vin} с ценой по запросу "
            "нужна согласованная цена больше нуля"
        )
    return None


def _check_unit(
    deal: Record, position: Record, product: Record | None
) -> FastDealReserveConflictError | None:
    """Everything that must hold for the unit itself; checked again at every send."""
    problem = _availability_problem(position, product)
    if problem is None and product is not None:
        problem = _ownership_and_price_problem(deal, position, product)
    return None if problem is None else _conflict(problem, position)


async def lock_products(session: AsyncSession, vehicles: list[Record]) -> None:
    """Lock every reservable product of the positions in one statement, by id.

    A flow that reserves several deals in one transaction (the DL split) calls this
    first, so concurrent sends over overlapping units take their locks in one order.
    Idempotent: ``reserve_deal`` locks the same rows again without waiting.
    """
    product_ids = [item["product_id"] for item in _reservable(vehicles) if item["product_id"]]
    await claims.lock_products(session, product_ids)


async def reserve_deal(
    session: AsyncSession, deal: Record, vehicles: list[Record], actor: Actor
) -> None:
    """Reserve every ``is_reservable`` active position of the deal."""
    positions = _reservable(vehicles)
    if not positions:
        return
    for position in positions:
        if position["product_id"] is None:
            raise _conflict(
                f"Техника с VIN {position['vin']} не связана с объявлением каталога", position
            )
    product_ids = [position["product_id"] for position in positions]
    products = await claims.lock_products(session, product_ids)
    open_claims = await claims.active_allocations(
        session, product_ids, visible_to=_visible_to(actor)
    )
    commerce_claimed = await claims.commerce_claims(session, product_ids)

    pending: list[Record] = []
    for position in positions:
        claim = open_claims.get(position["product_id"])
        if claim is not None and claim["fast_deal_vehicle_id"] == position["id"]:
            continue  # this very position already holds the unit
        if claim is not None:
            raise _foreign_claim(position, claim)
        if position["product_id"] in commerce_claimed:
            raise _conflict(
                f"Техника с VIN {position['vin']} уже закреплена за другой заявкой или покупкой",
                position,
            )
        error = _check_unit(deal, position, products.get(position["product_id"]))
        if error is not None:
            raise error
        pending.append(position)

    for position in pending:
        failure = await claims.claim_unit(
            session,
            product_id=position["product_id"],
            vehicle_id=position["id"],
            vin=position["vin"],
            unit_price=position["final_price"],
            created_by=actor.user_id,
        )
        if failure == "claimed":
            raise _conflict(
                f"Техника с VIN {position['vin']} только что закреплена за другой сделкой или заявкой",
                position,
            )
        if failure == "price":
            raise _conflict(
                f"Для техники с VIN {position['vin']} нет цены, достаточной для резерва",
                position,
            )
        if failure == "unavailable":
            raise _conflict(
                f"Техника с VIN {position['vin']} стала недоступна для резервирования", position
            )


async def release_deal(session: AsyncSession, deal_id: UUID, *, reason: str) -> None:
    """Release every active allocation of the deal; completed ones are untouched."""
    released: list[UUID] = await claims.release_deal_claims(session, deal_id, reason=reason)
    await claims.restore_available(session, released)


async def release_vehicle(session: AsyncSession, vehicle_id: UUID, *, reason: str) -> None:
    """Release the allocation of one position (removal or replacement)."""
    released: list[UUID] = await claims.release_vehicle_claims(
        session, vehicle_id, reason=reason
    )
    await claims.restore_available(session, released)


async def complete_deal(session: AsyncSession, deal_id: UUID) -> None:
    """Complete the deal's allocations and mark their products ``sold``.

    Ownership and the hold are verified again: the deal is refused when a unit is
    no longer held by it, instead of selling something it does not own.
    """
    deal: Record | None = await repo.get_deal(session, deal_id)
    if deal is None:
        return
    vehicles: list[Record] = await repo.list_vehicles(session, deal_id)
    positions = _reservable(vehicles)
    if not positions:
        return
    products = await claims.lock_products(
        session, [position["product_id"] for position in positions]
    )
    held: dict[UUID, Record] = {
        allocation["fast_deal_vehicle_id"]: allocation
        for allocation in await claims.deal_allocations(session, deal_id)
    }
    for position in positions:
        if not _is_held(deal, position, held.get(position["id"]), products.get(position["product_id"])):
            raise FastDealStateError(
                f"Техника с VIN {position['vin']} больше не закреплена за сделкой, "
                "подтверждение невозможно. Измените сделку или отмените её"
            )
    await claims.complete_allocations(
        session, [held[position["id"]]["id"] for position in positions]
    )
    await claims.mark_sold(session, [position["product_id"] for position in positions])


def _is_held(
    deal: Record, position: Record, allocation: Record | None, product: Record | None
) -> bool:
    """The position's own open allocation covers the unit, its status and owner fit."""
    if allocation is None or product is None:
        return False
    if allocation["product_id"] != position["product_id"]:
        return False
    if product["owner_company_id"] != _expected_owner(deal, position):
        return False
    expected_status = "sold" if allocation["completed_at"] is not None else "reserved"
    return bool(product["sale_status"] == expected_status)
