from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.applications.update_additional_options import (
    UpdateAdditionalOptionsCommand,
    handle_update_additional_options,
)
from application.errors import ServiceError
from domain.additional_options import InvalidAdditionalOptionsError
from domain.errors import ApplicationNotOwnedError
from infrastructure.models.applications import (
    AdditionalEquipment,
    AdditionalService,
    ApplicationVehicle,
    LeasingApplication,
)
from infrastructure.models.companies import Company, DistributorDealerLink
from infrastructure.models.notification_delivery import NotificationEventOutbox
from infrastructure.models.users import User
from infrastructure.models.vehicles import Warehouse
from infrastructure.repositories import application_repository
from tests.legacy_compat import Vehicle, VehicleWarehouse

pytestmark = pytest.mark.asyncio


async def test_option_comments_order_and_decimal_format_do_not_notify_again(
    db_session: AsyncSession,
) -> None:
    company, dealer, application, vehicle = await _seed_application(db_session)
    command = UpdateAdditionalOptionsCommand(
        application_id=application.id, application_vehicle_id=vehicle.id,
        actor_id=dealer.id, actor_role="dealer", actor_company_id=company.id,
        equipments=[{"equipment_code": "alarm", "price": "25000"},
                    {"equipment_code": "mats", "price": "5000"}],
        services=[],
    )
    await handle_update_additional_options(command, db_session)
    await handle_update_additional_options(
        UpdateAdditionalOptionsCommand(
            application_id=application.id, application_vehicle_id=vehicle.id,
            actor_id=dealer.id, actor_role="dealer", actor_company_id=company.id,
            equipments=[{"equipment_code": "mats", "price": "5000.00", "comment": "private"},
                        {"equipment_code": "alarm", "price": "25000.00"}],
            services=[],
        ), db_session,
    )
    events = (await db_session.scalars(sa.select(NotificationEventOutbox).where(
        NotificationEventOutbox.aggregate_id == application.id,
    ))).all()
    assert len(events) == 1
    assert events[0].event_type == "leasing.additional_price_changed"
    assert "private" not in str(events[0].payload)


async def _seed_application(
    db_session: AsyncSession,
) -> tuple[Company, User, LeasingApplication, ApplicationVehicle]:
    company = Company(name="Client Company", inn="7700000000", company_type="other")
    dealer_company = Company(
        name="Dealer Company", inn="7700000001", company_type="dealer"
    )
    db_session.add(company)
    db_session.add(dealer_company)
    await db_session.flush()
    dealer = User(
        phone="+76660000123",
        email="dealer-options@test.local",
        name="Dealer Options",
        role="dealer",
        company_id=dealer_company.id,
        is_active=True,
    )
    db_session.add(dealer)
    db_session.add_all(
        [
            AdditionalEquipment(
                equipment_code="alarm",
                equipment_display_name="Alarm",
            ),
            AdditionalEquipment(
                equipment_code="mats",
                equipment_display_name="Mats",
            ),
            AdditionalService(
                service_code="kasko",
                service_display_name="Kasko",
            ),
            AdditionalService(
                service_code="delivery",
                service_display_name="Delivery",
            ),
        ]
    )
    await db_session.flush()
    application = LeasingApplication(
        company_id=company.id,
        dealer_company_id=dealer_company.id,
        created_by=dealer.id,
        status="active",
        total_amount=Decimal("1000000"),
        selected_leasing_companies=[],
    )
    db_session.add(application)
    await db_session.flush()
    vehicle = ApplicationVehicle(
        application_id=application.id,
        vehicle_id=None,
        modification_id="mod-1",
        quantity=2,
        unit_price=Decimal("1000000"),
        total_price=Decimal("2000000"),
        equipments=[{"equipment_code": "alarm", "price": 0}],
        services=[{"service_code": "kasko", "price": 0}],
        is_model_order=True,
    )
    db_session.add(vehicle)
    await db_session.flush()
    return dealer_company, dealer, application, vehicle


async def test_update_additional_options_recalculates_vehicle_and_application(
    db_session: AsyncSession,
) -> None:
    dealer_company, dealer, application, vehicle = await _seed_application(db_session)

    result = await handle_update_additional_options(
        UpdateAdditionalOptionsCommand(
            application_id=application.id,
            application_vehicle_id=vehicle.id,
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=dealer_company.id,
            equipments=[
                {
                    "equipment_code": "alarm",
                    "price": "25000",
                    "comment": "Install before delivery",
                },
                {
                    "equipment_code": "mats",
                    "price": "5000",
                    "comment": None,
                },
            ],
            services=[
                {
                    "service_code": "kasko",
                    "price": "100000",
                    "comment": "Annual policy",
                }
            ],
        ),
        db_session,
    )

    assert result["application_vehicle"]["equipments"] == [
        {
            "equipment_code": "alarm",
            "price": "25000",
            "comment": "Install before delivery",
        },
        {"equipment_code": "mats", "price": "5000", "comment": None},
    ]
    assert result["application_vehicle"]["services"] == [
        {
            "service_code": "kasko",
            "price": "100000",
            "comment": "Annual policy",
        }
    ]
    assert result["application_vehicle"]["total_price"] == Decimal("2260000")
    assert result["application"]["total_amount"] == Decimal("2260000")


async def test_dealer_cannot_update_options_for_another_dealers_vehicle(
    db_session: AsyncSession,
) -> None:
    dealer_company, dealer, application, _ = await _seed_application(db_session)
    foreign_dealer = Company(
        name="Foreign Dealer",
        inn="7700000002",
        company_type="dealer",
    )
    db_session.add(foreign_dealer)
    await db_session.flush()
    inventory_vehicle = Vehicle(dealer_id=foreign_dealer.id)
    db_session.add(inventory_vehicle)
    await db_session.flush()
    foreign_vehicle = ApplicationVehicle(
        application_id=application.id,
        vehicle_id=inventory_vehicle.id,
        dealer_company_id=foreign_dealer.id,
        quantity=1,
        unit_price=Decimal("1000000"),
        total_price=Decimal("1000000"),
        equipments=[{"equipment_code": "alarm", "price": 0}],
        services=[],
        is_model_order=False,
    )
    db_session.add(foreign_vehicle)
    await db_session.flush()

    with pytest.raises(ApplicationNotOwnedError):
        await handle_update_additional_options(
            UpdateAdditionalOptionsCommand(
                application_id=application.id,
                application_vehicle_id=foreign_vehicle.id,
                actor_id=dealer.id,
                actor_role="dealer",
                actor_company_id=dealer_company.id,
                equipments=[{"equipment_code": "alarm", "price": "1", "comment": None}],
                services=[],
            ),
            db_session,
        )


async def test_existing_options_without_comment_are_read_as_null(
    db_session: AsyncSession,
) -> None:
    _, _, _, vehicle = await _seed_application(db_session)

    stored = await application_repository.get_application_vehicle(
        db_session, vehicle.id
    )

    assert stored is not None
    assert stored["equipments"] == [
        {"equipment_code": "alarm", "price": 0, "comment": None}
    ]
    assert stored["services"] == [
        {"service_code": "kasko", "price": 0, "comment": None}
    ]


async def test_distributor_cannot_update_options_outside_linked_dealer_scope(
    db_session: AsyncSession,
) -> None:
    _, _, application, vehicle = await _seed_application(db_session)
    distributor_company = Company(
        name="Scoped Distributor",
        inn="7700000003",
        company_type="distributor",
    )
    linked_dealer = Company(
        name="Linked Dealer",
        inn="7700000004",
        company_type="dealer",
    )
    db_session.add_all([distributor_company, linked_dealer])
    await db_session.flush()
    distributor = User(
        phone="+76660000124",
        email="distributor-options@test.local",
        name="Distributor Options",
        role="distributor",
        company_id=distributor_company.id,
        is_active=True,
    )
    db_session.add_all(
        [
            distributor,
            DistributorDealerLink(
                distributor_company_id=distributor_company.id,
                dealer_company_id=linked_dealer.id,
            ),
        ]
    )
    await db_session.flush()

    with pytest.raises(ApplicationNotOwnedError):
        await handle_update_additional_options(
            UpdateAdditionalOptionsCommand(
                application_id=application.id,
                application_vehicle_id=vehicle.id,
                actor_id=distributor.id,
                actor_role="distributor",
                actor_company_id=distributor_company.id,
                equipments=[{"equipment_code": "alarm", "price": "1", "comment": None}],
                services=[],
            ),
            db_session,
        )


async def test_update_additional_options_can_clear_comment(
    db_session: AsyncSession,
) -> None:
    dealer_company, dealer, application, vehicle = await _seed_application(db_session)

    result = await handle_update_additional_options(
        UpdateAdditionalOptionsCommand(
            application_id=application.id,
            application_vehicle_id=vehicle.id,
            actor_id=dealer.id,
            actor_role="dealer",
            actor_company_id=dealer_company.id,
            equipments=[
                {"equipment_code": "alarm", "price": "25000", "comment": None}
            ],
            services=[
                {"service_code": "kasko", "price": "100000", "comment": None}
            ],
        ),
        db_session,
    )

    assert result["application_vehicle"]["equipments"][0]["comment"] is None
    assert result["application_vehicle"]["services"][0]["comment"] is None


@pytest.mark.parametrize(
    ("equipments", "services", "expected_detail"),
    [
        (
            [
                {"equipment_code": "alarm", "price": "1", "comment": None},
                {"equipment_code": "alarm", "price": "2", "comment": None},
            ],
            [{"service_code": "kasko", "price": "3", "comment": None}],
            "повторяется",
        ),
        (
            [{"equipment_code": "delivery", "price": "1", "comment": None}],
            [{"service_code": "kasko", "price": "3", "comment": None}],
            "относится к услугам",
        ),
        (
            [{"equipment_code": "missing", "price": "1", "comment": None}],
            [{"service_code": "kasko", "price": "3", "comment": None}],
            "не найден",
        ),
        (
            [{"equipment_code": "alarm", "price": "1", "comment": None}],
            [{"service_code": "alarm", "price": "3", "comment": None}],
            "относится к оборудованию",
        ),
    ],
)
async def test_invalid_catalog_options_are_rejected_atomically(
    db_session: AsyncSession,
    equipments: list[dict[str, Any]],
    services: list[dict[str, Any]],
    expected_detail: str,
) -> None:
    dealer_company, dealer, application, vehicle = await _seed_application(db_session)

    with pytest.raises(InvalidAdditionalOptionsError) as exc:
        await handle_update_additional_options(
            UpdateAdditionalOptionsCommand(
                application_id=application.id,
                application_vehicle_id=vehicle.id,
                actor_id=dealer.id,
                actor_role="dealer",
                actor_company_id=dealer_company.id,
                equipments=equipments,
                services=services,
            ),
            db_session,
        )

    stored = await application_repository.get_application_vehicle(
        db_session, vehicle.id
    )
    assert expected_detail in str(exc.value)
    assert stored is not None
    assert stored["equipments"] == [
        {"equipment_code": "alarm", "price": 0, "comment": None}
    ]
    assert stored["services"] == [
        {"service_code": "kasko", "price": 0, "comment": None}
    ]


@pytest.mark.parametrize("actor_role", ["dealer", "distributor"])
async def test_authorized_organization_roles_can_update_additional_options(
    db_session: AsyncSession,
    actor_role: str,
) -> None:
    dealer_company, dealer, application, vehicle = await _seed_application(db_session)
    if actor_role == "distributor":
        dealer_company.company_type = "distributor"
        dealer.role = "distributor"
        warehouse = Warehouse(company_id=dealer_company.id, address="Own stock", brand="FAW")
        stock_vehicle = Vehicle(dealer_id=dealer_company.id, status="available")
        db_session.add_all([warehouse, stock_vehicle])
        await db_session.flush()
        db_session.add(VehicleWarehouse(vehicle_id=stock_vehicle.id, warehouse_id=warehouse.id))
        vehicle.vehicle_id = stock_vehicle.id
        vehicle.is_model_order = False
        await db_session.flush()

    result = await handle_update_additional_options(
        UpdateAdditionalOptionsCommand(
            application_id=application.id,
            application_vehicle_id=vehicle.id,
            actor_id=dealer.id,
            actor_role=actor_role,
            actor_company_id=dealer_company.id,
            equipments=[
                {"equipment_code": "alarm", "price": "25000", "comment": None}
            ],
            services=[
                {"service_code": "kasko", "price": "100000", "comment": None}
            ],
        ),
        db_session,
    )

    assert result["application_vehicle"]["equipments"][0]["price"] == "25000"


async def test_selected_leasing_company_can_update_additional_options(
    db_session: AsyncSession,
) -> None:
    dealer_company, dealer, application, vehicle = await _seed_application(db_session)
    leasing_company_id = dealer.id
    application.selected_leasing_companies = [leasing_company_id]
    await db_session.flush()

    result = await handle_update_additional_options(
        UpdateAdditionalOptionsCommand(
            application_id=application.id,
            application_vehicle_id=vehicle.id,
            actor_id=dealer.id,
            actor_role="leasing_company",
            actor_company_id=dealer_company.id,
            actor_leasing_company_id=leasing_company_id,
            equipments=[
                {"equipment_code": "alarm", "price": "25000", "comment": None}
            ],
            services=[
                {"service_code": "kasko", "price": "100000", "comment": None}
            ],
        ),
        db_session,
    )

    assert result["application_vehicle"]["services"][0]["price"] == "100000"


async def test_employee_cannot_update_additional_options(
    db_session: AsyncSession,
) -> None:
    dealer_company, dealer, application, vehicle = await _seed_application(db_session)

    with pytest.raises(ServiceError) as exc:
        await handle_update_additional_options(
            UpdateAdditionalOptionsCommand(
                application_id=application.id,
                application_vehicle_id=vehicle.id,
                actor_id=dealer.id,
                actor_role="carcraft_employee",
                actor_company_id=dealer_company.id,
                equipments=[],
                services=[],
            ),
            db_session,
        )

    assert exc.value.status_code == 403


async def test_update_additional_options_denies_client_role(
    db_session: AsyncSession,
) -> None:
    dealer_company, dealer, application, vehicle = await _seed_application(db_session)

    with pytest.raises(ServiceError) as exc:
        await handle_update_additional_options(
            UpdateAdditionalOptionsCommand(
                application_id=application.id,
                application_vehicle_id=vehicle.id,
                actor_id=dealer.id,
                actor_role="client",
                actor_company_id=dealer_company.id,
                equipments=[],
                services=[],
            ),
            db_session,
        )

    assert exc.value.status_code == 403
