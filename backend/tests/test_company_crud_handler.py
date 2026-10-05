"""Handler-level tests for the G4 companies CRUD additions.

Covers list / upsert-own / update / external-data / deactivate.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.companies import (
    DeactivateCompanyCommand,
    UpdateCompanyCommand,
    UpdateCompanyExternalDataCommand,
    UpsertMyCompanyProfileCommand,
    handle_deactivate_company,
    handle_update_company,
    handle_update_company_external_data,
    handle_upsert_my_company_profile,
)
from application.queries.companies import (
    ListCompaniesQuery,
    handle_list_companies,
)
from domain.errors import (
    CompanyAccessDeniedError,
    CompanyAlreadyDeactivatedError,
    CompanyAlreadyExistsError,
    CompanyHasNoInnError,
    InvalidCompanyTypeError,
    InvalidInnError,
)
from infrastructure.models.companies import Company
from infrastructure.models.users import User

pytestmark = pytest.mark.asyncio


async def _seed_company(
    db: AsyncSession,
    *,
    name: str,
    inn: str,
    company_type: str = "dealer",
    is_active: bool = True,
    phone: str | None = None,
) -> Company:
    c = Company(
        name=name, inn=inn, company_type=company_type, is_active=is_active, phone=phone
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c


@pytest_asyncio.fixture
async def owner_user(db_session: AsyncSession) -> User:
    u = User(phone="+70000000900", role="client", is_active=True)
    db_session.add(u)
    await db_session.flush()
    await db_session.refresh(u)
    return u


# ---------------------------------------------------------------------------
# list_companies
# ---------------------------------------------------------------------------


async def test_list_companies_employee_sees_all(
    db_session: AsyncSession, employee_user: User
) -> None:
    a = await _seed_company(db_session, name="A", inn="1000000001")
    b = await _seed_company(db_session, name="B", inn="1000000002")
    result = await handle_list_companies(
        ListCompaniesQuery(
            actor_id=employee_user.id,
            actor_role="carcraft_employee",
        ),
        db_session,
    )
    ids = {item["id"] for item in result["companies"]}
    assert {a.id, b.id}.issubset(ids)


async def test_list_companies_client_sees_only_own(
    db_session: AsyncSession, owner_user: User
) -> None:
    mine = await _seed_company(db_session, name="Mine", inn="2000000001")
    await _seed_company(db_session, name="Theirs", inn="2000000002")
    owner_user.company_id = mine.id
    await db_session.flush()

    result = await handle_list_companies(
        ListCompaniesQuery(actor_id=owner_user.id, actor_role="client"),
        db_session,
    )
    ids = [item["id"] for item in result["companies"]]
    assert ids == [mine.id]


async def test_list_companies_filters_by_name_phone_type_and_status(
    db_session: AsyncSession, employee_user: User
) -> None:
    wanted = await _seed_company(
        db_session,
        name="Европлан",
        inn="3000000001",
        company_type="leasing_company",
        phone="+76662000004",
    )
    await _seed_company(
        db_session,
        name="Европлан неактивный",
        inn="3000000002",
        company_type="leasing_company",
        is_active=False,
        phone="+76662000004",
    )
    result = await handle_list_companies(
        ListCompaniesQuery(
            actor_id=employee_user.id,
            actor_role="carcraft_employee",
            name="евро",
            phone="6662",
            company_type="leasing_company",
            is_active=True,
        ),
        db_session,
    )
    assert [item["id"] for item in result["companies"]] == [wanted.id]
    assert result["pagination"]["total"] == 1


# ---------------------------------------------------------------------------
# Phase 15 H3 — /{id}/stats query deleted; no caller.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# upsert_my_profile
# ---------------------------------------------------------------------------


async def test_upsert_my_profile_creates_and_attaches(
    db_session: AsyncSession, owner_user: User
) -> None:
    result = await handle_upsert_my_company_profile(
        UpsertMyCompanyProfileCommand(
            user_id=owner_user.id,
            data={
                "name": "Новая",
                "inn": "4000000001",
                "company_type": "leasing_company",
                "legal_address": "Россия",
                "phone": "+7 000",
                "email": "ok@ok.ok",
            },
        ),
        db_session,
    )
    assert result["company"]["id"] == result["company_id"]
    # User is now linked.
    await db_session.refresh(owner_user)
    assert owner_user.company_id == result["company_id"]


async def test_upsert_my_profile_rejects_duplicate_inn(
    db_session: AsyncSession, owner_user: User
) -> None:
    await _seed_company(db_session, name="Already", inn="4000000002")
    with pytest.raises(CompanyAlreadyExistsError):
        await handle_upsert_my_company_profile(
            UpsertMyCompanyProfileCommand(
                user_id=owner_user.id,
                data={
                    "name": "Новая",
                    "inn": "4000000002",
                    "company_type": "dealer",
                    "legal_address": "г",
                    "phone": "+7",
                    "email": "e@e.e",
                },
            ),
            db_session,
        )


async def test_upsert_my_profile_rejects_invalid_inn(
    db_session: AsyncSession, owner_user: User
) -> None:
    with pytest.raises(InvalidInnError):
        await handle_upsert_my_company_profile(
            UpsertMyCompanyProfileCommand(
                user_id=owner_user.id,
                data={
                    "name": "Bad",
                    "inn": "short",
                    "company_type": "dealer",
                    "legal_address": "a",
                    "phone": "+7",
                    "email": "e@e.e",
                },
            ),
            db_session,
        )


async def test_upsert_my_profile_rejects_unknown_type(
    db_session: AsyncSession, owner_user: User
) -> None:
    with pytest.raises(InvalidCompanyTypeError):
        await handle_upsert_my_company_profile(
            UpsertMyCompanyProfileCommand(
                user_id=owner_user.id,
                data={
                    "name": "Bad",
                    "inn": "4000000003",
                    "company_type": "bogus",
                    "legal_address": "a",
                    "phone": "+7",
                    "email": "e@e.e",
                },
            ),
            db_session,
        )


# ---------------------------------------------------------------------------
# update_company
# ---------------------------------------------------------------------------


async def test_update_company_owner_can_edit(
    db_session: AsyncSession, owner_user: User
) -> None:
    company = await _seed_company(
        db_session, name="Mine", inn="5000000001"
    )
    owner_user.company_id = company.id
    await db_session.flush()

    result = await handle_update_company(
        UpdateCompanyCommand(
            company_id=company.id,
            actor_id=owner_user.id,
            actor_role="client",
            data={"name": "Переименована"},
        ),
        db_session,
    )
    assert result["company"]["name"] == "Переименована"


async def test_update_company_stranger_denied(
    db_session: AsyncSession, owner_user: User
) -> None:
    company = await _seed_company(
        db_session, name="X", inn="5000000002"
    )
    with pytest.raises(CompanyAccessDeniedError):
        await handle_update_company(
            UpdateCompanyCommand(
                company_id=company.id,
                actor_id=owner_user.id,
                actor_role="client",
                data={"name": "Hack"},
            ),
            db_session,
        )


# ---------------------------------------------------------------------------
# external-data
# ---------------------------------------------------------------------------


async def test_update_external_data_requires_inn(
    db_session: AsyncSession, employee_user: User
) -> None:
    # Company without INN
    c = Company(name="No INN", company_type="other")
    db_session.add(c)
    await db_session.flush()
    await db_session.refresh(c)

    with pytest.raises(CompanyHasNoInnError):
        await handle_update_company_external_data(
            UpdateCompanyExternalDataCommand(
                company_id=c.id,
                actor_id=employee_user.id,
                actor_role="carcraft_employee",
                data={"full_name": "Полное"},
            ),
            db_session,
        )


async def test_update_external_data_persists_enrichment_fields(
    db_session: AsyncSession, employee_user: User
) -> None:
    c = await _seed_company(db_session, name="Y", inn="6000000001")
    result = await handle_update_company_external_data(
        UpdateCompanyExternalDataCommand(
            company_id=c.id,
            actor_id=employee_user.id,
            actor_role="carcraft_employee",
            data={
                "full_name": "Полное",
                "director_full_name": "Иванов И.И.",
                "main_okved_code": "45.11",
            },
        ),
        db_session,
    )
    assert result["data"]["full_name"] == "Полное"
    assert result["data"]["director_full_name"] == "Иванов И.И."


# ---------------------------------------------------------------------------
# deactivate
# ---------------------------------------------------------------------------


async def test_deactivate_company_employee_ok(
    db_session: AsyncSession,
) -> None:
    c = await _seed_company(db_session, name="DelMe", inn="7000000001")
    result = await handle_deactivate_company(
        DeactivateCompanyCommand(
            company_id=c.id, actor_role="carcraft_employee"
        ),
        db_session,
    )
    assert result["company"]["is_active"] is False


async def test_deactivate_company_non_employee_denied(
    db_session: AsyncSession,
) -> None:
    c = await _seed_company(db_session, name="Keep", inn="7000000002")
    with pytest.raises(CompanyAccessDeniedError):
        await handle_deactivate_company(
            DeactivateCompanyCommand(company_id=c.id, actor_role="client"),
            db_session,
        )


async def test_deactivate_company_already_inactive_raises(
    db_session: AsyncSession,
) -> None:
    c = await _seed_company(
        db_session, name="Dead", inn="7000000003", is_active=False
    )
    with pytest.raises(CompanyAlreadyDeactivatedError):
        await handle_deactivate_company(
            DeactivateCompanyCommand(
                company_id=c.id, actor_role="carcraft_employee"
            ),
            db_session,
        )
