from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.misc import LeasingRate

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    csrf = "test-csrf-token"
    return {
        "Cookie": f"accessToken={token}; csrfToken={csrf}",
        "X-CSRF-Token": csrf,
    }


async def test_admin_calculator_rates_crud_and_calculator_use_current_rate(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    historical = await client.post(
        "/api/v1/admin/calculator-rates",
        headers=_auth(employee_token),
        json={
            "date_from": "2024-01-01",
            "date_to": "2025-01-01",
            "key_rate": 10,
            "surcharge": 2,
            "vat_rate": 18,
            "profit_tax_rate": 20,
        },
    )
    assert historical.status_code == 201, historical.text

    current = await client.post(
        "/api/v1/admin/calculator-rates",
        headers=_auth(employee_token),
        json={
            "date_from": "2025-01-01",
            "date_to": None,
            "key_rate": 21,
            "surcharge": 4,
            "vat_rate": 22,
            "profit_tax_rate": 25,
        },
    )
    assert current.status_code == 201, current.text
    current_body = current.json()["calculator_rate"]
    assert current_body["is_current"] is True

    listed = await client.get(
        "/api/v1/admin/calculator-rates",
        headers=_auth(employee_token),
    )
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert [item["date_to"] for item in items] == [None, "2025-01-01"]

    patched = await client.patch(
        f"/api/v1/admin/calculator-rates/{current_body['id']}",
        headers=_auth(employee_token),
        json={"vat_rate": 24},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["calculator_rate"]["vat_rate"] == 24

    calculation = await client.post(
        "/api/v1/calculator/calculate",
        json={
            "total_amount": 1_000_000,
            "down_payment": 100_000,
            "down_payment_percent": 10,
            "lease_term_months": 12,
        },
    )
    assert calculation.status_code == 200, calculation.text
    body = calculation.json()
    assert body["calculation"]["rate"] == 25.0
    assert body["calculation"]["vatRefund"] > 0

    rows = (await db_session.execute(select(LeasingRate))).scalars().all()
    assert len(rows) == 2


async def test_admin_calculator_rates_rejects_overlapping_period(
    client: AsyncClient,
    employee_token: str,
) -> None:
    first = await client.post(
        "/api/v1/admin/calculator-rates",
        headers=_auth(employee_token),
        json={
            "date_from": "2024-01-01",
            "date_to": "2025-01-01",
            "key_rate": 10,
            "surcharge": 2,
            "vat_rate": 18,
            "profit_tax_rate": 20,
        },
    )
    assert first.status_code == 201, first.text

    overlap = await client.post(
        "/api/v1/admin/calculator-rates",
        headers=_auth(employee_token),
        json={
            "date_from": "2024-06-01",
            "date_to": "2025-06-01",
            "key_rate": 11,
            "surcharge": 2,
            "vat_rate": 20,
            "profit_tax_rate": 20,
        },
    )

    assert overlap.status_code == 422
    assert "Период пересекается" in overlap.text


async def test_admin_calculator_rates_patch_rejects_second_current_rate(
    client: AsyncClient,
    employee_token: str,
) -> None:
    first = await client.post(
        "/api/v1/admin/calculator-rates",
        headers=_auth(employee_token),
        json={
            "date_from": "2024-01-01",
            "date_to": "2025-01-01",
            "key_rate": 10,
            "surcharge": 2,
            "vat_rate": 18,
            "profit_tax_rate": 20,
        },
    )
    assert first.status_code == 201, first.text

    current = await client.post(
        "/api/v1/admin/calculator-rates",
        headers=_auth(employee_token),
        json={
            "date_from": "2025-01-01",
            "date_to": None,
            "key_rate": 21,
            "surcharge": 4,
            "vat_rate": 20,
            "profit_tax_rate": 25,
        },
    )
    assert current.status_code == 201, current.text

    patched = await client.patch(
        f"/api/v1/admin/calculator-rates/{first.json()['calculator_rate']['id']}",
        headers=_auth(employee_token),
        json={"date_to": None},
    )

    assert patched.status_code == 422
    assert "текущая ставка" in patched.text


async def test_admin_calculator_rates_forbids_client_access(
    client: AsyncClient,
    client_token: str,
) -> None:
    response = await client.get(
        "/api/v1/admin/calculator-rates",
        headers=_auth(client_token),
    )

    assert response.status_code == 403
