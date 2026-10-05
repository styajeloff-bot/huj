from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from application.queries.application_status_funnel import ApplicationFunnelError
from infrastructure.database import get_db
from presentation.dependencies.auth import get_current_user
from presentation.routers import application_status_funnel as router_module


def _success_result() -> dict[str, Any]:
    return {
        "unit": "lca",
        "timezone": "Europe/Moscow",
        "period_from": "2026-07-10",
        "period_to": "2026-07-10",
        "selection_mode": "created_in_period",
        "history_available_from": "2026-07-01",
        "selected_count": 0,
        "rows": [],
    }


@pytest.mark.asyncio
async def test_registered_route_accepts_query_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor_id = uuid4()
    handler = AsyncMock(return_value=_success_result())
    monkeypatch.setattr(router_module, "handle_get_application_status_funnel", handler)

    app = FastAPI()
    app.include_router(router_module.router, prefix="/api/v1/analytics")
    app.dependency_overrides[get_current_user] = lambda: {
        "id": actor_id,
        "role": "carcraft_employee",
        "company_id": None,
    }
    app.dependency_overrides[get_db] = object

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/analytics/applications/funnel",
            params={
                "period_from": "2026-07-10",
                "period_to": "2026-07-10",
                "selection_mode": "active_during_period",
            },
        )

    assert response.status_code == 200
    assert handler.await_args is not None
    query = handler.await_args.args[0]
    assert query.actor_id == actor_id
    assert query.selection_mode == (
        router_module.ApplicationFunnelSelectionMode.ACTIVE_DURING_PERIOD
    )


@pytest.mark.asyncio
async def test_router_serializes_success_with_camel_case_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = AsyncMock(return_value=_success_result())
    monkeypatch.setattr(router_module, "handle_get_application_status_funnel", handler)

    response = await router_module.application_status_funnel(
        user={"id": str(uuid4()), "role": "carcraft_employee", "company_id": None},
        session=object(),  # type: ignore[arg-type]
        period_from=date(2026, 7, 10),
        period_to=date(2026, 7, 10),
        selection_mode=router_module.ApplicationFunnelSelectionMode.CREATED_IN_PERIOD,
    )

    body = bytes(response.body).decode("utf-8")
    assert '"periodFrom":"2026-07-10"' in body
    assert '"historyAvailableFrom":"2026-07-01"' in body
    assert '"selectedCount":0' in body


@pytest.mark.asyncio
async def test_history_error_keeps_watermark_in_structured_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = AsyncMock(
        side_effect=ApplicationFunnelError(
            "Достоверная история статусов доступна с 2026-07-11",
            422,
            "HISTORY_NOT_AVAILABLE",
            history_available_from=date(2026, 7, 11),
        )
    )
    monkeypatch.setattr(router_module, "handle_get_application_status_funnel", handler)

    response = await router_module.application_status_funnel(
        user={"id": str(uuid4()), "role": "dealer", "company_id": str(uuid4())},
        session=object(),  # type: ignore[arg-type]
        period_from=date(2026, 7, 1),
        period_to=date(2026, 7, 10),
        selection_mode=router_module.ApplicationFunnelSelectionMode.CREATED_IN_PERIOD,
    )

    assert response.status_code == 422
    assert json.loads(bytes(response.body))["detail"] == {
        "message": "Достоверная история статусов доступна с 2026-07-11",
        "error_code": "HISTORY_NOT_AVAILABLE",
        "history_available_from": "2026-07-11",
    }


@pytest.mark.asyncio
async def test_invalid_user_claim_uses_stable_error_contract() -> None:
    response = await router_module.application_status_funnel(
        user={"id": "not-a-uuid", "role": "dealer", "company_id": str(uuid4())},
        session=object(),  # type: ignore[arg-type]
        period_from=date(2026, 7, 10),
        period_to=date(2026, 7, 10),
        selection_mode=router_module.ApplicationFunnelSelectionMode.CREATED_IN_PERIOD,
    )

    assert response.status_code == 403
    assert json.loads(bytes(response.body))["detail"] == {
        "message": "Некорректные данные пользователя",
        "error_code": "ACCESS_DENIED",
    }


def test_openapi_documents_funnel_error_responses() -> None:
    app = FastAPI()
    app.include_router(router_module.router, prefix="/api/v1/analytics")

    operation = app.openapi()["paths"][
        "/api/v1/analytics/applications/funnel"
    ]["get"]

    assert {"200", "403", "422", "503"}.issubset(operation["responses"])
