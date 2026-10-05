"""Idempotent bulk upserts for the async data-import pipeline.

Only repositories may touch ORM models, so all ``pg_insert ... ON CONFLICT``
statements for vehicles / exchange / distributor-dealer-links live here. The
application service builds plain column-value dicts and calls these helpers.
"""
from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import DistributorDealerLink
from infrastructure.models.exchange import ExchangeBid, ExchangeRequest
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.vehicles import Warehouse

_VW_NS = uuid.UUID("d6f1b2a0-0000-4000-8000-000000000001")


async def _upsert_by_id(
    session: AsyncSession, model: Any, values: dict[str, Any]
) -> None:
    stmt = pg_insert(model).values(**values)
    update_cols = {k: stmt.excluded[k] for k in values if k != "id"}
    stmt = stmt.on_conflict_do_update(index_elements=[model.id], set_=update_cols)
    await session.execute(stmt)


async def upsert_vehicle(session: AsyncSession, values: dict[str, Any]) -> None:
    await _upsert_by_id(session, SpecialEquipmentProduct, values)


async def upsert_warehouse(session: AsyncSession, values: dict[str, Any]) -> None:
    await _upsert_by_id(session, Warehouse, values)


async def upsert_vehicle_warehouse(
    session: AsyncSession, vehicle_id: UUID, warehouse_id: UUID
) -> None:
    """Place a product in a warehouse."""
    stmt = (
        sa.update(SpecialEquipmentProduct)
        .where(SpecialEquipmentProduct.id == vehicle_id)
        .values(warehouse_id=warehouse_id)
    )
    await session.execute(stmt)


async def upsert_exchange_request(
    session: AsyncSession, values: dict[str, Any]
) -> None:
    await _upsert_by_id(session, ExchangeRequest, values)


async def upsert_exchange_bid(session: AsyncSession, values: dict[str, Any]) -> None:
    await _upsert_by_id(session, ExchangeBid, values)


async def upsert_distributor_dealer_link(
    session: AsyncSession, distributor_company_id: UUID, dealer_company_id: UUID
) -> None:
    stmt = (
        pg_insert(DistributorDealerLink)
        .values(
            distributor_company_id=distributor_company_id,
            dealer_company_id=dealer_company_id,
        )
        .on_conflict_do_nothing(
            index_elements=[
                DistributorDealerLink.distributor_company_id,
                DistributorDealerLink.dealer_company_id,
            ]
        )
    )
    await session.execute(stmt)
