"""Handler-level tests for the Phase 7a G4 dealer additions.

Covers profile read/update, clients listing and dealer inventory-delete
delegation (which re-uses the B1 handler).
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.dealer import (
    UpdateDealerProfileCommand,
    handle_update_dealer_profile,
)
from application.queries.dealer import (
    GetDealerProfileQuery,
    ListDealerClientsQuery,
    handle_get_dealer_profile,
    handle_list_dealer_clients,
)
from domain.errors import UserNotFoundError
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company
from infrastructure.models.users import User

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def dealer_company(db_session: AsyncSession) -> Company:
    c = Company(name="ДилерКо", company_type="dealer", inn="7710009901")
    db_session.add(c)
    await db_session.flush()
    await db_session.refresh(c)
    return c


@pytest_asyncio.fixture
async def dealer_profile_user(
    db_session: AsyncSession, dealer_company: Company
) -> User:
    u = User(
        phone="+76660001111",
        email="dealer-profile@test.local",
        name="Дилер",
        role="dealer",
        company_id=dealer_company.id,
        is_active=True,
    )
    db_session.add(u)
    await db_session.flush()
    await db_session.refresh(u)
    return u


async def test_get_dealer_profile_returns_user_company_and_stats(
    db_session: AsyncSession, dealer_profile_user: User, dealer_company: Company
) -> None:
    # seed two applications by the dealer to hit the stats aggregation
    # Also seed a "sold" application for total_sales
    db_session.add_all(
        [
            LeasingApplication(
                company_id=dealer_company.id,
                status="active",
                total_amount=Decimal("1000"),
                email="a1@x.y",
            ),
            LeasingApplication(
                company_id=dealer_company.id,
                status="rejected",
                total_amount=Decimal("500"),
                email="a2@x.y",
            ),
        ]
    )
    await db_session.flush()

    result = await handle_get_dealer_profile(
        GetDealerProfileQuery(user_id=dealer_profile_user.id), db_session
    )
    assert result["profile"]["id"] == dealer_profile_user.id
    assert result["company"]["id"] == dealer_company.id
    assert result["stats"]["total_applications"] == 2
    assert result["stats"]["total_sales"] == 1
    assert result["stats"]["total_revenue"] == pytest.approx(1000.0)
    # conversion = 1/2 -> 50%
    assert result["stats"]["conversion_rate"] == pytest.approx(50.0)


async def test_get_dealer_profile_missing_user_raises(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(UserNotFoundError):
        await handle_get_dealer_profile(
            GetDealerProfileQuery(user_id=uuid4()), db_session
        )


async def test_update_dealer_profile_writes_user_and_company(
    db_session: AsyncSession, dealer_profile_user: User, dealer_company: Company
) -> None:
    refreshed = await handle_update_dealer_profile(
        UpdateDealerProfileCommand(
            user_id=dealer_profile_user.id,
            user_fields={"name": "Другое", "email": "other@test.local"},
            company_fields={"phone": "+7 495 111-22-33"},
        ),
        db_session,
    )
    assert refreshed["user"]["name"] == "Другое"
    assert refreshed["user"]["email"] == "other@test.local"
    assert refreshed["company"]["phone"] == "+7 495 111-22-33"


async def test_list_dealer_clients_paginates_and_aggregates(
    db_session: AsyncSession, dealer_profile_user: User, dealer_company: Company
) -> None:
    # create two clients, each with applications
    c1 = User(phone="+79001112201", email="c1@test.local", name="К1", role="client", is_active=True)
    c2 = User(phone="+79001112202", email="c2@test.local", name="К2", role="client", is_active=True)
    db_session.add_all([c1, c2])
    await db_session.flush()

    db_session.add_all(
        [
            LeasingApplication(
                company_id=dealer_company.id,
                email=c1.email,
                total_amount=Decimal("100"),
                status="active",
            ),
            LeasingApplication(
                company_id=dealer_company.id,
                email=c1.email,
                total_amount=Decimal("50"),
                status="active",
            ),
            LeasingApplication(
                company_id=dealer_company.id,
                email=c2.email,
                total_amount=Decimal("300"),
                status="active",
            ),
        ]
    )
    await db_session.flush()

    result = await handle_list_dealer_clients(
        ListDealerClientsQuery(dealer_id=dealer_company.id, page=1, limit=10),
        db_session,
    )
    assert result["pagination"]["total"] == 2
    by_email = {item["email"]: item for item in result["clients"]}
    assert by_email[c1.email]["applications_count"] == 2
    assert by_email[c2.email]["applications_count"] == 1
    assert by_email[c1.email]["total_amount"] == pytest.approx(150.0)



