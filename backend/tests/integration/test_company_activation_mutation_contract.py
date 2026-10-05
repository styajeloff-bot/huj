"""HTTP contract for guarded admin activation and immutable profile status."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.users import User
from tests.special_equipment_factories import special_equipment_directory

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("current", "requested"), [(True, False), (False, True)]
)
async def test_put_company_preserves_explicit_activation_contract(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
    current: bool,
    requested: bool,
) -> None:
    company = Company(
        name=f"Activation contract {uuid4()}",
        company_type="dealer",
        is_active=current,
    )
    db_session.add(company)
    await db_session.flush()

    response = await client.put(
        f"/api/v1/companies/{company.id}",
        headers=_auth(employee_token),
        json={"is_active": requested},
    )

    assert response.status_code == 200, response.text
    assert response.json()["company"]["is_active"] is requested
    await db_session.refresh(company)
    assert company.is_active is requested


@pytest.mark.parametrize("via_put", [False, True])
async def test_company_deactivation_endpoints_block_published_seller(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
    via_put: bool,
) -> None:
    seller = Company(
        name=f"Published seller {uuid4()}",
        company_type="dealer",
        is_active=True,
    )
    mark, model, modification = special_equipment_directory(
        mark_name=f"Published mark {uuid4()}",
        model_name="Published model",
        modification_name="Published modification",
    )
    db_session.add_all([seller, mark, model, modification])
    await db_session.flush()
    db_session.add(
        SpecialEquipmentProduct(
            code=f"published-company-guard-{uuid4().hex}",
            modification_id=modification.id,
            seller_company_id=seller.id,
            slug=f"published-company-guard-{uuid4().hex}",
            condition="new",
            vin=None,
            no_vin=True,
            owners_count=None,
            publication_status="published",
            sale_status="available",
            published_at=datetime.now(UTC),
        )
    )
    await db_session.flush()

    if via_put:
        response = await client.put(
            f"/api/v1/companies/{seller.id}",
            headers=_auth(employee_token),
            json={"is_active": False},
        )
    else:
        response = await client.delete(
            f"/api/v1/companies/{seller.id}",
            headers=_auth(employee_token),
        )

    assert response.status_code == 409
    await db_session.refresh(seller)
    assert seller.is_active is True


@pytest.mark.parametrize("requested", [False, True, None])
async def test_company_owner_cannot_mutate_activation_via_put(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
    requested: bool | None,
) -> None:
    company = Company(
        name=f"Owner activation guard {uuid4()}",
        company_type="dealer",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    client_user.company_id = company.id
    await db_session.flush()

    response = await client.put(
        f"/api/v1/companies/{company.id}",
        headers=_auth(client_token),
        json={"is_active": requested},
    )

    assert response.status_code == 403, response.text
    await db_session.refresh(company)
    assert company.is_active is True


async def test_company_update_openapi_documents_employee_only_activation(
    client: AsyncClient,
    employee_token: str,
) -> None:
    response = await client.get(
        "/api/v1/openapi.json", headers=_auth(employee_token)
    )

    assert response.status_code == 200
    description = response.json()["paths"]["/api/v1/companies/{company_id}"][
        "put"
    ]["description"]
    assert "`is_active`" in description
    assert "только сотрудникам CarCraft" in description
    assert "`null`" in description


@pytest.mark.parametrize("requested", [False, True])
async def test_profile_upsert_rejects_activation_mutation(
    client: AsyncClient,
    client_token: str,
    requested: bool,
) -> None:
    response = await client.post(
        "/api/v1/companies/profile",
        headers=_auth(client_token),
        json={
            "name": "Activation contract",
            "inn": str(uuid4().int)[:10],
            "company_type": "dealer",
            "legal_address": "Россия",
            "phone": "+70000000000",
            "email": "activation-contract@example.test",
            "is_active": requested,
        },
    )

    assert response.status_code == 422
