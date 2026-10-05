"""Unit tests for the admin LCA CSV import: decimal parsing, financial
forwarding into the parent application, and the canonical DWH payload
(financial fields + denormalized leasing_company_name)."""
from __future__ import annotations

import importlib
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.legacy_compat import Vehicle

imp: Any = importlib.import_module("application.commands.admin_applications.import_applications")


class _NoopSession:
    """The handlers here have all DB calls monkeypatched, so the session is a
    pure placeholder."""


class _TrackingSavepoint:
    def __init__(self, session: _SavepointSession) -> None:
        self.session = session
        self.write_count = len(session.writes)

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: object,
    ) -> bool:
        if exc_type is not None:
            self.session.rolled_back += 1
            del self.session.writes[self.write_count :]
        return False


class _SavepointSession:
    def __init__(self) -> None:
        self.savepoints = 0
        self.rolled_back = 0
        self.writes: list[str] = []

    def begin_nested(self) -> _TrackingSavepoint:
        self.savepoints += 1
        return _TrackingSavepoint(self)


def _session() -> AsyncSession:
    return cast("AsyncSession", _NoopSession())


# ---------------------------------------------------------------------------
# _parse_decimal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1500000", Decimal("1500000")),
        ("1 500 000", Decimal("1500000")),
        ("1500000,50", Decimal("1500000.50")),
        ("12,5", Decimal("12.5")),
        (" 2 000 ", Decimal("2000")),
        ("", None),
        ("   ", None),
        (None, None),
        ("not-a-number", None),
    ],
)
def test_parse_decimal(raw: str | None, expected: Decimal | None) -> None:
    assert imp._parse_decimal(raw) == expected


# ---------------------------------------------------------------------------
# _ensure_parent_application — financial forwarding
# ---------------------------------------------------------------------------


async def test_parent_created_with_financial_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_id = uuid4()
    company_id = uuid4()
    lc_id = uuid4()
    captured: dict[str, Any] = {}

    async def _get_by_id(_session: AsyncSession, _app_id: UUID) -> dict[str, Any] | None:
        # First call: parent does not exist yet; after create: return a stub.
        if captured.get("created"):
            return {"id": app_id, "company_id": company_id, **captured["payload"]}
        return None

    async def _get_company(_session: AsyncSession, _cid: UUID) -> dict[str, Any]:
        return {"id": company_id, "name": "ООО Тест"}

    async def _create(_session: AsyncSession, *, payload: dict[str, Any]) -> UUID:
        captured["created"] = True
        captured["payload"] = payload
        return app_id

    monkeypatch.setattr(imp.app_repo, "get_by_id", _get_by_id)
    monkeypatch.setattr(imp.company_repo, "get_company_by_id", _get_company)
    monkeypatch.setattr(imp.app_repo, "create_application", _create)

    row = {
        "company_id": str(company_id),
        "vehicle_id": str(uuid4()),
        "total_amount": "1 500 000",
        "down_payment": "300000,00",
        "down_payment_percent": "20",
        "lease_term_months": "36",
        "monthly_payment": "45000,5",
        "rate": "12,5",
        "total_savings": "100000",
        "buyout_amount": "1000",
    }

    parent, err = await imp._ensure_parent_application(
        _session(), app_id, row, lc_id
    )
    assert err is None
    assert parent is not None
    payload = captured["payload"]
    assert payload["total_amount"] == Decimal("1500000")
    assert payload["down_payment"] == Decimal("300000.00")
    assert payload["down_payment_percent"] == Decimal("20")
    assert payload["lease_term_months"] == 36
    assert payload["monthly_payment"] == Decimal("45000.5")
    assert payload["rate"] == Decimal("12.5")
    assert payload["total_savings"] == Decimal("100000")
    assert payload["buyout_amount"] == Decimal("1000")
    assert "vehicle_id" in payload


async def test_parent_existing_not_overwritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_id = uuid4()
    existing = {"id": app_id, "total_amount": Decimal("999")}
    create_called = {"n": 0}

    async def _get_by_id(_session: AsyncSession, _app_id: UUID) -> dict[str, Any]:
        return existing

    async def _create(  # pragma: no cover - must not run
        _session: AsyncSession,
        *,
        payload: dict[str, Any],
    ) -> UUID:
        create_called["n"] += 1
        return app_id

    monkeypatch.setattr(imp.app_repo, "get_by_id", _get_by_id)
    monkeypatch.setattr(imp.app_repo, "create_application", _create)

    parent, err = await imp._ensure_parent_application(
        _session(), app_id, {"total_amount": "1"}, uuid4()
    )
    assert err is None
    assert parent is existing
    assert create_called["n"] == 0


# ---------------------------------------------------------------------------
# _build_lca_dwh_payload — canonical financial and denormalized fields
# ---------------------------------------------------------------------------

async def test_build_lca_dwh_canonical_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lca_id = uuid4()
    app_id = uuid4()
    lc_id = uuid4()
    dealer_cid = uuid4()
    vehicle_id = uuid4()

    parent = {
        "id": app_id,
        "company_id": uuid4(),
        "dealer_company_id": dealer_cid,
        "display_number": "IMP-1",
        "name": "Клиент",
        "email": "c@example.com",
        "status": "deal",
        "vehicle_id": vehicle_id,
        "total_amount": Decimal("1500000"),
        "lease_term_months": 36,
        "rate": Decimal("12.5"),
    }

    async def _get_link(_session: AsyncSession, _id: UUID) -> dict[str, Any]:
        return {
            "id": lca_id,
            "application_id": app_id,
            "leasing_company_id": lc_id,
            "status": "deal",
            "created_at": None,
            "updated_at": None,
        }

    async def _get_distributor(_session: AsyncSession, _cid: UUID) -> dict[str, Any]:
        return {"id": uuid4()}

    # Enrichment lookups
    async def _get_company(_session: AsyncSession, _cid: UUID) -> dict[str, Any]:
        return {"name": "Дилер Авто", "city": "Москва"}

    async def _get_lc_name(_session: AsyncSession, _lc_id: UUID) -> str:
        assert _lc_id == lc_id
        return "Лизинг Компания №1"

    async def _get_vehicle(_session: AsyncSession, _vid: UUID) -> dict[str, Any]:
        return {
            "mark_id": "mk1",
            "model_id": "md1",
            "mark_name": "BMW",
            "model_name": "X5",
        }

    monkeypatch.setattr(imp.lca_repo, "get_link_by_id", _get_link)
    monkeypatch.setattr(imp.company_repo, "get_distributor_extension", _get_distributor)

    # Patch the repos used inside dwh_enrichment.build_lca_payload.
    dwh_enrichment = importlib.import_module("application.dwh_enrichment")

    monkeypatch.setattr(
        dwh_enrichment.company_repository, "get_company_by_id", _get_company
    )
    monkeypatch.setattr(
        dwh_enrichment.company_repository, "get_leasing_company_name", _get_lc_name
    )
    monkeypatch.setattr(
        dwh_enrichment.vehicle_repo, "get_admin_vehicle", _get_vehicle
    )

    payload = await imp._build_lca_dwh_payload(
        _session(), lca_id, {"distributor_id": ""}, parent
    )

    assert payload is not None
    # Canonical financial fields denormalized from the parent application.
    assert payload["total_amount"] == Decimal("1500000")
    assert payload["lease_term_months"] == 36
    assert payload["rate"] == Decimal("12.5")
    assert payload["vehicle_id"] == vehicle_id
    assert payload["application_status"] == "deal"
    # Denormalized names.
    assert payload["dealer_name"] == "Дилер Авто"
    assert payload["dealer_city"] == "Москва"
    assert payload["leasing_company_name"] == "Лизинг Компания №1"
    assert payload["mark_name"] == "BMW"
    assert payload["model_name"] == "X5"
    assert payload["vehicle_mark_id"] == "mk1"
    # distributor_id resolved via the dealer extension.
    assert payload["distributor_id"] is not None


# ---------------------------------------------------------------------------
# _upsert_lca_row — creates application_vehicles when vehicle columns present
# ---------------------------------------------------------------------------

async def test_upsert_lca_row_creates_application_vehicle_when_vehicle_columns_present(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decimal import Decimal
    from uuid import uuid4

    from sqlalchemy import select

    from infrastructure.models.applications import ApplicationVehicle
    from infrastructure.models.companies import Company, LeasingCompany

    _upsert_lca_row = imp._upsert_lca_row
    built: list[UUID] = []

    async def _build_lca_dwh_payload(
        _session: AsyncSession,
        lca_id: UUID,
        _row: dict[str, str],
        _parent: dict[str, Any],
    ) -> dict[str, Any]:
        built.append(lca_id)
        return {"lca_id": str(lca_id)}

    monkeypatch.setattr(imp, "_build_lca_dwh_payload", _build_lca_dwh_payload)

    company_id = uuid4()
    leasing_company_company_id = uuid4()
    leasing_company_id = uuid4()
    vehicle_id = uuid4()
    application_id = uuid4()

    db_session.add(Company(id=company_id, name="Client", company_type="other"))
    db_session.add(
        Company(
            id=leasing_company_company_id,
            name="LC",
            company_type="leasing_company",
        )
    )
    db_session.add(
        LeasingCompany(
            id=leasing_company_id,
            company_id=leasing_company_company_id,
        )
    )
    db_session.add(Vehicle(id=vehicle_id, vin="LINKVIN000000001"))
    await db_session.flush()

    result = await _upsert_lca_row(
        db_session,
        {
            "application_id": str(application_id),
            "leasing_company_id": str(leasing_company_company_id),
            "status": "approved_final",
            "company_id": str(company_id),
            "vehicle_id": str(vehicle_id),
            "modification_id": "MERCEDES_GLE_001",
            "quantity": "1",
            "unit_price": "10000000",
            "total_price": "10000000",
        },
    )

    assert result.error is None
    assert result.action == "created"
    rows = (
        await db_session.execute(
            select(ApplicationVehicle).where(
                ApplicationVehicle.application_id == application_id
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].vehicle_id == vehicle_id
    assert rows[0].modification_id == "MERCEDES_GLE_001"
    assert rows[0].quantity == 1
    assert rows[0].unit_price == Decimal("10000000")
    assert rows[0].total_price == Decimal("10000000")
    assert rows[0].is_model_order is False
    assert len(built) == 1
    assert result.dwh_payloads == {
        imp.LCA_SNAPSHOT: [{"lca_id": str(built[0])}],
        imp.LCA_CHANGED: [{"lca_id": str(built[0])}],
    }


# ---------------------------------------------------------------------------
# handle_import_applications — row-level savepoints
# ---------------------------------------------------------------------------

async def test_handle_import_rolls_back_sql_failure_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _SavepointSession()

    async def _upsert_lca_row(
        _session: AsyncSession,
        row: dict[str, str],
    ) -> Any:
        row_id = row["application_id"]
        session.writes.append(row_id)
        if row_id == "sql-failure":
            raise RuntimeError("database write failed")
        return imp.ImportApplicationRowResult(
            "created",
            dwh_payloads={imp.LCA_SNAPSHOT: [{"id": row_id}]},
        )

    monkeypatch.setattr(imp, "_upsert_lca_row", _upsert_lca_row)

    result = await imp.handle_import_applications(
        imp.ImportApplicationsCommand(
            csv_bytes=b"application_id\nsql-failure\nsuccess\n"
        ),
        cast("AsyncSession", session),
    )

    assert session.savepoints == 2
    assert session.rolled_back == 1
    assert session.writes == ["success"]
    assert result.created == 1
    assert result.updated == 0
    assert result.errors == ["Строка 1: database write failed"]
    assert result.dwh_payloads == {
        imp.LCA_SNAPSHOT: [{"id": "success"}],
    }


async def test_handle_import_rolls_back_logical_failure_and_excludes_its_dwh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _SavepointSession()

    async def _upsert_lca_row(
        _session: AsyncSession,
        row: dict[str, str],
    ) -> Any:
        row_id = row["application_id"]
        session.writes.append(row_id)
        if row_id == "logical-failure":
            return imp.ImportApplicationRowResult(
                "error",
                "vehicle row is incomplete",
                {imp.LCA_SNAPSHOT: [{"id": "rolled-back"}]},
            )
        return imp.ImportApplicationRowResult(
            "updated",
            dwh_payloads={imp.LCA_SNAPSHOT: [{"id": row_id}]},
        )

    monkeypatch.setattr(imp, "_upsert_lca_row", _upsert_lca_row)

    result = await imp.handle_import_applications(
        imp.ImportApplicationsCommand(
            csv_bytes=b"application_id\nlogical-failure\nsuccess\n"
        ),
        cast("AsyncSession", session),
    )

    assert session.savepoints == 2
    assert session.rolled_back == 1
    assert session.writes == ["success"]
    assert result.created == 0
    assert result.updated == 1
    assert result.errors == ["Строка 1: vehicle row is incomplete"]
    assert result.dwh_payloads == {
        imp.LCA_SNAPSHOT: [{"id": "success"}],
    }
