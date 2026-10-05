"""Integration tests for /api/v1/calculator/* (full HTTP round-trip)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import CalculationHistory
from infrastructure.models.companies import Company, Distributor
from infrastructure.models.misc import LeasingRate
from infrastructure.models.support import SupportProgram
from infrastructure.models.users import User
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Seed helpers
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


async def _seed_distributor(db: AsyncSession) -> Distributor:
    company = Company(
        name="Calculator Support Distributor",
        inn="7700000001",
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


async def _seed_support_program(
    db: AsyncSession, *, distributor_id: UUID | None = None
) -> SupportProgram:
    program = SupportProgram(
        name="Router support status program",
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 100000},
        is_active=True,
        show_to_client=True,
        distributor_id=distributor_id,
    )
    db.add(program)
    await db.flush()
    await db.refresh(program)
    return program


# ---------------------------------------------------------------------------
# POST /calculate
# ---------------------------------------------------------------------------


async def test_calculate_anonymous_golden_path(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_rates(db_session)
    response = await client.post(
        "/api/v1/calculator/calculate",
        json={
            "total_amount": 2_000_000,
            "down_payment": 200_000,
            "down_payment_percent": 10.0,
            "lease_term_months": 36,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["calculation"]["monthlyPayment"] > 0
    assert body["calculation"]["rate"] > 0
    assert body["calculation_parameters"]["lease_term_months"] == 36
    assert "support" not in body


async def test_calculate_authenticated_persists_history(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    response = await client.post(
        "/api/v1/calculator/calculate",
        headers=_auth(client_token),
        json={
            "total_amount": 1_500_000,
            "down_payment": 150_000,
            "down_payment_percent": 10.0,
            "lease_term_months": 24,
        },
    )
    assert response.status_code == 200

    rows = (
        (await db_session.execute(CalculationHistory.__table__.select()))
        .mappings()
        .all()
    )
    saved = [r for r in rows if r["user_id"] == client_user.id]
    assert len(saved) == 1


async def test_calculate_invalid_term_returns_422(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/calculator/calculate",
        json={
            "total_amount": 1_000_000,
            "down_payment": 100_000,
            "down_payment_percent": 10.0,
            "lease_term_months": 5,
        },
    )
    assert response.status_code == 422


async def test_calculate_advance_over_total_returns_400(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_rates(db_session)
    response = await client.post(
        "/api/v1/calculator/calculate",
        json={
            "total_amount": 1_000_000,
            "down_payment": 2_000_000,
            "down_payment_percent": 10.0,
            "lease_term_months": 24,
        },
    )
    # Domain raises InvalidCalculationParamsError → 400
    assert response.status_code == 400


async def test_calculate_uses_price_override_for_zero_price_vehicle(
    client: AsyncClient,
    db_session: AsyncSession,
    client_token: str,
) -> None:
    await _seed_rates(db_session)
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("0.00"))

    response = await client.post(
        "/api/v1/calculator/calculate",
        headers=_auth(client_token),
        json={
            "total_amount": 1_500_000,
            "down_payment": 150_000,
            "down_payment_percent": 10.0,
            "lease_term_months": 36,
            "vehicle_ids": [str(vehicle.id)],
            "vehicle_price_overrides": {str(vehicle.id): 1_500_000},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["calculation"]["monthlyPayment"] > 0
    assert body["calculation_parameters"]["total_amount"] == 1_500_000
    assert body["support"]["base_total"] == 1_500_000


async def test_calculate_rejects_client_price_override_for_regular_vehicle(
    client: AsyncClient,
    db_session: AsyncSession,
    client_token: str,
) -> None:
    await _seed_rates(db_session)
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("2000000.00"))

    response = await client.post(
        "/api/v1/calculator/calculate",
        headers=_auth(client_token),
        json={
            "total_amount": 1_500_000,
            "down_payment": 150_000,
            "down_payment_percent": 10.0,
            "lease_term_months": 36,
            "vehicle_ids": [str(vehicle.id)],
            "vehicle_price_overrides": {str(vehicle.id): 1_500_000},
        },
    )
    assert response.status_code == 403, response.text
    assert "цен" in response.json()["detail"].lower()


async def test_calculate_uses_vehicle_quantities_for_application_total(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("2000000.00"))

    response = await client.post(
        "/api/v1/calculator/calculate",
        json={
            "total_amount": 6_000_000,
            "down_payment": 600_000,
            "down_payment_percent": 10.0,
            "lease_term_months": 36,
            "vehicle_ids": [str(vehicle.id)],
            "vehicle_quantities": {str(vehicle.id): 3},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["calculation_parameters"]["total_amount"] == 6_000_000
    assert body["support"]["base_total"] == 6_000_000
    assert (
        body["calculation_without_support"]["calculation_parameters"]["total_amount"]
        == 6_000_000
    )


async def test_calculate_combines_authoritative_vehicle_and_explicit_additional_amount(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("2000000.00"))

    response = await client.post(
        "/api/v1/calculator/calculate",
        json={
            "total_amount": 17_100_000,
            "additional_amount": 15_300_000,
            "down_payment": 3_420_000,
            "down_payment_percent": 20.0,
            "lease_term_months": 36,
            "vehicle_ids": [str(vehicle.id)],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["support"]["base_total"] == 17_300_000
    assert body["calculation_parameters"]["total_amount"] == 17_300_000


async def test_calculate_uses_server_discount_with_special_equipment_amount(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    vehicle = await _seed_vehicle(
        db_session,
        base_price=Decimal("2000000.00"),
        discount_price=Decimal("1800000.00"),
    )

    response = await client.post(
        "/api/v1/calculator/calculate",
        json={
            "total_amount": 17_100_000,
            "additional_amount": 15_300_000,
            "down_payment": 3_420_000,
            "down_payment_percent": 20.0,
            "lease_term_months": 36,
            "vehicle_ids": [str(vehicle.id)],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["support"]["base_total"] == 17_100_000
    assert body["calculation_parameters"]["total_amount"] == 17_100_000


async def test_calculate_employee_override_on_paid_vehicle_with_special_amount(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    await _seed_rates(db_session)
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("2000000.00"))

    response = await client.post(
        "/api/v1/calculator/calculate",
        headers=_auth(employee_token),
        json={
            "total_amount": 16_950_000,
            "additional_amount": 15_300_000,
            "down_payment": 3_390_000,
            "down_payment_percent": 20.0,
            "lease_term_months": 36,
            "vehicle_ids": [str(vehicle.id)],
            "vehicle_price_overrides": {str(vehicle.id): 1_650_000},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["support"]["base_total"] == 16_950_000
    assert body["calculation_parameters"]["total_amount"] == 16_950_000


async def test_calculate_rejects_additional_amount_above_total(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/calculator/calculate",
        json={
            "total_amount": 1_000_000,
            "additional_amount": 1_000_001,
            "down_payment": 100_000,
            "down_payment_percent": 10.0,
            "lease_term_months": 36,
        },
    )

    assert response.status_code == 422


async def test_calculate_rejects_price_override_above_limit(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _seed_rates(db_session)
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("0.00"))

    response = await client.post(
        "/api/v1/calculator/calculate",
        json={
            "total_amount": 1_500_000,
            "down_payment": 150_000,
            "down_payment_percent": 10.0,
            "lease_term_months": 36,
            "vehicle_ids": [str(vehicle.id)],
            "vehicle_price_overrides": {str(vehicle.id): 10_000_000_001},
        },
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /support-status
# ---------------------------------------------------------------------------


async def test_support_status_returns_items(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    vehicle = await _seed_vehicle(db_session)
    response = await client.post(
        "/api/v1/calculator/support-status",
        json={"vehicle_ids": [vehicle.id]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "items": [
            {
                "vehicle_id": str(vehicle.id),
                "has_support": False,
                "support_type": None,
                    "support_params": None,
                    "eligible_program_ids": [],
                    "applicable_support_programs": [],
            }
        ]
    }


async def test_support_status_serializes_uuid_ids_and_details(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    vehicle = await _seed_vehicle(db_session)
    program = await _seed_support_program(db_session)

    response = await client.post(
        "/api/v1/calculator/support-status",
        json={"vehicle_ids": [str(vehicle.id)]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "items": [
            {
                "vehicle_id": str(vehicle.id),
                "has_support": True,
                "support_type": "down_payment_compensation",
                "support_params": {"value_type": "amount", "value": 100000},
                "eligible_program_ids": [str(program.id)],
                "applicable_support_programs": [
                    {
                        "vehicle_id": str(vehicle.id),
                        "id": str(program.id),
                        "name": "Router support status program",
                        "support_type": "down_payment_compensation",
                        "support_params": {
                            "value_type": "amount",
                            "value": 100000,
                        },
                        "comment": None,
                        "starts_at": None,
                        "ends_at": None,
                        "support_amount": 100000,
                        "base_price": 2000000,
                        "display_price": 2000000,
                        "is_compatible": False,
                        "compatible_support_ids": [],
                        "bill_of_lading": None,
                    }
                ],
            }
        ]
    }


async def test_support_status_includes_program_with_required_distributor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    vehicle = await _seed_vehicle(db_session)
    distributor = await _seed_distributor(db_session)
    assert distributor.company_id is not None
    program = await _seed_support_program(
        db_session, distributor_id=distributor.company_id
    )

    response = await client.post(
        "/api/v1/calculator/support-status",
        json={"vehicle_ids": [str(vehicle.id)]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"][0]["has_support"] is True
    assert body["items"][0]["eligible_program_ids"] == [str(program.id)]


async def test_support_status_validates_min_length(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/calculator/support-status",
        json={"vehicle_ids": []},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Phase 15 H3 — /calculator/leasing-companies and /calculator/history
# deleted. Companies moved to /leasing/companies; history is surfaced via
# the /client/calculations (/client/saved-calculations alias before H3).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# POST /send-calculation-email
# ---------------------------------------------------------------------------


async def test_send_email_invokes_email_sender(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_send = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "application.commands.calculator.send_calculation_email.send_email",
        fake_send,
    )

    response = await client.post(
        "/api/v1/calculator/send-calculation-email",
        json={
            "to": "user@example.com",
            "subject": "Расчёт лизинга",
            "text": "Привет!",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"success": True}
    fake_send.assert_awaited_once()


async def test_send_email_validation_error(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/calculator/send-calculation-email",
        json={"to": "not-an-email", "subject": "subj"},
    )
    assert response.status_code == 422


async def test_send_email_smtp_failure_returns_502(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("smtp down")

    monkeypatch.setattr(
        "application.commands.calculator.send_calculation_email.send_email",
        _boom,
    )

    response = await client.post(
        "/api/v1/calculator/send-calculation-email",
        json={
            "to": "user@example.com",
            "subject": "subj",
            "text": "hi",
        },
    )
    assert response.status_code == 502
