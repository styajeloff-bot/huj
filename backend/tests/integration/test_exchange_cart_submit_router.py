from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.companies import Company
from infrastructure.models.exchange import (
    ExchangeCartItem,
    ExchangeCartItemWarehouse,
    ExchangeRequest,
    ExchangeRequestWarehouse,
)
from infrastructure.models.users import User
from infrastructure.models.vehicles import Warehouse
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_submit_exchange_cart_routes_request_to_warehouse_company(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    lc_company = Company(
        name="Test Leasing Company",
        company_type="leasing_company",
        inn="9705000000",
    )
    dealer_center_1 = Company(
        name="Dealer Center 1",
        company_type="dealer",
        inn="7702000000",
    )
    dealer_center_3 = Company(
        name="Dealer Center 3",
        company_type="dealer",
        inn="7702000003",
    )
    db_session.add_all([lc_company, dealer_center_1, dealer_center_3])
    await db_session.flush()

    lc_user = User(
        phone="+76660001001",
        email="lc-submit@test.local",
        name="LC Admin",
        role="leasing_company",
        company_id=lc_company.id,
        is_active=True,
    )
    dealer_center_1_user = User(
        phone="+76660001002",
        email="dealer-center-1-submit@test.local",
        name="Dealer Center 1 Admin",
        role="dealer",
        company_id=dealer_center_1.id,
        is_active=True,
    )
    dealer_center_3_user = User(
        phone="+76660001003",
        email="dealer-center-3-submit@test.local",
        name="Dealer Center 3 Admin",
        role="dealer",
        company_id=dealer_center_3.id,
        is_active=True,
    )
    vehicle = Vehicle(
        status="available",
        is_available=True,
        base_price=Decimal("2500000.00"),
    )
    db_session.add_all(
        [lc_user, dealer_center_1_user, dealer_center_3_user, vehicle]
    )
    await db_session.flush()

    warehouse = Warehouse(
        address="Москва, тестовый склад",
        brand="Test Brand",
        # Reproduce Bitrix 21854: stale dealer_id points to DC1 while the
        # warehouse itself belongs to the selected DC3 company.
        dealer_id=dealer_center_1.id,
        company_id=dealer_center_3.id,
        status="active",
    )
    db_session.add(warehouse)
    await db_session.flush()

    item = ExchangeCartItem(
        user_id=lc_user.id,
        vehicle_id=vehicle.id,
        quantity=1,
    )
    db_session.add(item)
    await db_session.flush()
    db_session.add(
        ExchangeCartItemWarehouse(
            cart_item_id=item.id,
            warehouse_id=warehouse.id,
        )
    )
    await db_session.flush()

    token, _ = generate_tokens(lc_user.id, "leasing_company", lc_company.id)

    response = await client.post(
        "/api/v1/exchange/cart/submit",
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 1
    assert len(body["request_ids"]) == 1

    request = (await db_session.execute(select(ExchangeRequest))).scalar_one()
    assert request.lc_user_id == lc_user.id
    assert request.vehicle_id == vehicle.id

    request_warehouse = (
        await db_session.execute(select(ExchangeRequestWarehouse))
    ).scalar_one()
    assert request_warehouse.request_id == request.id
    assert request_warehouse.warehouse_id == warehouse.id
    assert request_warehouse.dealer_id == dealer_center_3.id

    dealer_center_1_token, _ = generate_tokens(
        dealer_center_1_user.id, "dealer", dealer_center_1.id
    )
    dealer_center_3_token, _ = generate_tokens(
        dealer_center_3_user.id, "dealer", dealer_center_3.id
    )

    dealer_center_3_response = await client.get(
        "/api/v1/exchange/requests/dealer",
        headers=_auth(dealer_center_3_token),
    )
    assert dealer_center_3_response.status_code == 200
    dealer_center_3_request_ids = {
        row["id"] for row in dealer_center_3_response.json()["requests"]
    }
    assert str(request.id) in dealer_center_3_request_ids

    dealer_center_1_response = await client.get(
        "/api/v1/exchange/requests/dealer",
        headers=_auth(dealer_center_1_token),
    )
    assert dealer_center_1_response.status_code == 200
    dealer_center_1_request_ids = {
        row["id"] for row in dealer_center_1_response.json()["requests"]
    }
    assert str(request.id) not in dealer_center_1_request_ids


async def test_submit_exchange_cart_falls_back_to_legacy_dealer_user_company(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    lc_company = Company(
        name="Legacy Leasing Company",
        company_type="leasing_company",
        inn="9705000001",
    )
    dealer_company = Company(
        name="Legacy Dealer Company",
        company_type="dealer",
        inn="7702000001",
    )
    db_session.add_all([lc_company, dealer_company])
    await db_session.flush()

    lc_user = User(
        phone="+766****1011",
        email="lc-submit-legacy@test.local",
        name="LC Legacy Admin",
        role="leasing_company",
        company_id=lc_company.id,
        is_active=True,
    )
    dealer_user = User(
        phone="+766****1012",
        email="dealer-submit-legacy@test.local",
        name="Dealer Legacy Admin",
        role="dealer",
        company_id=dealer_company.id,
        is_active=True,
    )
    vehicle = Vehicle(
        status="available",
        is_available=True,
        base_price=Decimal("2600000.00"),
    )
    db_session.add_all([lc_user, dealer_user, vehicle])
    await db_session.flush()

    warehouse = Warehouse(
        address="Москва, legacy склад",
        brand="Legacy Brand",
        dealer_id=dealer_company.id,
        # Only warehouses without company_id may use the legacy dealer_id path.
        company_id=None,
        status="active",
    )
    db_session.add(warehouse)
    await db_session.flush()

    # Simulate legacy/imported data where warehouses.dealer_id still points to
    # a dealer user. The runtime submit flow must still store companies.id in
    # exchange_request_warehouses.dealer_id instead of raising a FK error.
    try:
        await db_session.execute(text("ALTER TABLE warehouses DISABLE TRIGGER ALL"))
        await db_session.execute(
            text("UPDATE warehouses SET dealer_id = :dealer_user_id WHERE id = :warehouse_id"),
            {"dealer_user_id": dealer_user.id, "warehouse_id": warehouse.id},
        )
    finally:
        await db_session.execute(text("ALTER TABLE warehouses ENABLE TRIGGER ALL"))
    await db_session.flush()

    item = ExchangeCartItem(
        user_id=lc_user.id,
        vehicle_id=vehicle.id,
        quantity=1,
    )
    db_session.add(item)
    await db_session.flush()
    db_session.add(
        ExchangeCartItemWarehouse(
            cart_item_id=item.id,
            warehouse_id=warehouse.id,
        )
    )
    await db_session.flush()

    token, _ = generate_tokens(lc_user.id, "leasing_company", lc_company.id)

    response = await client.post(
        "/api/v1/exchange/cart/submit",
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 1

    request_warehouse = (
        await db_session.execute(select(ExchangeRequestWarehouse))
    ).scalar_one()
    assert request_warehouse.warehouse_id == warehouse.id
    assert request_warehouse.dealer_id == dealer_company.id
