"""Integration tests for /api/v1/distributor/analytics.

The ClickHouse read-only client is replaced by an in-memory fake that records
the queries it receives, so we can assert (a) the endpoints return 200 with the
expected widget IDs, (b) every query is scoped to the distributor's *linked*
dealers, (c) carcraft_employee is unscoped, and (d) a ClickHouse failure
surfaces as 503 (which is what makes the frontend show its error state).
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure import clickhouse_readonly as ch_ro
from infrastructure.auth import generate_tokens
from infrastructure.models.companies import Company, DistributorDealerLink
from infrastructure.models.users import User

pytestmark = pytest.mark.asyncio


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fake ClickHouse client
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, columns: list[str], rows: list[tuple]) -> None:
        self.column_names = columns
        self.result_rows = rows


class _FakeClickHouse:
    """Records queries; returns empty result sets."""

    def __init__(self) -> None:
        self.queries: list[tuple[str, dict[str, Any]]] = []

    def query(self, query: str, parameters: dict[str, Any] | None = None) -> _FakeResult:
        self.queries.append((query, parameters or {}))
        return _FakeResult([], [])


class _WarehouseRowsClickHouse(_FakeClickHouse):
    def query(self, query: str, parameters: dict[str, Any] | None = None) -> _FakeResult:
        self.queries.append((query, parameters or {}))
        if "GROUP BY dealer_name" in query:
            return _FakeResult(
                ["dealer_name", "cnt", "total_value"],
                [("Dealer One", 7, 1234567.0)],
            )
        if "GROUP BY city" in query:
            return _FakeResult(
                ["city", "cnt", "total_value"],
                [("Москва", 5, 765432.0)],
            )
        if (
            "uniqExact(v.dealer_id) AS total" in query
            or "uniqExact(coalesce(c.city, '—')) AS total" in query
        ):
            return _FakeResult(["total"], [(1,)])
        return _FakeResult([], [])


class _DashboardRowsClickHouse(_FakeClickHouse):
    def query(self, query: str, parameters: dict[str, Any] | None = None) -> _FakeResult:
        self.queries.append((query, parameters or {}))
        result = _FakeResult([], [])
        if "count() AS total FROM dm_distributor_exchange" in query:
            result = _FakeResult(["total"], [(1,)])
        elif "FROM dm_distributor_exchange AS er" in query and "LIMIT" in query:
            result = _FakeResult(
                [
                    "status",
                    "mark",
                    "model",
                    "quantity",
                    "discount_type",
                    "discount_value",
                    "expiration_date",
                    "created_at",
                    "bids_count",
                    "accepted_bids",
                    "average_price",
                ],
                [
                    (
                        "active",
                        "FAW",
                        "FAW_BESTUNE_B70_NEW",
                        2,
                        "percent",
                        7,
                        "2024-12-31",
                        "2024-12-01",
                        4,
                        1,
                        5000000,
                    )
                ],
            )
        elif "uniqExact(application_id) AS total" in query:
            result = _FakeResult(["total"], [(1,)])
        elif "FROM dm_distributor_applications AS la" in query and "LIMIT" in query:
            result = _FakeResult(
                [
                    "display_number",
                    "status",
                    "status_bucket",
                    "total_amount",
                    "down_payment",
                    "total_cost",
                    "rate",
                    "lease_term_months",
                    "down_payment_percent",
                    "monthly_payment",
                    "mark",
                    "model",
                    "leasing_company",
                    "created_at",
                ],
                [
                    (
                        "IMP-1",
                        "approved_final",
                        "active",
                        2000000,
                        400000,
                        2300000,
                        0.15,
                        36,
                        0.2,
                        50000,
                        "FAW",
                        "FAW_BESTUNE_B70_NEW",
                        "ЛК",
                        "2024-12-01",
                    )
                ],
            )
        elif "count() AS total" in query:
            result = _FakeResult(["total"], [(471,)])
        elif "GROUP BY month, dealer_name" in query:
            result = _FakeResult(
                [
                    "month",
                    "dealer_name",
                    "new_applications",
                    "new_clients",
                    "approved_applications",
                    "approved_clients",
                    "financed_applications",
                    "financed_clients",
                    "avg_vehicle_cost",
                    "avg_contract_amount",
                    "avg_down_payment_percent",
                    "avg_down_payment_amount",
                    "avg_lease_term",
                    "avg_rate",
                ],
                [("2024-12-01", "Урал Авто", 10, 8, 6, 5, 2, 2, 2500000, 3000000, 0.2, 600000, 36, 0.15)],
            )
        return result


class _BoomClickHouse:
    def query(self, query: str, parameters: dict[str, Any] | None = None) -> _FakeResult:
        raise RuntimeError("clickhouse down")


@pytest.fixture
def fake_ch() -> Iterator[_FakeClickHouse]:
    fake = _FakeClickHouse()
    ch_ro.set_clickhouse_readonly_client(cast("Any", fake))
    try:
        yield fake
    finally:
        ch_ro.set_clickhouse_readonly_client(None)


# ---------------------------------------------------------------------------
# Seed fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def linked_distributor(db_session: AsyncSession) -> dict[str, Any]:
    dist = Company(name="Dist Co", company_type="distributor", inn="7700000001")
    dealer = Company(name="Dealer Co", company_type="dealer", inn="7700000002")
    db_session.add_all([dist, dealer])
    await db_session.flush()
    db_session.add(
        DistributorDealerLink(
            distributor_company_id=dist.id, dealer_company_id=dealer.id
        )
    )
    user = User(
        phone="+76660000101",
        email="dist-analytics@test.local",
        name="Dist Analytics",
        role="distributor",
        company_id=dist.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    token, _ = generate_tokens(user.id, "distributor", user.company_id)
    return {"dist": dist, "dealer": dealer, "user": user, "token": token}


@pytest_asyncio.fixture
async def unlinked_distributor(db_session: AsyncSession) -> dict[str, Any]:
    dist = Company(name="Lonely Dist", company_type="distributor", inn="7700000003")
    db_session.add(dist)
    await db_session.flush()
    user = User(
        phone="+76660000102",
        email="lonely-dist@test.local",
        name="Lonely Dist",
        role="distributor",
        company_id=dist.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    token, _ = generate_tokens(user.id, "distributor", user.company_id)
    return {"dist": dist, "user": user, "token": token}


@pytest_asyncio.fixture
async def carcraft_employee(db_session: AsyncSession) -> dict[str, Any]:
    user = User(
        phone="+76660000103",
        email="employee-analytics@test.local",
        name="Employee",
        role="carcraft_employee",
        company_id=None,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    token, _ = generate_tokens(user.id, "carcraft_employee", None)
    return {"user": user, "token": token}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


_TABS = ["warehouse", "applications", "exchange", "financials", "sales-dc", "sales-dc-regions"]


@pytest.mark.parametrize("tab", _TABS)
async def test_tab_returns_200_and_is_scoped_to_linked_dealers(
    client: AsyncClient, fake_ch: _FakeClickHouse, linked_distributor: dict[str, Any], tab: str
) -> None:
    resp = await client.get(
        f"/api/v1/distributor/analytics/{tab}", headers=_bearer(linked_distributor["token"])
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tab"] == tab

    dealer_id = str(linked_distributor["dealer"].id)
    assert fake_ch.queries, "expected at least one ClickHouse query"
    # The security boundary: every query carries exactly the linked dealer id.
    for query, params in fake_ch.queries:
        assert params.get("scope_dealer_ids") == [dealer_id]
        assert "scope_dealer_ids" in query


async def test_warehouse_returns_expected_widget_ids(
    client: AsyncClient, fake_ch: _FakeClickHouse, linked_distributor: dict[str, Any]
) -> None:
    resp = await client.get(
        "/api/v1/distributor/analytics/warehouse", headers=_bearer(linked_distributor["token"])
    )
    assert resp.status_code == 200
    widgets = resp.json()["widgets"]
    for wid in ("W-WHS-01", "W-WHS-02", "W-WHS-05", "W-WHS-11", "W-WHS-12"):
        assert wid in widgets


async def test_warehouse_tables_expose_frontend_contract_fields(
    client: AsyncClient, linked_distributor: dict[str, Any]
) -> None:
    fake = _WarehouseRowsClickHouse()
    ch_ro.set_clickhouse_readonly_client(cast("Any", fake))
    try:
        resp = await client.get(
            "/api/v1/distributor/analytics/warehouse",
            headers=_bearer(linked_distributor["token"]),
        )
    finally:
        ch_ro.set_clickhouse_readonly_client(None)

    assert resp.status_code == 200, resp.text
    widgets = resp.json()["widgets"]
    dealer = widgets["W-WHS-11"]["items"][0]
    city = widgets["W-WHS-12"]["items"][0]

    assert dealer == {"dealer_name": "Dealer One", "count": 7, "value": 1234567.0}
    assert city == {"city": "Москва", "count": 5, "value": 765432.0}
    assert "cnt" not in dealer
    assert "total_value" not in dealer
    assert "cnt" not in city
    assert "total_value" not in city


async def test_exchange_and_financials_tables_expose_russian_status_and_model_labels(
    client: AsyncClient, linked_distributor: dict[str, Any]
) -> None:
    fake = _DashboardRowsClickHouse()
    ch_ro.set_clickhouse_readonly_client(cast("Any", fake))
    try:
        exchange_resp = await client.get(
            "/api/v1/distributor/analytics/exchange",
            headers=_bearer(linked_distributor["token"]),
        )
        financials_resp = await client.get(
            "/api/v1/distributor/analytics/financials",
            headers=_bearer(linked_distributor["token"]),
        )
    finally:
        ch_ro.set_clickhouse_readonly_client(None)

    assert exchange_resp.status_code == 200, exchange_resp.text
    assert financials_resp.status_code == 200, financials_resp.text

    exchange_item = exchange_resp.json()["widgets"]["W-EXC-07"]["items"][0]
    financials_item = financials_resp.json()["widgets"]["W-FIN-08"]["items"][0]

    assert exchange_item["status"] == "active"
    assert exchange_item["status_label"] == "Активен"
    assert exchange_item["model"] == "Bestune B70 New"
    assert financials_item["status"] == "approved_final"
    assert financials_item["status_label"] == "Одобрено (финально)"
    assert financials_item["model"] == "Bestune B70 New"


async def test_sales_dc_uses_api_pagination(
    client: AsyncClient, linked_distributor: dict[str, Any]
) -> None:
    fake = _DashboardRowsClickHouse()
    ch_ro.set_clickhouse_readonly_client(cast("Any", fake))
    try:
        resp = await client.get(
            "/api/v1/distributor/analytics/sales-dc?page=2&limit=20",
            headers=_bearer(linked_distributor["token"]),
        )
    finally:
        ch_ro.set_clickhouse_readonly_client(None)

    assert resp.status_code == 200, resp.text
    widgets = resp.json()["widgets"]
    assert widgets["W-SDC-01"]["pagination"] == {
        "total": 471,
        "page": 2,
        "limit": 20,
        "pages": 24,
    }
    assert widgets["W-SDC-02"]["pagination"] == {
        "total": 471,
        "page": 2,
        "limit": 20,
        "pages": 24,
    }


async def test_unlinked_distributor_is_scoped_to_empty_set(
    client: AsyncClient, fake_ch: _FakeClickHouse, unlinked_distributor: dict[str, Any]
) -> None:
    resp = await client.get(
        "/api/v1/distributor/analytics/warehouse", headers=_bearer(unlinked_distributor["token"])
    )
    assert resp.status_code == 200
    # No linked dealers → empty array filter → guarantees zero rows, never a leak.
    for _query, params in fake_ch.queries:
        assert params.get("scope_dealer_ids") == []


async def test_carcraft_employee_is_unscoped(
    client: AsyncClient, fake_ch: _FakeClickHouse, carcraft_employee: dict[str, Any]
) -> None:
    resp = await client.get(
        "/api/v1/distributor/analytics/financials", headers=_bearer(carcraft_employee["token"])
    )
    assert resp.status_code == 200
    assert fake_ch.queries
    for query, params in fake_ch.queries:
        assert "scope_dealer_ids" not in params
        assert "scope_dealer_ids" not in query


async def test_dealer_filter_uses_uuid_contract(
    client: AsyncClient, fake_ch: _FakeClickHouse, linked_distributor: dict[str, Any]
) -> None:
    dealer_id = str(linked_distributor["dealer"].id)
    resp = await client.get(
        f"/api/v1/distributor/analytics/applications?dealers={dealer_id}",
        headers=_bearer(linked_distributor["token"]),
    )

    assert resp.status_code == 200, resp.text
    assert fake_ch.queries
    assert any(params.get("dealers") == [dealer_id] for _query, params in fake_ch.queries)


async def test_dealer_filter_rejects_non_uuid_values(
    client: AsyncClient, fake_ch: _FakeClickHouse, linked_distributor: dict[str, Any]
) -> None:
    resp = await client.get(
        "/api/v1/distributor/analytics/applications?dealers=Урал%20Авто",
        headers=_bearer(linked_distributor["token"]),
    )

    assert resp.status_code == 422
    assert fake_ch.queries == []


async def test_clickhouse_failure_returns_503(
    client: AsyncClient, linked_distributor: dict[str, Any]
) -> None:
    ch_ro.set_clickhouse_readonly_client(cast("Any", _BoomClickHouse()))
    try:
        resp = await client.get(
            "/api/v1/distributor/analytics/warehouse",
            headers=_bearer(linked_distributor["token"]),
        )
    finally:
        ch_ro.set_clickhouse_readonly_client(None)
    assert resp.status_code == 503


async def test_client_role_is_forbidden(
    client: AsyncClient, fake_ch: _FakeClickHouse, db_session: AsyncSession
) -> None:
    user = User(
        phone="+76660000104",
        email="client-analytics@test.local",
        name="Client",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    token, _ = generate_tokens(user.id, "client", None)
    resp = await client.get(
        "/api/v1/distributor/analytics/warehouse", headers=_bearer(token)
    )
    assert resp.status_code == 403
