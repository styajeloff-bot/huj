"""Company deactivation invariants for special-equipment sellers."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import CreateIndex, Table

from application.commands.companies import (
    DeactivateCompanyCommand,
    UpdateCompanyCommand,
    UpsertMyCompanyProfileCommand,
    handle_deactivate_company,
    handle_update_company,
    handle_upsert_my_company_profile,
)
from domain.errors import (
    CompanyAccessDeniedError,
    CompanySpecialEquipmentConflictError,
    InvalidCompanyPayloadError,
)
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
    SpecialEquipmentPurchaseOrder,
)
from infrastructure.models.users import User
from infrastructure.repositories.special_equipment_seller_guard_repository import (
    seller_deactivation_blocker_statement,
    seller_deactivation_blockers,
)
from presentation.schemas.companies import (
    UpdateCompanyRequest,
    UpsertCompanyProfileRequest,
)
from tests.special_equipment_factories import special_equipment_directory

pytestmark = pytest.mark.asyncio


async def test_seller_guard_query_and_partial_index_contract() -> None:
    seller_id = uuid4()
    sql = str(
        seller_deactivation_blocker_statement(seller_id).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert "coalesce" not in sql
    assert "seller_company_id is null" in sql
    assert "publication_status = 'published'" in sql
    assert "sale_status in ('reserved', 'sold')" in sql
    assert "item_status in ('active', 'reserved')" in sql
    assert "cancellation_requested" in sql

    expected = {
        SpecialEquipmentProduct.__table__: "idx_se_products_claimed_seller",
        SpecialEquipmentApplicationItem.__table__: (
            "idx_se_application_items_live_seller"
        ),
        SpecialEquipmentPurchaseOrder.__table__: "idx_se_orders_live_seller",
    }
    for table, index_name in expected.items():
        typed_table = cast("Table", table)
        index = next(
            item for item in typed_table.indexes if item.name == index_name
        )
        ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect())).lower()
        assert "seller_company_id" in ddl
        assert " where " in ddl

    migration = (
        Path(__file__).parents[1]
        / "alembic/versions/078_special_equipment_registry_persistence.py"
    ).read_text(encoding="utf-8")
    for index_name in expected.values():
        assert migration.count(index_name) == 2


async def _seller_and_product(
    session: AsyncSession,
    *,
    publication_status: str = "draft",
    sale_status: str = "available",
) -> tuple[Company, SpecialEquipmentProduct]:
    seller = Company(
        name=f"Special-equipment seller {uuid4()}",
        company_type="dealer",
        is_active=True,
    )
    mark, model, modification = special_equipment_directory(
        mark_name=f"Guard mark {uuid4()}",
        model_name="Guard model",
        modification_name="Guard modification",
    )
    session.add_all([seller, mark, model, modification])
    await session.flush()
    product = SpecialEquipmentProduct(
        code=f"guard-product-{uuid4().hex}",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug=f"guard-product-{uuid4().hex}",
        condition="new",
        vin=None,
        no_vin=True,
        owners_count=None,
        price=(
            Decimal("100.00")
            if sale_status in {"reserved", "sold"}
            else None
        ),
        publication_status=publication_status,
        sale_status=sale_status,
        published_at=(
            datetime.now(UTC) if publication_status == "published" else None
        ),
    )
    session.add(product)
    await session.flush()
    return seller, product


async def _deactivate(session: AsyncSession, seller_id: UUID) -> None:
    await handle_deactivate_company(
        DeactivateCompanyCommand(
            company_id=seller_id,
            actor_role="carcraft_employee",
        ),
        session,
    )


@pytest.mark.parametrize(
    ("publication_status", "sale_status", "expected_field"),
    [
        ("published", "available", "published_products"),
        ("draft", "reserved", "claimed_products"),
        ("draft", "sold", "claimed_products"),
    ],
)
async def test_live_product_blocks_seller_deactivation(
    db_session: AsyncSession,
    publication_status: str,
    sale_status: str,
    expected_field: Literal["published_products", "claimed_products"],
) -> None:
    seller, _product = await _seller_and_product(
        db_session,
        publication_status=publication_status,
        sale_status=sale_status,
    )

    blockers = await seller_deactivation_blockers(db_session, seller.id)
    assert blockers[expected_field] == 1
    with pytest.raises(CompanySpecialEquipmentConflictError):
        await _deactivate(db_session, seller.id)

    await db_session.refresh(seller)
    assert seller.is_active is True


async def test_live_application_and_order_snapshots_block_seller_deactivation(
    db_session: AsyncSession,
) -> None:
    seller, product = await _seller_and_product(db_session)
    buyer = Company(
        name=f"Guard buyer {uuid4()}", company_type="other", is_active=True
    )
    user = User(phone=f"+79{uuid4().int % 10**9:09d}", role="client")
    db_session.add_all([buyer, user])
    await db_session.flush()
    application = LeasingApplication(company_id=buyer.id, created_by=user.id)
    db_session.add(application)
    await db_session.flush()
    db_session.add(
        SpecialEquipmentApplicationItem(
            application_id=application.id,
            product_id=product.id,
            seller_company_id=seller.id,
            item_snapshot={},
            item_status="active",
        )
    )
    db_session.add(
        SpecialEquipmentPurchaseOrder(
            user_id=user.id,
            product_id=product.id,
            seller_company_id=seller.id,
            purchase_type="reservation",
            status="payment_pending",
            unit_price=Decimal("100.00"),
            total_price=Decimal("100.00"),
            paid_amount=Decimal("0.00"),
            remaining_amount=Decimal("100.00"),
            item_snapshot={},
            idempotency_key=f"guard-{uuid4()}",
            request_hash="a" * 64,
        )
    )
    await db_session.flush()

    blockers = await seller_deactivation_blockers(db_session, seller.id)
    assert blockers["live_application_items"] == 1
    assert blockers["live_purchase_orders"] == 1
    with pytest.raises(CompanySpecialEquipmentConflictError):
        await _deactivate(db_session, seller.id)


async def test_terminal_commerce_history_does_not_block_deactivation(
    db_session: AsyncSession,
) -> None:
    seller, product = await _seller_and_product(db_session)
    buyer = Company(
        name=f"Historical buyer {uuid4()}", company_type="other", is_active=True
    )
    user = User(phone=f"+78{uuid4().int % 10**9:09d}", role="client")
    db_session.add_all([buyer, user])
    await db_session.flush()
    application = LeasingApplication(company_id=buyer.id, created_by=user.id)
    db_session.add(application)
    await db_session.flush()
    db_session.add_all(
        [
            SpecialEquipmentApplicationItem(
                application_id=application.id,
                product_id=product.id,
                seller_company_id=seller.id,
                item_snapshot={},
                item_status="removed",
            ),
            SpecialEquipmentPurchaseOrder(
                user_id=user.id,
                product_id=product.id,
                seller_company_id=seller.id,
                purchase_type="reservation",
                status="cancelled",
                unit_price=Decimal("100.00"),
                total_price=Decimal("100.00"),
                paid_amount=Decimal("0.00"),
                remaining_amount=Decimal("100.00"),
                item_snapshot={},
                idempotency_key=f"historical-{uuid4()}",
                request_hash="b" * 64,
            ),
        ]
    )
    await db_session.flush()

    assert not any((await seller_deactivation_blockers(db_session, seller.id)).values())
    await _deactivate(db_session, seller.id)
    await db_session.refresh(seller)
    assert seller.is_active is False


async def test_put_command_uses_explicit_deactivation_and_reactivation(
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    seller = Company(
        name=f"Direct mutation seller {uuid4()}",
        inn=str(uuid4().int)[:10],
        company_type="dealer",
        is_active=True,
    )
    db_session.add(seller)
    await db_session.flush()

    linked_user = User(
        phone=f"+77{uuid4().int % 10**9:09d}",
        role="client",
        company_id=seller.id,
        is_active=True,
    )
    db_session.add(linked_user)
    await db_session.flush()

    deactivated = await handle_update_company(
        UpdateCompanyCommand(
            company_id=seller.id,
            actor_id=employee_user.id,
            actor_role="carcraft_employee",
            data={"is_active": False},
        ),
        db_session,
    )
    assert deactivated["company"]["is_active"] is False
    await db_session.refresh(linked_user)
    assert linked_user.is_active is False

    reactivated = await handle_update_company(
        UpdateCompanyCommand(
            company_id=seller.id,
            actor_id=employee_user.id,
            actor_role="carcraft_employee",
            data={"is_active": True},
        ),
        db_session,
    )
    assert reactivated["company"]["is_active"] is True
    await db_session.refresh(linked_user)
    assert linked_user.is_active is False


@pytest.mark.parametrize("requested", [False, True, None])
async def test_company_owner_cannot_mutate_activation_via_put_command(
    db_session: AsyncSession,
    requested: bool | None,
) -> None:
    seller = Company(
        name=f"Owner status guard {uuid4()}",
        inn=str(uuid4().int)[:10],
        company_type="dealer",
        is_active=True,
    )
    db_session.add(seller)
    await db_session.flush()
    owner = User(
        phone=f"+76{uuid4().int % 10**9:09d}",
        role="client",
        company_id=seller.id,
        is_active=True,
    )
    db_session.add(owner)
    await db_session.flush()

    with pytest.raises(CompanyAccessDeniedError):
        await handle_update_company(
            UpdateCompanyCommand(
                company_id=seller.id,
                actor_id=owner.id,
                actor_role="client",
                data={"is_active": requested},
            ),
            db_session,
        )

    await db_session.refresh(seller)
    assert seller.is_active is True


async def test_direct_profile_command_rejects_is_active_mutation(
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    seller = Company(
        name=f"Profile mutation seller {uuid4()}",
        inn=str(uuid4().int)[:10],
        company_type="dealer",
        is_active=True,
    )
    db_session.add(seller)
    await db_session.flush()
    employee_user.company_id = seller.id
    await db_session.flush()
    with pytest.raises(InvalidCompanyPayloadError):
        await handle_upsert_my_company_profile(
            UpsertMyCompanyProfileCommand(
                user_id=employee_user.id,
                data={
                    "name": seller.name,
                    "inn": seller.inn,
                    "company_type": seller.company_type,
                    "is_active": True,
                },
            ),
            db_session,
        )


@pytest.mark.parametrize("value", [False, True, None])
async def test_only_admin_update_schema_accepts_is_active(value: bool | None) -> None:
    assert UpdateCompanyRequest.model_validate({"is_active": value}).is_active is value
    with pytest.raises(ValidationError):
        UpsertCompanyProfileRequest.model_validate(
            {
                "name": "Seller",
                "inn": "1234567890",
                "company_type": "dealer",
                "legal_address": "Address",
                "phone": "+70000000000",
                "email": "seller@example.test",
                "is_active": value,
            }
        )
