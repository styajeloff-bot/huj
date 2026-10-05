"""A supplier quantity edit must rebuild every persisted financing snapshot."""
import json
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.application_vehicles.recalculate_quantity import (
    _snapshot_payload_fields,
    recalculate_quantity,
)
from domain.entities.leasing_calculator import LeasingCalculator, LeasingRates
from infrastructure.models.applications import LeasingApplicationVehicleCalculation
from infrastructure.models.users import User
from infrastructure.repositories import application_repository
from tests.test_vehicle_fulfillment import seed


async def test_quantity_rebuilds_individual_snapshot_with_options_and_preserves_rate(db_session: AsyncSession, employee_user: User) -> None:
    app, line, _cars, _cmd = await seed(db_session, employee_user)
    rates = LeasingRates(key_rate=12.3456, surcharge=0, vat_rate=20, profit_tax_rate=20)
    for key, value in {
        "lease_term_months": 36, "down_payment_percent": Decimal("20"),
        "rate": Decimal("12.3456"), "total_cost": Decimal("2400000"),
        "vat_refund": Decimal("400000"), "profit_tax_savings": Decimal("400000"),
    }.items():
        setattr(app, key, value)
    for key, value in {
        "quantity": 2, "requested_quantity": 2, "unit_price": Decimal("1200000"),
        "final_price": Decimal("1000000"), "equipments": [{"price": 10000}],
        "services": [{"price": 5000}], "total_price": Decimal("2030000"),
    }.items():
        setattr(line, key, value)
    previous = LeasingCalculator.compute_leasing(2030000, 406000, 36, rates, 12345)
    snapshot = LeasingApplicationVehicleCalculation(
        leasing_application_id=app.id, vehicle_id=None, quantity=2,
        unit_price=1000000, total_amount=2030000, down_payment=406000,
        down_payment_percent=20, lease_term_months=36, rate=Decimal("12.3456"),
        buyout_amount=12345, monthly_payment=previous.monthly_payment,
        total_cost=previous.total_cost, total_interest=previous.total_interest,
        vat_refund=previous.vat_refund, profit_tax_savings=previous.profit_tax_savings,
        total_savings=previous.total_savings,
    )
    db_session.add(snapshot)
    await db_session.flush()
    snapshot_id = snapshot.id
    line.quantity = 3
    await db_session.flush()
    await recalculate_quantity(db_session, application_vehicle_id=line.id, previous_quantity=2)
    await db_session.refresh(snapshot)
    await db_session.refresh(app)
    expected = LeasingCalculator.compute_leasing(3045000, 609000, 36, rates, 12345)
    assert snapshot.id == snapshot_id
    assert snapshot.quantity == 3
    assert snapshot.unit_price == Decimal("1000000")
    assert snapshot.total_amount == Decimal("3045000")
    assert snapshot.down_payment == Decimal("609000")
    stored = await application_repository.get_calculation(db_session, app.id)
    assert stored is not None
    assert snapshot.rate == stored["rate"] == Decimal("12.3456")
    assert app.rate == Decimal("12.35")  # Existing application column is Numeric(5, 2).
    assert snapshot.buyout_amount == Decimal("12345")
    for field in ("monthly_payment", "total_cost", "total_interest", "vat_refund", "profit_tax_savings", "total_savings"):
        # Historic storage rounds tax totals; recovering those rates can differ by a rouble.
        assert abs(getattr(snapshot, field) - Decimal(str(getattr(expected, field)))) <= 1
        assert getattr(snapshot, field) != Decimal(str(getattr(previous, field)))


def test_calculator_uuid_snapshots_are_serializable_without_custom_engine_encoder() -> None:
    vehicle_id, support_id = uuid4(), uuid4()
    response = {
        "calculations_per_vehicle": [{"vehicle_id": vehicle_id, "calculation": {"monthlyPayment": 12345}}],
        "support_per_vehicle": [{"vehicle_id": vehicle_id, "applied_supports": [{"id": support_id}]}],
        "support_per_program": [{"support_program_id": support_id, "amount": Decimal("120.50")}],
        "support_program_details": [{"id": support_id}],
    }
    payload = _snapshot_payload_fields(response, {"selected_support": {vehicle_id: [support_id]}})
    persisted = json.loads(json.dumps(payload))
    assert persisted["calculations_per_vehicle"][0]["vehicle_id"] == str(vehicle_id)
    assert persisted["selected_support"] == {str(vehicle_id): [str(support_id)]}
    assert persisted["support_per_vehicle"][0]["applied_supports"][0]["id"] == str(support_id)
    assert persisted["support_per_program"][0]["amount"] == "120.50"
    assert persisted["calculations_per_vehicle"][0]["calculation"]["monthlyPayment"] == 12345
