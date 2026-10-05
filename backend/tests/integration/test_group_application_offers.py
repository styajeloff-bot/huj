"""Tests for group-application card backend: LC selection, КП cancel, LCA filters."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.leasing_company_application import (
    _TRANSITIONS,
    LCA_STATUS_APPROVED_FINAL,
    LCA_STATUS_APPROVED_FINAL_ANOTHER_COND,
    LCA_STATUS_DEAL,
    LCA_STATUS_SELECTED_LC,
)
from infrastructure.auth import generate_tokens
from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyApplication,
    LeasingProposal,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.users import User

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    csrf = "test-csrf-token"
    return {
        "Cookie": f"accessToken={token}; csrfToken={csrf}",
        "X-CSRF-Token": csrf,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def group_app_fixture(db_session: AsyncSession) -> dict[str, Any]:
    """Group-application card scenario: client company + user, two LCs,
    one leasing application and two offers (approved_final / submitted)."""
    client_company = Company(name="Group App Client Co", company_type="other")
    db_session.add(client_company)
    await db_session.flush()

    client_user = User(
        phone="+76660009901",
        email="groupclient@test.local",
        name="Group Client",
        role="client",
        is_active=True,
        company_id=client_company.id,
    )
    db_session.add(client_user)
    await db_session.flush()

    lc_company_1 = Company(name="Group LC One", company_type="leasing_company")
    lc_company_2 = Company(name="Group LC Two", company_type="leasing_company")
    db_session.add_all([lc_company_1, lc_company_2])
    await db_session.flush()

    lc1 = LeasingCompany(company_id=lc_company_1.id, is_active=True)
    lc2 = LeasingCompany(company_id=lc_company_2.id, is_active=True)
    db_session.add_all([lc1, lc2])
    await db_session.flush()

    application = LeasingApplication(
        company_id=client_company.id,
        created_by=client_user.id,
        name="Group App",
        email="groupapp@test.local",
        status="active",
        selected_leasing_companies=[lc1.id, lc2.id],
    )
    db_session.add(application)
    await db_session.flush()

    lca_approved_final = LeasingCompanyApplication(
        application_id=application.id,
        leasing_company_id=lc1.id,
        status="approved_final",
    )
    lca_submitted = LeasingCompanyApplication(
        application_id=application.id,
        leasing_company_id=lc2.id,
        status="submitted",
    )
    db_session.add_all([lca_approved_final, lca_submitted])
    await db_session.flush()

    # Two offers in approved_scoring, each with a complete preliminary КП
    # (uq_leasing_proposals_lca_kind allows one preliminary per LCA).
    lca_scoring_accepted = LeasingCompanyApplication(
        application_id=application.id,
        leasing_company_id=lc1.id,
        status="approved_scoring",
    )
    lca_scoring_fresh = LeasingCompanyApplication(
        application_id=application.id,
        leasing_company_id=lc2.id,
        status="approved_scoring",
    )
    db_session.add_all([lca_scoring_accepted, lca_scoring_fresh])
    await db_session.flush()

    # All fields required by LeasingProposal.is_complete() are filled.
    proposal_money: dict[str, Any] = {
        "total_amount": Decimal("5000000.00"),
        "down_payment": Decimal("1000000.00"),
        "down_payment_percent": Decimal("20.00"),
        "lease_term_months": 36,
        "monthly_payment": Decimal("150000.00"),
    }
    proposal_preliminary_accepted = LeasingProposal(
        leasing_company_application_id=lca_scoring_accepted.id,
        kind="preliminary",
        client_decision_action="accepted",
        client_decision_at=datetime.now(UTC),
        **proposal_money,
    )
    proposal_preliminary_fresh = LeasingProposal(
        leasing_company_application_id=lca_scoring_fresh.id,
        kind="preliminary",
        **proposal_money,
    )
    db_session.add_all([proposal_preliminary_accepted, proposal_preliminary_fresh])
    await db_session.flush()

    # Offer with a preliminary approval on other conditions: no submitted_at,
    # must still be visible to the client in leasing-responses (Task 4).
    lca_scoring_another_cond = LeasingCompanyApplication(
        application_id=application.id,
        leasing_company_id=lc1.id,
        status="approved_scoring_another_cond",
        submitted_at=None,
    )
    db_session.add(lca_scoring_another_cond)
    await db_session.flush()

    # Second application of the same client company with its own offer —
    # noise for the ?application_id= filter test (Task 4).
    other_application = LeasingApplication(
        company_id=client_company.id,
        created_by=client_user.id,
        name="Group App Other",
        email="groupapp-other@test.local",
        status="active",
        selected_leasing_companies=[lc1.id],
    )
    db_session.add(other_application)
    await db_session.flush()

    other_application_lca = LeasingCompanyApplication(
        application_id=other_application.id,
        leasing_company_id=lc1.id,
        status="submitted",
    )
    db_session.add(other_application_lca)
    await db_session.flush()

    token, _ = generate_tokens(client_user.id, "client", client_company.id)

    return {
        "company": client_company,
        "client_user": client_user,
        "client_token": cast("str", token),
        "leasing_companies": [lc1, lc2],
        "application": application,
        "lca_approved_final": lca_approved_final,
        "lca_submitted": lca_submitted,
        "lca_scoring_accepted": lca_scoring_accepted,
        "lca_scoring_fresh": lca_scoring_fresh,
        "lca_scoring_another_cond": lca_scoring_another_cond,
        "proposal_preliminary_accepted": proposal_preliminary_accepted,
        "proposal_preliminary_fresh": proposal_preliminary_fresh,
        "other_application": other_application,
        "other_application_lca": other_application_lca,
    }


@pytest_asyncio.fixture
async def other_client_token(db_session: AsyncSession) -> str:
    """Token for a client user from a different (foreign) company."""
    other_company = Company(name="Other Group Co", company_type="other")
    db_session.add(other_company)
    await db_session.flush()

    other_user = User(
        phone="+76660009902",
        email="othergroupclient@test.local",
        name="Other Group Client",
        role="client",
        is_active=True,
        company_id=other_company.id,
    )
    db_session.add(other_user)
    await db_session.flush()

    token, _ = generate_tokens(other_user.id, "client", other_company.id)
    return cast("str", token)


class TestSelectedLcTransitions:
    async def test_approved_final_allows_selected_lc(self) -> None:
        assert LCA_STATUS_SELECTED_LC in _TRANSITIONS[LCA_STATUS_APPROVED_FINAL]

    async def test_approved_final_another_cond_allows_selected_lc(self) -> None:
        assert (
            LCA_STATUS_SELECTED_LC
            in _TRANSITIONS[LCA_STATUS_APPROVED_FINAL_ANOTHER_COND]
        )

    async def test_selected_lc_allows_deal(self) -> None:
        assert LCA_STATUS_DEAL in _TRANSITIONS[LCA_STATUS_SELECTED_LC]


class TestSelectLeasingCompany:
    async def test_client_selects_final_approved_lc(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        group_app_fixture: dict[str, Any],
    ) -> None:
        """Клиент выбирает ЛК у оффера в статусе approved_final → selected_lc."""
        app_id = group_app_fixture["application"].id
        lca = group_app_fixture["lca_approved_final"]
        token = group_app_fixture["client_token"]

        resp = await client.post(
            f"/api/v1/applications/{app_id}/lca/{lca.id}/select",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "selected_lc"
        assert body["leasing_company_application_id"] == str(lca.id)

    async def test_select_rejected_for_submitted_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        group_app_fixture: dict[str, Any],
    ) -> None:
        """Оффер в статусе submitted выбрать нельзя — 409/400."""
        app_id = group_app_fixture["application"].id
        lca = group_app_fixture["lca_submitted"]
        token = group_app_fixture["client_token"]

        resp = await client.post(
            f"/api/v1/applications/{app_id}/lca/{lca.id}/select",
            headers=_auth(token),
        )
        assert resp.status_code in (400, 409)

    async def test_second_select_rejected_when_lc_already_selected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        group_app_fixture: dict[str, Any],
    ) -> None:
        """ТЗ №18 п.2.10.2.2: по заявке можно выбрать только одну ЛК."""
        application = group_app_fixture["application"]
        token = group_app_fixture["client_token"]
        lc2 = group_app_fixture["leasing_companies"][1]

        second_final = LeasingCompanyApplication(
            application_id=application.id,
            leasing_company_id=lc2.id,
            status="approved_final",
        )
        db_session.add(second_final)
        await db_session.flush()

        first = await client.post(
            f"/api/v1/applications/{application.id}/lca/"
            f"{group_app_fixture['lca_approved_final'].id}/select",
            headers=_auth(token),
        )
        assert first.status_code == 200

        second = await client.post(
            f"/api/v1/applications/{application.id}/lca/{second_final.id}/select",
            headers=_auth(token),
        )
        assert second.status_code == 400
        assert "уже выбрана" in second.json()["detail"]

    async def test_select_foreign_application_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        group_app_fixture: dict[str, Any],
        other_client_token: str,
    ) -> None:
        """Чужой клиент не может выбрать ЛК."""
        app_id = group_app_fixture["application"].id
        lca = group_app_fixture["lca_approved_final"]

        resp = await client.post(
            f"/api/v1/applications/{app_id}/lca/{lca.id}/select",
            headers=_auth(other_client_token),
        )
        assert resp.status_code in (403, 404)


class TestCancelProposalAcceptance:
    async def test_cancel_clears_accepted_decision(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        group_app_fixture: dict[str, Any],
    ) -> None:
        """accepted → cancelled очищает client_decision_* (ТЗ №18, п. 2.10.1)."""
        app_id = group_app_fixture["application"].id
        proposal = group_app_fixture["proposal_preliminary_accepted"]
        token = group_app_fixture["client_token"]

        resp = await client.post(
            f"/api/v1/applications/{app_id}/proposals/{proposal.id}/decision",
            json={"action": "cancelled"},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["client_decision_action"] is None
        assert body["proposal"]["client_decision_action"] is None
        assert body["proposal"]["client_decision_at"] is None
        assert body["proposal"]["client_decision_comment"] is None

    async def test_cancel_without_acceptance_is_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        group_app_fixture: dict[str, Any],
    ) -> None:
        """Отменить можно только ранее принятое КП."""
        app_id = group_app_fixture["application"].id
        proposal = group_app_fixture["proposal_preliminary_fresh"]
        token = group_app_fixture["client_token"]

        resp = await client.post(
            f"/api/v1/applications/{app_id}/proposals/{proposal.id}/decision",
            json={"action": "cancelled"},
            headers=_auth(token),
        )
        assert resp.status_code in (400, 409)


class TestLcaListApplicationFilter:
    async def test_filter_by_application_id(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        group_app_fixture: dict[str, Any],
    ) -> None:
        """?application_id= возвращает только офферы этой заявки."""
        app_id = group_app_fixture["application"].id
        token = group_app_fixture["client_token"]

        resp = await client.get(
            f"/api/v1/leasing-company-applications/?application_id={app_id}&limit=100",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert items, "должны вернуться офферы заявки"
        assert all(i["application_id"] == str(app_id) for i in items)
        leasing_company_names = {i.get("leasing_company_name") for i in items}
        assert {"Group LC One", "Group LC Two"} <= leasing_company_names

    async def test_without_filter_returns_all_company_offers(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        group_app_fixture: dict[str, Any],
    ) -> None:
        """Без фильтра клиент видит офферы всех своих заявок."""
        app_id = group_app_fixture["application"].id
        other_app_id = group_app_fixture["other_application"].id
        token = group_app_fixture["client_token"]

        resp = await client.get(
            "/api/v1/leasing-company-applications/?limit=100",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        app_ids = {i["application_id"] for i in resp.json()["items"]}
        assert {str(app_id), str(other_app_id)} <= app_ids


class TestLeasingResponsesIncludeScoringAnotherCond:
    async def test_scoring_another_cond_visible(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        group_app_fixture: dict[str, Any],
    ) -> None:
        """LCA в approved_scoring_another_cond без submitted_at виден клиенту."""
        app_id = group_app_fixture["application"].id
        token = group_app_fixture["client_token"]

        resp = await client.get(
            f"/api/v1/applications/{app_id}/leasing-responses",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        decisions = [r["decision"] for r in resp.json()["responses"]]
        assert "approved_scoring_another_cond" in decisions


class TestClientApprovalOffers:
    async def test_leasing_responses_include_proposal_centric_approval_offers(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        group_app_fixture: dict[str, Any],
    ) -> None:
        """approval_offers contains only complete КП of matching kind/status."""
        application = group_app_fixture["application"]
        other_application = group_app_fixture["other_application"]
        token = group_app_fixture["client_token"]
        lc1, lc2 = group_app_fixture["leasing_companies"]

        preliminary_money: dict[str, Any] = {
            "total_amount": Decimal("6100000.00"),
            "down_payment": Decimal("1220000.00"),
            "down_payment_percent": Decimal("20.00"),
            "lease_term_months": 36,
            "monthly_payment": Decimal("166000.00"),
        }
        final_money: dict[str, Any] = {
            "total_amount": Decimal("6200000.00"),
            "down_payment": Decimal("1240000.00"),
            "down_payment_percent": Decimal("20.00"),
            "lease_term_months": 48,
            "monthly_payment": Decimal("144000.00"),
        }

        preliminary_another_cond = LeasingProposal(
            leasing_company_application_id=group_app_fixture[
                "lca_scoring_another_cond"
            ].id,
            kind="preliminary",
            **preliminary_money,
        )
        preliminary_incomplete_lca = LeasingCompanyApplication(
            application_id=application.id,
            leasing_company_id=lc2.id,
            status="approved_scoring",
        )
        final_another_cond_lca = LeasingCompanyApplication(
            application_id=application.id,
            leasing_company_id=lc1.id,
            status="approved_final_another_cond",
        )
        final_selected_lca = LeasingCompanyApplication(
            application_id=application.id,
            leasing_company_id=lc2.id,
            status="selected_lc",
        )
        final_incomplete_lca = LeasingCompanyApplication(
            application_id=application.id,
            leasing_company_id=lc1.id,
            status="selected_lc",
        )
        other_application_lca = LeasingCompanyApplication(
            application_id=other_application.id,
            leasing_company_id=lc1.id,
            status="approved_scoring",
        )
        db_session.add_all(
            [
                preliminary_another_cond,
                preliminary_incomplete_lca,
                final_another_cond_lca,
                final_selected_lca,
                final_incomplete_lca,
                other_application_lca,
            ]
        )
        await db_session.flush()

        preliminary_incomplete = LeasingProposal(
            leasing_company_application_id=preliminary_incomplete_lca.id,
            kind="preliminary",
            total_amount=Decimal("6300000.00"),
            down_payment=Decimal("1260000.00"),
            down_payment_percent=Decimal("20.00"),
            lease_term_months=36,
            monthly_payment=None,
        )
        preliminary_wrong_status = LeasingProposal(
            leasing_company_application_id=group_app_fixture[
                "lca_approved_final"
            ].id,
            kind="preliminary",
            **preliminary_money,
        )
        final_approved = LeasingProposal(
            leasing_company_application_id=group_app_fixture[
                "lca_approved_final"
            ].id,
            kind="final",
            **final_money,
        )
        final_another_cond = LeasingProposal(
            leasing_company_application_id=final_another_cond_lca.id,
            kind="final",
            **final_money,
        )
        final_selected = LeasingProposal(
            leasing_company_application_id=final_selected_lca.id,
            kind="final",
            **final_money,
        )
        final_incomplete = LeasingProposal(
            leasing_company_application_id=final_incomplete_lca.id,
            kind="final",
            total_amount=Decimal("6400000.00"),
            down_payment=Decimal("1280000.00"),
            down_payment_percent=Decimal("20.00"),
            lease_term_months=48,
            monthly_payment=None,
        )
        final_wrong_status = LeasingProposal(
            leasing_company_application_id=group_app_fixture[
                "lca_scoring_fresh"
            ].id,
            kind="final",
            **final_money,
        )
        other_application_proposal = LeasingProposal(
            leasing_company_application_id=other_application_lca.id,
            kind="preliminary",
            **preliminary_money,
        )
        db_session.add_all(
            [
                preliminary_incomplete,
                preliminary_wrong_status,
                final_approved,
                final_another_cond,
                final_selected,
                final_incomplete,
                final_wrong_status,
                other_application_proposal,
            ]
        )
        await db_session.flush()

        resp = await client.get(
            f"/api/v1/applications/{application.id}/leasing-responses",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "responses" in body
        assert "approval_offers" in body

        approval_offers = body["approval_offers"]
        assert set(approval_offers) == {"preliminary", "final"}

        preliminary_ids = {
            row["proposal"]["id"] for row in approval_offers["preliminary"]
        }
        assert preliminary_ids == {
            str(group_app_fixture["proposal_preliminary_accepted"].id),
            str(group_app_fixture["proposal_preliminary_fresh"].id),
            str(preliminary_another_cond.id),
        }
        assert str(preliminary_incomplete.id) not in preliminary_ids
        assert str(preliminary_wrong_status.id) not in preliminary_ids
        assert str(other_application_proposal.id) not in preliminary_ids

        final_ids = {row["proposal"]["id"] for row in approval_offers["final"]}
        assert final_ids == {
            str(final_approved.id),
            str(final_another_cond.id),
            str(final_selected.id),
        }
        assert str(final_incomplete.id) not in final_ids
        assert str(final_wrong_status.id) not in final_ids

        sample = next(
            row
            for row in approval_offers["preliminary"]
            if row["proposal"]["id"] == str(preliminary_another_cond.id)
        )
        assert sample["lca"]["id"] == str(
            group_app_fixture["lca_scoring_another_cond"].id
        )
        assert sample["lca"]["status"] == "approved_scoring_another_cond"
        assert sample["leasing_company"] == {
            "id": str(lc1.id),
            "name": "Group LC One",
            "inn": None,
        }
        assert sample["proposal"]["kind"] == "preliminary"
        assert any(
            diff["field"] == "total_amount"
            and diff["offered"] is not None
            and diff["changed"] is True
            for diff in sample["proposal"]["diff"]
        )
