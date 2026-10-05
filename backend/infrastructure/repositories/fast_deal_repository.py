"""Persistence of the fast deal aggregate: deal, positions, invitations, offers, history.

Every function returns plain dicts (never ORM objects) and never commits. Money is
``Decimal``. Parents are locked before children; callers lock the deal first.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.fast_deals import (
    FastDeal,
    FastDealAssignee,
    FastDealFile,
    FastDealLcApplication,
    FastDealOffer,
    FastDealStatusHistory,
    FastDealSupportRequest,
    FastDealVehicle,
)
from infrastructure.models.support import ApplicationAppliedSupport
from infrastructure.repository_timing import timed_repository

Record = dict[str, Any]


def _dict(row: Any) -> Record:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _now() -> datetime:
    return datetime.now(UTC)


# ------------------------------------------------------------------------- numbering

@timed_repository
async def acquire_number_lock(session: AsyncSession, key: str) -> None:
    """Transaction advisory lock serialising numbers of one direction, INN and day."""
    await session.execute(
        sa.select(sa.func.pg_advisory_xact_lock(sa.func.hashtextextended(key, 0)))
    )


@timed_repository
async def max_number_sequence(session: AsyncSession, prefix: str) -> int:
    """Highest sequence among numbers that start with ``prefix`` (``DD-<INN>-<DDMMYY>-``)."""
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    value = await session.scalar(
        sa.select(
            sa.func.max(
                sa.cast(
                    sa.func.substr(FastDeal.display_number, len(prefix) + 1), sa.Integer
                )
            )
        ).where(FastDeal.display_number.like(escaped + "%", escape="\\"))
    )
    return int(value or 0)


# ---------------------------------------------------------------------------- deals

@timed_repository
async def get_deal(session: AsyncSession, deal_id: UUID, *, lock: bool = False) -> Record | None:
    stmt = sa.select(FastDeal).where(FastDeal.id == deal_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = await session.scalar(stmt)
    return _dict(row) if row else None


@timed_repository
async def deal_id_of_vehicle(session: AsyncSession, vehicle_id: UUID) -> UUID | None:
    return await session.scalar(
        sa.select(FastDealVehicle.fast_deal_id).where(FastDealVehicle.id == vehicle_id)
    )


@timed_repository
async def deal_id_of_lc_application(session: AsyncSession, lc_application_id: UUID) -> UUID | None:
    return await session.scalar(
        sa.select(FastDealLcApplication.fast_deal_id).where(
            FastDealLcApplication.id == lc_application_id
        )
    )


@timed_repository
async def deal_id_of_support_request(session: AsyncSession, request_id: UUID) -> UUID | None:
    return await session.scalar(
        sa.select(FastDealSupportRequest.fast_deal_id).where(
            FastDealSupportRequest.id == request_id
        )
    )


@timed_repository
async def deal_id_of_file(session: AsyncSession, file_id: UUID) -> UUID | None:
    return await session.scalar(
        sa.select(FastDealFile.fast_deal_id).where(FastDealFile.id == file_id)
    )


@timed_repository
async def insert_deal(session: AsyncSession, values: Record) -> Record:
    row = FastDeal(**values)
    session.add(row)
    await session.flush()
    return _dict(row)


@timed_repository
async def update_deal(session: AsyncSession, deal_id: UUID, values: Record) -> Record:
    """Write business columns; the version is bumped separately by ``bump_version``."""
    await session.execute(
        sa.update(FastDeal)
        .where(FastDeal.id == deal_id)
        .values(**values, updated_at=sa.func.now())
    )
    deal = await get_deal(session, deal_id)
    assert deal is not None
    return deal


@timed_repository
async def bump_version(session: AsyncSession, deal_id: UUID) -> int:
    """Every parent or child mutation advances the parent version exactly once."""
    version = await session.scalar(
        sa.update(FastDeal)
        .where(FastDeal.id == deal_id)
        .values(version=FastDeal.version + 1, updated_at=sa.func.now())
        .returning(FastDeal.version)
    )
    assert version is not None
    return int(version)


@timed_repository
async def delete_draft_cascade(session: AsyncSession, deal_id: UUID) -> list[str]:
    """Explicit removal of a never-sent draft; returns storage keys to clean up.

    Sent deals keep their history; no FK of this module cascades. The caller checks
    ``sent_at IS NULL`` and the draft status under the deal lock.
    """
    vehicle_ids = list(
        (
            await session.scalars(
                sa.select(FastDealVehicle.id).where(FastDealVehicle.fast_deal_id == deal_id)
            )
        ).all()
    )
    file_rows = (
        await session.execute(
            sa.select(FastDealFile.storage_key).where(FastDealFile.fast_deal_id == deal_id)
        )
    ).all()
    keys = sorted({row.storage_key for row in file_rows})
    # Offers reference files and applications; the PDF link goes first.
    await session.execute(
        sa.update(FastDealOffer)
        .where(
            FastDealOffer.lc_application_id.in_(
                sa.select(FastDealLcApplication.id).where(
                    FastDealLcApplication.fast_deal_id == deal_id
                )
            )
        )
        .values(pdf_file_id=None)
    )
    await session.execute(
        sa.update(FastDealLcApplication)
        .where(FastDealLcApplication.fast_deal_id == deal_id)
        .values(current_offer_id=None)
    )
    await session.execute(sa.update(FastDeal).where(FastDeal.id == deal_id).values(final_offer_id=None))
    await session.execute(sa.delete(FastDealFile).where(FastDealFile.fast_deal_id == deal_id))
    await session.execute(
        sa.delete(FastDealOffer).where(
            FastDealOffer.lc_application_id.in_(
                sa.select(FastDealLcApplication.id).where(
                    FastDealLcApplication.fast_deal_id == deal_id
                )
            )
        )
    )
    await session.execute(
        sa.delete(ApplicationAppliedSupport).where(ApplicationAppliedSupport.fast_deal_id == deal_id)
    )
    await session.execute(
        sa.delete(FastDealSupportRequest).where(FastDealSupportRequest.fast_deal_id == deal_id)
    )
    await session.execute(
        sa.delete(FastDealStatusHistory).where(FastDealStatusHistory.fast_deal_id == deal_id)
    )
    await session.execute(
        sa.delete(FastDealLcApplication).where(FastDealLcApplication.fast_deal_id == deal_id)
    )
    await session.execute(sa.delete(FastDealAssignee).where(FastDealAssignee.fast_deal_id == deal_id))
    if vehicle_ids:
        await session.execute(
            sa.update(FastDealVehicle)
            .where(FastDealVehicle.id.in_(vehicle_ids))
            .values(replaced_by_id=None)
        )
        await session.execute(sa.delete(FastDealVehicle).where(FastDealVehicle.id.in_(vehicle_ids)))
    await session.execute(sa.delete(FastDeal).where(FastDeal.id == deal_id))
    await session.flush()
    return keys


# ------------------------------------------------------------------------- positions

@timed_repository
async def list_vehicles(
    session: AsyncSession, deal_id: UUID, *, include_inactive: bool = False
) -> list[Record]:
    stmt = sa.select(FastDealVehicle).where(FastDealVehicle.fast_deal_id == deal_id)
    if not include_inactive:
        stmt = stmt.where(FastDealVehicle.item_status == "active")
    rows = await session.scalars(stmt.order_by(FastDealVehicle.position, FastDealVehicle.id))
    return [_dict(row) for row in rows.all()]


@timed_repository
async def get_vehicle(
    session: AsyncSession, vehicle_id: UUID, *, lock: bool = False
) -> Record | None:
    stmt = sa.select(FastDealVehicle).where(FastDealVehicle.id == vehicle_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = await session.scalar(stmt)
    return _dict(row) if row else None


@timed_repository
async def next_vehicle_position(session: AsyncSession, deal_id: UUID) -> int:
    value = await session.scalar(
        sa.select(sa.func.max(FastDealVehicle.position)).where(
            FastDealVehicle.fast_deal_id == deal_id
        )
    )
    return 0 if value is None else int(value) + 1


@timed_repository
async def insert_vehicle(session: AsyncSession, values: Record) -> Record:
    row = FastDealVehicle(**values)
    session.add(row)
    await session.flush()
    return _dict(row)


@timed_repository
async def update_vehicle(session: AsyncSession, vehicle_id: UUID, values: Record) -> Record:
    await session.execute(
        sa.update(FastDealVehicle)
        .where(FastDealVehicle.id == vehicle_id)
        .values(**values, updated_at=sa.func.now())
    )
    vehicle = await get_vehicle(session, vehicle_id)
    assert vehicle is not None
    return vehicle


@timed_repository
async def vins_in_other_active_deals(
    session: AsyncSession, vins: list[str], *, exclude_deal_id: UUID
) -> list[Record]:
    """Active positions with the same VIN in other unfinished deals (informational)."""
    if not vins:
        return []
    rows = await session.execute(
        sa.select(FastDealVehicle.vin, FastDeal.id, FastDeal.display_number, FastDeal.status)
        .join(FastDeal, FastDeal.id == FastDealVehicle.fast_deal_id)
        .where(
            FastDealVehicle.vin.in_(vins),
            FastDealVehicle.item_status == "active",
            FastDeal.id != exclude_deal_id,
            FastDeal.status.notin_(("cancelled", "rejected")),
        )
    )
    return [
        {"vin": r.vin, "deal_id": r.id, "display_number": r.display_number, "status": r.status}
        for r in rows
    ]


# ------------------------------------------------------------- invitations and offers

@timed_repository
async def list_lc_applications(
    session: AsyncSession,
    deal_id: UUID,
    *,
    current_cycle_only: bool = True,
    leasing_company_id: UUID | None = None,
    lock: bool = False,
) -> list[Record]:
    stmt = sa.select(FastDealLcApplication).where(FastDealLcApplication.fast_deal_id == deal_id)
    if current_cycle_only:
        stmt = stmt.where(FastDealLcApplication.archived_at.is_(None))
    if leasing_company_id is not None:
        stmt = stmt.where(FastDealLcApplication.leasing_company_id == leasing_company_id)
    stmt = stmt.order_by(FastDealLcApplication.created_at, FastDealLcApplication.id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return [_dict(row) for row in (await session.scalars(stmt)).all()]


@timed_repository
async def get_lc_application(
    session: AsyncSession, lc_application_id: UUID, *, lock: bool = False
) -> Record | None:
    stmt = sa.select(FastDealLcApplication).where(FastDealLcApplication.id == lc_application_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = await session.scalar(stmt)
    return _dict(row) if row else None


@timed_repository
async def insert_lc_application(session: AsyncSession, values: Record) -> Record:
    row = FastDealLcApplication(**values)
    session.add(row)
    await session.flush()
    return _dict(row)


@timed_repository
async def update_lc_application(
    session: AsyncSession, lc_application_id: UUID, values: Record
) -> Record:
    await session.execute(
        sa.update(FastDealLcApplication)
        .where(FastDealLcApplication.id == lc_application_id)
        .values(**values, updated_at=sa.func.now())
    )
    row = await get_lc_application(session, lc_application_id)
    assert row is not None
    return row


@timed_repository
async def archive_current_cycle(session: AsyncSession, deal_id: UUID) -> list[Record]:
    """Close the review cycle: supersede its offers and archive its invitations.

    Returns the invitations that were archived, for notifications. History, offers
    and files stay; they are only marked.
    """
    applications = await list_lc_applications(session, deal_id, lock=True)
    if not applications:
        return []
    ids = [item["id"] for item in applications]
    now = _now()
    await session.execute(
        sa.update(FastDealOffer)
        .where(FastDealOffer.lc_application_id.in_(ids), FastDealOffer.superseded_at.is_(None))
        .values(superseded_at=now)
    )
    await session.execute(
        sa.update(FastDealLcApplication)
        .where(FastDealLcApplication.id.in_(ids))
        .values(archived_at=now, updated_at=now)
    )
    return applications


@timed_repository
async def insert_offer(session: AsyncSession, values: Record) -> Record:
    row = FastDealOffer(**values)
    session.add(row)
    await session.flush()
    return _dict(row)


@timed_repository
async def get_offer(session: AsyncSession, offer_id: UUID) -> Record | None:
    row = await session.get(FastDealOffer, offer_id)
    return _dict(row) if row else None


@timed_repository
async def list_offers(
    session: AsyncSession, lc_application_ids: list[UUID], *, current_only: bool = True
) -> list[Record]:
    if not lc_application_ids:
        return []
    stmt = sa.select(FastDealOffer).where(FastDealOffer.lc_application_id.in_(lc_application_ids))
    if current_only:
        stmt = stmt.where(FastDealOffer.superseded_at.is_(None))
    rows = await session.scalars(stmt.order_by(FastDealOffer.created_at, FastDealOffer.id))
    return [_dict(row) for row in rows.all()]


# ------------------------------------------------------------------------------ history

@timed_repository
async def append_history(
    session: AsyncSession,
    *,
    deal_id: UUID,
    event_type: str,
    actor_user_id: UUID | None,
    actor_company_id: UUID | None,
    from_status: str | None = None,
    to_status: str | None = None,
    reason: str | None = None,
    changes: Record | None = None,
    lc_application_id: UUID | None = None,
    deal_version: int | None = None,
    review_cycle: int | None = None,
) -> Record:
    row = FastDealStatusHistory(
        fast_deal_id=deal_id,
        lc_application_id=lc_application_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=actor_user_id,
        actor_company_id=actor_company_id,
        reason=reason,
        changes=changes,
        deal_version=deal_version,
        review_cycle=review_cycle,
    )
    session.add(row)
    await session.flush()
    return _dict(row)


@timed_repository
async def list_history(session: AsyncSession, deal_id: UUID) -> list[Record]:
    """History with the actor's name and company name, oldest first."""
    from infrastructure.models.companies import Company
    from infrastructure.models.users import User

    rows = await session.execute(
        sa.select(
            FastDealStatusHistory,
            User.name.label("actor_name"),
            Company.name.label("actor_company_name"),
        )
        .outerjoin(User, User.id == FastDealStatusHistory.actor_user_id)
        .outerjoin(Company, Company.id == FastDealStatusHistory.actor_company_id)
        .where(FastDealStatusHistory.fast_deal_id == deal_id)
        .order_by(FastDealStatusHistory.created_at, FastDealStatusHistory.id)
    )
    return [
        {**_dict(item), "actor_name": name, "actor_company_name": company}
        for item, name, company in rows.all()
    ]
