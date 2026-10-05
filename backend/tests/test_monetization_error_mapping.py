"""Domain errors use the shared mapping through real in-memory HTTP routes."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from application.errors import ServiceError, domain_to_http
from domain.errors import DomainError
from domain.monetization.errors import (
    MonetizationAccessDenied,
    MonetizationConflict,
    MonetizationValidation,
)
from presentation.routers import monetization


@pytest.mark.parametrize(
    ("error_type", "status"),
    [
        (MonetizationValidation, 400),
        (MonetizationConflict, 409),
        (MonetizationAccessDenied, 403),
    ],
)
def test_shared_domain_mapping_preserves_monetization_statuses(
    error_type: type[DomainError], status: int
) -> None:
    error = error_type("Ошибка финансового действия")
    assert isinstance(error, DomainError)
    mapped = domain_to_http(error)
    assert mapped.status_code == status
    assert str(mapped) == str(error)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_type", "status"),
    [
        (MonetizationValidation, 400),
        (MonetizationConflict, 409),
        (MonetizationAccessDenied, 403),
    ],
)
@pytest.mark.parametrize("write", [False, True])
async def test_router_uses_shared_domain_mapping_and_write_rollback(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[DomainError],
    status: int,
    write: bool,
) -> None:
    app = FastAPI()
    app.include_router(monetization.router)
    session = AsyncMock()
    actor = {"role": "admin", "user_id": uuid4()}

    async def session_dependency() -> AsyncIterator[AsyncMock]:
        yield session

    app.dependency_overrides[monetization.get_db] = session_dependency
    app.dependency_overrides[monetization.admin_actor] = lambda: actor
    app.dependency_overrides[monetization.read_actor] = lambda: actor
    error = error_type("Ошибка финансового действия")
    mapping_calls: list[DomainError] = []

    def shared_mapping(exc: DomainError) -> ServiceError:
        mapping_calls.append(exc)
        return domain_to_http(exc)

    monkeypatch.setattr(monetization, "domain_to_http", shared_mapping, raising=False)
    if write:
        monkeypatch.setattr(
            monetization.programs, "create_program", AsyncMock(side_effect=error)
        )
    else:
        monkeypatch.setattr(
            monetization.views, "get_program", AsyncMock(side_effect=error)
        )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        if write:
            response = await client.post(
                "/api/v1/admin/monetization/programs",
                json={
                    "name": "Условия",
                    "leasing_company_id": str(uuid4()),
                    "period_start": "2026-09-01",
                    "sources": [
                        {
                            "source_type": "platform",
                            "expenses": [
                                {
                                    "local_id": "expense-1",
                                    "participant_type": "leasing",
                                    "calc_type": "amount",
                                    "base_type": "none",
                                    "value": "1000",
                                }
                            ],
                            "incomes": [],
                        }
                    ],
                },
            )
        else:
            response = await client.get(
                f"/api/v1/admin/monetization/programs/{uuid4()}"
            )
    assert response.status_code == status, response.text
    assert response.json() == {"detail": str(error)}
    assert mapping_calls == [error]
    session.commit.assert_not_awaited()
    assert session.rollback.await_count == int(write)


def test_service_errors_keep_their_existing_status_and_message() -> None:
    response = monetization._http(ServiceError("Не найдено", 404))
    assert response.status_code == 404
    assert response.detail == "Не найдено"
