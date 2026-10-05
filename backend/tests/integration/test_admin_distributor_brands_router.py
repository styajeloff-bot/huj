"""Integration coverage for admin distributor-company brand settings."""

from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company, DistributorBrand
from tests.legacy_compat import Mark

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _company(
    session: AsyncSession,
    *,
    company_type: str = "distributor",
) -> Company:
    value = Company(
        name=f"Brand settings {uuid4()}",
        inn=None,
        company_type=company_type,
        is_active=True,
    )
    session.add(value)
    await session.flush()
    return value


async def _marks(session: AsyncSession) -> tuple[Mark, Mark, Mark]:
    values = (
        Mark(id=f"z-{uuid4()}", name="Zeta"),
        Mark(id=f"a-{uuid4()}", name="alpha"),
        Mark(id=f"n-{uuid4()}", name=None, cyrillic_name="Бренд"),
    )
    session.add_all(values)
    await session.flush()
    return values


async def test_distributor_brands_requires_carcraft_employee(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session)
    path = f"/api/v1/admin/companies/{company.id}/distributor-brands"

    anonymous = await client.get(path)
    assert anonymous.status_code == 401

    forbidden = await client.get(path, headers=_auth(client_token))
    assert forbidden.status_code == 403

    forbidden_write = await client.put(
        path,
        json={"brand_ids": []},
        headers=_auth(client_token),
    )
    assert forbidden_write.status_code == 403


async def test_get_returns_full_sorted_directory_and_only_active_selection(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session)
    zeta, alpha, cyrillic = await _marks(db_session)
    db_session.add_all(
        [
            DistributorBrand(
                distributor_company_id=company.id,
                brand_id=zeta.id,
                is_active=True,
            ),
            DistributorBrand(
                distributor_company_id=company.id,
                brand_id=alpha.id,
                is_active=False,
            ),
        ]
    )
    await db_session.flush()

    response = await client.get(
        f"/api/v1/admin/companies/{company.id}/distributor-brands",
        headers=_auth(employee_token),
    )

    assert response.status_code == 200
    body = response.json()
    returned = {
        item["id"]: item["name"] for item in body["available_brands"]
    }
    assert returned[zeta.id] == "Zeta"
    assert returned[alpha.id] == "alpha"
    assert returned[cyrillic.id] == "Бренд"
    assert body["selected_brand_ids"] == [zeta.id]

    selected_items = [
        item["name"]
        for item in body["available_brands"]
        if item["id"] in {zeta.id, alpha.id, cyrillic.id}
    ]
    assert selected_items == ["alpha", "Zeta", "Бренд"]


@pytest.mark.parametrize("method", ["GET", "PUT"])
async def test_distributor_brands_company_not_found(
    method: str,
    client: AsyncClient,
    employee_token: str,
) -> None:
    response = await client.request(
        method,
        f"/api/v1/admin/companies/{uuid4()}/distributor-brands",
        json={"brand_ids": []} if method == "PUT" else None,
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


@pytest.mark.parametrize("method", ["GET", "PUT"])
async def test_distributor_brands_rejects_non_distributor_company(
    method: str,
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session, company_type="dealer")
    response = await client.request(
        method,
        f"/api/v1/admin/companies/{company.id}/distributor-brands",
        json={"brand_ids": []} if method == "PUT" else None,
        headers=_auth(employee_token),
    )
    assert response.status_code == 400


async def test_put_is_idempotent_and_reactivates_the_same_row(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session)
    first, second, _ = await _marks(db_session)
    path = f"/api/v1/admin/companies/{company.id}/distributor-brands"

    create = await client.put(
        path,
        json={"brand_ids": [second.id, first.id, first.id]},
        headers=_auth(employee_token),
    )
    assert create.status_code == 200
    assert create.json()["selected_brand_ids"] == sorted([first.id, second.id])

    rows = list(
        (
            await db_session.scalars(
                sa.select(DistributorBrand).where(
                    DistributorBrand.distributor_company_id == company.id
                )
            )
        ).all()
    )
    assert len(rows) == 2
    first_row = next(row for row in rows if row.brand_id == first.id)
    first_row_id = first_row.id

    repeat = await client.put(
        path,
        json={"brand_ids": [first.id, second.id]},
        headers=_auth(employee_token),
    )
    assert repeat.status_code == 200
    assert (
        await db_session.scalar(
            sa.select(sa.func.count(DistributorBrand.id)).where(
                DistributorBrand.distributor_company_id == company.id
            )
        )
        == 2
    )

    deactivate = await client.put(
        path,
        json={"brand_ids": [second.id]},
        headers=_auth(employee_token),
    )
    assert deactivate.status_code == 200
    await db_session.refresh(first_row)
    assert first_row.is_active is False

    reactivate = await client.put(
        path,
        json={"brand_ids": [first.id, second.id]},
        headers=_auth(employee_token),
    )
    assert reactivate.status_code == 200
    reactivated = await db_session.scalar(
        sa.select(DistributorBrand).where(
            DistributorBrand.id == first_row_id
        )
    )
    assert reactivated is not None
    assert reactivated.is_active is True
    assert (
        await db_session.scalar(
            sa.select(sa.func.count(DistributorBrand.id)).where(
                DistributorBrand.distributor_company_id == company.id
            )
        )
        == 2
    )


async def test_put_rejects_unknown_brand_without_partial_update(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session)
    selected, valid_new, _ = await _marks(db_session)
    existing = DistributorBrand(
        distributor_company_id=company.id,
        brand_id=selected.id,
        is_active=True,
    )
    db_session.add(existing)
    await db_session.flush()

    response = await client.put(
        f"/api/v1/admin/companies/{company.id}/distributor-brands",
        json={"brand_ids": [valid_new.id, "unknown-brand"]},
        headers=_auth(employee_token),
    )

    assert response.status_code == 400
    await db_session.refresh(existing)
    assert existing.is_active is True
    assert (
        await db_session.scalar(
            sa.select(sa.func.count(DistributorBrand.id)).where(
                DistributorBrand.distributor_company_id == company.id
            )
        )
        == 1
    )


async def test_put_empty_set_soft_deactivates_all_rows(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session)
    first, second, _ = await _marks(db_session)
    db_session.add_all(
        [
            DistributorBrand(
                distributor_company_id=company.id,
                brand_id=first.id,
                is_active=True,
            ),
            DistributorBrand(
                distributor_company_id=company.id,
                brand_id=second.id,
                is_active=True,
            ),
        ]
    )
    await db_session.flush()

    response = await client.put(
        f"/api/v1/admin/companies/{company.id}/distributor-brands",
        json={"brand_ids": []},
        headers=_auth(employee_token),
    )

    assert response.status_code == 200
    assert response.json()["selected_brand_ids"] == []
    active_count = await db_session.scalar(
        sa.select(sa.func.count(DistributorBrand.id)).where(
            DistributorBrand.distributor_company_id == company.id,
            DistributorBrand.is_active.is_(True),
        )
    )
    assert active_count == 0
