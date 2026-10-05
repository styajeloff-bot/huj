"""Handler-level tests for the exchange subsystem (Phase 5 E2).

Uses the real Postgres testcontainer + rolled-back transactions from
``conftest``. Each test builds the minimal graph (LC user, dealer user,
vehicle, warehouse) it needs.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.exchange import (
    AddToExchangeCartCommand,
    ApproveBidCommand,
    CreateBidCommand,
    CreateExchangeRequestCommand,
    ExchangeRequestWarehousePayload,
    UpdateBidCommand,
    handle_add_to_exchange_cart,
    handle_approve_bid,
    handle_create_bid,
    handle_create_exchange_request,
    handle_update_bid,
)
from application.queries.compensations import (
    ListCompensationsQuery,
    handle_list_compensations,
)
from application.queries.exchange import (
    GetRequestCountsQuery,
    ListDealerRequestsQuery,
    ListLcRequestsQuery,
    handle_get_request_counts,
    handle_list_dealer_requests,
    handle_list_lc_requests,
)
from domain.entities.exchange_bid import KP_ACCEPTED
from domain.entities.exchange_request import STATUS_DEAL
from domain.errors import (
    BidAlreadyExistsError,
    ExchangeRequestAccessDeniedError,
    InvalidExchangeRequestStatusError,
    VehicleNotFoundError,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.compensations import (
    CompensationModel,
    CompensationTemplateModel,
)
from infrastructure.models.exchange import ExchangeBid
from infrastructure.models.support import (
    ApplicationAppliedSupport,
    SupportProgram,
    SupportProgramLeasingCompany,
)
from infrastructure.models.users import User
from infrastructure.models.vehicles import City, Warehouse
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


def _company_id(user: User) -> UUID:
    assert user.company_id is not None
    return user.company_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def lc_user(db_session: AsyncSession) -> User:
    company = Company(name="Exchange LC", company_type="leasing_company")
    db_session.add(company)
    await db_session.flush()
    user = User(
        company_id=company.id,
        phone="+76660000001",
        email="exc-lc@test.local",
        name="Exc LC",
        role="leasing_company",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def dealer_company(db_session: AsyncSession) -> Company:
    company = Company(
        name="Exc Dealer Co",
        company_type="dealer",
        inn="7700000001",
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def dealer_user(db_session: AsyncSession, dealer_company: Company) -> User:
    user = User(
        phone="+76660000002",
        email="exc-dealer@test.local",
        name="Exc Dealer",
        role="dealer",
        is_active=True,
        company_id=dealer_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def other_dealer_company(db_session: AsyncSession) -> Company:
    company = Company(
        name="Other Dealer Co",
        company_type="dealer",
        inn="7700000002",
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def other_dealer_user(db_session: AsyncSession, other_dealer_company: Company) -> User:
    user = User(
        phone="+76660000003",
        email="exc-other-dealer@test.local",
        name="Other Dealer",
        role="dealer",
        is_active=True,
        company_id=other_dealer_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def exc_city(db_session: AsyncSession) -> City:
    city = City(name="TestCity")
    db_session.add(city)
    await db_session.flush()
    return city


@pytest_asyncio.fixture
async def exc_warehouse(
    db_session: AsyncSession, exc_city: City, dealer_company: Company
) -> Warehouse:
    wh = Warehouse(
        address="WH-1",
        brand="Brand",
        city_id=exc_city.id,
        dealer_id=dealer_company.id,
    )
    db_session.add(wh)
    await db_session.flush()
    return wh


@pytest_asyncio.fixture
async def exc_vehicle(db_session: AsyncSession) -> Vehicle:
    v = Vehicle(
        status="available",
        is_available=True,
        base_price=Decimal("3000000.00"),
    )
    db_session.add(v)
    await db_session.flush()
    return v


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------


async def test_add_to_cart_creates_item(
    db_session: AsyncSession, lc_user: User, exc_vehicle: Vehicle
) -> None:
    result = await handle_add_to_exchange_cart(
        AddToExchangeCartCommand(
            user_id=lc_user.id, vehicle_id=exc_vehicle.id, quantity=2
        ),
        db_session,
    )
    assert result["created"] is True
    assert result["item"]["quantity"] == 2


async def test_add_to_cart_duplicate_increments_quantity(
    db_session: AsyncSession, lc_user: User, exc_vehicle: Vehicle
) -> None:
    await handle_add_to_exchange_cart(
        AddToExchangeCartCommand(
            user_id=lc_user.id, vehicle_id=exc_vehicle.id, quantity=1
        ),
        db_session,
    )
    second = await handle_add_to_exchange_cart(
        AddToExchangeCartCommand(
            user_id=lc_user.id, vehicle_id=exc_vehicle.id, quantity=3
        ),
        db_session,
    )
    assert second["created"] is False
    assert second["item"]["quantity"] == 4


async def test_add_to_cart_unknown_vehicle(
    db_session: AsyncSession, lc_user: User
) -> None:
    with pytest.raises(VehicleNotFoundError):
        await handle_add_to_exchange_cart(
            AddToExchangeCartCommand(
                user_id=lc_user.id, vehicle_id=uuid4(), quantity=1
            ),
            db_session,
        )


# ---------------------------------------------------------------------------
# Request creation + submit
# ---------------------------------------------------------------------------


async def test_create_request_happy_path(
    db_session: AsyncSession,
    lc_user: User,
    dealer_user: User,
    exc_vehicle: Vehicle,
    exc_warehouse: Warehouse,
) -> None:
    cmd = CreateExchangeRequestCommand(
        lc_user_id=lc_user.id,
        vehicle_id=exc_vehicle.id,
        quantity=1,
        warehouses=[
            ExchangeRequestWarehousePayload(
                warehouse_id=exc_warehouse.id,
                dealer_id=_company_id(dealer_user),
                dealer_comment="подготовьте автомобиль",
            )
        ],
    )
    result = await handle_create_exchange_request(cmd, db_session)
    assert result["request"]["status"] == "open"
    assert result["request"]["vehicle_id"] == exc_vehicle.id
    assert result["batch_number"] >= 1


# ---------------------------------------------------------------------------
# Bid create / update / approve
# ---------------------------------------------------------------------------


async def _create_open_request(
    db_session: AsyncSession,
    lc: User,
    dealer: User,
    warehouse: Warehouse,
    vehicle: Vehicle,
) -> UUID:
    result = await handle_create_exchange_request(
        CreateExchangeRequestCommand(
            lc_user_id=lc.id,
            vehicle_id=vehicle.id,
            quantity=3,
            warehouses=[
                ExchangeRequestWarehousePayload(
                    warehouse_id=warehouse.id,
                    dealer_id=_company_id(dealer),
                )
            ],
        ),
        db_session,
    )
    return UUID(str(result["request"]["id"]))


async def test_create_bid_happy_path(
    db_session: AsyncSession,
    lc_user: User,
    dealer_user: User,
    exc_warehouse: Warehouse,
    exc_vehicle: Vehicle,
) -> None:
    req_id = await _create_open_request(
        db_session, lc_user, dealer_user, exc_warehouse, exc_vehicle
    )
    result = await handle_create_bid(
        CreateBidCommand(
            request_id=req_id,
            dealer_id=dealer_user.id,
            company_id=_company_id(dealer_user),
            price=Decimal("2500000.00"),
            quantity=2,
            comment="ок",
        ),
        db_session,
    )
    assert result["bid"]["request_id"] == req_id
    assert result["bid"]["quantity"] == 2


async def test_create_bid_denied_for_unrelated_dealer(
    db_session: AsyncSession,
    lc_user: User,
    dealer_user: User,
    other_dealer_user: User,
    exc_warehouse: Warehouse,
    exc_vehicle: Vehicle,
) -> None:
    req_id = await _create_open_request(
        db_session, lc_user, dealer_user, exc_warehouse, exc_vehicle
    )
    with pytest.raises(ExchangeRequestAccessDeniedError):
        await handle_create_bid(
            CreateBidCommand(
                request_id=req_id,
                dealer_id=other_dealer_user.id,
                company_id=_company_id(other_dealer_user),
                price=Decimal("1000000"),
            ),
            db_session,
        )


async def test_duplicate_bid_raises(
    db_session: AsyncSession,
    lc_user: User,
    dealer_user: User,
    exc_warehouse: Warehouse,
    exc_vehicle: Vehicle,
) -> None:
    req_id = await _create_open_request(
        db_session, lc_user, dealer_user, exc_warehouse, exc_vehicle
    )
    await handle_create_bid(
        CreateBidCommand(
            request_id=req_id,
            dealer_id=dealer_user.id,
            company_id=_company_id(dealer_user),
            price=Decimal("1000000"),
        ),
        db_session,
    )
    with pytest.raises(BidAlreadyExistsError):
        await handle_create_bid(
            CreateBidCommand(
                request_id=req_id,
                dealer_id=dealer_user.id,
                company_id=_company_id(dealer_user),
                price=Decimal("1200000"),
            ),
            db_session,
        )


async def test_update_bid_changes_price_and_quantity(
    db_session: AsyncSession,
    lc_user: User,
    dealer_user: User,
    exc_warehouse: Warehouse,
    exc_vehicle: Vehicle,
) -> None:
    req_id = await _create_open_request(
        db_session, lc_user, dealer_user, exc_warehouse, exc_vehicle
    )
    created = await handle_create_bid(
        CreateBidCommand(
            request_id=req_id,
            dealer_id=dealer_user.id,
            company_id=_company_id(dealer_user),
            price=Decimal("1000000"),
            quantity=1,
        ),
        db_session,
    )
    bid_id = created["bid"]["id"]
    updated = await handle_update_bid(
        UpdateBidCommand(
            bid_id=bid_id,
            dealer_id=dealer_user.id,
            price=Decimal("1500000"),
            quantity=2,
        ),
        db_session,
    )
    assert updated["bid"]["price"] == Decimal("1500000")
    assert updated["bid"]["quantity"] == 2


async def test_approve_without_kp_succeeds(
    db_session: AsyncSession,
    lc_user: User,
    dealer_user: User,
    exc_warehouse: Warehouse,
    exc_vehicle: Vehicle,
) -> None:
    """KP acceptance is optional — LC can close the deal directly."""
    req_id = await _create_open_request(
        db_session, lc_user, dealer_user, exc_warehouse, exc_vehicle
    )
    created = await handle_create_bid(
        CreateBidCommand(
            request_id=req_id,
            dealer_id=dealer_user.id,
            company_id=_company_id(dealer_user),
            price=Decimal("1000000"),
        ),
        db_session,
    )
    bid_id = created["bid"]["id"]
    approved = await handle_approve_bid(
        ApproveBidCommand(bid_id=bid_id, lc_user_id=lc_user.id),
        db_session,
    )
    assert approved["bid"]["is_accepted"] is True


async def test_approve_cascades_request_to_deal(
    db_session: AsyncSession,
    lc_user: User,
    dealer_user: User,
    exc_warehouse: Warehouse,
    exc_vehicle: Vehicle,
) -> None:
    req_id = await _create_open_request(
        db_session, lc_user, dealer_user, exc_warehouse, exc_vehicle
    )
    created = await handle_create_bid(
        CreateBidCommand(
            request_id=req_id,
            dealer_id=dealer_user.id,
            company_id=_company_id(dealer_user),
            price=Decimal("1000000"),
        ),
        db_session,
    )
    bid_id = created["bid"]["id"]

    # Simulate dealer accepting KP — bypass the dealer KP endpoint and
    # mark kp_status directly via the ORM (this handler flow is about
    # the LC approve cascade, not the KP dealer response).
    bid_row = await db_session.get(ExchangeBid, bid_id)
    assert bid_row is not None
    bid_row.kp_status = KP_ACCEPTED
    await db_session.flush()

    result = await handle_approve_bid(
        ApproveBidCommand(bid_id=bid_id, lc_user_id=lc_user.id),
        db_session,
    )
    assert result["bid"]["is_accepted"] is True

    # Request must cascade to `deal`.
    listing = await handle_list_lc_requests(
        ListLcRequestsQuery(lc_user_id=lc_user.id), db_session
    )
    request = next(r for r in listing["requests"] if r["id"] == req_id)
    assert request["status"] == STATUS_DEAL
    assert request["accepted_bid_id"] == bid_id


async def test_exchange_deal_creates_idempotent_sourced_compensation_snapshot(
    db_session: AsyncSession,
    lc_user: User,
    dealer_user: User,
    exc_warehouse: Warehouse,
    exc_vehicle: Vehicle,
) -> None:
    lc_company = Company(
        name="Exchange LC Company",
        company_type="leasing_company",
        inn="7700000099",
    )
    db_session.add(lc_company)
    await db_session.flush()
    lc_user.company_id = lc_company.id
    leasing_company = LeasingCompany(
        company_id=lc_company.id,
        is_active=True,
    )
    db_session.add(leasing_company)
    await db_session.flush()

    program = SupportProgram(
        name="Exchange immutable support",
        comment="Исходное описание",
        support_type="vehicle_discount_dealer_compensation",
        support_params={"value_type": "amount", "value": 100_000},
        is_active=True,
        show_to_leasing_company=True,
    )
    db_session.add(program)
    await db_session.flush()
    db_session.add_all(
        [
            SupportProgramLeasingCompany(
                support_program_id=program.id,
                leasing_company_id=leasing_company.id,
            ),
            CompensationTemplateModel(
                support_program_id=program.id,
                payer="distributor",
                recipient="leasing_company",
                calculation_base="support_amount",
                value_type="percent",
                value=100,
                payment_schedule_type="days_count",
                payment_schedule_value="30",
            ),
        ]
    )
    await db_session.flush()

    created_request = await handle_create_exchange_request(
        CreateExchangeRequestCommand(
            lc_user_id=lc_user.id,
            vehicle_id=exc_vehicle.id,
            quantity=1,
            selected_support_ids=[program.id],
            warehouses=[
                ExchangeRequestWarehousePayload(
                    warehouse_id=exc_warehouse.id,
                    dealer_id=_company_id(dealer_user),
                )
            ],
        ),
        db_session,
    )
    request_id = UUID(str(created_request["request"]["id"]))
    created_bid = await handle_create_bid(
        CreateBidCommand(
            request_id=request_id,
            dealer_id=dealer_user.id,
            company_id=_company_id(dealer_user),
            price=Decimal("2500000"),
        ),
        db_session,
    )
    bid_id = UUID(str(created_bid["bid"]["id"]))

    await handle_approve_bid(
        ApproveBidCommand(bid_id=bid_id, lc_user_id=lc_user.id),
        db_session,
    )
    from application.commands.exchange.finalize_supports import (
        finalize_exchange_supports,
    )

    await finalize_exchange_supports(
        db_session,
        request_id=request_id,
        accepted_bid=created_bid["bid"],
        actor_id=lc_user.id,
    )

    snapshots = (
        await db_session.execute(
            select(ApplicationAppliedSupport).where(
                ApplicationAppliedSupport.exchange_request_id == request_id
            )
        )
    ).scalars().all()
    assert len(snapshots) == 1
    assert snapshots[0].comment == "Исходное описание"
    compensation = (
        await db_session.execute(
            select(CompensationModel).where(
                CompensationModel.exchange_request_id == request_id
            )
        )
    ).scalar_one()
    assert compensation.source == "exchange"
    assert compensation.application_id is None
    assert Decimal(str(compensation.amount)) == Decimal("100000")
    snapshot_count = (
        await db_session.execute(
            select(func.count(ApplicationAppliedSupport.id)).where(
                ApplicationAppliedSupport.exchange_request_id == request_id
            )
        )
    ).scalar_one()
    assert snapshot_count == 1

    program.name = "Изменённое название"
    program.comment = "Изменённое описание"
    await db_session.flush()
    listing = await handle_list_lc_requests(
        ListLcRequestsQuery(lc_user_id=lc_user.id),
        db_session,
    )
    request = next(
        item for item in listing["requests"] if item["id"] == request_id
    )
    assert request["support_program_details"][0]["name"] == (
        "Exchange immutable support"
    )
    assert request["support_program_details"][0]["comment"] == (
        "Исходное описание"
    )

    registry = await handle_list_compensations(
        ListCompensationsQuery(
            user_role="carcraft_employee",
            source="exchange",
        ),
        db_session,
    )
    assert any(
        item["exchange_request_id"] == request_id
        and item["source"] == "exchange"
        for item in registry["compensations"]
    )


async def test_bid_on_non_open_request_rejected(
    db_session: AsyncSession,
    lc_user: User,
    dealer_user: User,
    exc_warehouse: Warehouse,
    exc_vehicle: Vehicle,
) -> None:
    from infrastructure.models.exchange import ExchangeRequest as ORMRequest

    req_id = await _create_open_request(
        db_session, lc_user, dealer_user, exc_warehouse, exc_vehicle
    )
    row = await db_session.get(ORMRequest, req_id)
    assert row is not None
    row.status = "archived"
    await db_session.flush()

    with pytest.raises(InvalidExchangeRequestStatusError):
        await handle_create_bid(
            CreateBidCommand(
                request_id=req_id,
                dealer_id=dealer_user.id,
                company_id=_company_id(dealer_user),
                price=Decimal("1000000"),
            ),
            db_session,
        )


# ---------------------------------------------------------------------------
# Query plumbing
# ---------------------------------------------------------------------------


async def test_list_lc_requests_counts(
    db_session: AsyncSession,
    lc_user: User,
    dealer_user: User,
    exc_warehouse: Warehouse,
    exc_vehicle: Vehicle,
) -> None:
    await _create_open_request(
        db_session, lc_user, dealer_user, exc_warehouse, exc_vehicle
    )
    counts = await handle_get_request_counts(
        GetRequestCountsQuery(lc_user_id=lc_user.id), db_session
    )
    assert counts["counts"]["open"] >= 1


async def test_list_dealer_requests_returns_assigned_only(
    db_session: AsyncSession,
    lc_user: User,
    dealer_user: User,
    other_dealer_user: User,
    exc_warehouse: Warehouse,
    exc_vehicle: Vehicle,
) -> None:
    await _create_open_request(
        db_session, lc_user, dealer_user, exc_warehouse, exc_vehicle
    )

    own = await handle_list_dealer_requests(
        ListDealerRequestsQuery(dealer_id=dealer_user.id, company_id=_company_id(dealer_user)),
        db_session,
    )
    assert len(own["requests"]) >= 1

    other = await handle_list_dealer_requests(
        ListDealerRequestsQuery(
            dealer_id=other_dealer_user.id,
            company_id=_company_id(other_dealer_user),
        ),
        db_session,
    )
    # Other dealer has no warehouses in any request.
    assert other["requests"] == []
