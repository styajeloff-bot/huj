"""Integration coverage for Bitrix 21752 dealer/employee assignment."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.applications import (
    ApplicationVehiclePayload,
    AssignApplicationEmployeesCommand,
    CreateApplicationCommand,
    CreateDraftCommand,
    handle_assign_application_employees,
    handle_create_application,
    handle_create_draft,
)
from application.commands.distributor import (
    AssignDealerCommand,
    handle_assign_dealer,
)
from application.errors import ServiceError
from application.queries.application_employees import (
    SearchApplicationEmployeesQuery,
    handle_search_application_employees,
)
from application.queries.applications import (
    GetApplicationQuery,
    handle_get_application,
)
from application.queries.distributor_dealer_assignment import (
    ListAssignableDealerGroupsQuery,
    handle_list_assignable_dealer_groups,
)
from domain.errors import (
    ApplicationNotOwnedError,
    EmployeeAssignmentNotAllowedError,
)
from infrastructure.auth import generate_tokens
from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
)
from infrastructure.models.companies import Company
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.models.users import User, UserCompany
from infrastructure.models.vehicles import (
    City,
    Warehouse,
)
from infrastructure.repositories import (
    application_assignment_repository as legacy_assignment_repo,
)
from tests.legacy_compat import Vehicle, VehicleWarehouse

pytestmark = pytest.mark.asyncio


@dataclass
class AssignmentGraph:
    distributor_company: Company
    dealer_one: Company
    dealer_two: Company
    client_company: Company
    distributor_user: User
    distributor_employee: User
    dealer_one_user: User
    dealer_two_user: User
    client_user: User
    dealer_one_primary: User
    dealer_one_additional: User
    foreign_employee: User
    inactive_employee: User
    carcraft_user: User
    group: DealerGroup
    inactive_group: DealerGroup
    application: LeasingApplication
    distributor_vehicle: Vehicle
    dealer_two_vehicle: Vehicle


async def _add_user(
    session: AsyncSession,
    *,
    company: Company,
    phone: str,
    name: str,
    role: str,
    sub_role: str = "employee",
    active: bool = True,
) -> User:
    user = User(
        company_id=company.id,
        phone=phone,
        name=name,
        role=role,
        is_active=active,
    )
    session.add(user)
    await session.flush()
    session.add(
        UserCompany(
            user_id=user.id,
            company_id=company.id,
            sub_role=sub_role,
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    await session.flush()
    return user


async def _add_warehouse_vehicle(
    session: AsyncSession,
    *,
    company: Company,
    city: City,
    brand: str,
    vin: str,
    address: str,
) -> tuple[Warehouse, Vehicle]:
    warehouse = Warehouse(
        company_id=company.id,
        city_id=city.id,
        brand=brand,
        address=address,
        status="active",
    )
    vehicle = Vehicle(
        dealer_id=company.id,
        vin=vin,
        status="available",
        is_available=True,
        base_price=Decimal("1000000"),
    )
    session.add_all([warehouse, vehicle])
    await session.flush()
    session.add(
        VehicleWarehouse(
            vehicle_id=vehicle.id,
            warehouse_id=warehouse.id,
        )
    )
    await session.flush()
    return warehouse, vehicle


@pytest_asyncio.fixture
async def assignment_graph(db_session: AsyncSession) -> AssignmentGraph:
    distributor_company = Company(
        name="21752 Distributor",
        company_type="distributor",
        is_active=True,
    )
    dealer_one = Company(
        name="Alpha Dealer",
        company_type="dealer",
        inn="2175200001",
        is_active=True,
    )
    dealer_two = Company(
        name="Beta Dealer",
        company_type="dealer",
        inn="2175200002",
        is_active=True,
    )
    inactive_dealer = Company(
        name="Inactive Dealer",
        company_type="dealer",
        inn="2175200003",
        is_active=False,
    )
    non_dealer = Company(
        name="Not A Dealer",
        company_type="other",
        inn="2175200004",
        is_active=True,
    )
    client_company = Company(
        name="21752 Client",
        company_type="other",
        inn="2175299999",
        is_active=True,
    )
    db_session.add_all(
        [
            distributor_company,
            dealer_one,
            dealer_two,
            inactive_dealer,
            non_dealer,
            client_company,
        ]
    )
    await db_session.flush()

    distributor_user = await _add_user(
        db_session,
        company=distributor_company,
        phone="+76662175201",
        name="Distributor Actor",
        role="distributor",
        sub_role="administrator",
    )
    distributor_employee = await _add_user(
        db_session,
        company=distributor_company,
        phone="+76662175211",
        name="Distributor Employee",
        role="distributor",
        sub_role="sales",
    )
    dealer_one_user = await _add_user(
        db_session,
        company=dealer_one,
        phone="+76662175202",
        name="Alpha Dealer Actor",
        role="dealer",
        sub_role="administrator",
    )
    dealer_two_user = await _add_user(
        db_session,
        company=dealer_two,
        phone="+76662175203",
        name="Beta Dealer Actor",
        role="dealer",
        sub_role="administrator",
    )
    client_user = await _add_user(
        db_session,
        company=client_company,
        phone="+76662175204",
        name="Client Actor",
        role="client",
    )
    dealer_one_primary = await _add_user(
        db_session,
        company=dealer_one,
        phone="+76662175205",
        name="Alpha Primary",
        role="dealer",
        sub_role="sales",
    )
    dealer_one_additional = await _add_user(
        db_session,
        company=dealer_one,
        phone="+76662175206",
        name="Alpha Additional",
        role="dealer",
        sub_role="assistant",
    )
    foreign_employee = await _add_user(
        db_session,
        company=dealer_two,
        phone="+76662175207",
        name="Foreign Employee",
        role="dealer",
    )
    inactive_employee = await _add_user(
        db_session,
        company=dealer_one,
        phone="+76662175208",
        name="Inactive Employee",
        role="dealer",
        active=False,
    )
    carcraft_user = await _add_user(
        db_session,
        company=dealer_one,
        phone="+76662175210",
        name="Carcraft Actor",
        role="carcraft_employee",
        sub_role="administrator",
    )
    city = City(name="Москва")
    db_session.add(city)
    await db_session.flush()
    _, distributor_vehicle = await _add_warehouse_vehicle(
        db_session,
        company=distributor_company,
        city=city,
        brand="FAW",
        vin="VIN21752DISTRIBUTOR",
        address="Дистрибьюторская, 1",
    )
    # Legacy data can still point vehicle.dealer_id at a dealer even though
    # the authoritative warehouse belongs to the distributor.  Creation must
    # honour the warehouse owner and leave dealer_company_id empty.
    distributor_vehicle.dealer_id = dealer_one.id
    await db_session.flush()
    await _add_warehouse_vehicle(
        db_session,
        company=dealer_one,
        city=city,
        brand="FAW",
        vin="VIN21752ALPHAFAW",
        address="Альфа, 1",
    )
    await _add_warehouse_vehicle(
        db_session,
        company=dealer_one,
        city=city,
        brand="Hongqi",
        vin="VIN21752ALPHAHQ",
        address="Альфа, 2",
    )
    _, dealer_two_vehicle = await _add_warehouse_vehicle(
        db_session,
        company=dealer_two,
        city=city,
        brand="FAW",
        vin="VIN21752BETAFAW",
        address="Бета, 1",
    )

    group = DealerGroup(
        distributor_company_id=distributor_company.id,
        name="Main Group",
        is_active=True,
        created_by=distributor_user.id,
    )
    inactive_group = DealerGroup(
        distributor_company_id=distributor_company.id,
        name="Inactive Group",
        is_active=False,
        created_by=distributor_user.id,
    )
    db_session.add_all([group, inactive_group])
    await db_session.flush()
    for dealer_company in (
        dealer_one,
        dealer_two,
        inactive_dealer,
        non_dealer,
    ):
        db_session.add(
            DealerGroupMember(
                dealer_group_id=group.id,
                dealer_company_id=dealer_company.id,
                created_by=distributor_user.id,
            )
        )
    db_session.add(
        DealerGroupMember(
            dealer_group_id=inactive_group.id,
            dealer_company_id=dealer_one.id,
            created_by=distributor_user.id,
        )
    )
    await db_session.flush()

    application = LeasingApplication(
        company_id=client_company.id,
        status="active",
        name="Assignment Application",
        email="assignment@example.test",
    )
    db_session.add(application)
    await db_session.flush()
    db_session.add(
        ApplicationVehicle(
            application_id=application.id,
            vehicle_id=distributor_vehicle.id,
            quantity=1,
            unit_price=Decimal("1000000"),
            total_price=Decimal("1000000"),
        )
    )
    await db_session.flush()

    return AssignmentGraph(
        distributor_company=distributor_company,
        dealer_one=dealer_one,
        dealer_two=dealer_two,
        client_company=client_company,
        distributor_user=distributor_user,
        distributor_employee=distributor_employee,
        dealer_one_user=dealer_one_user,
        dealer_two_user=dealer_two_user,
        client_user=client_user,
        dealer_one_primary=dealer_one_primary,
        dealer_one_additional=dealer_one_additional,
        foreign_employee=foreign_employee,
        inactive_employee=inactive_employee,
        carcraft_user=carcraft_user,
        group=group,
        inactive_group=inactive_group,
        application=application,
        distributor_vehicle=distributor_vehicle,
        dealer_two_vehicle=dealer_two_vehicle,
    )


def _auth_token(user: User) -> str:
    token, _ = generate_tokens(
        user.id,
        cast("str", user.role),
        user.company_id,
    )
    return cast("str", token)


def _assert_coded_error(
    response: Response,
    *,
    status_code: int,
    code: str,
) -> None:
    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code
    assert response.json()["detail"]["message"]


async def _seed_legacy_assignment(command: AssignDealerCommand, session: AsyncSession) -> None:
    """Fixture for assignments saved before the quantity-distribution migration."""
    await legacy_assignment_repo.update_dealer_assignment(
        session, application_id=command.application_id,
        dealer_group_id=command.dealer_group_id, dealer_company_id=command.dealer_company_id,
        assigned_by=command.actor_id,
    )


async def test_assignable_groups_filter_active_dealers_and_brand(
    db_session: AsyncSession,
    assignment_graph: AssignmentGraph,
) -> None:
    graph = assignment_graph
    unfiltered = await handle_list_assignable_dealer_groups(
        ListAssignableDealerGroupsQuery(
            actor_id=graph.distributor_user.id,
            actor_role="distributor",
            actor_company_id=graph.distributor_company.id,
            application_id=graph.application.id,
        ),
        db_session,
    )
    assert [group["name"] for group in unfiltered["groups"]] == ["Main Group"]
    assert [
        dealer["name"]
        for dealer in unfiltered["groups"][0]["dealers"]
    ] == ["Alpha Dealer", "Beta Dealer"]
    assert unfiltered["groups"][0]["dealers"][0]["brands"] == [
        "FAW",
        "Hongqi",
    ]

    result = await handle_list_assignable_dealer_groups(
        ListAssignableDealerGroupsQuery(
            actor_id=graph.distributor_user.id,
            actor_role="distributor",
            actor_company_id=graph.distributor_company.id,
            application_id=graph.application.id,
            brand="Hongqi",
        ),
        db_session,
    )

    assert [group["name"] for group in result["groups"]] == ["Main Group"]
    dealers = result["groups"][0]["dealers"]
    assert [dealer["name"] for dealer in dealers] == ["Alpha Dealer"]
    assert dealers[0]["brands"] == ["FAW", "Hongqi"]

    empty = await handle_list_assignable_dealer_groups(
        ListAssignableDealerGroupsQuery(
            actor_id=graph.distributor_user.id,
            actor_role="distributor",
            actor_company_id=graph.distributor_company.id,
            application_id=graph.application.id,
            brand="Missing brand",
        ),
        db_session,
    )
    assert empty == {"groups": []}


async def test_retired_assignment_rejects_overwrite_and_preserves_saved_data(
    client: AsyncClient, db_session: AsyncSession, assignment_graph: AssignmentGraph,
) -> None:
    graph = assignment_graph
    await _seed_legacy_assignment(AssignDealerCommand(
        application_id=graph.application.id, actor_id=graph.distributor_user.id,
        actor_role="distributor", actor_company_id=graph.distributor_company.id,
        dealer_group_id=graph.group.id, dealer_company_id=graph.dealer_one.id,
    ), db_session)
    response = await client.patch(
        f"/api/v1/distributor/leasing-applications/{graph.application.id}",
        json={"dealer_group_id": graph.group.id, "dealer_company_id": graph.dealer_two.id},
        headers={"Authorization": f"Bearer {_auth_token(graph.distributor_user)}"},
    )
    assert response.status_code == 409
    await db_session.refresh(graph.application)
    assert graph.application.status == "active"
    assert graph.application.dealer_company_id == graph.dealer_one.id
    assert graph.application.assigned_dealer_group_id == graph.group.id


async def test_assignment_validates_group_owner_membership_and_dealer(
    db_session: AsyncSession,
    assignment_graph: AssignmentGraph,
) -> None:
    graph = assignment_graph

    with pytest.raises(ServiceError, match="dealer-distributions"):
        await handle_assign_dealer(
            AssignDealerCommand(
                application_id=graph.application.id,
                actor_id=graph.distributor_user.id,
                actor_role="distributor",
                actor_company_id=graph.distributor_company.id,
                dealer_group_id=graph.inactive_group.id,
                dealer_company_id=graph.dealer_one.id,
            ),
            db_session,
        )
    with pytest.raises(ServiceError, match="dealer-distributions"):
        await handle_assign_dealer(
            AssignDealerCommand(
                application_id=graph.application.id,
                actor_id=graph.distributor_user.id,
                actor_role="distributor",
                actor_company_id=graph.distributor_company.id,
                dealer_group_id=graph.group.id,
                dealer_company_id=graph.client_company.id,
            ),
            db_session,
        )
    with pytest.raises(ServiceError, match="dealer-distributions"):
        await handle_assign_dealer(
            AssignDealerCommand(
                application_id=graph.application.id,
                actor_id=graph.distributor_user.id,
                actor_role="distributor",
                actor_company_id=graph.distributor_company.id,
                dealer_group_id=graph.group.id,
                dealer_company_id=UUID("00000000-0000-0000-0000-000000000001"),
            ),
            db_session,
        )


async def test_assignment_http_returns_400_without_actor_warehouse_vehicle(
    client: AsyncClient,
    db_session: AsyncSession,
    assignment_graph: AssignmentGraph,
) -> None:
    graph = assignment_graph
    application = LeasingApplication(
        company_id=graph.client_company.id,
        status="active",
        name="No Distributor Stock Application",
        email="no-distributor-stock@example.test",
    )
    db_session.add(application)
    await db_session.flush()
    db_session.add(
        ApplicationVehicle(
            application_id=application.id,
            vehicle_id=graph.dealer_two_vehicle.id,
            quantity=1,
            unit_price=Decimal("1000000"),
            total_price=Decimal("1000000"),
        )
    )
    await db_session.flush()
    headers = {
        "Authorization": f"Bearer {_auth_token(graph.distributor_user)}",
    }

    groups_response = await client.get(
        "/api/v1/distributor/dealer-groups",
        params={"applicationId": str(application.id)},
        headers=headers,
    )
    _assert_coded_error(
        groups_response,
        status_code=400,
        code="DEALER_ASSIGNMENT_NOT_ALLOWED",
    )
    assert groups_response.json()["detail"]["message"] == (
        "В заявке нет автомобиля со склада текущего дистрибьютора"
    )

    assignment_response = await client.patch(
        f"/api/v1/distributor/leasing-applications/{application.id}",
        json={
            "dealer_group_id": str(graph.group.id),
            "dealer_company_id": str(graph.dealer_one.id),
        },
        headers=headers,
    )
    _assert_coded_error(assignment_response, status_code=409, code="ASSIGNMENT_INVALID")
    assert "dealer-distributions" in assignment_response.json()["detail"]["message"]
    await db_session.refresh(application)
    assert application.dealer_company_id is None
    assert application.assigned_dealer_group_id is None
    assert application.dealer_assigned_by is None
    assert application.dealer_assigned_at is None


async def test_assignment_http_errors_are_coded_400_403_404(
    client: AsyncClient,
    db_session: AsyncSession,
    assignment_graph: AssignmentGraph,
) -> None:
    graph = assignment_graph
    path = (
        "/api/v1/distributor/leasing-applications/"
        f"{graph.application.id}"
    )
    token = _auth_token(graph.distributor_user)

    groups_response = await client.get(
        "/api/v1/distributor/dealer-groups",
        params={
            "applicationId": str(graph.application.id),
            "brand": "FAW",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert groups_response.status_code == 200
    assert [
        group["name"] for group in groups_response.json()["groups"]
    ] == ["Main Group"]

    invalid = await client.patch(
        path,
        json={
            "dealer_group_id": str(graph.inactive_group.id),
            "dealer_company_id": str(graph.dealer_one.id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    _assert_coded_error(
        invalid,
        status_code=409,
        code="ASSIGNMENT_INVALID",
    )

    other_distributor_company = Company(
        name="Other 21752 Distributor",
        company_type="distributor",
        is_active=True,
    )
    db_session.add(other_distributor_company)
    await db_session.flush()
    other_distributor = await _add_user(
        db_session,
        company=other_distributor_company,
        phone="+76662175209",
        name="Other Distributor",
        role="distributor",
    )
    other_distributor_city = City(name="Казань 21752")
    db_session.add(other_distributor_city)
    await db_session.flush()
    _, other_distributor_vehicle = await _add_warehouse_vehicle(
        db_session,
        company=other_distributor_company,
        city=other_distributor_city,
        brand="FAW",
        vin="VIN21752OTHERDIST",
        address="Другого дистрибьютора, 1",
    )
    db_session.add(
        ApplicationVehicle(
            application_id=graph.application.id,
            vehicle_id=other_distributor_vehicle.id,
            quantity=1,
            unit_price=Decimal("1000000"),
            total_price=Decimal("1000000"),
        )
    )
    await db_session.flush()

    forbidden = await client.patch(
        path,
        json={
            "dealer_group_id": str(graph.group.id),
            "dealer_company_id": str(graph.dealer_one.id),
        },
        headers={
            "Authorization": f"Bearer {_auth_token(other_distributor)}",
        },
    )
    _assert_coded_error(
        forbidden,
        status_code=409,
        code="ASSIGNMENT_INVALID",
    )

    missing = await client.patch(
        "/api/v1/distributor/leasing-applications/"
        "00000000-0000-0000-0000-000000000001",
        json={
            "dealer_group_id": str(graph.group.id),
            "dealer_company_id": str(graph.dealer_one.id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    _assert_coded_error(
        missing,
        status_code=409,
        code="ASSIGNMENT_INVALID",
    )


async def test_detail_exposes_warehouse_owner_city_and_reassignment_flag(
    db_session: AsyncSession,
    assignment_graph: AssignmentGraph,
) -> None:
    graph = assignment_graph
    await _seed_legacy_assignment(
        AssignDealerCommand(
            application_id=graph.application.id,
            actor_id=graph.distributor_user.id,
            actor_role="distributor",
            actor_company_id=graph.distributor_company.id,
            dealer_group_id=graph.group.id,
            dealer_company_id=graph.dealer_one.id,
        ),
        db_session,
    )

    detail = await handle_get_application(
        GetApplicationQuery(
            application_id=graph.application.id,
            actor_id=graph.distributor_user.id,
            actor_role="distributor",
            actor_company_id=graph.distributor_company.id,
        ),
        db_session,
    )

    assert detail["can_assign_dealer"] is True
    assert detail["assigned_dealer"]["id"] == graph.dealer_one.id
    assert detail["dealer_assigned_by_id"] == graph.distributor_user.id
    assert detail["dealer_assigned_by"]["id"] == graph.distributor_user.id
    assert detail["dealer_assigned_at"] is not None
    warehouse = detail["vehicles"][0]["warehouse"]
    assert warehouse == {
        "id": warehouse["id"],
        "address": "Дистрибьюторская, 1",
        "brand": "FAW",
        "city": "Москва",
        "company_id": graph.distributor_company.id,
        "company_name": "21752 Distributor",
    }


async def test_employee_search_patch_clear_and_foreign_rejection(
    db_session: AsyncSession,
    assignment_graph: AssignmentGraph,
) -> None:
    graph = assignment_graph
    await _seed_legacy_assignment(
        AssignDealerCommand(
            application_id=graph.application.id,
            actor_id=graph.distributor_user.id,
            actor_role="distributor",
            actor_company_id=graph.distributor_company.id,
            dealer_group_id=graph.group.id,
            dealer_company_id=graph.dealer_one.id,
        ),
        db_session,
    )

    search = await handle_search_application_employees(
        SearchApplicationEmployeesQuery(
            application_id=graph.application.id,
            actor_id=graph.dealer_one_user.id,
            actor_role="dealer",
            actor_company_id=graph.dealer_one.id,
            query="Alpha",
            limit=2,
        ),
        db_session,
    )
    assert len(search["employees"]) == 2
    assert all(
        employee["id"] != graph.inactive_employee.id
        for employee in search["employees"]
    )
    inactive_search = await handle_search_application_employees(
        SearchApplicationEmployeesQuery(
            application_id=graph.application.id,
            actor_id=graph.dealer_one_user.id,
            actor_role="dealer",
            actor_company_id=graph.dealer_one.id,
            query="Inactive Employee",
            limit=20,
        ),
        db_session,
    )
    assert inactive_search["employees"] == []

    assigned = await handle_assign_application_employees(
        AssignApplicationEmployeesCommand(
            application_id=graph.application.id,
            actor_id=graph.dealer_one_user.id,
            actor_role="dealer",
            actor_company_id=graph.dealer_one.id,
            update_primary=True,
            primary_employee_id=graph.dealer_one_primary.id,
            update_additional=True,
            additional_employee_id=graph.dealer_one_additional.id,
        ),
        db_session,
    )
    assert assigned["application"]["primary_employee"]["id"] == (
        graph.dealer_one_primary.id
    )
    assert assigned["application"]["additional_employee"]["id"] == (
        graph.dealer_one_additional.id
    )
    assert assigned["application"]["employees_assigned_by"]["id"] == (
        graph.dealer_one_user.id
    )
    assert assigned["application"]["employees_assigned_by_id"] == (
        graph.dealer_one_user.id
    )
    assert assigned["application"]["employees_assigned_at"] is not None

    cleared = await handle_assign_application_employees(
        AssignApplicationEmployeesCommand(
            application_id=graph.application.id,
            actor_id=graph.dealer_one_user.id,
            actor_role="dealer",
            actor_company_id=graph.dealer_one.id,
            update_primary=True,
            primary_employee_id=None,
        ),
        db_session,
    )
    assert cleared["application"]["primary_employee"] is None

    with pytest.raises(EmployeeAssignmentNotAllowedError):
        await handle_assign_application_employees(
            AssignApplicationEmployeesCommand(
                application_id=graph.application.id,
                actor_id=graph.dealer_one_user.id,
                actor_role="dealer",
                actor_company_id=graph.dealer_one.id,
                update_primary=True,
                primary_employee_id=graph.foreign_employee.id,
            ),
            db_session,
        )
    with pytest.raises(ApplicationNotOwnedError):
        await handle_search_application_employees(
            SearchApplicationEmployeesQuery(
                application_id=graph.application.id,
                actor_id=graph.dealer_two_user.id,
                actor_role="dealer",
                actor_company_id=graph.dealer_two.id,
            ),
            db_session,
        )


async def test_distributor_searches_and_assigns_company_employee(
    db_session: AsyncSession,
    assignment_graph: AssignmentGraph,
) -> None:
    graph = assignment_graph
    search = await handle_search_application_employees(
        SearchApplicationEmployeesQuery(
            application_id=graph.application.id,
            actor_id=graph.distributor_user.id,
            actor_role="distributor",
            actor_company_id=graph.distributor_company.id,
            query="Distributor Employee",
            limit=20,
        ),
        db_session,
    )
    assert [employee["id"] for employee in search["employees"]] == [
        graph.distributor_employee.id
    ]

    assigned = await handle_assign_application_employees(
        AssignApplicationEmployeesCommand(
            application_id=graph.application.id,
            actor_id=graph.distributor_user.id,
            actor_role="distributor",
            actor_company_id=graph.distributor_company.id,
            update_primary=True,
            primary_employee_id=graph.distributor_employee.id,
        ),
        db_session,
    )
    application = assigned["application"]
    assert application["primary_employee_id"] == graph.distributor_employee.id
    assert application["primary_employee"]["id"] == graph.distributor_employee.id
    assert application["employees_assigned_by_id"] == graph.distributor_user.id
    assert application["employees_assigned_at"] is not None

    await db_session.refresh(graph.application)
    assert graph.application.primary_employee_id == graph.distributor_employee.id
    assert graph.application.employees_assigned_by == graph.distributor_user.id
    assert graph.application.employees_assigned_at is not None


async def test_partial_employee_patch_rejects_duplicate_current_assignment(
    db_session: AsyncSession,
    assignment_graph: AssignmentGraph,
) -> None:
    graph = assignment_graph
    await _seed_legacy_assignment(
        AssignDealerCommand(
            application_id=graph.application.id,
            actor_id=graph.distributor_user.id,
            actor_role="distributor",
            actor_company_id=graph.distributor_company.id,
            dealer_group_id=graph.group.id,
            dealer_company_id=graph.dealer_one.id,
        ),
        db_session,
    )
    await handle_assign_application_employees(
        AssignApplicationEmployeesCommand(
            application_id=graph.application.id,
            actor_id=graph.dealer_one_user.id,
            actor_role="dealer",
            actor_company_id=graph.dealer_one.id,
            update_primary=True,
            primary_employee_id=graph.dealer_one_primary.id,
            update_additional=True,
            additional_employee_id=graph.dealer_one_additional.id,
        ),
        db_session,
    )

    with pytest.raises(
        EmployeeAssignmentNotAllowedError,
        match="Основной и дополнительный сотрудник должны быть разными",
    ):
        await handle_assign_application_employees(
            AssignApplicationEmployeesCommand(
                application_id=graph.application.id,
                actor_id=graph.dealer_one_user.id,
                actor_role="dealer",
                actor_company_id=graph.dealer_one.id,
                update_primary=True,
                primary_employee_id=graph.dealer_one_additional.id,
            ),
            db_session,
        )

    with pytest.raises(
        EmployeeAssignmentNotAllowedError,
        match="Основной и дополнительный сотрудник должны быть разными",
    ):
        await handle_assign_application_employees(
            AssignApplicationEmployeesCommand(
                application_id=graph.application.id,
                actor_id=graph.dealer_one_user.id,
                actor_role="dealer",
                actor_company_id=graph.dealer_one.id,
                update_additional=True,
                additional_employee_id=graph.dealer_one_primary.id,
            ),
            db_session,
        )

    await db_session.refresh(graph.application)
    assert graph.application.primary_employee_id == graph.dealer_one_primary.id
    assert (
        graph.application.additional_employee_id
        == graph.dealer_one_additional.id
    )


async def test_employee_search_and_assignment_support_primary_company_membership(
    db_session: AsyncSession,
    assignment_graph: AssignmentGraph,
) -> None:
    graph = assignment_graph
    legacy_employee = User(
        company_id=graph.dealer_one.id,
        phone="+76662175220",
        name="Primary Company Employee",
        role="dealer",
        is_active=True,
    )
    foreign_legacy_employee = User(
        company_id=graph.dealer_two.id,
        phone="+76662175221",
        name="Primary Company Foreign Employee",
        role="dealer",
        is_active=True,
    )
    inactive_legacy_employee = User(
        company_id=graph.dealer_one.id,
        phone="+76662175222",
        name="Primary Company Inactive Employee",
        role="dealer",
        is_active=False,
    )
    db_session.add_all(
        [
            legacy_employee,
            foreign_legacy_employee,
            inactive_legacy_employee,
        ]
    )
    await db_session.flush()
    await _seed_legacy_assignment(
        AssignDealerCommand(
            application_id=graph.application.id,
            actor_id=graph.distributor_user.id,
            actor_role="distributor",
            actor_company_id=graph.distributor_company.id,
            dealer_group_id=graph.group.id,
            dealer_company_id=graph.dealer_one.id,
        ),
        db_session,
    )

    search = await handle_search_application_employees(
        SearchApplicationEmployeesQuery(
            application_id=graph.application.id,
            actor_id=graph.dealer_one_user.id,
            actor_role="dealer",
            actor_company_id=graph.dealer_one.id,
            query="Primary Company",
            limit=20,
        ),
        db_session,
    )

    assert search["employees"] == [
        {
            "id": legacy_employee.id,
            "name": "Primary Company Employee",
            "phone": "+76662175220",
            "sub_role": "administrator",
        }
    ]

    assigned = await handle_assign_application_employees(
        AssignApplicationEmployeesCommand(
            application_id=graph.application.id,
            actor_id=graph.dealer_one_user.id,
            actor_role="dealer",
            actor_company_id=graph.dealer_one.id,
            update_primary=True,
            primary_employee_id=legacy_employee.id,
        ),
        db_session,
    )
    assert assigned["application"]["primary_employee"] == {
        "id": legacy_employee.id,
        "name": "Primary Company Employee",
        "phone": "+76662175220",
        "sub_role": "administrator",
    }

    with pytest.raises(EmployeeAssignmentNotAllowedError):
        await handle_assign_application_employees(
            AssignApplicationEmployeesCommand(
                application_id=graph.application.id,
                actor_id=graph.dealer_one_user.id,
                actor_role="dealer",
                actor_company_id=graph.dealer_one.id,
                update_primary=True,
                primary_employee_id=foreign_legacy_employee.id,
            ),
            db_session,
        )


async def test_employee_http_get_patch_and_coded_errors(
    client: AsyncClient,
    db_session: AsyncSession,
    assignment_graph: AssignmentGraph,
) -> None:
    graph = assignment_graph
    await _seed_legacy_assignment(
        AssignDealerCommand(
            application_id=graph.application.id,
            actor_id=graph.distributor_user.id,
            actor_role="distributor",
            actor_company_id=graph.distributor_company.id,
            dealer_group_id=graph.group.id,
            dealer_company_id=graph.dealer_one.id,
        ),
        db_session,
    )
    base_path = f"/api/v1/applications/{graph.application.id}/employees"
    dealer_headers = {
        "Authorization": f"Bearer {_auth_token(graph.dealer_one_user)}",
    }

    search = await client.get(
        f"{base_path}/search",
        params={"query": "Alpha", "limit": 10},
        headers=dealer_headers,
    )
    assert search.status_code == 200
    assert graph.dealer_one_primary.id in {
        UUID(employee["id"]) for employee in search.json()["employees"]
    }

    patched = await client.patch(
        base_path,
        json={
            "primary_employee_id": str(graph.dealer_one_primary.id),
            "additional_employee_id": str(graph.dealer_one_additional.id),
        },
        headers=dealer_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["application"]["primary_employee"]["id"] == str(
        graph.dealer_one_primary.id
    )

    duplicate = await client.patch(
        base_path,
        json={"additional_employee_id": str(graph.dealer_one_primary.id)},
        headers=dealer_headers,
    )
    _assert_coded_error(
        duplicate,
        status_code=400,
        code="EMPLOYEE_ASSIGNMENT_NOT_ALLOWED",
    )
    assert duplicate.json()["detail"]["message"] == (
        "Основной и дополнительный сотрудник должны быть разными"
    )

    invalid = await client.patch(
        base_path,
        json={"primary_employee_id": str(graph.foreign_employee.id)},
        headers=dealer_headers,
    )
    _assert_coded_error(
        invalid,
        status_code=400,
        code="EMPLOYEE_ASSIGNMENT_NOT_ALLOWED",
    )

    forbidden = await client.get(
        f"{base_path}/search",
        headers={
            "Authorization": f"Bearer {_auth_token(graph.dealer_two_user)}",
        },
    )
    _assert_coded_error(
        forbidden,
        status_code=403,
        code="APPLICATION_ACCESS_DENIED",
    )

    missing = await client.get(
        "/api/v1/applications/"
        "00000000-0000-0000-0000-000000000001/employees/search",
        headers=dealer_headers,
    )
    _assert_coded_error(
        missing,
        status_code=404,
        code="APPLICATION_NOT_FOUND",
    )


async def test_carcraft_employee_uses_selected_company_membership(
    db_session: AsyncSession,
    assignment_graph: AssignmentGraph,
) -> None:
    graph = assignment_graph
    search = await handle_search_application_employees(
        SearchApplicationEmployeesQuery(
            application_id=graph.application.id,
            actor_id=graph.carcraft_user.id,
            actor_role="carcraft_employee",
            actor_company_id=graph.dealer_one.id,
            query="Primary",
            limit=20,
        ),
        db_session,
    )
    assert [employee["id"] for employee in search["employees"]] == [
        graph.dealer_one_primary.id
    ]

    result = await handle_assign_application_employees(
        AssignApplicationEmployeesCommand(
            application_id=graph.application.id,
            actor_id=graph.carcraft_user.id,
            actor_role="carcraft_employee",
            actor_company_id=graph.dealer_one.id,
            update_primary=True,
            primary_employee_id=graph.dealer_one_primary.id,
        ),
        db_session,
    )
    assert result["application"]["primary_employee"]["id"] == (
        graph.dealer_one_primary.id
    )


async def test_creation_routes_dealer_company_by_actor_then_warehouse_type(
    db_session: AsyncSession,
    assignment_graph: AssignmentGraph,
) -> None:
    graph = assignment_graph

    dealer_created = await handle_create_draft(
        CreateDraftCommand(
            source_type="platform",
            actor_id=graph.dealer_one_user.id,
            actor_role="dealer",
            actor_company_id=graph.dealer_one.id,
            company_id=None,
            company={
                "name": "21752 External Client",
                "inn": "2175211111",
                "kpp": "217521001",
                "ogrn": "1021752111111",
                "legal_address": "Москва",
            },
            vehicles=[
                ApplicationVehiclePayload(
                    vehicle_id=graph.dealer_two_vehicle.id,
                    custom_price=Decimal("100"),
                )
            ],
        ),
        db_session,
    )
    dealer_application = await db_session.get(
        LeasingApplication,
        dealer_created["application_id"],
    )
    assert dealer_application is not None
    assert dealer_application.dealer_company_id == graph.dealer_one.id

    client_created = await handle_create_draft(
        CreateDraftCommand(
            source_type="platform",
            actor_id=graph.client_user.id,
            actor_role="client",
            actor_company_id=graph.client_company.id,
            company_id=graph.client_company.id,
            vehicles=[
                ApplicationVehiclePayload(
                    vehicle_id=graph.dealer_two_vehicle.id,
                    custom_price=Decimal("100"),
                )
            ],
        ),
        db_session,
    )
    client_application = await db_session.get(
        LeasingApplication,
        client_created["application_id"],
    )
    assert client_application is not None
    assert client_application.dealer_company_id == graph.dealer_two.id

    distributor_created = await handle_create_draft(
        CreateDraftCommand(
            source_type="platform",
            actor_id=graph.distributor_user.id,
            actor_role="distributor",
            actor_company_id=graph.distributor_company.id,
            company_id=graph.client_company.id,
            vehicles=[
                ApplicationVehiclePayload(
                    vehicle_id=graph.distributor_vehicle.id,
                    custom_price=Decimal("100"),
                )
            ],
        ),
        db_session,
    )
    distributor_application = await db_session.get(
        LeasingApplication,
        distributor_created["application_id"],
    )
    assert distributor_application is not None
    assert distributor_application.dealer_company_id is None

    for vehicles in (
        [graph.distributor_vehicle, graph.dealer_two_vehicle],
        [graph.dealer_two_vehicle, graph.distributor_vehicle],
    ):
        mixed_created = await handle_create_draft(
            CreateDraftCommand(
                source_type="platform",
                actor_id=graph.distributor_user.id,
                actor_role="distributor",
                actor_company_id=graph.distributor_company.id,
                company_id=graph.client_company.id,
                vehicles=[
                    ApplicationVehiclePayload(
                        vehicle_id=vehicle.id,
                        custom_price=Decimal("100"),
                    )
                    for vehicle in vehicles
                ],
            ),
            db_session,
        )
        mixed_application = await db_session.get(
            LeasingApplication,
            mixed_created["application_id"],
        )
        assert mixed_application is not None
        assert mixed_application.dealer_company_id is None

    full_distributor_created = await handle_create_application(
        CreateApplicationCommand(
            source_type="platform",
            actor_id=graph.distributor_user.id,
            actor_role="distributor",
            company_id=graph.client_company.id,
            name="Full distributor flow",
            email="full-distributor@example.test",
            vehicles=[
                ApplicationVehiclePayload(
                    vehicle_id=graph.distributor_vehicle.id,
                    custom_price=Decimal("100"),
                )
            ],
        ),
        db_session,
    )
    full_distributor_application = await db_session.get(
        LeasingApplication,
        full_distributor_created["application_id"],
    )
    assert full_distributor_application is not None
    assert full_distributor_application.dealer_company_id is None

    db_session.add(
        UserCompany(
            user_id=graph.dealer_one_user.id,
            company_id=graph.client_company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    await db_session.flush()
    full_dealer_created = await handle_create_application(
        CreateApplicationCommand(
            source_type="platform",
            actor_id=graph.dealer_one_user.id,
            actor_role="dealer",
            company_id=graph.client_company.id,
            name="Full dealer-on-behalf flow",
            email="full-dealer@example.test",
            vehicles=[
                ApplicationVehiclePayload(
                    vehicle_id=graph.dealer_two_vehicle.id,
                    custom_price=Decimal("100"),
                )
            ],
        ),
        db_session,
    )
    full_dealer_application = await db_session.get(
        LeasingApplication,
        full_dealer_created["application_id"],
    )
    assert full_dealer_application is not None
    assert full_dealer_application.dealer_company_id == graph.dealer_one.id
