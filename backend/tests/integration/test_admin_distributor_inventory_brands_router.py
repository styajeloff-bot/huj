"""Distributor inventory brands use the same ownership as the vehicle cabinet."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import (
    Company,
    DistributorBrand,
    DistributorDealerLink,
)
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.models.users import User
from infrastructure.models.vehicles import Warehouse
from tests.legacy_compat import Mark, Vehicle, VehicleWarehouse

pytestmark = pytest.mark.asyncio


def _path(company_id: UUID) -> str:
    return f"/api/v1/admin/companies/{company_id}/distributor-inventory-brands"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _company(session: AsyncSession, company_type: str) -> Company:
    company = Company(
        name=f"Inventory brands {uuid4()}",
        company_type=company_type,
        is_active=True,
    )
    session.add(company)
    await session.flush()
    return company


async def _vehicle(
    session: AsyncSession,
    mark: Mark,
    *,
    dealer_id: UUID | None = None,
    warehouse: Warehouse | None = None,
) -> Vehicle:
    vehicle = Vehicle(mark_id=mark.id, dealer_id=dealer_id)
    session.add(vehicle)
    await session.flush()
    if warehouse is not None:
        session.add(VehicleWarehouse(vehicle_id=vehicle.id, warehouse_id=warehouse.id))
        await session.flush()
    return vehicle


async def test_inventory_brands_require_employee(
    client: AsyncClient,
    client_token: str,
) -> None:
    path = _path(uuid4())
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=_auth(client_token))).status_code == 403


async def test_inventory_brands_validate_company(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    headers = _auth(employee_token)
    assert (await client.get(_path(uuid4()), headers=headers)).status_code == 404
    dealer = await _company(db_session, "dealer")
    assert (await client.get(_path(dealer.id), headers=headers)).status_code == 400


@pytest.mark.parametrize("linked_dealer", [False, True])
async def test_inventory_brands_do_not_fall_back_to_manual_assignments_or_catalog(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
    linked_dealer: bool,
) -> None:
    distributor = await _company(db_session, "distributor")
    dealer = await _company(db_session, "dealer")
    mark = Mark(id=f"manual-{uuid4()}", name="Assigned without inventory")
    db_session.add(mark)
    await db_session.flush()
    db_session.add(
        DistributorBrand(distributor_company_id=distributor.id, brand_id=mark.id)
    )
    if linked_dealer:
        db_session.add(
            DistributorDealerLink(
                distributor_company_id=distributor.id, dealer_company_id=dealer.id
            )
        )
    await _vehicle(db_session, mark)

    response = await client.get(_path(distributor.id), headers=_auth(employee_token))

    assert response.status_code == 200
    assert response.json() == {"brands": []}


@pytest.mark.parametrize(
    ("warehouse_company", "warehouse_dealer", "vehicle_dealer", "expected"),
    [
        ("linked", "other", "other", True),
        ("other", "linked", "linked", False),
        (None, "linked", "other", True),
        (None, "other", "linked", False),
        (None, None, "linked", True),
        (None, None, "other", False),
        (None, None, None, False),
    ],
)
async def test_inventory_brands_resolve_warehouse_ownership_before_legacy_vehicle_dealer(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
    warehouse_company: str | None,
    warehouse_dealer: str | None,
    vehicle_dealer: str | None,
    expected: bool,
) -> None:
    distributor = await _company(db_session, "distributor")
    dealer = await _company(db_session, "dealer")
    other_dealer = await _company(db_session, "dealer")
    owners = {"linked": dealer.id, "other": other_dealer.id, None: None}
    mark = Mark(id=f"owned-{uuid4()}", name="Owned brand")
    warehouse = Warehouse(
        address="Inventory test warehouse",
        brand="Not the vehicle brand",
        company_id=owners[warehouse_company],
        dealer_id=owners[warehouse_dealer],
    )
    db_session.add_all(
        [
            mark,
            warehouse,
            DistributorDealerLink(
                distributor_company_id=distributor.id, dealer_company_id=dealer.id
            ),
        ]
    )
    await db_session.flush()
    await _vehicle(
        db_session, mark, dealer_id=owners[vehicle_dealer], warehouse=warehouse
    )

    response = await client.get(_path(distributor.id), headers=_auth(employee_token))

    assert response.status_code == 200
    assert response.json() == {
        "brands": [{"id": mark.id, "name": mark.name}] if expected else []
    }


async def test_inventory_brands_include_direct_and_active_group_dealers_with_stable_ids(
    client: AsyncClient,
    employee_token: str,
    employee_user: User,
    db_session: AsyncSession,
) -> None:
    distributor = await _company(db_session, "distributor")
    other_distributor = await _company(db_session, "distributor")
    direct = await _company(db_session, "dealer")
    grouped = await _company(db_session, "dealer")
    inactive = await _company(db_session, "dealer")
    other = await _company(db_session, "dealer")
    group = DealerGroup(
        distributor_company_id=distributor.id,
        name="Active inventory group",
        is_active=True,
        created_by=employee_user.id,
    )
    inactive_group = DealerGroup(
        distributor_company_id=distributor.id,
        name="Inactive inventory group",
        is_active=False,
        created_by=employee_user.id,
    )
    marks = [
        Mark(id=f"{prefix}-{uuid4()}", name=name)
        for prefix, name in [
            ("a", "Alpha"),
            ("b", "Alpha"),
            ("z", "Zeta"),
            ("x", "Excluded"),
        ]
    ]
    db_session.add_all([group, inactive_group, *marks])
    await db_session.flush()
    db_session.add_all(
        [
            DistributorDealerLink(
                distributor_company_id=distributor.id, dealer_company_id=direct.id
            ),
            DistributorDealerLink(
                distributor_company_id=other_distributor.id, dealer_company_id=other.id
            ),
            DealerGroupMember(
                dealer_group_id=group.id,
                dealer_company_id=grouped.id,
                created_by=employee_user.id,
            ),
            DealerGroupMember(
                dealer_group_id=group.id,
                dealer_company_id=direct.id,
                created_by=employee_user.id,
            ),
            DealerGroupMember(
                dealer_group_id=inactive_group.id,
                dealer_company_id=inactive.id,
                created_by=employee_user.id,
            ),
        ]
    )
    await db_session.flush()
    for mark, dealer in [
        (marks[0], direct),
        (marks[0], direct),
        (marks[1], grouped),
        (marks[2], grouped),
        (marks[3], inactive),
        (marks[3], other),
    ]:
        await _vehicle(db_session, mark, dealer_id=dealer.id)

    response = await client.get(_path(distributor.id), headers=_auth(employee_token))

    assert response.status_code == 200
    assert response.json() == {
        "brands": [{"id": mark.id, "name": mark.name} for mark in marks[:3]]
    }
    other_response = await client.get(
        _path(other_distributor.id), headers=_auth(employee_token)
    )
    assert other_response.status_code == 200
    assert other_response.json() == {
        "brands": [{"id": marks[3].id, "name": marks[3].name}]
    }
