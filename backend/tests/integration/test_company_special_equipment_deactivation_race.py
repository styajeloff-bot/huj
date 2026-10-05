"""Serialization tests for company deactivation versus seller selection."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from application.commands.companies import (
    DeactivateCompanyCommand,
    handle_deactivate_company,
)
from domain.errors import CompanySpecialEquipmentConflictError
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
)
from infrastructure.repositories import (
    special_equipment_management_repository as management_repository,
)
from tests.special_equipment_factories import special_equipment_directory

pytestmark = pytest.mark.asyncio


async def _setup(engine: AsyncEngine) -> tuple[UUID, UUID, UUID, UUID]:
    seller = Company(
        name=f"Concurrent seller {uuid4()}",
        company_type="dealer",
        is_active=True,
    )
    mark, model, modification = special_equipment_directory(
        mark_name=f"Concurrent mark {uuid4()}",
        model_name="Concurrent model",
        modification_name="Concurrent modification",
    )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add_all([seller, mark, model, modification])
        await session.commit()
    return seller.id, mark.id, model.id, modification.id


async def _cleanup(
    engine: AsyncEngine,
    seller_id: UUID,
    mark_id: UUID,
    model_id: UUID,
    modification_id: UUID,
) -> None:
    async with AsyncSession(engine) as session:
        await session.execute(
            delete(SpecialEquipmentProduct).where(
                SpecialEquipmentProduct.seller_company_id == seller_id
            )
        )
        await session.execute(
            delete(SpecialEquipmentModification).where(
                SpecialEquipmentModification.id == modification_id
            )
        )
        await session.execute(
            delete(SpecialEquipmentModel).where(SpecialEquipmentModel.id == model_id)
        )
        await session.execute(
            delete(SpecialEquipmentMark).where(SpecialEquipmentMark.id == mark_id)
        )
        await session.execute(delete(Company).where(Company.id == seller_id))
        await session.commit()


async def test_product_seller_lock_first_makes_deactivation_wait_then_conflict(
    _engine: AsyncEngine,
) -> None:
    seller_id, mark_id, model_id, modification_id = await _setup(_engine)
    deactivation_started = asyncio.Event()

    async def deactivate() -> str:
        async with AsyncSession(_engine) as session:
            deactivation_started.set()
            try:
                await handle_deactivate_company(
                    DeactivateCompanyCommand(
                        company_id=seller_id,
                        actor_role="carcraft_employee",
                    ),
                    session,
                )
            except CompanySpecialEquipmentConflictError:
                await session.rollback()
                return "blocked"
            await session.commit()
            return "deactivated"

    task: asyncio.Task[str] | None = None
    try:
        async with AsyncSession(_engine) as product_session:
            assert await management_repository.lock_active_seller_company(
                product_session, seller_id
            )
            product_session.add(
                SpecialEquipmentProduct(
                    code=f"concurrent-published-{uuid4().hex}",
                    modification_id=modification_id,
                    seller_company_id=seller_id,
                    slug=f"concurrent-published-{uuid4().hex}",
                    condition="new",
                    vin=None,
                    no_vin=True,
                    owners_count=None,
                    publication_status="published",
                    sale_status="available",
                    published_at=datetime.now(UTC),
                )
            )
            await product_session.flush()
            task = asyncio.create_task(deactivate())
            await deactivation_started.wait()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.1)
            await product_session.commit()

        assert await asyncio.wait_for(task, timeout=2) == "blocked"
        async with AsyncSession(_engine) as verify:
            assert await verify.scalar(
                select(Company.is_active).where(Company.id == seller_id)
            ) is True
    finally:
        if task is not None and not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        await _cleanup(
            _engine, seller_id, mark_id, model_id, modification_id
        )


async def test_deactivation_lock_first_makes_seller_selection_fail_inactive(
    _engine: AsyncEngine,
) -> None:
    seller_id, mark_id, model_id, modification_id = await _setup(_engine)
    selection_started = asyncio.Event()

    async def select_seller() -> bool:
        async with AsyncSession(_engine) as session:
            selection_started.set()
            selected = await management_repository.lock_active_seller_company(
                session, seller_id
            )
            await session.rollback()
            return selected

    task: asyncio.Task[bool] | None = None
    try:
        async with AsyncSession(_engine) as deactivation_session:
            await handle_deactivate_company(
                DeactivateCompanyCommand(
                    company_id=seller_id,
                    actor_role="carcraft_employee",
                ),
                deactivation_session,
            )
            task = asyncio.create_task(select_seller())
            await selection_started.wait()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.1)
            await deactivation_session.commit()

        assert await asyncio.wait_for(task, timeout=2) is False
        async with AsyncSession(_engine) as verify:
            assert await verify.scalar(
                select(Company.is_active).where(Company.id == seller_id)
            ) is False
    finally:
        if task is not None and not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        await _cleanup(
            _engine, seller_id, mark_id, model_id, modification_id
        )
