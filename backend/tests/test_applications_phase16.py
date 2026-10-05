"""Phase 16 — draft-first checkout flow: sub-resource PUTs + listing filter.

Covers the happy path:

1. Create a draft via ``handle_create_draft``.
2. Update conditions / company / vehicles / questionnaire / LCs via the
   new sub-resource handlers.
3. ``ensure_editable`` rejects mutation once admin has dispatched the
   application (row in ``leasing_company_applications``).
4. ``list_for_user`` keeps the parent application visible after LCA dispatch.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.applications import (
    ApplicationVehiclePayload,
    CreateDraftCommand,
    UpdateCompanyCommand,
    UpdateConditionsCommand,
    UpdateLeasingCompaniesCommand,
    UpdateQuestionnaireCommand,
    UpdateVehiclesCommand,
    handle_create_draft,
    handle_update_company,
    handle_update_conditions,
    handle_update_leasing_companies,
    handle_update_questionnaire,
    handle_update_vehicles,
)
from application.errors import ServiceError
from application.queries.applications import (
    ListApplicationsQuery,
    handle_list_applications,
)
from application.queries.leasing_company_applications import (
    ListLcaQuery,
    handle_list_lca,
)
from domain.errors import (
    ApplicationNotEditableError,
    ApplicationNotSubmittableError,
    CompanyNotFoundError,
)
from infrastructure.models.applications import (
    ApplicationQuestionnaire,
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.users import User, UserCompany
from infrastructure.repositories import application_repository as app_repo
from tests.legacy_compat import Vehicle

# ---------------------------------------------------------------------------
# Fixtures — duplicated locally with unique phones/names to avoid collision
# with other test files sharing the same session.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client_company(db_session: AsyncSession) -> Company:
    company = Company(name="P16 Client Co", company_type="other")
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def other_company(db_session: AsyncSession) -> Company:
    company = Company(name="P16 Other Co", company_type="other")
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def lc_company(db_session: AsyncSession) -> Company:
    company = Company(name="P16 LC Provider", company_type="leasing_company")
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def leasing_company(
    db_session: AsyncSession, lc_company: Company
) -> LeasingCompany:
    lc = LeasingCompany(company_id=lc_company.id, is_active=True)
    db_session.add(lc)
    await db_session.flush()
    return lc


@pytest_asyncio.fixture
async def client_user(
    db_session: AsyncSession, client_company: Company
) -> User:
    user = User(
        phone="+76660007666",
        email="p16-client@test.local",
        name="Phase16 Client",
        role="client",
        is_active=True,
        company_id=client_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def draft(
    db_session: AsyncSession, client_user: User, client_company: Company
) -> dict:
    """Create a baseline draft owned by ``client_user``."""
    cmd = CreateDraftCommand(
        source_type="platform",
        actor_id=client_user.id,
        actor_role="client",
        actor_company_id=client_user.company_id,
        company_id=client_company.id,
        name="Phase16 Draft",
        email="p16-draft@test.local",
        vehicles=[
            ApplicationVehiclePayload(
                modification_id="MOD-P16",
                quantity=1,
                custom_price=Decimal("100"),
            )
        ],
    )
    return await handle_create_draft(cmd, db_session)


# ---------------------------------------------------------------------------
# Sub-resource PUTs happy path
# ---------------------------------------------------------------------------


async def test_update_conditions_patches_provided_fields(
    db_session: AsyncSession, client_user: User, draft: dict
) -> None:
    cmd = UpdateConditionsCommand(
        application_id=draft["application_id"],
        actor_id=client_user.id,
        actor_role="client",
        actor_company_id=client_user.company_id,
        down_payment=Decimal("500000"),
        down_payment_percent=30.0,
        lease_term_months=36,
    )
    result = await handle_update_conditions(cmd, db_session)
    app = result["application"]
    assert app["down_payment"] == Decimal("500000")
    assert app["down_payment_percent"] == 30.0
    assert app["lease_term_months"] == 36


async def test_update_company_rejects_unknown_company(
    db_session: AsyncSession, client_user: User, draft: dict
) -> None:
    cmd = UpdateCompanyCommand(
        application_id=draft["application_id"],
        actor_id=client_user.id,
        actor_role="client",
        actor_company_id=client_user.company_id,
        company_id=uuid4(),
    )
    with pytest.raises(CompanyNotFoundError):
        await handle_update_company(cmd, db_session)


async def test_update_company_assigns_missing_display_number(
    db_session: AsyncSession,
    client_user: User,
    draft: dict,
    other_company: Company,
) -> None:
    other_company.inn = "7711223344"
    await db_session.flush()

    cmd = UpdateCompanyCommand(
        application_id=draft["application_id"],
        actor_id=client_user.id,
        actor_role="client",
        actor_company_id=client_user.company_id,
        company_id=other_company.id,
    )
    result = await handle_update_company(cmd, db_session)

    assert result["application"]["display_number"] is not None
    assert result["application"]["display_number"].startswith("7711223344-")
    assert result["application"]["display_number"].endswith("-001")


async def test_update_vehicles_replaces_entire_set(
    db_session: AsyncSession, client_user: User, draft: dict
) -> None:
    cmd = UpdateVehiclesCommand(
        application_id=draft["application_id"],
        actor_id=client_user.id,
        actor_role="client",
        actor_company_id=client_user.company_id,
        vehicles=[
            ApplicationVehiclePayload(
                modification_id="MOD-NEW-1",
                quantity=2,
                custom_price=Decimal("200"),
            ),
            ApplicationVehiclePayload(
                modification_id="MOD-NEW-2",
                quantity=1,
                custom_price=Decimal("150"),
            ),
        ],
    )
    result = await handle_update_vehicles(cmd, db_session)
    app = result["application"]
    # total = 200*2 + 150*1 = 550
    assert app["total_amount"] == Decimal("550")


async def test_update_conditions_keeps_total_amount_from_vehicle_rows(
    db_session: AsyncSession, client_user: User, draft: dict
) -> None:
    await handle_update_vehicles(
        UpdateVehiclesCommand(
            application_id=draft["application_id"],
            actor_id=client_user.id,
            actor_role="client",
            actor_company_id=client_user.company_id,
            vehicles=[
                ApplicationVehiclePayload(
                    modification_id="MOD-P16-TOTAL",
                    quantity=2,
                    custom_price=Decimal("1000000"),
                )
            ],
        ),
        db_session,
    )

    result = await handle_update_conditions(
        UpdateConditionsCommand(
            application_id=draft["application_id"],
            actor_id=client_user.id,
            actor_role="client",
            actor_company_id=client_user.company_id,
            total_amount=Decimal("2600000"),
            down_payment=Decimal("400000"),
            down_payment_percent=20,
            lease_term_months=36,
            monthly_payment=Decimal("75000"),
            total_cost=Decimal("3100000"),
            total_interest=Decimal("1100000"),
        ),
        db_session,
    )

    assert result["application"]["total_amount"] == Decimal("2000000")
    assert result["application"]["monthly_payment"] == Decimal("75000")
    assert result["application"]["total_cost"] == Decimal("3100000")
    assert result["application"]["total_interest"] == Decimal("1100000")


async def test_update_conditions_keeps_zero_total_from_vehicle_rows(
    db_session: AsyncSession, client_user: User, draft: dict
) -> None:
    await handle_update_vehicles(
        UpdateVehiclesCommand(
            application_id=draft["application_id"],
            actor_id=client_user.id,
            actor_role="client",
            actor_company_id=client_user.company_id,
            vehicles=[
                ApplicationVehiclePayload(
                    modification_id="MOD-P16-ZERO-TOTAL",
                    quantity=2,
                    custom_price=Decimal("0"),
                )
            ],
        ),
        db_session,
    )

    result = await handle_update_conditions(
        UpdateConditionsCommand(
            application_id=draft["application_id"],
            actor_id=client_user.id,
            actor_role="client",
            actor_company_id=client_user.company_id,
            total_amount=Decimal("1"),
            down_payment=Decimal("0"),
            down_payment_percent=0,
            lease_term_months=36,
        ),
        db_session,
    )

    assert result["application"]["total_amount"] == Decimal("0")


async def test_update_questionnaire_upserts(
    db_session: AsyncSession, client_user: User, draft: dict
) -> None:
    cmd = UpdateQuestionnaireCommand(
        application_id=draft["application_id"],
        actor_id=client_user.id,
        actor_role="client",
        actor_company_id=client_user.company_id,
        payload={"legal_form": "ООО", "revenue_annual": "100000000"},
    )
    result = await handle_update_questionnaire(cmd, db_session)
    assert result["questionnaire"] is not None


async def test_update_questionnaire_ignores_readonly_projection_fields(
    db_session: AsyncSession, client_user: User, draft: dict
) -> None:
    """Checkout can resubmit GET projection fields without corrupting DB types."""
    app_id = draft["application_id"]

    cmd = UpdateQuestionnaireCommand(
        application_id=app_id,
        actor_id=client_user.id,
        actor_role="client",
        actor_company_id=client_user.company_id,
        payload={
            "id": str(uuid4()),
            "application_id": str(uuid4()),
            "created_at": "2026-05-25T20:23:40.121090+00:00",
            "updated_at": "2026-05-25T20:23:40.121090+00:00",
            "legal_address": "Projection-safe legal address",
        },
    )

    result = await handle_update_questionnaire(cmd, db_session)

    row = await db_session.get(ApplicationQuestionnaire, result["questionnaire"]["id"])
    assert row is not None
    assert row.application_id == app_id
    assert row.legal_address == "Projection-safe legal address"


async def test_update_questionnaire_assigns_missing_display_number_from_inn(
    db_session: AsyncSession, client_user: User, draft: dict
) -> None:
    cmd = UpdateQuestionnaireCommand(
        application_id=draft["application_id"],
        actor_id=client_user.id,
        actor_role="client",
        actor_company_id=client_user.company_id,
        payload={"inn": "7722334455", "legal_form": "ООО"},
    )
    await handle_update_questionnaire(cmd, db_session)

    row = await db_session.get(LeasingApplication, draft["application_id"])
    assert row is not None
    assert row.display_number is not None
    assert row.display_number.startswith("7722334455-")
    assert row.display_number.endswith("-001")


async def test_update_leasing_companies_dedups(
    db_session: AsyncSession,
    client_user: User,
    draft: dict,
    leasing_company: LeasingCompany,
) -> None:
    cmd = UpdateLeasingCompaniesCommand(
        application_id=draft["application_id"],
        actor_id=client_user.id,
        actor_role="client",
        actor_company_id=client_user.company_id,
        leasing_company_ids=[leasing_company.id, leasing_company.id],
    )
    result = await handle_update_leasing_companies(cmd, db_session)
    assert result["application"]["selected_leasing_companies"] == [
        leasing_company.id
    ]


# ---------------------------------------------------------------------------
# Edit guard: dispatched drafts are locked down
# ---------------------------------------------------------------------------


async def test_updates_rejected_once_lc_children_exist(
    db_session: AsyncSession,
    client_user: User,
    draft: dict,
    leasing_company: LeasingCompany,
) -> None:
    # Admin dispatched to LC — creates a child row.
    db_session.add(
        LeasingCompanyApplication(
            application_id=draft["application_id"],
            leasing_company_id=leasing_company.id,
        )
    )
    await db_session.flush()

    cmd = UpdateConditionsCommand(
        application_id=draft["application_id"],
        actor_id=client_user.id,
        actor_role="client",
        actor_company_id=client_user.company_id,
        down_payment=Decimal("1"),
    )
    with pytest.raises(ApplicationNotEditableError):
        await handle_update_conditions(cmd, db_session)


async def test_client_can_update_when_only_legacy_unassigned_draft_lca_exists(
    db_session: AsyncSession,
    client_user: User,
    draft: dict,
) -> None:
    db_session.add(
        LeasingCompanyApplication(
            application_id=draft["application_id"],
            leasing_company_id=None,
            status="draft",
        )
    )
    await db_session.flush()

    cmd = UpdateConditionsCommand(
        application_id=draft["application_id"],
        actor_id=client_user.id,
        actor_role="client",
        actor_company_id=client_user.company_id,
        down_payment=Decimal("500000"),
        down_payment_percent=30.0,
        lease_term_months=36,
    )

    result = await handle_update_conditions(cmd, db_session)

    app = result["application"]
    assert app["down_payment"] == Decimal("500000")
    assert app["down_payment_percent"] == 30.0
    assert app["lease_term_months"] == 36


async def test_carcraft_employee_can_update_conditions_after_lc_distribution(
    db_session: AsyncSession,
    client_user: User,
    draft: dict,
    leasing_company: LeasingCompany,
) -> None:
    db_session.add(
        LeasingCompanyApplication(
            application_id=draft["application_id"],
            leasing_company_id=leasing_company.id,
            status="submitted",
        )
    )
    await db_session.flush()

    cmd = UpdateConditionsCommand(
        application_id=draft["application_id"],
        actor_id=client_user.id,
        actor_role="carcraft_employee",
        actor_company_id=None,
        down_payment=Decimal("500000"),
        down_payment_percent=30.0,
        lease_term_months=36,
    )

    result = await handle_update_conditions(cmd, db_session)

    app = result["application"]
    assert app["down_payment"] == Decimal("500000")
    assert app["down_payment_percent"] == 30.0
    assert app["lease_term_months"] == 36


# ---------------------------------------------------------------------------
# Listing: clients/dealers keep the parent application after LC dispatch
# ---------------------------------------------------------------------------


async def test_list_keeps_parent_application_visible_once_dispatched(
    db_session: AsyncSession,
    client_user: User,
    client_company: Company,
    draft: dict,
    leasing_company: LeasingCompany,
) -> None:
    # Before dispatch: client sees the application.
    before = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=client_user.id,
            actor_role="client",
            actor_company_id=client_company.id,
            actor_leasing_company_id=None,
        ),
        db_session,
    )
    ids_before = {a["id"] for a in before["applications"]}
    assert draft["application_id"] in ids_before

    # Admin creates an LC child row; LC then takes it into work.
    db_session.add(
        LeasingCompanyApplication(
            application_id=draft["application_id"],
            leasing_company_id=leasing_company.id,
            status="under_review",
        )
    )
    await db_session.flush()

    after = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=client_user.id,
            actor_role="client",
            actor_company_id=client_company.id,
            actor_leasing_company_id=None,
        ),
        db_session,
    )
    ids_after = {a["id"] for a in after["applications"]}
    assert draft["application_id"] in ids_after
    listed = next(
        a for a in after["applications"] if a["id"] == draft["application_id"]
    )
    assert listed["lc_summary"]


async def test_list_applications_includes_client_company_display_fields(
    db_session: AsyncSession,
    client_user: User,
    client_company: Company,
    draft: dict,
) -> None:
    result = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=client_user.id,
            actor_role="client",
            actor_company_id=client_company.id,
            actor_leasing_company_id=None,
        ),
        db_session,
    )

    app = next(
        item
        for item in result["applications"]
        if item["id"] == draft["application_id"]
    )
    assert app["company_name"] == client_company.name
    assert app["company_inn"] == client_company.inn


# ---------------------------------------------------------------------------
# Questionnaire → company sync
# ---------------------------------------------------------------------------


async def test_update_questionnaire_syncs_company_fields(
    db_session: AsyncSession,
    client_user: User,
    client_company: Company,
    draft: dict,
) -> None:
    """When questionnaire fields overlap with companies columns the
    parent company row is updated as well.
    """
    app_id = draft["application_id"]
    payload = {
        "full_company_name": "Synced Name LLC",
        "short_company_name": "Synced",
        "legal_address": "Synced Legal",
        "actual_address": "Synced Actual",
        "phone": "+7 111 222-33-44",
        "email": "synced@example.com",
        "website": "https://synced.example.com",
        "tax_system": "ОСН",
    }

    await handle_update_questionnaire(
        UpdateQuestionnaireCommand(
            application_id=app_id,
            actor_id=client_user.id,
            actor_role="client",
            actor_company_id=client_company.id,
            payload=payload,
        ),
        db_session,
    )
    await db_session.commit()

    from sqlalchemy import select
    stmt = select(Company).where(Company.id == client_company.id)
    refreshed = (await db_session.execute(stmt)).scalar_one()
    assert refreshed.name == "Synced Name LLC"
    assert refreshed.full_name == "Synced Name LLC"
    assert refreshed.short_name == "Synced"
    assert refreshed.legal_address == "Synced Legal"
    assert refreshed.actual_address == "Synced Actual"
    assert refreshed.phone == "+7 111 222-33-44"
    assert refreshed.email == "synced@example.com"
    assert refreshed.website == "https://synced.example.com"
    assert refreshed.tax_system == "ОСН"


async def test_draft_sets_created_by(
    db_session: AsyncSession,
    client_user: User,
    client_company: Company,
) -> None:
    cmd = CreateDraftCommand(
        source_type="platform",
        actor_id=client_user.id,
        actor_role="client",
        actor_company_id=client_user.company_id,
        company_id=client_company.id,
        name="Created By Test",
        email="createdby@test.local",
        vehicles=[
            ApplicationVehiclePayload(
                modification_id="MOD-CREATED-BY", quantity=1, custom_price=Decimal("100")
            )
        ],
    )
    result = await handle_create_draft(cmd, db_session)
    row = await db_session.get(LeasingApplication, result["application_id"])
    assert row is not None
    assert row.created_by == client_user.id


async def test_client_without_company_can_update_own_draft_questionnaire(
    db_session: AsyncSession,
    client_company: Company,
) -> None:
    user = User(
        phone="+76660006666",
        email="client_no_co_p16@test.local",
        name="Phase16 Client No Co",
        role="client",
        is_active=True,
        company_id=None,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=user.id,
            company_id=client_company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    await db_session.flush()

    cmd = CreateDraftCommand(
        source_type="platform",
        actor_id=user.id,
        actor_role="client",
        actor_company_id=None,
        company_id=client_company.id,
        name="No Co Draft",
        email="noco@test.local",
        vehicles=[
            ApplicationVehiclePayload(
                modification_id="MOD-NOCO", quantity=1, custom_price=Decimal("100")
            )
        ],
    )
    draft = await handle_create_draft(cmd, db_session)

    result = await handle_update_questionnaire(
        UpdateQuestionnaireCommand(
            application_id=draft["application_id"],
            actor_id=user.id,
            actor_role="client",
            actor_company_id=None,
            payload={"legal_form": "ООО"},
        ),
        db_session,
    )
    assert result["questionnaire"] is not None


async def test_dealer_creates_draft_for_client_company_payload_without_link(
    db_session: AsyncSession,
) -> None:
    dealer_company = Company(name="P16 Dealer Co", company_type="dealer")
    db_session.add(dealer_company)
    await db_session.flush()
    dealer_user = User(
        phone="+766****1601",
        email="p16-dealer-client-company@test.local",
        name="Phase16 Dealer",
        role="dealer",
        is_active=True,
        company_id=dealer_company.id,
    )
    db_session.add(dealer_user)
    await db_session.flush()

    result = await handle_create_draft(
        CreateDraftCommand(
            source_type="platform",
            actor_id=dealer_user.id,
            actor_role="dealer",
            actor_company_id=dealer_company.id,
            company_id=None,
            company={
                "name": "P16 External Client",
                "full_name": "ООО P16 External Client",
                "inn": "7716010001",
                "kpp": "771601001",
                "ogrn": "1027700160101",
                "legal_address": "Москва, ул. Клиентская, 1",
                "actual_address": "Москва, ул. Клиентская, 2",
                "phone": "+7 495 160-10-01",
                "email": "client1601@example.com",
                "manager_name": "Иванов Иван",
                "entity_type": "LEGAL",
            },
            name="Dealer client company draft",
            email="draft1601@example.com",
            vehicles=[
                ApplicationVehiclePayload(
                    modification_id="MOD-DEALER-CLIENT",
                    quantity=1,
                    custom_price=Decimal("100"),
                )
            ],
        ),
        db_session,
    )

    app = await db_session.get(LeasingApplication, result["application_id"])
    assert app is not None
    assert app.company_id is not None
    client_company = await db_session.get(Company, app.company_id)
    assert client_company is not None
    assert client_company.inn == "7716010001"
    assert app.company_id == client_company.id
    assert app.dealer_company_id == dealer_company.id
    link = await db_session.get(UserCompany, (dealer_user.id, client_company.id))
    assert link is None


async def test_dealer_can_continue_client_company_draft_without_client_company_link(
    db_session: AsyncSession,
) -> None:
    dealer_company = Company(name="P16 Dealer Continue Co", company_type="dealer")
    db_session.add(dealer_company)
    await db_session.flush()
    dealer_user = User(
        phone="+76662119601",
        email="p16-dealer-continue@test.local",
        name="Phase16 Dealer Continue",
        role="dealer",
        is_active=True,
        company_id=dealer_company.id,
    )
    db_session.add(dealer_user)
    await db_session.flush()

    draft = await handle_create_draft(
        CreateDraftCommand(
            source_type="platform",
            actor_id=dealer_user.id,
            actor_role="dealer",
            actor_company_id=dealer_company.id,
            company_id=None,
            company={
                "name": "P16 Continue Client",
                "inn": "7721196001",
                "kpp": "772101001",
                "ogrn": "1027721196001",
                "legal_address": "Москва, ул. Продолжения, 1",
            },
            name="Dealer continue draft",
            email="continue@example.com",
            vehicles=[
                ApplicationVehiclePayload(
                    modification_id="MOD-DEALER-CONTINUE",
                    quantity=1,
                    custom_price=Decimal("100"),
                )
            ],
        ),
        db_session,
    )

    app = await db_session.get(LeasingApplication, draft["application_id"])
    assert app is not None
    client_company_id = app.company_id
    assert client_company_id is not None
    assert await db_session.get(UserCompany, (dealer_user.id, client_company_id)) is None

    questionnaire = await handle_update_questionnaire(
        UpdateQuestionnaireCommand(
            application_id=draft["application_id"],
            actor_id=dealer_user.id,
            actor_role="dealer",
            actor_company_id=dealer_company.id,
            payload={"legal_form": "ООО", "legal_address": "Москва"},
        ),
        db_session,
    )
    assert questionnaire["questionnaire"] is not None

    conditions = await handle_update_conditions(
        UpdateConditionsCommand(
            application_id=draft["application_id"],
            actor_id=dealer_user.id,
            actor_role="dealer",
            actor_company_id=dealer_company.id,
            lease_term_months=36,
            down_payment_percent=20,
        ),
        db_session,
    )
    assert conditions["application"]["lease_term_months"] == 36

    lcs = await handle_update_leasing_companies(
        UpdateLeasingCompaniesCommand(
            application_id=draft["application_id"],
            actor_id=dealer_user.id,
            actor_role="dealer",
            actor_company_id=dealer_company.id,
            leasing_company_ids=[],
        ),
        db_session,
    )
    assert lcs["application"]["selected_leasing_companies"] == []

    listed = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=dealer_user.id,
            actor_role="dealer",
            actor_company_id=dealer_company.id,
            page=1,
            limit=50,
        ),
        db_session,
    )
    assert any(item["id"] == draft["application_id"] for item in listed["applications"])


async def test_dealer_cannot_reassign_client_company_on_dealer_owned_draft(
    db_session: AsyncSession,
) -> None:
    dealer_company = Company(name="P16 Dealer Reassign Co", company_type="dealer")
    other_client_company = Company(
        name="P16 Other Client",
        inn="7721196003",
        company_type="other",
    )
    db_session.add_all([dealer_company, other_client_company])
    await db_session.flush()
    dealer_user = User(
        phone="+76662119602",
        email="p16-dealer-reassign@test.local",
        name="Phase16 Dealer Reassign",
        role="dealer",
        is_active=True,
        company_id=dealer_company.id,
    )
    db_session.add(dealer_user)
    await db_session.flush()

    draft = await handle_create_draft(
        CreateDraftCommand(
            source_type="platform",
            actor_id=dealer_user.id,
            actor_role="dealer",
            actor_company_id=dealer_company.id,
            company_id=None,
            company={
                "name": "P16 Original Client",
                "inn": "7721196002",
                "kpp": "772101002",
                "ogrn": "1027721196002",
                "legal_address": "Москва, ул. Исходная, 1",
            },
            name="Dealer reassign draft",
            email="reassign@example.com",
            vehicles=[
                ApplicationVehiclePayload(
                    modification_id="MOD-DEALER-REASSIGN",
                    quantity=1,
                    custom_price=Decimal("100"),
                )
            ],
        ),
        db_session,
    )

    with pytest.raises(ServiceError):
        await handle_update_company(
            UpdateCompanyCommand(
                application_id=draft["application_id"],
                actor_id=dealer_user.id,
                actor_role="dealer",
                actor_company_id=dealer_company.id,
                company_id=other_client_company.id,
            ),
            db_session,
        )


async def test_dealer_company_payload_without_inn_fails(
    db_session: AsyncSession,
) -> None:
    dealer_company = Company(name="P16 Dealer Missing Inn", company_type="dealer")
    db_session.add(dealer_company)
    await db_session.flush()
    dealer_user = User(
        phone="+766****1602",
        email="p16-dealer-no-inn@test.local",
        name="Phase16 Dealer No Inn",
        role="dealer",
        is_active=True,
        company_id=dealer_company.id,
    )
    db_session.add(dealer_user)
    await db_session.flush()

    with pytest.raises(ApplicationNotSubmittableError) as exc_info:
        await handle_create_draft(
            CreateDraftCommand(
                source_type="platform",
                actor_id=dealer_user.id,
                actor_role="dealer",
                actor_company_id=dealer_company.id,
                company_id=None,
                company={"name": "Только свободный текст"},
                vehicles=[
                    ApplicationVehiclePayload(
                        modification_id="MOD-DEALER-NO-INN",
                        quantity=1,
                        custom_price=Decimal("100"),
                    )
                ],
            ),
            db_session,
        )

    assert str(exc_info.value) == "Для создания заявки на компанию клиента выберите компанию из списка"


async def test_non_dealer_company_payload_does_not_bypass_permission(
    db_session: AsyncSession,
) -> None:
    client_company = Company(name="P16 Client Own Strict", company_type="other")
    forbidden_company = Company(name="P16 Forbidden Strict", company_type="other")
    db_session.add_all([client_company, forbidden_company])
    await db_session.flush()
    client_user = User(
        phone="+766****1603",
        email="p16-client-payload-bypass@test.local",
        name="Phase16 Client Payload Bypass",
        role="client",
        is_active=True,
        company_id=client_company.id,
    )
    db_session.add(client_user)
    await db_session.flush()

    with pytest.raises(ServiceError) as exc_info:
        await handle_create_draft(
            CreateDraftCommand(
                source_type="platform",
                actor_id=client_user.id,
                actor_role="client",
                actor_company_id=client_company.id,
                company_id=forbidden_company.id,
                company={
                    "name": "P16 Payload Company Ignored",
                    "inn": "7716010003",
                },
                vehicles=[
                    ApplicationVehiclePayload(
                        modification_id="MOD-CLIENT-BYPASS",
                        quantity=1,
                        custom_price=Decimal("100"),
                    )
                ],
            ),
            db_session,
        )

    assert exc_info.value.status_code == 403


async def test_dealer_old_company_id_path_still_works(
    db_session: AsyncSession,
) -> None:
    dealer_company = Company(name="P16 Dealer Old Path", company_type="dealer")
    db_session.add(dealer_company)
    await db_session.flush()
    dealer_user = User(
        phone="+766****1604",
        email="p16-dealer-old-path@test.local",
        name="Phase16 Dealer Old Path",
        role="dealer",
        is_active=True,
        company_id=dealer_company.id,
    )
    db_session.add(dealer_user)
    await db_session.flush()

    result = await handle_create_draft(
        CreateDraftCommand(
            source_type="platform",
            actor_id=dealer_user.id,
            actor_role="dealer",
            actor_company_id=dealer_company.id,
            company_id=dealer_company.id,
            vehicles=[
                ApplicationVehiclePayload(
                    modification_id="MOD-DEALER-OLD-PATH",
                    quantity=1,
                    custom_price=Decimal("100"),
                )
            ],
        ),
        db_session,
    )

    app = await db_session.get(LeasingApplication, result["application_id"])
    assert app is not None
    assert app.company_id == dealer_company.id
    assert app.dealer_company_id == dealer_company.id


async def test_application_detail_exposes_business_status_labels(
    db_session: AsyncSession,
    draft: dict,
    leasing_company: LeasingCompany,
) -> None:
    db_session.add(
        LeasingCompanyApplication(
            application_id=draft["application_id"],
            leasing_company_id=leasing_company.id,
            status="deal",
        )
    )
    await db_session.flush()

    app = await app_repo.get_by_id(db_session, draft["application_id"])

    assert app is not None
    assert app["application_status"] == "active"
    assert app["application_status_label"] == "Активна"
    assert app["group_status"] == "deal"
    assert app["group_status_label"] == "Сделка"


async def test_lca_list_enriches_leasing_company_from_company_table(
    db_session: AsyncSession,
    client_user: User,
    client_company: Company,
    draft: dict,
    leasing_company: LeasingCompany,
    lc_company: Company,
) -> None:
    lc_company.name = "Реальная Лизинговая Компания"
    lc_company.inn = "7711223344"
    db_session.add(
        LeasingCompanyApplication(
            application_id=draft["application_id"],
            leasing_company_id=leasing_company.id,
            status="approved_scoring",
        )
    )
    await db_session.flush()

    result = await handle_list_lca(
        ListLcaQuery(
            actor_id=client_user.id,
            actor_role="client",
            actor_company_id=client_company.id,
            application_id=draft["application_id"],
            page=1,
            limit=10,
        ),
        db_session,
    )

    assert result["items"][0]["leasing_company_name"] == "Реальная Лизинговая Компания"
    assert result["items"][0]["leasing_company_inn"] == "7711223344"


async def test_application_list_exposes_closed_group_status_when_all_offers_closed(
    db_session: AsyncSession,
    draft: dict,
    client_user: User,
    leasing_company: LeasingCompany,
) -> None:
    db_session.add(
        LeasingCompanyApplication(
            application_id=draft["application_id"],
            leasing_company_id=leasing_company.id,
            status="rejected_prescoring",
        )
    )
    await db_session.flush()

    apps, _ = await app_repo.list_for_user(
        db_session,
        user_id=client_user.id,
        role="carcraft_employee",
        company_id=client_user.company_id,
        page=1,
        limit=20,
    )
    app = next(item for item in apps if item["id"] == draft["application_id"])

    assert app["group_status"] == "closed"
    assert app["group_status_label"] == "Закрыта"


async def test_application_list_keeps_group_active_for_mixed_non_deal_offers(
    db_session: AsyncSession,
    draft: dict,
    client_user: User,
    leasing_company: LeasingCompany,
) -> None:
    db_session.add(
        LeasingCompanyApplication(
            application_id=draft["application_id"],
            leasing_company_id=leasing_company.id,
            status="under_review",
        )
    )
    await db_session.flush()

    apps, _ = await app_repo.list_for_user(
        db_session,
        user_id=client_user.id,
        role="carcraft_employee",
        company_id=client_user.company_id,
        page=1,
        limit=20,
    )
    app = next(item for item in apps if item["id"] == draft["application_id"])

    assert app["group_status"] == "active"
    assert app["group_status_label"] == "Активна"


@pytest.mark.asyncio
async def test_update_vehicle_stock_validation_preserves_original_request(
    db_session: AsyncSession, client_user: User, draft: dict,
) -> None:
    from domain.errors import InsufficientVehiclesError

    vehicle = Vehicle(status='available', is_available=True, base_price=1000)
    db_session.add(vehicle)
    await db_session.flush()
    command = UpdateVehiclesCommand(
        application_id=draft['application_id'], actor_id=client_user.id,
        actor_role='client', actor_company_id=client_user.company_id,
        vehicles=[ApplicationVehiclePayload(vehicle_id=vehicle.id, quantity=1, custom_price=Decimal('1000'))],
    )
    await handle_update_vehicles(command, db_session)
    before = await app_repo.list_application_vehicles(db_session, draft['application_id'])
    command.vehicles[0].quantity = 5
    with pytest.raises(InsufficientVehiclesError):
        await handle_update_vehicles(command, db_session)
    after = await app_repo.list_application_vehicles(db_session, draft['application_id'])
    assert [(v['id'], v['quantity']) for v in after] == [(v['id'], v['quantity']) for v in before]
    command.vehicles[0].allow_overstock = True
    await handle_update_vehicles(command, db_session)
    after = await app_repo.list_application_vehicles(db_session, draft['application_id'])
    assert after[0]['quantity'] == 5
    assert after[0]['requested_quantity'] == 1


@pytest.mark.asyncio
async def test_update_vehicle_respects_persisted_storefront_even_with_overstock(
    db_session: AsyncSession, client_user: User, draft: dict,
) -> None:
    from infrastructure.models.storefronts import Storefront

    storefront = Storefront(slug=f'isolated-{uuid4().hex}', is_default=False, is_active=True, version=1)
    vehicle = Vehicle(status='available', is_available=True)
    db_session.add_all([storefront, vehicle])
    await db_session.flush()
    await app_repo.update_application_fields(db_session, draft['application_id'], fields={'storefront_id': storefront.id})
    with pytest.raises(ApplicationNotSubmittableError):
        await handle_update_vehicles(UpdateVehiclesCommand(
            application_id=draft['application_id'], actor_id=client_user.id,
            actor_role='client', actor_company_id=client_user.company_id,
            vehicles=[ApplicationVehiclePayload(vehicle_id=vehicle.id, quantity=5, allow_overstock=True)],
        ), db_session)
