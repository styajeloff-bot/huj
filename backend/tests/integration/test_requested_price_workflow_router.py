from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from domain.special_equipment_application_pricing import (
    ItemNotPriceOnRequestError,
    PriceOnRequestPendingError,
)
from infrastructure.auth import generate_tokens
from infrastructure.models.companies import Company
from infrastructure.models.users import User
from presentation.routers import admin_applications as admin_router
from presentation.routers import dealer_leasing_applications as dealer_router

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _dealer_token(db_session: AsyncSession) -> str:
    company = Company(
        name="Dealer requested price",
        inn="7700122144",
        company_type="dealer",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    user = User(
        phone="+76661221440",
        email="price-dealer@test.local",
        name="Price dealer",
        role="dealer",
        company_id=company.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    token, _ = generate_tokens(user.id, "dealer", company.id)
    return token


async def test_dealer_price_patch_uses_exact_success_contract(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application_id = uuid4()
    item_id = uuid4()
    actor_id = uuid4()
    changed_at = datetime.now(UTC)
    observed: dict[str, Any] = {}

    async def set_price(command: Any, _session: Any) -> dict[str, Any]:
        observed["command"] = command
        return {
            "item_id": item_id,
            "application_id": application_id,
            "agreed_price": Decimal("7250000.00"),
            "currency": "RUB",
            "status": "price_set",
            "price_set_by": actor_id,
            "price_set_at": changed_at,
            "application_total_amount": Decimal("11000000.00"),
        }

    monkeypatch.setattr(
        dealer_router,
        "handle_set_dealer_application_item_price",
        set_price,
    )
    token = await _dealer_token(db_session)

    response = await client.patch(
        f"/api/v1/dealer/leasing-applications/{application_id}/items/{item_id}/price",
        json={"agreed_price": "7250000.00"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    assert response.json() == {
        "item_id": str(item_id),
        "application_id": str(application_id),
        "agreed_price": "7250000.00",
        "currency": "RUB",
        "status": "price_set",
        "price_set_by": str(actor_id),
        "price_set_at": changed_at.isoformat(),
        "application_total_amount": "11000000.00",
    }
    assert observed["command"].agreed_price == Decimal("7250000.00")


async def test_dealer_price_patch_returns_exact_endpoint_error_envelope(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise ItemNotPriceOnRequestError()

    monkeypatch.setattr(
        dealer_router,
        "handle_set_dealer_application_item_price",
        reject,
    )
    token = await _dealer_token(db_session)

    response = await client.patch(
        "/api/v1/dealer/leasing-applications/"
        f"{uuid4()}/items/{uuid4()}/price",
        json={"agreed_price": "1.00"},
        headers=_auth(token),
    )

    assert response.status_code == 422
    assert response.json() == {
        "error_code": "ITEM_NOT_PRICE_ON_REQUEST",
        "message": "Для позиции не требуется согласование цены",
    }


async def test_admin_assignment_pending_price_maps_to_409_code(
    client: AsyncClient,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise PriceOnRequestPendingError()

    monkeypatch.setattr(
        admin_router,
        "handle_assign_leasing_companies_to_application",
        reject,
    )

    response = await client.put(
        f"/api/v1/admin/applications/{uuid4()}/assign-leasing-companies",
        json={"leasing_company_ids": [str(uuid4())]},
        headers=_auth(employee_token),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "PRICE_ON_REQUEST_PENDING"
