"""Persisted monetization adjustments, exercised through isolated API fixtures."""

from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.monetization import adjustments, amounts
from tests import test_monetization_api as api_fixtures
from tests.test_monetization_api import DEALS, _auth, _captured_deal

# Reuse the savepoint-isolated API fixtures rather than a second seed/database.
api_seed = api_fixtures.api_seed
db_session = api_fixtures.db_session


async def test_half_up_amount_and_audit_survive_reload_and_rounded_noop(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    api_seed: dict[str, Any],
) -> None:
    deal = await _captured_deal(client, db_session, employee_token, api_seed)
    confirm_url = f"{DEALS}/{deal['id']}/confirm"
    adjust_url = f"/api/v1/admin/monetization/deals/{deal['id']}/adjust-conditions"
    amount_id = deal["expenses"][0]["id"]
    confirmed = await client.post(
        confirm_url,
        json={"revision": 1},
        headers=_auth(api_seed["dealer"]["token"]),
    )
    assert confirmed.status_code == 200, confirmed.text
    adjusted = await client.post(
        adjust_url,
        json={
            "revision": 1,
            "items": [
                {
                    "deal_participant_amount_id": amount_id,
                    "new_value": "1000.50",
                }
            ],
        },
        headers=_auth(employee_token),
    )
    assert adjusted.status_code == 200, adjusted.text
    assert adjusted.json()["confirmations_reset"] is True
    db_session.expire_all()
    reloaded = await client.get(f"{DEALS}/{deal['id']}", headers=_auth(employee_token))
    assert reloaded.status_code == 200, reloaded.text
    assert reloaded.json()["revision"] == 2
    assert Decimal(reloaded.json()["expenses"][0]["amount"]) == Decimal("1001")
    assert reloaded.json()["confirmations"]["dealer"]["confirmed_at"] is None
    stored_amount = await db_session.scalar(
        sa.select(amounts.c.amount).where(
            amounts.c.id == UUID(amount_id),
        )
    )
    assert stored_amount == Decimal("1001")
    audit = (
        (
            await db_session.execute(
                sa.select(adjustments).where(
                    adjustments.c.deal_id == UUID(deal["id"]),
                )
            )
        )
        .mappings()
        .one()
    )
    assert audit["old_value"] == Decimal("1000")
    assert audit["new_value"] == Decimal("1001")
    assert audit["revision"] == 2
    assert audit["amount_id"] == UUID(amount_id)

    confirmed = await client.post(
        confirm_url,
        json={"revision": 2},
        headers=_auth(api_seed["dealer"]["token"]),
    )
    assert confirmed.status_code == 200, confirmed.text
    unchanged = await client.post(
        adjust_url,
        json={
            "revision": 2,
            "items": [
                {
                    "deal_participant_amount_id": amount_id,
                    "new_value": "1001.49",
                }
            ],
        },
        headers=_auth(employee_token),
    )
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["revision"] == 2
    assert unchanged.json()["confirmations_reset"] is False
    assert unchanged.json()["confirmations"]["dealer"]["confirmed_at"] is not None
    assert (
        await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(adjustments)
            .where(
                adjustments.c.deal_id == UUID(deal["id"]),
            )
        )
        == 1
    )
