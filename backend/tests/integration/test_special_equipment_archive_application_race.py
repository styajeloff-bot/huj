"""Serialization between catalog archive and leasing-application creation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from application import special_equipment_commerce as commerce_service
from application.commands import special_equipment_management as management_commands
from application.queries.special_equipment_management import (
    GetRegistryEntityQuery,
    handle_get,
)
from application.special_equipment_commerce import (
    CreateLeasingApplicationCommand,
)
from domain.errors import DomainError
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import (
    SpecialEquipmentCategory,
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentModificationCategory,
    SpecialEquipmentProduct,
    SpecialEquipmentProductCategory,
)
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
)
from infrastructure.models.users import User
from tests.special_equipment_factories import special_equipment_directory

pytestmark = pytest.mark.asyncio


async def _setup(
    engine: AsyncEngine,
) -> tuple[UUID, UUID, UUID, UUID, UUID, UUID, UUID, UUID, int]:
    seller_id = uuid4()
    buyer_id = uuid4()
    actor_id = uuid4()
    mark_id = uuid4()
    model_id = uuid4()
    modification_id = uuid4()
    category_id = uuid4()
    product_id = uuid4()
    mark, model, modification = special_equipment_directory(
        mark_name=f"Archive race mark {uuid4()}",
        model_name="Archive race model",
        modification_name="Archive race modification",
        mark_id=mark_id,
        model_id=model_id,
        modification_id=modification_id,
    )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add_all(
            [
                Company(
                    id=seller_id,
                    name=f"Archive race seller {uuid4()}",
                    company_type="dealer",
                    is_active=True,
                ),
                Company(
                    id=buyer_id,
                    name=f"Archive race buyer {uuid4()}",
                    company_type="other",
                    is_active=True,
                ),
                User(
                    id=actor_id,
                    phone=f"+75{uuid4().int % 10**9:09d}",
                    role="carcraft_employee",
                    is_active=True,
                ),
                mark,
                model,
                modification,
                SpecialEquipmentCategory(
                    id=category_id,
                    code=f"archive-race-category-{uuid4().hex}",
                    name="Archive race category",
                    slug=f"archive-race-category-{uuid4().hex}",
                    usage_metric="engine_hours",
                ),
                SpecialEquipmentModificationCategory(
                    modification_id=modification_id,
                    category_id=category_id,
                ),
                SpecialEquipmentProduct(
                    id=product_id,
                    code=f"archive-race-product-{uuid4().hex}",
                    modification_id=modification_id,
                    seller_company_id=seller_id,
                    slug=f"archive-race-product-{uuid4().hex}",
                    condition="new",
                    vin=None,
                    no_vin=True,
                    owners_count=None,
                    price=Decimal("100.00"),
                    publication_status="published",
                    sale_status="available",
                    published_at=datetime.now(UTC),
                ),
                SpecialEquipmentProductCategory(
                    product_id=product_id,
                    category_id=category_id,
                ),
            ]
        )
        await session.commit()
        resource = await handle_get(
            GetRegistryEntityQuery("product", product_id), session
        )
        lock_version = int(resource["lock_version"])
    return (
        seller_id,
        buyer_id,
        actor_id,
        mark_id,
        model_id,
        modification_id,
        category_id,
        product_id,
        lock_version,
    )


async def _cleanup(
    engine: AsyncEngine,
    *,
    seller_id: UUID,
    buyer_id: UUID,
    actor_id: UUID,
    mark_id: UUID,
    model_id: UUID,
    modification_id: UUID,
    category_id: UUID,
    product_id: UUID,
) -> None:
    async with AsyncSession(engine) as session:
        await session.execute(
            delete(SpecialEquipmentApplicationItem).where(
                SpecialEquipmentApplicationItem.product_id == product_id
            )
        )
        await session.execute(
            delete(LeasingApplication).where(
                LeasingApplication.created_by == actor_id
            )
        )
        await session.execute(
            delete(SpecialEquipmentProduct).where(
                SpecialEquipmentProduct.id == product_id
            )
        )
        await session.execute(
            delete(SpecialEquipmentModificationCategory).where(
                SpecialEquipmentModificationCategory.modification_id
                == modification_id
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
        await session.execute(
            delete(SpecialEquipmentCategory).where(
                SpecialEquipmentCategory.id == category_id
            )
        )
        await session.execute(delete(User).where(User.id == actor_id))
        await session.execute(
            delete(Company).where(Company.id.in_([seller_id, buyer_id]))
        )
        await session.commit()


def _application_command(
    *, actor_id: UUID, buyer_id: UUID, product_id: UUID
) -> CreateLeasingApplicationCommand:
    return CreateLeasingApplicationCommand(
        source_type="platform",
        user_id=actor_id,
        company_id=buyer_id,
        product_id=product_id,
        actor_role="carcraft_employee",
    )


async def test_archive_lock_first_makes_late_application_fail(
    _engine: AsyncEngine,
) -> None:
    (
        seller_id,
        buyer_id,
        actor_id,
        mark_id,
        model_id,
        modification_id,
        category_id,
        product_id,
        lock_version,
    ) = (
        await _setup(_engine)
    )
    application_started = asyncio.Event()

    async def create_application() -> str:
        async with AsyncSession(_engine) as session:
            application_started.set()
            try:
                await commerce_service.create_leasing_application(
                    _application_command(
                        actor_id=actor_id,
                        buyer_id=buyer_id,
                        product_id=product_id,
                    ),
                    session,
                )
            except DomainError:
                await session.rollback()
                return "unavailable"
            await session.commit()
            return "created"

    task: asyncio.Task[str] | None = None
    try:
        async with AsyncSession(_engine) as archive_session:
            await management_commands.lock_catalog_for_mutation(archive_session)
            await management_commands.patch_entity(
                archive_session,
                entity_type="product",
                entity_id=product_id,
                expected_version=lock_version,
                values={"publication_status": "archived"},
            )
            task = asyncio.create_task(create_application())
            await application_started.wait()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.1)
            await archive_session.commit()

        assert await asyncio.wait_for(task, timeout=2) == "unavailable"
        async with AsyncSession(_engine) as verification:
            assert await verification.scalar(
                select(SpecialEquipmentProduct.publication_status).where(
                    SpecialEquipmentProduct.id == product_id
                )
            ) == "archived"
            assert int(
                await verification.scalar(
                    select(func.count())
                    .select_from(SpecialEquipmentApplicationItem)
                    .where(SpecialEquipmentApplicationItem.product_id == product_id)
                )
                or 0
            ) == 0
    finally:
        if task is not None and not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        await _cleanup(
            _engine,
            seller_id=seller_id,
            buyer_id=buyer_id,
            actor_id=actor_id,
            mark_id=mark_id,
            model_id=model_id,
            modification_id=modification_id,
            category_id=category_id,
            product_id=product_id,
        )


async def test_application_lock_first_makes_late_archive_fail(
    _engine: AsyncEngine,
) -> None:
    (
        seller_id,
        buyer_id,
        actor_id,
        mark_id,
        model_id,
        modification_id,
        category_id,
        product_id,
        lock_version,
    ) = (
        await _setup(_engine)
    )
    archive_started = asyncio.Event()

    async def archive() -> str:
        async with AsyncSession(_engine) as session:
            archive_started.set()
            try:
                await management_commands.lock_catalog_for_mutation(session)
                await management_commands.patch_entity(
                    session,
                    entity_type="product",
                    entity_id=product_id,
                    expected_version=lock_version,
                    values={"publication_status": "archived"},
                )
            except DomainError:
                await session.rollback()
                return "blocked"
            await session.commit()
            return "archived"

    task: asyncio.Task[str] | None = None
    try:
        async with AsyncSession(_engine) as application_session:
            await commerce_service.create_leasing_application(
                _application_command(
                    actor_id=actor_id,
                    buyer_id=buyer_id,
                    product_id=product_id,
                ),
                application_session,
            )
            task = asyncio.create_task(archive())
            await archive_started.wait()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.1)
            await application_session.commit()

        assert await asyncio.wait_for(task, timeout=2) == "blocked"
        async with AsyncSession(_engine) as verification:
            assert await verification.scalar(
                select(SpecialEquipmentProduct.publication_status).where(
                    SpecialEquipmentProduct.id == product_id
                )
            ) == "published"
            assert int(
                await verification.scalar(
                    select(func.count())
                    .select_from(SpecialEquipmentApplicationItem)
                    .where(
                        SpecialEquipmentApplicationItem.product_id == product_id,
                        SpecialEquipmentApplicationItem.item_status == "active",
                    )
                )
                or 0
            ) == 1
    finally:
        if task is not None and not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        await _cleanup(
            _engine,
            seller_id=seller_id,
            buyer_id=buyer_id,
            actor_id=actor_id,
            mark_id=mark_id,
            model_id=model_id,
            modification_id=modification_id,
            category_id=category_id,
            product_id=product_id,
        )
