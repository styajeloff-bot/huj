"""HTTP regressions for indivisible financial data after quantity grants."""

from decimal import Decimal
from typing import Any, cast
from unittest.mock import Mock
from uuid import uuid4

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.applications import (
    ApplicationDealerDistributionRequest,
    ApplicationVehicle,
    ApplicationVehicleDealerDistribution,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import Company, LeasingCompany
from tests import test_distributor_dealer_assignment as assignment_fixtures

assignment_graph = assignment_fixtures.assignment_graph
pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("endpoint", ["leasing-responses", "response-pdf", "export.pdf"])
@pytest.mark.parametrize("scenario", [
    "partial", "full_with_hidden_line", "full_with_visible_legacy_null", "full", "legacy", "dealer_stock_owner",
    "distributor_stock_owner", "admin",
])
async def test_financial_endpoints_require_whole_application_for_new_recipient(  # noqa: PLR0915
    db_session: AsyncSession, client: AsyncClient,
    assignment_graph: assignment_fixtures.AssignmentGraph,
    monkeypatch: pytest.MonkeyPatch, endpoint: str, scenario: str,
) -> None:
    graph = assignment_graph
    line = await db_session.scalar(sa.select(ApplicationVehicle).where(
        ApplicationVehicle.application_id == graph.application.id,
    ))
    assert line is not None
    line.quantity = 5
    cast("Any", line).total_price = Decimal("500")
    cast("Any", graph.application).total_amount = Decimal("500")
    actor = graph.dealer_two_user
    if scenario == "legacy":
        line.dealer_company_id = graph.dealer_two.id
    else:
        journal = ApplicationDealerDistributionRequest(
            application_id=graph.application.id,
            distributor_company_id=graph.distributor_company.id,
            actor_id=graph.distributor_user.id,
            client_request_id=uuid4(), payload_hash="financial-read",
        )
        db_session.add(journal)
        await db_session.flush()
        db_session.add(ApplicationVehicleDealerDistribution(
            application_vehicle_id=line.id, dealer_company_id=graph.dealer_two.id,
            quantity=5 if scenario in {"full", "full_with_hidden_line", "full_with_visible_legacy_null"} else 1,
            request_id=journal.id,
        ))
    if scenario == "full_with_hidden_line":
        db_session.add(ApplicationVehicle(
            application_id=graph.application.id, vehicle_id=None, is_model_order=True,
            quantity=3, unit_price=Decimal("100"), total_price=Decimal("300"),
        ))
    if scenario == "full_with_visible_legacy_null":
        legacy_line = ApplicationVehicle(
            application_id=graph.application.id, vehicle_id=None, is_model_order=True,
            dealer_company_id=graph.dealer_two.id, quantity=sa.null(),
            unit_price=Decimal("100"), total_price=Decimal("100"),
        )
        db_session.add(legacy_line)
        await db_session.flush()
        await db_session.refresh(legacy_line)
        assert legacy_line.quantity is None
    if scenario == "dealer_stock_owner":
        line.vehicle_id = graph.dealer_two_vehicle.id
    elif scenario == "distributor_stock_owner":
        actor = graph.distributor_user
    elif scenario == "admin":
        actor = graph.carcraft_user

    lc_company = Company(name="21864 financial LC", company_type="leasing_company")
    db_session.add(lc_company)
    await db_session.flush()
    lc = LeasingCompany(company_id=lc_company.id, is_active=True)
    db_session.add(lc)
    await db_session.flush()
    db_session.add(LeasingCompanyApplication(
        application_id=graph.application.id, leasing_company_id=lc.id,
    ))
    await db_session.flush()

    response_renderer = Mock(return_value=b"%PDF-financial-test")
    application_renderer = Mock(return_value=b"%PDF-application-test")
    monkeypatch.setattr("application.queries.leasing_response_pdf.render_leasing_response_pdf", response_renderer)
    monkeypatch.setattr("application.queries.applications.export_application.render_application_export_pdf", application_renderer)
    token, _ = generate_tokens(actor.id, actor.role, actor.company_id)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/applications/{graph.application.id}"
    detail = await client.get(base, headers=headers)
    assert detail.status_code == 200, detail.text
    if scenario == "partial":
        assert detail.json()["vehicles"][0]["quantity"] == 1
    path = f"leasing-responses/{lc.id}/pdf" if endpoint == "response-pdf" else endpoint
    response = await client.get(f"{base}/{path}", headers=headers)
    denied = scenario in {"partial", "full_with_hidden_line"}
    assert response.status_code == (403 if denied else 200), response.text
    if denied:
        response_renderer.assert_not_called()
        application_renderer.assert_not_called()
    elif endpoint == "response-pdf":
        response_renderer.assert_called_once()
        assert response.content == b"%PDF-financial-test"
    elif endpoint == "export.pdf":
        application_renderer.assert_called_once()
        assert response.content == b"%PDF-application-test"
    else:
        assert Decimal(str(response.json()["requested"]["total_amount"])) == Decimal("500")
