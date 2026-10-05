"""Functional tests for the calculator handlers (real Postgres, no HTTP)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.calculator import CalculateCommand, handle_calculate
from application.queries.calculator import (
    GetSupportStatusQuery,
    handle_get_support_status,
)
from domain.errors import CartCustomPriceDeniedError, InvalidCalculationParamsError
from infrastructure.models.applications import CalculationHistory
from infrastructure.models.companies import Company, Distributor, DistributorDealerLink
from infrastructure.models.misc import LeasingRate
from infrastructure.models.support import (
    DealerGroup,
    DealerGroupMember,
    SupportProgram,
    SupportProgramCompatibility,
    SupportProgramDealerGroup,
)
from infrastructure.models.users import User
from infrastructure.models.vehicles import Warehouse
from infrastructure.repositories.calculator_repository import (
    get_vehicles_with_support_info,
)
from tests.legacy_compat import (
    CarModel,
    Configuration,
    Generation,
    Mark,
    Modification,
    Vehicle,
    VehicleWarehouse,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _seed_rates(db: AsyncSession) -> None:
    db.add(
        LeasingRate(key_rate=21.0, surcharge=4.0, vat_rate=20.0, profit_tax_rate=20.0)
    )
    await db.flush()


async def _seed_vehicle(
    db: AsyncSession,
    *,
    base_price: Decimal | None = Decimal("2000000.00"),
    discount_price: Decimal | None = None,
) -> Vehicle:
    v = Vehicle(
        status="available",
        is_available=True,
        base_price=base_price,
        discount_price=discount_price,
    )
    db.add(v)
    await db.flush()
    await db.refresh(v)
    return v


async def _seed_support_program(
    db: AsyncSession,
    *,
    program_id: UUID | None = None,
    support_type: str = "vehicle_discount_dealer_compensation",
    support_params: dict[str, object] | None = None,
    distributor_id: UUID | None = None,
    is_compatible: bool = False,
) -> SupportProgram:
    program = SupportProgram(
        name="Zero price custom support",
        support_type=support_type,
        support_params=support_params or {"value_type": "percent", "value": 10},
        is_active=True,
        show_to_client=True,
        distributor_id=distributor_id,
        is_compatible=is_compatible,
    )
    if program_id is not None:
        program.id = program_id
    db.add(program)
    await db.flush()
    await db.refresh(program)
    return program


async def _link_compatible_supports(
    db: AsyncSession,
    left: SupportProgram,
    right: SupportProgram,
) -> None:
    first_id, second_id = sorted((left.id, right.id))
    db.add(
        SupportProgramCompatibility(
            support_program_id=first_id,
            compatible_support_program_id=second_id,
        )
    )
    await db.flush()


async def _seed_distributor(db: AsyncSession) -> Distributor:
    company = Company(
        name="Calculator Handler Distributor",
        inn="7700000002",
        company_type="distributor",
        is_active=True,
    )
    db.add(company)
    await db.flush()
    distributor = Distributor(company_id=company.id, is_active=True)
    db.add(distributor)
    await db.flush()
    await db.refresh(distributor)
    return distributor


async def _seed_employee(db: AsyncSession) -> User:
    user = User(
        phone="+75550001000",
        email="calc-employee@test.local",
        name="Calc Employee",
        role="carcraft_employee",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def _seed_dealer_company(
    db: AsyncSession,
    *,
    distributor_company_id: UUID,
    suffix: str,
) -> Company:
    company = Company(
        name=f"Calculator Dealer {suffix}",
        inn=f"77000010{int(suffix):02d}",
        company_type="dealer",
        is_active=True,
    )
    db.add(company)
    await db.flush()
    db.add(
        DistributorDealerLink(
            distributor_company_id=distributor_company_id,
            dealer_company_id=company.id,
        )
    )
    await db.flush()
    return company


async def _bind_vehicle_to_dealer_warehouse(
    db: AsyncSession,
    *,
    vehicle: Vehicle,
    dealer_company_id: UUID,
    suffix: str,
) -> None:
    warehouse = Warehouse(
        address=f"Warehouse {suffix}",
        brand="BMW",
        dealer_id=dealer_company_id,
        company_id=dealer_company_id,
        status="active",
    )
    db.add(warehouse)
    await db.flush()
    db.add(VehicleWarehouse(vehicle_id=vehicle.id, warehouse_id=warehouse.id))
    await db.flush()


async def _seed_dealer_group(
    db: AsyncSession,
    *,
    distributor_company_id: UUID,
    dealer_company_id: UUID,
) -> DealerGroup:
    employee = await _seed_employee(db)
    group = DealerGroup(
        name="Calculator Dealer Group",
        distributor_company_id=distributor_company_id,
        created_by=employee.id,
        is_active=True,
    )
    db.add(group)
    await db.flush()
    db.add(
        DealerGroupMember(
            dealer_group_id=group.id,
            dealer_company_id=dealer_company_id,
            created_by=employee.id,
        )
    )
    await db.flush()
    return group


# ---------------------------------------------------------------------------
# Support-program configuration matching
# ---------------------------------------------------------------------------


async def test_support_program_matches_trim_id_from_support_form(
    db_session: AsyncSession,
    default_vehicle_category_id: int,
) -> None:
    mark = Mark(id="support-trim-mark", name="Support trim mark")
    db_session.add(mark)
    await db_session.flush()
    model = CarModel(
        id="support-trim-model",
        name="Support trim model",
        mark_id=mark.id,
        category=default_vehicle_category_id,
    )
    db_session.add(model)
    await db_session.flush()
    generation = Generation(id="support-trim-generation", name="G1", model_id=model.id)
    db_session.add(generation)
    await db_session.flush()
    configuration = Configuration(
        id="support-trim-configuration",
        configuration_name="Configuration",
        generation_id=generation.id,
    )
    db_session.add(configuration)
    await db_session.flush()
    modification = Modification(
        complectation_id="support-raw-complectation",
        group_name="Premium",
        configuration_id=configuration.id,
    )
    db_session.add(modification)
    await db_session.flush()

    vehicle = Vehicle(
        status="available",
        is_available=True,
        base_price=Decimal("2000000"),
        mark_id=mark.id,
        model_id=model.id,
        generation_id=generation.id,
        configuration_id=configuration.id,
        complectation_id=modification.complectation_id,
    )
    support = SupportProgram(
        name="Premium-only support",
        support_type="vehicle_discount_dealer_compensation",
        support_params={"value_type": "amount", "value": 100000},
        complectation_ids=[f"{configuration.id}_{modification.group_name}"],
        is_active=True,
        show_to_client=True,
    )
    unrestricted_support = SupportProgram(
        name="All-trims support",
        support_type="vehicle_discount_dealer_compensation",
        support_params={"value_type": "amount", "value": 50000},
        complectation_ids=[],
        is_active=True,
        show_to_client=True,
    )
    db_session.add_all([vehicle, support, unrestricted_support])
    await db_session.flush()

    rows = await get_vehicles_with_support_info(db_session, [vehicle.id])

    assert {row["support_program_id"] for row in rows} == {
        support.id,
        unrestricted_support.id,
    }


# ---------------------------------------------------------------------------
# handle_calculate — anonymous, no support
# ---------------------------------------------------------------------------


async def test_calculate_no_user_no_history(
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)

    cmd = CalculateCommand(
        total_amount=2_000_000,
        down_payment=200_000,
        down_payment_percent=10.0,
        lease_term_months=36,
        buyout_amount=0.0,
        buyout_percent=None,
        vehicle_ids=[],
        selected_support={},
        user=None,
    )
    result = await handle_calculate(cmd, db_session)
    response = result.response

    assert response["calculation"]["monthlyPayment"] > 0
    assert response["calculation"]["rate"] > 0
    assert response["calculation_parameters"]["total_amount"] == 2_000_000
    assert response["calculation_parameters"]["down_payment"] == 200_000
    assert response["calculation_parameters"]["down_payment_percent"] == 10.0
    assert "support" not in response

    history = (await db_session.execute(CalculationHistory.__table__.select())).all()
    assert history == []


async def test_calculate_authenticated_writes_history(
    db_session: AsyncSession, client_user: User
) -> None:
    await _seed_rates(db_session)
    cmd = CalculateCommand(
        total_amount=1_500_000,
        down_payment=150_000,
        down_payment_percent=10.0,
        lease_term_months=24,
        buyout_amount=0.0,
        buyout_percent=None,
        vehicle_ids=[],
        selected_support={},
        user={"id": client_user.id, "role": "client", "company_id": None},
    )
    await handle_calculate(cmd, db_session)

    rows = (
        (await db_session.execute(CalculationHistory.__table__.select()))
        .mappings()
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["user_id"] == client_user.id
    assert row["lease_term_months"] == 24


async def test_calculate_falls_back_to_default_rates_when_table_empty(
    db_session: AsyncSession,
) -> None:
    cmd = CalculateCommand(
        total_amount=2_000_000,
        down_payment=200_000,
        down_payment_percent=10.0,
        lease_term_months=36,
        buyout_amount=0.0,
        buyout_percent=None,
        vehicle_ids=[],
        selected_support={},
        user=None,
    )
    result = await handle_calculate(cmd, db_session)
    # Default key_rate (21) + surcharge (4) = 25.
    assert result.response["calculation"]["rate"] == 25.0


async def test_calculate_uses_override_when_vehicle_base_price_is_zero(
    db_session: AsyncSession,
    client_user: User,
) -> None:
    await _seed_rates(db_session)
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("0.00"))

    result = await handle_calculate(
        CalculateCommand(
            total_amount=1_500_000,
            down_payment=150_000,
            down_payment_percent=10.0,
            lease_term_months=36,
            vehicle_ids=[vehicle.id],
            vehicle_price_overrides={vehicle.id: 1_500_000},
            selected_support={},
            user={"id": client_user.id, "role": "client", "company_id": None},
        ),
        db_session,
    )
    response = result.response

    assert response["calculation"]["monthlyPayment"] > 0
    assert response["calculation_parameters"]["total_amount"] == 1_500_000
    assert response["calculation_parameters"]["down_payment"] == 150_000
    assert response["support"]["base_total"] == 1_500_000
    assert (
        response["calculation_without_support"]["calculation_parameters"][
            "total_amount"
        ]
        == 1_500_000
    )


async def test_calculate_uses_override_when_vehicle_base_price_is_null(
    db_session: AsyncSession,
    client_user: User,
) -> None:
    await _seed_rates(db_session)
    vehicle = await _seed_vehicle(db_session, base_price=None)

    result = await handle_calculate(
        CalculateCommand(
            total_amount=1_700_000,
            down_payment=170_000,
            down_payment_percent=10.0,
            lease_term_months=36,
            vehicle_ids=[vehicle.id],
            vehicle_price_overrides={vehicle.id: 1_700_000},
            selected_support={},
            user={"id": client_user.id, "role": "client", "company_id": None},
        ),
        db_session,
    )

    assert result.response["calculation"]["monthlyPayment"] > 0
    assert result.response["calculation_parameters"]["total_amount"] == 1_700_000
    assert result.response["support"]["base_total"] == 1_700_000


async def test_calculate_support_program_uses_override_price_for_zero_price_vehicle(
    db_session: AsyncSession,
    client_user: User,
) -> None:
    await _seed_rates(db_session)
    await _seed_support_program(db_session)
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("0.00"))

    result = await handle_calculate(
        CalculateCommand(
            total_amount=1_500_000,
            down_payment=150_000,
            down_payment_percent=10.0,
            lease_term_months=36,
            vehicle_ids=[vehicle.id],
            vehicle_price_overrides={vehicle.id: 1_500_000},
            selected_support={},
            user={"id": client_user.id, "role": "client", "company_id": None},
        ),
        db_session,
    )
    response = result.response

    assert response["support"]["base_total"] == 1_500_000
    assert response["support"]["vehicle_discount_support"] == 150_000
    assert response["support"]["effective_total"] == 1_350_000
    assert response["support_per_vehicle"][0]["base_price"] == 1_500_000
    assert (
        response["support_per_vehicle"][0]["applied_supports"][0]["amount"] == 150_000
    )
    assert response["support_per_program"][0]["totals"]["amount"] == 150_000
    assert response["calculations_per_vehicle"][0]["calculation"]["monthlyPayment"] > 0


async def test_calculate_vehicle_quantity_scales_application_totals(
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    await _seed_support_program(db_session)
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("2000000.00"))

    result = await handle_calculate(
        CalculateCommand(
            total_amount=6_000_000,
            down_payment=600_000,
            down_payment_percent=10.0,
            lease_term_months=36,
            vehicle_ids=[vehicle.id],
            vehicle_quantities={vehicle.id: 3},
            selected_support={},
            user=None,
        ),
        db_session,
    )
    response = result.response

    assert response["support"]["base_total"] == 6_000_000
    assert response["support"]["vehicle_discount_support"] == 600_000
    assert response["support"]["effective_total"] == 5_400_000
    assert (
        response["calculation_without_support"]["calculation_parameters"][
            "total_amount"
        ]
        == 6_000_000
    )
    per_vehicle = response["calculations_per_vehicle"][0]
    assert per_vehicle["support_breakdown"]["vehicle_discount_support"] == 200_000
    assert per_vehicle["calculation_without_support"]["monthlyPayment"] > 0


async def test_calculate_keeps_non_vehicle_amount_in_mixed_total(
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    await _seed_support_program(db_session)
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("2000000.00"))

    result = await handle_calculate(
        CalculateCommand(
            # 2m vehicle + 15.3m special-equipment product.
            total_amount=17_300_000,
            down_payment=3_460_000,
            down_payment_percent=20.0,
            lease_term_months=36,
            vehicle_ids=[vehicle.id],
            selected_support={},
            user=None,
        ),
        db_session,
    )
    response = result.response

    assert response["support"]["base_total"] == 17_300_000
    # The support program is still calculated only from the vehicle subset.
    assert response["support"]["vehicle_discount_support"] == 200_000
    assert response["support"]["effective_total"] == 17_100_000
    assert response["calculation_parameters"]["total_amount"] == 17_100_000
    assert (
        response["calculation_without_support"]["calculation_parameters"][
            "total_amount"
        ]
        == 17_300_000
    )


async def test_calculate_uses_explicit_additional_amount_with_newer_vehicle_price(
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    await _seed_support_program(db_session)
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("2000000.00"))

    result = await handle_calculate(
        CalculateCommand(
            # Browser saw the vehicle at 1.8m; the server now has 2m.
            total_amount=17_100_000,
            additional_amount=15_300_000,
            down_payment=3_420_000,
            down_payment_percent=20.0,
            lease_term_months=36,
            vehicle_ids=[vehicle.id],
            selected_support={},
            user=None,
        ),
        db_session,
    )
    response = result.response

    # 2m authoritative vehicle + 15.3m explicit special-equipment subtotal.
    assert response["support"]["base_total"] == 17_300_000
    assert response["support"]["vehicle_discount_support"] == 200_000
    assert response["calculation_parameters"]["total_amount"] == 17_100_000
    assert (
        response["calculation_without_support"]["calculation_parameters"][
            "total_amount"
        ]
        == 17_300_000
    )


async def test_calculate_uses_server_discount_price_with_special_equipment(
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    vehicle = await _seed_vehicle(
        db_session,
        base_price=Decimal("2000000.00"),
        discount_price=Decimal("1800000.00"),
    )

    result = await handle_calculate(
        CalculateCommand(
            total_amount=17_100_000,
            additional_amount=15_300_000,
            down_payment=3_420_000,
            down_payment_percent=20.0,
            lease_term_months=36,
            vehicle_ids=[vehicle.id],
            selected_support={},
            user=None,
        ),
        db_session,
    )

    assert result.response["support"]["base_total"] == 17_100_000
    assert result.response["calculation_parameters"]["total_amount"] == 17_100_000


async def test_calculate_applies_explicit_support_to_server_discount_price(
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    await _seed_support_program(
        db_session,
        program_id=UUID("00000000-0000-0000-0000-000000000001"),
        support_params={"value_type": "amount", "value": 100_000},
    )
    selected_program = await _seed_support_program(
        db_session,
        program_id=UUID("00000000-0000-0000-0000-000000000002"),
        support_params={"value_type": "amount", "value": 500_000},
    )
    vehicle = await _seed_vehicle(
        db_session,
        base_price=Decimal("5000000.00"),
        discount_price=Decimal("4400000.00"),
    )

    result = await handle_calculate(
        CalculateCommand(
            total_amount=4_400_000,
            down_payment=440_000,
            down_payment_percent=10.0,
            lease_term_months=36,
            vehicle_ids=[vehicle.id],
            selected_support={str(vehicle.id): [str(selected_program.id)]},
            user=None,
        ),
        db_session,
    )
    response = result.response

    assert response["support"]["base_total"] == 4_400_000
    assert response["support"]["vehicle_discount_support"] == 500_000
    assert response["support"]["effective_total"] == 3_900_000
    assert response["support"]["contract_down_payment"] == 440_000
    assert response["support"]["effective_down_payment"] == 440_000
    assert response["calculation_parameters"]["total_amount"] == 3_900_000
    assert response["calculation_parameters"]["down_payment"] == 440_000
    assert response["calculation_parameters"]["down_payment_percent"] == 11.28
    per_vehicle = response["calculations_per_vehicle"][0]["support_breakdown"]
    assert per_vehicle["contract_down_payment"] == 440_000
    assert per_vehicle["client_down_payment"] == 440_000
    assert [
        program["support_program_id"]
        for program in response["support_per_program"]
    ] == [selected_program.id]
    assert response["support_per_program"][0]["totals"]["amount"] == 500_000


async def test_calculate_down_payment_support_only_reduces_client_advance(
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    selected_program = await _seed_support_program(
        db_session,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 100_000},
    )
    vehicle = await _seed_vehicle(
        db_session,
        base_price=Decimal("5000000.00"),
        discount_price=Decimal("4400000.00"),
    )

    result = await handle_calculate(
        CalculateCommand(
            total_amount=4_400_000,
            down_payment=440_000,
            down_payment_percent=10.0,
            lease_term_months=36,
            vehicle_ids=[vehicle.id],
            selected_support={str(vehicle.id): [str(selected_program.id)]},
            user=None,
        ),
        db_session,
    )
    response = result.response

    assert response["support"]["base_total"] == 4_400_000
    assert response["support"]["vehicle_discount_support"] == 0
    assert response["support"]["down_payment_support"] == 100_000
    assert response["support"]["effective_total"] == 4_400_000
    assert response["support"]["contract_down_payment"] == 440_000
    assert response["support"]["effective_down_payment"] == 340_000
    assert response["calculation_parameters"]["down_payment"] == 340_000
    per_vehicle = response["calculations_per_vehicle"][0]["support_breakdown"]
    assert per_vehicle["contract_down_payment"] == 440_000
    assert per_vehicle["client_down_payment"] == 340_000


async def test_calculate_sums_pairwise_compatible_vehicle_and_advance_supports(
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    vehicle_discount = await _seed_support_program(
        db_session,
        support_type="vehicle_discount_dealer_compensation",
        support_params={"value_type": "amount", "value": 100_000},
        is_compatible=True,
    )
    advance_support = await _seed_support_program(
        db_session,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 50_000},
        is_compatible=True,
    )
    await _link_compatible_supports(db_session, vehicle_discount, advance_support)
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("2000000.00"))

    result = await handle_calculate(
        CalculateCommand(
            total_amount=2_000_000,
            down_payment=400_000,
            down_payment_percent=20.0,
            lease_term_months=36,
            vehicle_ids=[vehicle.id],
            selected_support={
                str(vehicle.id): [
                    str(vehicle_discount.id),
                    str(advance_support.id),
                ]
            },
        ),
        db_session,
    )

    response = result.response
    assert response["support"]["vehicle_discount_support"] == 100_000
    assert response["support"]["down_payment_support"] == 50_000
    assert response["support"]["effective_total"] == 1_900_000
    assert response["support"]["contract_down_payment"] == 400_000
    assert response["support"]["effective_down_payment"] == 350_000
    assert {
        item["support_program_id"] for item in response["support_per_program"]
    } == {vehicle_discount.id, advance_support.id}
    details = response["support_program_details"]
    assert {item["id"] for item in details} == {
        vehicle_discount.id,
        advance_support.id,
    }
    assert all(item["vehicle_id"] == vehicle.id for item in details)
    assert all(item["is_compatible"] is True for item in details)


async def test_calculate_applies_vehicle_support_before_percent_advance_support(
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    vehicle_discount = await _seed_support_program(
        db_session,
        support_type="vehicle_discount_dealer_compensation",
        support_params={"value_type": "amount", "value": 100_000},
        is_compatible=True,
    )
    advance_support = await _seed_support_program(
        db_session,
        support_type="down_payment_compensation",
        support_params={"value_type": "percent", "value": 10},
        is_compatible=True,
    )
    await _link_compatible_supports(db_session, vehicle_discount, advance_support)
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("2000000.00"))

    async def calculate(selected_program_ids: list[UUID]) -> dict[str, Any]:
        result = await handle_calculate(
            CalculateCommand(
                total_amount=2_000_000,
                down_payment=400_000,
                down_payment_percent=20.0,
                lease_term_months=36,
                vehicle_ids=[vehicle.id],
                selected_support={
                    str(vehicle.id): [str(program_id) for program_id in selected_program_ids]
                },
            ),
            db_session,
        )
        return result.response

    forward = await calculate([vehicle_discount.id, advance_support.id])
    reverse = await calculate([advance_support.id, vehicle_discount.id])

    for response in (forward, reverse):
        support = response["support"]
        assert support["vehicle_discount_support"] == 100_000
        assert support["down_payment_support"] == 38_000
        assert support["effective_total"] == 1_900_000
        assert support["contract_down_payment"] == 400_000
        assert support["effective_down_payment"] == 362_000

        per_program = {
            item["support_program_id"]: item for item in response["support_per_program"]
        }
        advance = per_program[advance_support.id]
        assert advance["totals"]["amount"] == 38_000
        assert advance["per_vehicle"][0]["base_amount"] == 380_000

    assert reverse["support"] == forward["support"]
    assert reverse["calculation_parameters"] == forward["calculation_parameters"]


async def test_calculate_rejects_multi_support_without_complete_compatibility(
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    first = await _seed_support_program(
        db_session,
        support_params={"value_type": "amount", "value": 100_000},
        is_compatible=True,
    )
    second = await _seed_support_program(
        db_session,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 50_000},
        is_compatible=True,
    )
    vehicle = await _seed_vehicle(db_session)

    with pytest.raises(InvalidCalculationParamsError, match="несовместимы"):
        await handle_calculate(
            CalculateCommand(
                total_amount=2_000_000,
                down_payment=400_000,
                down_payment_percent=20.0,
                lease_term_months=36,
                vehicle_ids=[vehicle.id],
                selected_support={
                    str(vehicle.id): [str(first.id), str(second.id)]
                },
            ),
            db_session,
        )


async def test_calculate_sums_two_compatible_supports_of_same_type(
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    first = await _seed_support_program(
        db_session,
        support_params={"value_type": "amount", "value": 100_000},
        is_compatible=True,
    )
    second = await _seed_support_program(
        db_session,
        support_params={"value_type": "amount", "value": 200_000},
        is_compatible=True,
    )
    await _link_compatible_supports(db_session, first, second)
    vehicle = await _seed_vehicle(db_session)

    result = await handle_calculate(
        CalculateCommand(
            total_amount=2_000_000,
            down_payment=400_000,
            down_payment_percent=20.0,
            lease_term_months=36,
            vehicle_ids=[vehicle.id],
            selected_support={str(vehicle.id): [str(first.id), str(second.id)]},
        ),
        db_session,
    )

    assert result.response["support"]["vehicle_discount_support"] == 300_000
    assert result.response["support"]["effective_total"] == 1_700_000


async def test_calculate_rejects_three_programs_when_one_pair_is_missing(
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    programs = [
        await _seed_support_program(
            db_session,
            support_params={"value_type": "amount", "value": amount},
            is_compatible=True,
        )
        for amount in (50_000, 75_000, 100_000)
    ]
    await _link_compatible_supports(db_session, programs[0], programs[1])
    await _link_compatible_supports(db_session, programs[0], programs[2])
    vehicle = await _seed_vehicle(db_session)

    with pytest.raises(InvalidCalculationParamsError, match="несовместимы"):
        await handle_calculate(
            CalculateCommand(
                total_amount=2_000_000,
                down_payment=400_000,
                down_payment_percent=20.0,
                lease_term_months=36,
                vehicle_ids=[vehicle.id],
                selected_support={
                    str(vehicle.id): [str(program.id) for program in programs]
                },
            ),
            db_session,
        )


async def test_calculate_rejects_explicit_program_not_applicable_to_vehicle(
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    unavailable = await _seed_support_program(
        db_session,
        support_params={"value_type": "amount", "value": 100_000},
    )
    unavailable.vin = "OTHER-VIN"
    vehicle = await _seed_vehicle(db_session)
    await db_session.flush()

    with pytest.raises(InvalidCalculationParamsError, match="неприменимы"):
        await handle_calculate(
            CalculateCommand(
                total_amount=2_000_000,
                down_payment=400_000,
                down_payment_percent=20.0,
                lease_term_months=36,
                vehicle_ids=[vehicle.id],
                selected_support={str(vehicle.id): [str(unavailable.id)]},
            ),
            db_session,
        )


async def test_calculate_employee_override_on_paid_vehicle_with_special_equipment(
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    employee = await _seed_employee(db_session)
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("2000000.00"))

    result = await handle_calculate(
        CalculateCommand(
            total_amount=16_950_000,
            additional_amount=15_300_000,
            down_payment=3_390_000,
            down_payment_percent=20.0,
            lease_term_months=36,
            vehicle_ids=[vehicle.id],
            vehicle_price_overrides={vehicle.id: 1_650_000},
            selected_support={},
            user={
                "id": employee.id,
                "role": "carcraft_employee",
                "company_id": None,
            },
        ),
        db_session,
    )

    assert result.response["support"]["base_total"] == 16_950_000
    assert result.response["calculation_parameters"]["total_amount"] == 16_950_000


async def test_calculate_rejects_additional_amount_above_request_total(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(InvalidCalculationParamsError):
        await handle_calculate(
            CalculateCommand(
                total_amount=1_000_000,
                additional_amount=1_000_001,
                down_payment=100_000,
                down_payment_percent=10.0,
                lease_term_months=36,
            ),
            db_session,
        )


async def test_calculate_rejects_client_override_when_vehicle_has_effective_price(
    db_session: AsyncSession,
    client_user: User,
) -> None:
    await _seed_rates(db_session)
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("2000000.00"))

    with pytest.raises(CartCustomPriceDeniedError):
        await handle_calculate(
            CalculateCommand(
                total_amount=1_500_000,
                down_payment=150_000,
                down_payment_percent=10.0,
                lease_term_months=36,
                vehicle_ids=[vehicle.id],
                vehicle_price_overrides={vehicle.id: 1_500_000},
                selected_support={},
                user={
                    "id": client_user.id,
                    "role": "client",
                    "company_id": None,
                },
            ),
            db_session,
        )


async def test_calculate_rejects_normalized_total_above_limit(
    db_session: AsyncSession,
    client_user: User,
) -> None:
    from domain.errors import InvalidCalculationParamsError

    await _seed_rates(db_session)
    vehicle_a = await _seed_vehicle(db_session, base_price=Decimal("0.00"))
    vehicle_b = await _seed_vehicle(db_session, base_price=Decimal("0.00"))

    with pytest.raises(InvalidCalculationParamsError):
        await handle_calculate(
            CalculateCommand(
                total_amount=1_000_000,
                down_payment=100_000,
                down_payment_percent=10.0,
                lease_term_months=36,
                vehicle_ids=[vehicle_a.id, vehicle_b.id],
                vehicle_price_overrides={
                    vehicle_a.id: 6_000_000_000,
                    vehicle_b.id: 6_000_000_000,
                },
                selected_support={},
                user={
                    "id": client_user.id,
                    "role": "client",
                    "company_id": None,
                },
            ),
            db_session,
        )


async def test_calculate_rejects_invalid_term(
    db_session: AsyncSession,
) -> None:
    from domain.errors import InvalidCalculationParamsError

    cmd = CalculateCommand(
        total_amount=1_000_000,
        down_payment=100_000,
        down_payment_percent=10.0,
        lease_term_months=2,
        user=None,
    )
    with pytest.raises(InvalidCalculationParamsError):
        await handle_calculate(cmd, db_session)


async def test_calculate_rejects_advance_over_total(
    db_session: AsyncSession,
) -> None:
    from domain.errors import InvalidCalculationParamsError

    await _seed_rates(db_session)
    cmd = CalculateCommand(
        total_amount=1_000_000,
        down_payment=2_000_000,
        down_payment_percent=10.0,
        lease_term_months=24,
        user=None,
    )
    with pytest.raises(InvalidCalculationParamsError):
        await handle_calculate(cmd, db_session)


# ---------------------------------------------------------------------------
# handle_get_support_status
# ---------------------------------------------------------------------------


async def test_support_status_no_programs_returns_empty_eligibility(
    db_session: AsyncSession,
) -> None:
    vehicle = await _seed_vehicle(db_session)
    items = await handle_get_support_status(
        GetSupportStatusQuery(vehicle_ids=[vehicle.id]), db_session
    )
    assert items == [
        {
            "vehicle_id": vehicle.id,
            "has_support": False,
            "support_type": None,
            "support_params": None,
            "eligible_program_ids": [],
            "applicable_support_programs": [],
        }
    ]


async def test_support_status_returns_uuid_vehicle_and_program_details(
    db_session: AsyncSession,
) -> None:
    vehicle = await _seed_vehicle(db_session)
    program = await _seed_support_program(
        db_session,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 100000},
    )

    items = await handle_get_support_status(
        GetSupportStatusQuery(vehicle_ids=[vehicle.id]), db_session
    )

    assert [
        {key: value for key, value in item.items() if key != "applicable_support_programs"}
        for item in items
    ] == [
        {
            "vehicle_id": vehicle.id,
            "has_support": True,
            "support_type": "down_payment_compensation",
            "support_params": {"value_type": "amount", "value": 100000},
            "eligible_program_ids": [program.id],
        }
    ]
    assert items[0]["applicable_support_programs"][0]["id"] == program.id
    assert items[0]["applicable_support_programs"][0]["support_amount"] == 100_000


async def test_support_status_includes_program_with_required_distributor(
    db_session: AsyncSession,
) -> None:
    vehicle = await _seed_vehicle(db_session)
    distributor = await _seed_distributor(db_session)
    assert distributor.company_id is not None
    program = await _seed_support_program(
        db_session,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 100000},
        distributor_id=distributor.company_id,
    )

    items = await handle_get_support_status(
        GetSupportStatusQuery(vehicle_ids=[vehicle.id]), db_session
    )

    assert [
        {key: value for key, value in item.items() if key != "applicable_support_programs"}
        for item in items
    ] == [
        {
            "vehicle_id": vehicle.id,
            "has_support": True,
            "support_type": "down_payment_compensation",
            "support_params": {"value_type": "amount", "value": 100000},
            "eligible_program_ids": [program.id],
        }
    ]
    assert items[0]["applicable_support_programs"][0]["id"] == program.id


async def test_support_status_with_group_matches_dealer_from_warehouse(
    db_session: AsyncSession,
) -> None:
    vehicle = await _seed_vehicle(db_session)
    distributor = await _seed_distributor(db_session)
    assert distributor.company_id is not None
    dealer = await _seed_dealer_company(
        db_session,
        distributor_company_id=distributor.company_id,
        suffix="1",
    )
    await _bind_vehicle_to_dealer_warehouse(
        db_session,
        vehicle=vehicle,
        dealer_company_id=dealer.id,
        suffix="1",
    )
    group = await _seed_dealer_group(
        db_session,
        distributor_company_id=distributor.company_id,
        dealer_company_id=dealer.id,
    )
    program = await _seed_support_program(
        db_session,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 100000},
        distributor_id=distributor.company_id,
    )
    db_session.add(
        SupportProgramDealerGroup(
            support_program_id=program.id,
            dealer_group_id=group.id,
        )
    )
    await db_session.execute(
        delete(DistributorDealerLink).where(
            DistributorDealerLink.distributor_company_id == distributor.company_id,
            DistributorDealerLink.dealer_company_id == dealer.id,
        )
    )
    await db_session.flush()

    items = await handle_get_support_status(
        GetSupportStatusQuery(vehicle_ids=[vehicle.id]), db_session
    )

    assert items[0]["has_support"] is True
    assert items[0]["eligible_program_ids"] == [program.id]


async def test_support_status_with_group_excludes_other_dealer_warehouse(
    db_session: AsyncSession,
) -> None:
    vehicle = await _seed_vehicle(db_session)
    distributor = await _seed_distributor(db_session)
    assert distributor.company_id is not None
    dealer_in_group = await _seed_dealer_company(
        db_session,
        distributor_company_id=distributor.company_id,
        suffix="1",
    )
    dealer_outside_group = await _seed_dealer_company(
        db_session,
        distributor_company_id=distributor.company_id,
        suffix="2",
    )
    await _bind_vehicle_to_dealer_warehouse(
        db_session,
        vehicle=vehicle,
        dealer_company_id=dealer_outside_group.id,
        suffix="2",
    )
    group = await _seed_dealer_group(
        db_session,
        distributor_company_id=distributor.company_id,
        dealer_company_id=dealer_in_group.id,
    )
    program = await _seed_support_program(
        db_session,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 100000},
        distributor_id=distributor.company_id,
    )
    db_session.add(
        SupportProgramDealerGroup(
            support_program_id=program.id,
            dealer_group_id=group.id,
        )
    )
    await db_session.flush()

    items = await handle_get_support_status(
        GetSupportStatusQuery(vehicle_ids=[vehicle.id]), db_session
    )

    assert items == [
        {
            "vehicle_id": vehicle.id,
            "has_support": False,
            "support_type": None,
            "support_params": None,
            "eligible_program_ids": [],
            "applicable_support_programs": [],
        }
    ]
