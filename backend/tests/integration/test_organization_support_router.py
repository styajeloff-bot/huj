"""Organization-scoped read access to support programs."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import null
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.auth import generate_tokens
from infrastructure.models.companies import (
    Company,
    DistributorDealerLink,
    LeasingCompany,
    LeasingCompanyUser,
)
from infrastructure.models.compensations import CompensationTemplateModel
from infrastructure.models.support import (
    DealerGroup,
    DealerGroupMember,
    SupportProgram,
    SupportProgramCompatibility,
    SupportProgramDealerGroup,
    SupportProgramDistributor,
    SupportProgramLeasingCompany,
)
from infrastructure.models.users import User
from presentation.routers import organization_support as router_module


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_router_maps_application_errors_to_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = AsyncMock(side_effect=ServiceError("Поддержки недоступны", 409))
    monkeypatch.setattr(
        router_module,
        "handle_list_organization_support_programs",
        handler,
    )

    with pytest.raises(HTTPException) as exc_info:
        await router_module.list_organization_support_programs(
            user={"id": uuid4(), "role": "dealer", "company_id": uuid4()},
            session=AsyncMock(),
            page=1,
            limit=20,
            search=None,
            mark_id=None,
            model_id=None,
            is_active=None,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Поддержки недоступны"


@pytest.mark.parametrize("program_has_distributor", [True, False])
async def test_dealer_sees_only_supports_linked_to_own_company(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_user: User,
    program_has_distributor: bool,
) -> None:
    distributor = Company(name="Support distributor", company_type="distributor")
    own_dealer = Company(name="Support dealer own", company_type="dealer")
    foreign_dealer = Company(name="Support dealer foreign", company_type="dealer")
    db_session.add_all([distributor, own_dealer, foreign_dealer])
    await db_session.flush()

    actor = User(
        phone="+76662184801",
        email="support-dealer-own@test.local",
        name="Support dealer",
        role="dealer",
        company_id=own_dealer.id,
        is_active=True,
    )
    own_group = DealerGroup(
        distributor_company_id=distributor.id,
        name="Own dealer group",
        created_by=employee_user.id,
        is_active=True,
    )
    foreign_group = DealerGroup(
        distributor_company_id=distributor.id,
        name="Foreign dealer group",
        created_by=employee_user.id,
        is_active=True,
    )
    db_session.add_all([actor, own_group, foreign_group])
    await db_session.flush()

    own_support = SupportProgram(
        name="Own dealer support",
        distributor_id=distributor.id if program_has_distributor else None,
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 1000},
        is_active=True,
    )
    foreign_support = SupportProgram(
        name="Foreign dealer support",
        distributor_id=distributor.id if program_has_distributor else None,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 2000},
        is_active=True,
    )
    legacy_own_support = SupportProgram(
        name="Legacy own dealer support",
        distributor_id=distributor.id if program_has_distributor else None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        dealer_group_id=own_group.id,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 3000},
        is_active=True,
    )
    legacy_foreign_support = SupportProgram(
        name="Legacy foreign dealer support",
        distributor_id=distributor.id if program_has_distributor else None,
        dealer_group_id=foreign_group.id,
        support_type="down_payment_compensation",
        is_active=True,
    )
    db_session.add_all(
        [
            own_support,
            foreign_support,
            legacy_own_support,
            legacy_foreign_support,
            DistributorDealerLink(
                distributor_company_id=distributor.id,
                dealer_company_id=own_dealer.id,
            ),
        ]
    )
    await db_session.flush()
    own_support.support_params = {
        "value_type": "amount",
        "value": 1000,
        "internal_program_id": str(foreign_support.id),
    }
    compatible_left, compatible_right = sorted((own_support.id, foreign_support.id))
    compensation_template = CompensationTemplateModel(
        support_program_id=own_support.id,
        payer="distributor",
        recipient="dealer",
        calculation_base="base_price",
        value_type="sum",
        value=1000,
        payment_schedule_type="days_count",
        created_by=employee_user.id,
    )
    db_session.add_all(
        [
            DealerGroupMember(
                dealer_group_id=own_group.id,
                dealer_company_id=own_dealer.id,
                created_by=employee_user.id,
            ),
            DealerGroupMember(
                dealer_group_id=foreign_group.id,
                dealer_company_id=foreign_dealer.id,
                created_by=employee_user.id,
            ),
            SupportProgramDealerGroup(
                support_program_id=own_support.id,
                dealer_group_id=own_group.id,
            ),
            SupportProgramDealerGroup(
                support_program_id=own_support.id,
                dealer_group_id=foreign_group.id,
            ),
            SupportProgramDealerGroup(
                support_program_id=foreign_support.id,
                dealer_group_id=foreign_group.id,
            ),
            SupportProgramCompatibility(
                support_program_id=compatible_left,
                compatible_support_program_id=compatible_right,
            ),
            compensation_template,
        ]
    )
    await db_session.flush()
    token, _ = generate_tokens(actor.id, "dealer", own_dealer.id)

    response = await client.get("/api/v1/support-programs", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert {item["id"] for item in response.json()["items"]} == {
        str(own_support.id),
        str(legacy_own_support.id),
    }
    assert response.json()["pagination"]["total"] == 2
    shared = next(
        item for item in response.json()["items"] if item["id"] == str(own_support.id)
    )
    assert shared["dealer_group_id"] is None
    assert shared["dealer_group_ids"] == []
    assert shared["dealer_groups"] == []
    assert shared["compatible_support_ids"] == []
    assert shared["bill_of_lading"] is None
    assert shared["support_params"] == {
        "value_type": "amount",
        "value": 1000,
    }
    assert shared["compensation_templates"] == [
        {
            "payer": "distributor",
            "recipient": "dealer",
            "calculation_base": "base_price",
            "value_type": "sum",
            "value": 1000.0,
            "min_amount": None,
            "max_amount": None,
            "min_percent": None,
            "max_percent": None,
            "payment_schedule_type": "days_count",
            "payment_schedule_period": None,
            "payment_schedule_value": None,
            "comment": "",
        }
    ]
    assert str(foreign_group.id) not in response.text
    assert foreign_group.name not in response.text
    assert str(foreign_support.id) not in response.text
    assert str(compensation_template.id) not in response.text
    assert str(employee_user.id) not in response.text

    for page, expected_ids in [
        (1, [str(own_support.id)]),
        (2, [str(legacy_own_support.id)]),
        (3, []),
    ]:
        paginated = await client.get(
            "/api/v1/support-programs",
            headers=_auth(token),
            params={"page": page, "limit": 1, "search": "own", "is_active": "true"},
        )
        assert paginated.status_code == 200, paginated.text
        assert [item["id"] for item in paginated.json()["items"]] == expected_ids
        assert paginated.json()["pagination"]["total"] == 2


async def test_dealer_without_selected_groups_sees_linked_distributor_supports(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    own_distributor = Company(
        name="Fallback support distributor",
        company_type="distributor",
    )
    foreign_distributor = Company(
        name="Foreign fallback distributor",
        company_type="distributor",
    )
    actor_company = Company(
        name="Fallback support dealer",
        company_type="dealer",
    )
    other_dealer = Company(
        name="Other fallback support dealer",
        company_type="dealer",
    )
    db_session.add_all(
        [own_distributor, foreign_distributor, actor_company, other_dealer]
    )
    await db_session.flush()

    actor = User(
        phone="+76662184803",
        email="support-dealer-fallback@test.local",
        name="Fallback support dealer",
        role="dealer",
        company_id=actor_company.id,
        is_active=True,
    )
    other_dealer_group = DealerGroup(
        distributor_company_id=own_distributor.id,
        name="Selected other dealer group",
        created_by=employee_user.id,
        is_active=True,
    )
    db_session.add_all([actor, other_dealer_group])
    await db_session.flush()

    related_support = SupportProgram(
        name="Related distributor support",
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 1000},
        is_active=True,
    )
    legacy_related_support = SupportProgram(
        name="Legacy related distributor support",
        distributor_id=own_distributor.id,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 2000},
        is_active=True,
    )
    foreign_support = SupportProgram(
        name="Foreign distributor support",
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 3000},
        is_active=True,
    )
    restricted_support = SupportProgram(
        name="Restricted distributor support",
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 4000},
        is_active=True,
    )
    support_without_distributor = SupportProgram(
        name="Support without distributor",
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 5000},
        is_active=True,
    )
    db_session.add_all(
        [
            related_support,
            legacy_related_support,
            foreign_support,
            restricted_support,
            support_without_distributor,
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            DistributorDealerLink(
                distributor_company_id=own_distributor.id,
                dealer_company_id=actor_company.id,
            ),
            DistributorDealerLink(
                distributor_company_id=own_distributor.id,
                dealer_company_id=other_dealer.id,
            ),
            DealerGroupMember(
                dealer_group_id=other_dealer_group.id,
                dealer_company_id=other_dealer.id,
                created_by=employee_user.id,
            ),
            SupportProgramDistributor(
                support_program_id=related_support.id,
                distributor_id=own_distributor.id,
            ),
            SupportProgramDistributor(
                support_program_id=foreign_support.id,
                distributor_id=foreign_distributor.id,
            ),
            SupportProgramDistributor(
                support_program_id=restricted_support.id,
                distributor_id=own_distributor.id,
            ),
            SupportProgramDealerGroup(
                support_program_id=restricted_support.id,
                dealer_group_id=other_dealer_group.id,
            ),
        ]
    )
    await db_session.flush()
    token, _ = generate_tokens(actor.id, "dealer", actor_company.id)

    response = await client.get("/api/v1/support-programs", headers=_auth(token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert {item["id"] for item in body["items"]} == {
        str(related_support.id),
        str(legacy_related_support.id),
    }
    assert body["pagination"]["total"] == 2
    assert str(foreign_support.id) not in response.text
    assert str(restricted_support.id) not in response.text
    assert str(support_without_distributor.id) not in response.text


async def test_leasing_company_sees_only_visible_supports_linked_to_it(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    own_company = Company(name="Support LC own", company_type="leasing_company")
    foreign_company = Company(name="Support LC foreign", company_type="leasing_company")
    db_session.add_all([own_company, foreign_company])
    await db_session.flush()
    own_lc = LeasingCompany(company_id=own_company.id, is_active=True)
    foreign_lc = LeasingCompany(company_id=foreign_company.id, is_active=True)
    actor = User(
        phone="+76662184802",
        email="support-lc-own@test.local",
        name="Support LC",
        role="leasing_company",
        company_id=own_company.id,
        is_active=True,
    )
    own_support = SupportProgram(
        name="Own LC support",
        support_type="leasing_interest_compensation",
        support_params={"value_type": "percent", "value": 1},
        show_to_leasing_company=True,
        is_active=True,
    )
    hidden_support = SupportProgram(
        name="Hidden own LC support",
        support_type="leasing_interest_compensation",
        support_params={"value_type": "percent", "value": 2},
        show_to_leasing_company=False,
        is_active=True,
    )
    foreign_support = SupportProgram(
        name="Foreign LC support",
        support_type="leasing_interest_compensation",
        support_params={"value_type": "percent", "value": 3},
        show_to_leasing_company=True,
        is_active=True,
    )
    unrestricted_support = SupportProgram(
        name="Unrestricted LC support",
        support_type="leasing_interest_compensation",
        support_params={"value_type": "percent", "value": 4},
        show_to_leasing_company=True,
        is_active=True,
    )
    hidden_unrestricted_support = SupportProgram(
        name="Hidden unrestricted LC support",
        support_type="leasing_interest_compensation",
        support_params={"value_type": "percent", "value": 5},
        show_to_leasing_company=False,
        is_active=True,
    )
    db_session.add_all(
        [
            own_lc,
            foreign_lc,
            actor,
            own_support,
            hidden_support,
            foreign_support,
            unrestricted_support,
            hidden_unrestricted_support,
        ]
    )
    await db_session.flush()
    compatible_left, compatible_right = sorted((own_support.id, foreign_support.id))
    db_session.add_all(
        [
            LeasingCompanyUser(user_id=actor.id, leasing_company_id=own_lc.id),
            SupportProgramLeasingCompany(
                support_program_id=own_support.id,
                leasing_company_id=own_lc.id,
            ),
            SupportProgramLeasingCompany(
                support_program_id=own_support.id,
                leasing_company_id=foreign_lc.id,
            ),
            SupportProgramLeasingCompany(
                support_program_id=hidden_support.id,
                leasing_company_id=own_lc.id,
            ),
            SupportProgramLeasingCompany(
                support_program_id=foreign_support.id,
                leasing_company_id=foreign_lc.id,
            ),
            SupportProgramCompatibility(
                support_program_id=compatible_left,
                compatible_support_program_id=compatible_right,
            ),
        ]
    )
    await db_session.flush()
    token, _ = generate_tokens(actor.id, "leasing_company", own_company.id)

    response = await client.get("/api/v1/support-programs", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert {item["id"] for item in response.json()["items"]} == {
        str(own_support.id),
        str(hidden_support.id),
        str(unrestricted_support.id),
        str(hidden_unrestricted_support.id),
    }
    assert response.json()["pagination"]["total"] == 4
    shared = next(
        item for item in response.json()["items"] if item["id"] == str(own_support.id)
    )
    assert shared["leasing_company_ids"] == []
    assert shared["leasing_companies"] == []
    assert shared["compatible_support_ids"] == []
    assert shared["bill_of_lading"] is None
    assert str(foreign_lc.id) not in response.text
    assert foreign_company.name not in response.text
    assert str(foreign_support.id) not in response.text


async def test_employee_cannot_read_organization_supports(
    client: AsyncClient,
    employee_token: str,
) -> None:
    response = await client.get(
        "/api/v1/support-programs", headers=_auth(employee_token)
    )

    assert response.status_code == 403


@pytest.mark.parametrize("support_link", ["legacy", "m2m", "both"])
@pytest.mark.parametrize(
    "dealer_link", ["direct", "active_group", "inactive_group", "both", "none"]
)
async def test_dealer_sees_unrestricted_supports_of_linked_distributor(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_user: User,
    support_link: str,
    dealer_link: str,
) -> None:
    distributor = Company(name="All dealers distributor", company_type="distributor")
    foreign_distributor = Company(name="Other distributor", company_type="distributor")
    dealer = Company(name="Directly linked dealer", company_type="dealer")
    db_session.add_all([distributor, foreign_distributor, dealer])
    await db_session.flush()
    actor = User(
        phone="+76662184803",
        name="Directly linked dealer",
        role="dealer",
        company_id=dealer.id,
        is_active=True,
    )
    own_support = SupportProgram(
        name="All dealers of own distributor",
        distributor_id=distributor.id if support_link in {"legacy", "both"} else None,
        support_type="down_payment_compensation",
        is_active=True,
    )
    foreign_support = SupportProgram(
        name="All dealers of other distributor",
        distributor_id=foreign_distributor.id,
        support_type="down_payment_compensation",
        is_active=True,
    )
    orphan_support = SupportProgram(
        name="Support without distributor",
        support_type="down_payment_compensation",
        is_active=True,
    )
    db_session.add_all([actor, own_support, foreign_support, orphan_support])
    await db_session.flush()
    if support_link in {"m2m", "both"}:
        db_session.add(
            SupportProgramDistributor(
                support_program_id=own_support.id,
                distributor_id=distributor.id,
            )
        )
    if dealer_link in {"direct", "both"}:
        db_session.add(
            DistributorDealerLink(
                distributor_company_id=distributor.id,
                dealer_company_id=dealer.id,
            )
        )
    if dealer_link in {"active_group", "inactive_group", "both"}:
        group = DealerGroup(
            name="Linked distributor group",
            distributor_company_id=distributor.id,
            created_by=employee_user.id,
            is_active=dealer_link != "inactive_group",
        )
        db_session.add(group)
        await db_session.flush()
        db_session.add(
            DealerGroupMember(
                dealer_group_id=group.id,
                dealer_company_id=dealer.id,
                created_by=employee_user.id,
            )
        )
    await db_session.flush()
    token, _ = generate_tokens(actor.id, "dealer", dealer.id)

    response = await client.get("/api/v1/support-programs", headers=_auth(token))

    assert response.status_code == 200, response.text
    if dealer_link in {"direct", "active_group", "both"}:
        assert [item["id"] for item in response.json()["items"]] == [
            str(own_support.id)
        ]
        assert response.json()["pagination"]["total"] == 1
    else:
        assert response.json()["items"] == []
        assert response.json()["pagination"]["total"] == 0


async def test_client_cannot_read_organization_supports(
    client: AsyncClient,
    client_token: str,
) -> None:
    response = await client.get("/api/v1/support-programs", headers=_auth(client_token))

    assert response.status_code == 403


@pytest.mark.parametrize("visible_flag", [True, None])
async def test_any_leasing_company_sees_supports_regardless_of_display_flag(
    client: AsyncClient,
    db_session: AsyncSession,
    visible_flag: bool | None,
) -> None:
    visible_support = SupportProgram(
        name="Support for any leasing company",
        support_type="leasing_interest_compensation",
        show_to_leasing_company=visible_flag if visible_flag is not None else null(),
        is_active=True,
    )
    hidden_support = SupportProgram(
        name="Hidden support for any leasing company",
        support_type="leasing_interest_compensation",
        show_to_leasing_company=False,
        is_active=True,
    )
    db_session.add_all([visible_support, hidden_support])
    await db_session.flush()
    for index in range(2):
        company = Company(name=f"Any LC {index}", company_type="leasing_company")
        db_session.add(company)
        await db_session.flush()
        leasing_company = LeasingCompany(company_id=company.id, is_active=True)
        actor = User(
            phone=f"+7666218481{index}",
            name=f"Any LC actor {index}",
            role="leasing_company",
            company_id=company.id,
            is_active=True,
        )
        db_session.add_all([leasing_company, actor])
        await db_session.flush()
        db_session.add(
            LeasingCompanyUser(
                user_id=actor.id,
                leasing_company_id=leasing_company.id,
            )
        )
        await db_session.flush()
        token, _ = generate_tokens(actor.id, "leasing_company", company.id)

        response = await client.get("/api/v1/support-programs", headers=_auth(token))

        assert response.status_code == 200, response.text
        assert {item["id"] for item in response.json()["items"]} == {
            str(visible_support.id),
            str(hidden_support.id),
        }
        assert response.json()["pagination"]["total"] == 2
