"""Focused tests for administrative company handlers and type transitions."""
from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import application.commands.admin_companies.update_company as update_company_command
from application.commands.admin_companies import (
    CreateCompanyCommand,
    handle_create_company,
)
from domain.errors import (
    CompanyAlreadyExistsError,
    InvalidCompanyTypeError,
    InvalidInnError,
)
from domain.values import CompanyInfo
from infrastructure.models.companies import Company
from infrastructure.repositories import company_type_transition_repository
from tests.fakes.company_lookup import FakeCompanyLookupProvider

pytestmark = pytest.mark.asyncio


def _make_info() -> CompanyInfo:
    return CompanyInfo(
        name="ООО Тест",
        full_name="Общество с ограниченной ответственностью «Тест»",
        inn="7700000001",
        kpp="770001001",
        ogrn="1234567890123",
        legal_address="Москва, ул. Проверочная, 1",
        actual_address=None,
        phone=None,
        email=None,
        foundation_date=None,
        employee_count=None,
        business_activity="47.11 - Розничная торговля",
        manager_name="Иванов Иван Иванович",
        entity_type="LEGAL",
    )


async def test_create_company_happy_path_with_enrichment(
    db_session: AsyncSession,
) -> None:
    fake = FakeCompanyLookupProvider(items=[_make_info()])
    cmd = CreateCompanyCommand(
        inn="7700000001",
        company_type="dealer",
    )
    result = await handle_create_company(cmd, db_session, fake)
    assert result["inn"] == "7700000001"
    assert result["company_type"] == "dealer"
    # Enrichment filled the short_name
    assert result["short_name"] == "ООО Тест"


async def test_create_company_emits_geo_to_dwh(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the create-path DWH emit must carry city/region/actual_address.

    ``get_by_id`` previously omitted these, so ``dwh_companies.city`` was NULL on
    first import (only the update path populated it). The warehouse city table
    depends on this.
    """
    import application.commands.admin_companies.create_company as cc

    captured: dict = {}

    def _capture(payload: dict) -> None:
        captured.update(payload)

    monkeypatch.setattr(cc, "emit_company_changed", _capture)

    cmd = CreateCompanyCommand(
        inn="7700000055",
        company_type="dealer",
        name="Гео Дилер",
        city="Казань",
        region="Татарстан",
        actual_address="г. Казань",
    )
    await handle_create_company(cmd, db_session)
    assert captured.get("city") == "Казань"
    assert captured.get("region") == "Татарстан"
    assert captured.get("actual_address") == "г. Казань"
    # The create-path emit must expose the same denormalized keys as the update
    # path (get_by_id used to omit them → empty in DWH on first import).
    for key in ("website", "okpo", "legal_form", "director_full_name", "tax_system"):
        assert key in captured


async def test_create_company_with_explicit_name_overrides_enrichment(
    db_session: AsyncSession,
) -> None:
    fake = FakeCompanyLookupProvider(items=[_make_info()])
    cmd = CreateCompanyCommand(
        inn="7700000002",
        company_type="dealer",
        name="Custom Name Override",
    )
    result = await handle_create_company(cmd, db_session, fake)
    assert result["name"] == "Custom Name Override"


async def test_create_company_dadata_unavailable_soft_failure(
    db_session: AsyncSession,
) -> None:
    fake = FakeCompanyLookupProvider()
    fake.raise_unavailable = True
    cmd = CreateCompanyCommand(
        inn="7700000003",
        company_type="dealer",
        name="Fallback Name",
    )
    result = await handle_create_company(cmd, db_session, fake)
    # Soft-failure: still creates the company with the client-provided name.
    assert result["name"] == "Fallback Name"


async def test_create_company_invalid_inn_raises(
    db_session: AsyncSession,
) -> None:
    cmd = CreateCompanyCommand(inn="abc", company_type="dealer")
    with pytest.raises(InvalidInnError):
        await handle_create_company(cmd, db_session)


async def test_create_company_invalid_type_raises(
    db_session: AsyncSession,
) -> None:
    cmd = CreateCompanyCommand(
        inn="7700000004", company_type="not-a-type"
    )
    with pytest.raises(InvalidCompanyTypeError):
        await handle_create_company(cmd, db_session)


async def test_create_company_duplicate_inn_raises(
    db_session: AsyncSession,
) -> None:
    existing = Company(
        name="Already Exists",
        inn="7700000005",
        company_type="dealer",
        is_active=True,
    )
    db_session.add(existing)
    await db_session.flush()

    cmd = CreateCompanyCommand(
        inn="7700000005", company_type="dealer", name="Dup"
    )
    with pytest.raises(CompanyAlreadyExistsError):
        await handle_create_company(cmd, db_session)


async def test_create_leasing_company_creates_subtype(
    db_session: AsyncSession,
) -> None:
    from infrastructure.repositories import admin_companies_repository as repo

    cmd = CreateCompanyCommand(
        inn="7700000006",
        company_type="leasing_company",
        name="LC Test",
    )
    result = await handle_create_company(cmd, db_session)
    company_id = result["id"]

    # LC subtype row created
    lcs = await repo.list_leasing_companies_all(db_session)
    assert any(lc["company_id"] == company_id for lc in lcs)


async def test_reverse_transition_reuses_inactive_target_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A prior safe exit must not turn the target subtype into a permanent 409."""
    company_id = uuid4()
    leasing_id = uuid4()
    distributor_id = uuid4()
    session = cast("AsyncSession", object())
    lock_state = AsyncMock(
        return_value=(
            {"id": company_id, "company_type": "distributor"},
            {"id": leasing_id, "company_id": company_id, "is_active": False},
            {"id": distributor_id, "company_id": company_id, "is_active": True},
        )
    )
    blockers = AsyncMock(return_value=[])
    apply = AsyncMock()
    monkeypatch.setattr(
        update_company_command.transition_repo,
        "lock_company_type_transition_state",
        lock_state,
    )
    monkeypatch.setattr(
        update_company_command.transition_repo,
        "list_type_transition_blockers",
        blockers,
    )
    monkeypatch.setattr(
        update_company_command.transition_repo, "apply_company_type_transition", apply
    )

    await update_company_command._transition_company_type(
        session, company_id=company_id, target_type="leasing_company"
    )

    blockers.assert_awaited_once()
    apply.assert_awaited_once_with(
        session,
        company_id=company_id,
        target_type="leasing_company",
        leaving_type="distributor",
        target_extension={
            "id": leasing_id,
            "company_id": company_id,
            "is_active": False,
        },
    )


class _RecordingSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.statements: list[Any] = []
        self.flush_count = 0

    def add(self, instance: Any) -> None:
        self.added.append(instance)

    async def execute(self, statement: Any) -> None:
        self.statements.append(statement)

    async def flush(self) -> None:
        self.flush_count += 1


async def test_apply_reverse_transition_reactivates_same_subtype_before_exit() -> None:
    """The target UUID is updated, never inserted, before the old role is disabled."""
    company_id = uuid4()
    leasing_id = uuid4()
    session = _RecordingSession()

    await company_type_transition_repository.apply_company_type_transition(
        cast("AsyncSession", session),
        company_id=company_id,
        target_type="leasing_company",
        leaving_type="distributor",
        target_extension={
            "id": leasing_id,
            "company_id": company_id,
            "is_active": False,
        },
    )

    assert session.added == []
    assert session.flush_count == 1
    assert str(session.statements[0]).startswith(
        "UPDATE leasing_companies SET is_active=:is_active, updated_at=:updated_at"
    )
    assert str(session.statements[1]).startswith(
        "UPDATE distributors SET is_active=:is_active, updated_at=:updated_at"
    )
    assert str(session.statements[2]).startswith(
        "UPDATE companies SET company_type=:company_type, updated_at=:updated_at"
    )
    assert session.statements[0].compile().params["id_1"] == leasing_id
