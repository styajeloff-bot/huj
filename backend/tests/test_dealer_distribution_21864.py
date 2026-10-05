
"""Real database regression coverage for quantity distribution and replay safety."""
import asyncio
from dataclasses import dataclass, replace
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from application.commands.applications.distribute_dealer import (
    DistributeDealerCommand,
    handle_distribute_dealer,
)
from domain.dealer_distribution import (
    DealerDistributionConflictError,
    DistributionItem,
    distribution_availability,
    ensure_distribution_items,
)
from domain.errors import (
    ApplicationNotOwnedError,
    ApplicationVehicleAssignmentError,
    ApplicationVehicleNotFoundError,
    CompanyAccessDeniedError,
    DealerAssignmentNotAllowedError,
)
from infrastructure.auth import generate_tokens
from infrastructure.models.applications import (
    ApplicationDealerDistributionRequest,
    ApplicationVehicle,
    ApplicationVehicleDealerDistribution,
    LeasingApplication,
)
from infrastructure.models.companies import Company, DistributorDealerLink
from infrastructure.models.users import User, UserCompany
from infrastructure.models.vehicles import Warehouse
from infrastructure.repositories.application_dealer_distribution_repository import (
    list_distributions,
)
from presentation.schemas.dealer_distribution import DealerDistributionItemRequest
from tests.legacy_compat import Vehicle, VehicleWarehouse


@pytest.mark.parametrize(
    (
        "role",
        "owner_type",
        "own_stock",
        "quantity",
        "allocated",
        "legacy",
        "status",
        "remaining",
        "can_assign",
    ),
    [
        ("distributor", "distributor", True, 5, 3, False, "active", 2, True),
        ("distributor", "distributor", True, 5, 5, False, "active", 0, False),
        ("distributor", "distributor", True, 5, 0, True, "active", 0, False),
        ("distributor", "dealer", False, 5, 0, False, "active", 0, False),
        ("distributor", "distributor", False, 5, 3, False, "active", 2, False),
        ("distributor", "distributor", True, 5, 3, False, "rejected", 2, False),
        ("distributor", "distributor", True, None, 0, False, "active", 0, False),
        ("dealer", "distributor", False, 5, 3, False, "active", 0, False),
    ],
    ids=[
        "partial",
        "complete",
        "legacy_full",
        "dealer_stock",
        "other_company",
        "historical",
        "unknown_quantity",
        "dealer_share",
    ],
)
def test_shared_availability_preserves_assignment_and_display_rules(
    role: str,
    owner_type: str,
    own_stock: bool,
    quantity: int | None,
    allocated: int,
    legacy: bool,
    status: str,
    remaining: int,
    can_assign: bool,
) -> None:
    company_id = uuid4()
    availability = distribution_availability(
        actor_role=role,
        actor_company_id=company_id,
        stock_owner_id=company_id if own_stock else uuid4(),
        stock_owner_type=owner_type,
        quantity=quantity,
        distributed_quantity=allocated,
        legacy_dealer_assigned=legacy,
        status=status,
    )
    assert availability.unassigned_quantity == remaining
    assert availability.can_assign_dealer is can_assign


@dataclass
class Graph:
    distributor: Company
    dealer: Company
    second_dealer: Company
    foreign_dealer: Company
    user: User
    app: LeasingApplication
    lines: list[ApplicationVehicle]
    warehouses: list[Warehouse]


async def _graph(session: AsyncSession) -> Graph:
    distributor = Company(
        name="21864 distributor", company_type="distributor", is_active=True
    )
    dealer = Company(
        name="21864 dealer A",
        inn=f"21864{uuid4().int % 10**7:07d}",
        company_type="dealer",
        is_active=True,
    )
    second_dealer = Company(
        name="21864 dealer B",
        inn=f"21864{uuid4().int % 10**7:07d}",
        company_type="dealer",
        is_active=True,
    )
    foreign = Company(name="21864 foreign", company_type="dealer", is_active=True)
    session.add_all([distributor, dealer, second_dealer, foreign])
    await session.flush()
    user = User(
        phone=f"+{uuid4().int % 10**14:014}",
        role="distributor",
        company_id=distributor.id,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    session.add(
        UserCompany(
            user_id=user.id,
            company_id=distributor.id,
            sub_role="administrator",
            can_view_applications=True,
        )
    )
    session.add_all(
        [
            DistributorDealerLink(
                distributor_company_id=distributor.id, dealer_company_id=d.id
            )
            for d in [dealer, second_dealer]
        ]
    )
    app = LeasingApplication(
        created_by=user.id, company_id=distributor.id, status="active"
    )
    session.add(app)
    await session.flush()
    lines, warehouses = [], []
    for quantity in [5, 3]:
        warehouse = Warehouse(
            address="21864 stock",
            brand="FAW",
            company_id=distributor.id,
            status="active",
        )
        vehicle = Vehicle(
            vin=f"21864{uuid4().hex[:12]}",
            dealer_id=distributor.id,
            base_price=Decimal("100"),
            status="available",
            is_available=True,
        )
        session.add_all([warehouse, vehicle])
        await session.flush()
        session.add(VehicleWarehouse(vehicle_id=vehicle.id, warehouse_id=warehouse.id))
        line = ApplicationVehicle(
            application_id=app.id,
            vehicle_id=vehicle.id,
            quantity=quantity,
            unit_price=Decimal("100"),
            total_price=Decimal(100 * quantity),
            car_status="active",
        )
        session.add(line)
        lines.append(line)
        warehouses.append(warehouse)
    await session.flush()
    return Graph(
        distributor, dealer, second_dealer, foreign, user, app, lines, warehouses
    )


@pytest_asyncio.fixture
async def graph(db_session: AsyncSession) -> Graph:
    return await _graph(db_session)


def _command(
    graph: Graph, quantity: int = 2, expected: int = 5
) -> DistributeDealerCommand:
    return DistributeDealerCommand(
        application_id=graph.app.id,
        dealer_id=graph.dealer.id,
        request_id=uuid4(),
        items=(DistributionItem(graph.lines[0].id, quantity, expected),),
        actor_id=graph.user.id,
        actor_role="distributor",
        actor_company_id=graph.distributor.id,
    )


@pytest.mark.asyncio
async def test_partial_assignments_multi_line_replay_and_prices(
    db_session: AsyncSession, graph: Graph
) -> None:
    first = _command(graph)
    await handle_distribute_dealer(first, db_session)
    await handle_distribute_dealer(first, db_session)
    second = replace(
        _command(graph, 1, 3),
        dealer_id=graph.second_dealer.id,
        items=(
            DistributionItem(graph.lines[0].id, 1, 3),
            DistributionItem(graph.lines[1].id, 2, 3),
        ),
    )
    await handle_distribute_dealer(second, db_session)
    await handle_distribute_dealer(_command(graph, 2, 2), db_session)
    result = await list_distributions(db_session, [line.id for line in graph.lines])
    assert {
        item["dealer"]["id"]: item["quantity"] for item in result[graph.lines[0].id]
    } == {graph.dealer.id: 4, graph.second_dealer.id: 1}
    assert result[graph.lines[1].id][0]["quantity"] == 2
    assert (
        await db_session.scalar(
            sa.select(sa.func.count()).select_from(ApplicationDealerDistributionRequest)
        )
        == 3
    )
    for line, quantity in zip(graph.lines, [5, 3], strict=True):
        await db_session.refresh(line)
        assert (
            line.quantity,
            line.unit_price,
            line.total_price,
            line.dealer_company_id,
        ) == (quantity, Decimal("100"), Decimal(100 * quantity), None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "warehouse",
        "legacy_warehouse_owner",
        "foreign_line",
        "dealer",
        "inactive_dealer",
        "legacy",
        "stale",
        "overflow",
        "duplicate",
        "replay",
        "actor",
        "inactive_owner",
        "missing_quantity",
        "inactive_actor",
        "revoked_read",
    ],
)
async def test_distribution_rejects_invalid_batch_without_writing(
    db_session: AsyncSession, graph: Graph, failure: str
) -> None:
    command = _command(graph)
    error: type[Exception] = DealerDistributionConflictError
    if failure in {"warehouse", "legacy_warehouse_owner"}:
        graph.warehouses[1].company_id = (
            graph.dealer.id if failure == "warehouse" else None  # type: ignore[assignment]
        )
        graph.warehouses[1].dealer_id = graph.distributor.id
        command = replace(
            command, items=(*command.items, DistributionItem(graph.lines[1].id, 1, 3))
        )
        error = ApplicationNotOwnedError
    elif failure == "foreign_line":
        command = replace(
            command, items=(*command.items, DistributionItem(uuid4(), 1, 1))
        )
        error = ApplicationVehicleNotFoundError
    elif failure in {"dealer", "inactive_dealer"}:
        command = replace(
            command,
            dealer_id=graph.foreign_dealer.id
            if failure == "dealer"
            else graph.dealer.id,
        )
        graph.dealer.is_active = failure != "inactive_dealer"
        error = DealerAssignmentNotAllowedError
    elif failure == "legacy":
        graph.lines[0].dealer_company_id = graph.dealer.id
    elif failure == "stale":
        command = _command(graph, 1, 4)
    elif failure == "overflow":
        command = _command(graph, 6, 5)
    elif failure == "duplicate":
        command = replace(command, items=(*command.items, *command.items))
        error = ApplicationVehicleAssignmentError
    elif failure == "replay":
        await handle_distribute_dealer(command, db_session)
        command = replace(command, dealer_id=graph.second_dealer.id)
    elif failure == "actor":
        command = replace(command, actor_role="dealer")
        error = ApplicationNotOwnedError
    elif failure in {"inactive_owner", "inactive_actor"}:
        actor = graph.distributor if failure == "inactive_owner" else graph.user
        actor.is_active = False
        error = CompanyAccessDeniedError
    elif failure == "missing_quantity":
        graph.lines[0].quantity = None
    elif failure == "revoked_read":
        await db_session.execute(
            sa.update(UserCompany)
            .where(UserCompany.user_id == graph.user.id)
            .values(can_view_applications=False, sub_role="employee")
        )
        error = CompanyAccessDeniedError
    await db_session.flush()
    before = await db_session.scalar(
        sa.select(sa.func.count()).select_from(ApplicationVehicleDealerDistribution)
    )
    with pytest.raises(error):
        await handle_distribute_dealer(command, db_session)
    assert (
        await db_session.scalar(
            sa.select(sa.func.count()).select_from(ApplicationVehicleDealerDistribution)
        )
        == before
    )


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True, "2"])
def test_quantity_strictly_positive_integer(quantity: object) -> None:
    with pytest.raises(ValidationError):
        DealerDistributionItemRequest.model_validate(
            {
                "application_vehicle_id": uuid4(),
                "quantity": quantity,
                "expected_unassigned_quantity": 5,
            }
        )
    with pytest.raises(ApplicationVehicleAssignmentError):
        ensure_distribution_items((DistributionItem(uuid4(), quantity, 5),))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_http_post_accepts_request_id_and_old_routes_cannot_overwrite(
    client: AsyncClient, db_session: AsyncSession, graph: Graph
) -> None:
    access, _ = generate_tokens(
        graph.user.id, "distributor", company_id=graph.distributor.id
    )
    headers = {"Authorization": f"Bearer {access}"}
    request = {
        "request_id": str(uuid4()),
        "dealer_id": str(graph.dealer.id),
        "items": [
            {
                "application_vehicle_id": str(graph.lines[0].id),
                "quantity": 2,
                "expected_unassigned_quantity": 5,
            }
        ],
    }
    path = f"/api/v1/applications/{graph.app.id}/dealer-distributions"
    for _ in range(2):
        response = await client.post(path, json=request, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json() == {"application_vehicle_ids": [str(graph.lines[0].id)]}
    legacy = await client.put(
        f"/api/v1/{graph.app.id}/{graph.lines[0].id}/diler",
        json={"dealer_id": str(graph.second_dealer.id)},
        headers=headers,
    )
    assert legacy.status_code == 409
    legacy_whole = await client.patch(
        f"/api/v1/distributor/leasing-applications/{graph.app.id}",
        json={
            "dealer_group_id": str(uuid4()),
            "dealer_company_id": str(graph.second_dealer.id),
        },
        headers=headers,
    )
    assert legacy_whole.status_code == 409
    allocations = await list_distributions(db_session, [graph.lines[0].id])
    assert allocations[graph.lines[0].id][0]["quantity"] == 2


@pytest.mark.asyncio
async def test_notification_selector_cannot_replace_active_distribution_company(
    client: AsyncClient,
    db_session: AsyncSession,
    graph: Graph,
) -> None:
    other = Company(
        name="Another distributor", company_type="distributor", is_active=True
    )
    db_session.add(other)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=graph.user.id,
            company_id=other.id,
            sub_role="administrator",
            can_view_applications=True,
        )
    )
    graph.warehouses[0].company_id = other.id
    await db_session.flush()
    access, _ = generate_tokens(
        graph.user.id, "distributor", company_id=graph.distributor.id
    )
    response = await client.post(
        f"/api/v1/applications/{graph.app.id}/dealer-distributions",
        params={"notification_company_id": str(other.id)},
        headers={"Authorization": f"Bearer {access}"},
        json={
            "request_id": str(uuid4()),
            "dealer_id": str(graph.dealer.id),
            "items": [
                {
                    "application_vehicle_id": str(graph.lines[0].id),
                    "quantity": 1,
                    "expected_unassigned_quantity": 5,
                },
            ],
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("same_request", [False, True])
async def test_parallel_requests_do_not_assign_same_remainder(
    _engine: AsyncEngine, same_request: bool
) -> None:
    async with AsyncSession(_engine, expire_on_commit=False) as seed:
        graph = await _graph(seed)
        await seed.commit()
    command = _command(graph, 4, 5)

    async def assign(request_id: UUID) -> bool:
        async with AsyncSession(_engine, expire_on_commit=False) as session:
            try:
                await handle_distribute_dealer(
                    replace(command, request_id=request_id), session
                )
                await session.commit()
                return True
            except DealerDistributionConflictError:
                await session.rollback()
                return False

    request_id = uuid4()
    try:
        assert sorted(
            await asyncio.gather(
                assign(request_id), assign(request_id if same_request else uuid4())
            )
        ) == [same_request, True]
        async with AsyncSession(_engine) as session:
            result = await list_distributions(session, [graph.lines[0].id])
            assert result[graph.lines[0].id][0]["quantity"] == 4
    finally:
        async with AsyncSession(_engine) as session:
            await session.execute(
                sa.delete(LeasingApplication).where(
                    LeasingApplication.id == graph.app.id
                )
            )
            vehicle_ids = [line.vehicle_id for line in graph.lines]
            await session.execute(
                sa.delete(VehicleWarehouse).where(
                    VehicleWarehouse.vehicle_id.in_(vehicle_ids)
                )
            )
            await session.execute(
                sa.delete(Warehouse).where(
                    Warehouse.id.in_([row.id for row in graph.warehouses])
                )
            )
            await session.execute(sa.delete(Vehicle).where(Vehicle.id.in_(vehicle_ids)))
            await session.execute(
                sa.delete(DistributorDealerLink).where(
                    DistributorDealerLink.distributor_company_id == graph.distributor.id
                )
            )
            await session.execute(
                sa.delete(UserCompany).where(UserCompany.user_id == graph.user.id)
            )
            await session.execute(sa.delete(User).where(User.id == graph.user.id))
            await session.execute(
                sa.delete(Company).where(
                    Company.id.in_(
                        [
                            graph.distributor.id,
                            graph.dealer.id,
                            graph.second_dealer.id,
                            graph.foreign_dealer.id,
                        ]
                    )
                )
            )
            await session.commit()
