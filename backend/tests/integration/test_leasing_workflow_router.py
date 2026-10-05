"""Integration tests for the new LC ↔ client workflow endpoints.

Covers:

- ``POST /api/v1/leasing/applications/{id}/take-in-work``  (Phase 1.4)
- ``POST /api/v1/leasing/applications/{id}/issue``         (Phase 4.1)
- ``GET  /api/v1/applications/{id}/leasing-responses/{lc_id}/pdf`` (Phase 2.1)
- ``POST /api/v1/applications/{id}/proposals/{pid}/decision``      (Phase 1.6)
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
    LeasingCompanyApplication,
    LeasingProposal,
)
from infrastructure.models.companies import (
    Company,
    LeasingCompany,
    LeasingCompanyUser,
)
from infrastructure.models.documents import Document
from infrastructure.models.lca_status_history import (
    LeasingCompanyApplicationStatusHistory,
)
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
    SpecialEquipmentLeasingPaymentSchedule,
    SpecialEquipmentPurchaseOrder,
)
from infrastructure.models.users import User, UserCompany
from infrastructure.services.object_storage import get_object_storage
from tests.fakes.object_storage import FakeObjectStorage
from tests.special_equipment_factories import special_equipment_directory

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    """Cookie-based auth — Bearer is locked to external-api role on this stack."""
    csrf = "test-csrf-token"
    return {
        "Cookie": f"accessToken={token}; csrfToken={csrf}",
        "X-CSRF-Token": csrf,
    }


# ---------------------------------------------------------------------------
# Fixtures — applicant + LC + tokens. Mirror test_leasing_router but with
# distinct identifiers so the suites don't share state.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def wf_applicant_company(db_session: AsyncSession) -> Company:
    c = Company(
        name="WF Applicant Co",
        company_type="other",
        inn="7700001001",
    )
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def wf_lc_company(db_session: AsyncSession) -> Company:
    c = Company(
        name="WF LC Provider",
        company_type="leasing_company",
        inn="7700009001",
    )
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def wf_other_lc_company(db_session: AsyncSession) -> Company:
    c = Company(
        name="WF Other LC",
        company_type="leasing_company",
        inn="7700009002",
    )
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def wf_leasing_company(
    db_session: AsyncSession, wf_lc_company: Company
) -> LeasingCompany:
    lc = LeasingCompany(company_id=wf_lc_company.id, is_active=True)
    db_session.add(lc)
    await db_session.flush()
    return lc


@pytest_asyncio.fixture
async def wf_other_leasing_company(
    db_session: AsyncSession, wf_other_lc_company: Company
) -> LeasingCompany:
    lc = LeasingCompany(
        company_id=wf_other_lc_company.id, is_active=True
    )
    db_session.add(lc)
    await db_session.flush()
    return lc


@pytest_asyncio.fixture
async def wf_lc_user(
    db_session: AsyncSession,
    wf_lc_company: Company,
    wf_leasing_company: LeasingCompany,
) -> User:
    u = User(
        phone="+76660009001",
        email="wflc@test.local",
        name="WF LC User",
        role="leasing_company",
        is_active=True,
        company_id=wf_lc_company.id,
    )
    db_session.add(u)
    await db_session.flush()
    db_session.add(
        LeasingCompanyUser(
            user_id=u.id,
            leasing_company_id=wf_leasing_company.id,
        )
    )
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def wf_other_lc_user(
    db_session: AsyncSession,
    wf_other_lc_company: Company,
    wf_other_leasing_company: LeasingCompany,
) -> User:
    u = User(
        phone="+76660009002",
        email="wfotherlc@test.local",
        name="WF Other LC User",
        role="leasing_company",
        is_active=True,
        company_id=wf_other_lc_company.id,
    )
    db_session.add(u)
    await db_session.flush()
    db_session.add(
        LeasingCompanyUser(
            user_id=u.id,
            leasing_company_id=wf_other_leasing_company.id,
        )
    )
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def wf_client_user(
    db_session: AsyncSession, wf_applicant_company: Company
) -> User:
    u = User(
        phone="+76660009100",
        email="wfclient@test.local",
        name="WF Client",
        role="client",
        is_active=True,
        company_id=wf_applicant_company.id,
    )
    db_session.add(u)
    await db_session.flush()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def wf_dealer_company(db_session: AsyncSession) -> Company:
    c = Company(
        name="WF Dealer",
        company_type="dealer",
        inn="7700009200",
    )
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def wf_dealer_user(
    db_session: AsyncSession, wf_dealer_company: Company
) -> User:
    u = User(
        phone="+766****9200",
        email="wfdealer@test.local",
        name="WF Dealer User",
        role="dealer",
        is_active=True,
        company_id=wf_dealer_company.id,
    )
    db_session.add(u)
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def wf_lc_token(wf_lc_user: User, wf_lc_company: Company) -> str:
    token, _ = generate_tokens(
        wf_lc_user.id, "leasing_company", wf_lc_company.id
    )
    return token


@pytest_asyncio.fixture
async def wf_other_lc_token(
    wf_other_lc_user: User, wf_other_lc_company: Company
) -> str:
    token, _ = generate_tokens(
        wf_other_lc_user.id,
        "leasing_company",
        wf_other_lc_company.id,
    )
    return token


@pytest_asyncio.fixture
async def wf_client_token(
    wf_client_user: User, wf_applicant_company: Company
) -> str:
    token, _ = generate_tokens(
        wf_client_user.id, "client", wf_applicant_company.id
    )
    return token


@pytest_asyncio.fixture
async def wf_dealer_token(wf_dealer_user: User, wf_dealer_company: Company) -> str:
    token, _ = generate_tokens(
        wf_dealer_user.id, "dealer", wf_dealer_company.id
    )
    return token


async def _seed(
    db_session: AsyncSession,
    *,
    applicant_company: Company,
    lc: LeasingCompany,
    parent_status: str = "active",
    lca_status: str = "under_review",
    submitted_at: bool = False,
) -> tuple[LeasingApplication, LeasingCompanyApplication]:
    app = LeasingApplication(
        company_id=applicant_company.id,
        name="WF Test",
        email="wftest@test.local",
        status=parent_status,
        selected_leasing_companies=[lc.id],
    )
    db_session.add(app)
    await db_session.flush()
    link = LeasingCompanyApplication(
        application_id=app.id,
        leasing_company_id=lc.id,
        status=lca_status,
    )
    if submitted_at:
        from datetime import UTC, datetime

        link.submitted_at = datetime.now(UTC)  # type: ignore[assignment]
    db_session.add(link)
    await db_session.flush()
    return app, link


# ---------------------------------------------------------------------------
# take-in-work
# ---------------------------------------------------------------------------


async def test_take_in_work_response_capability_and_safe_retry(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
) -> None:
    app, link = await _seed(
        db_session, applicant_company=wf_applicant_company, lc=wf_leasing_company,
        parent_status="active", lca_status="submitted",
    )
    url = f"/api/v1/leasing/applications/{app.id}"
    initial = await client.get(f"{url}/response", headers=_auth(wf_lc_token))
    assert initial.status_code == 200, initial.text
    assert initial.json()["can_review"] is True
    assert initial.json()["link"]["status"] == "submitted"
    first = await client.post(f"{url}/take-in-work", headers=_auth(wf_lc_token))
    assert first.status_code == 200, first.text
    assert first.json()["replayed"] is False
    replay = await client.post(f"{url}/take-in-work", headers=_auth(wf_lc_token))
    assert replay.json()["lca_status"] == "under_review"
    assert replay.json()["replayed"] is True
    link.status = "approved_final"
    await db_session.flush()
    stale = await client.post(f"{url}/take-in-work", headers=_auth(wf_lc_token))
    assert stale.json()["lca_status"] == "approved_final"
    assert stale.json()["replayed"] is True
    assert stale.json()["message"] != "Заявка взята в работу"


@pytest.mark.parametrize("secondary_company", [False, True])
async def test_read_only_lc_cannot_take_application_in_work(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_user: User,
    wf_lc_token: str,
    wf_other_lc_company: Company,
    secondary_company: bool,
) -> None:
    app, _ = await _seed(
        db_session, applicant_company=wf_applicant_company, lc=wf_leasing_company,
        lca_status="submitted",
    )
    db_session.add(UserCompany(
        user_id=wf_lc_user.id, company_id=wf_leasing_company.company_id,
        can_view_applications=True, can_create_applications=False,
    ))
    if secondary_company:
        wf_lc_user.company_id = wf_other_lc_company.id
        wf_lc_token, _ = generate_tokens(wf_lc_user.id, wf_lc_user.role, wf_other_lc_company.id)
    await db_session.flush()
    url = f"/api/v1/leasing/applications/{app.id}"
    selector = f"?leasing_company_id={wf_leasing_company.id}"
    response = await client.get(f"{url}/response{selector}", headers=_auth(wf_lc_token))
    assert response.status_code == 200, response.text
    assert response.json()["can_review"] is False
    take = await client.post(f"{url}/take-in-work{selector}", headers=_auth(wf_lc_token))
    assert take.status_code == 403, take.text
    draft = await client.put(f"{url}/proposals/preliminary{selector}", headers=_auth(wf_lc_token), json={"monthly_payment": 10000})
    assert draft.status_code == 403, draft.text
    delete_draft = await client.delete(f"{url}/proposals/preliminary{selector}", headers=_auth(wf_lc_token))
    assert delete_draft.status_code == 403, delete_draft.text
    decision = await client.put(f"{url}/decision{selector}", headers=_auth(wf_lc_token), json={"action": "approve", "kind": "preliminary"})
    assert decision.status_code == 403, decision.text
    pdf = await client.post(f"{url}/response-pdf{selector}", headers=_auth(wf_lc_token), files={"file": ("quote.pdf", b"%PDF-1.4\n", "application/pdf")})
    assert pdf.status_code == 403, pdf.text
    delete_pdf = await client.delete(f"{url}/response-pdf{selector}", headers=_auth(wf_lc_token))
    assert delete_pdf.status_code == 403, delete_pdf.text
    for kind in ("preliminary", "final"):
        slot_pdf = await client.post(f"{url}/proposals/{kind}/pdf{selector}", headers=_auth(wf_lc_token), files={"file": ("quote.pdf", b"%PDF-1.4\n", "application/pdf")})
        assert slot_pdf.status_code == 403, slot_pdf.text
        delete_slot_pdf = await client.delete(f"{url}/proposals/{kind}/pdf{selector}", headers=_auth(wf_lc_token))
        assert delete_slot_pdf.status_code == 403, delete_slot_pdf.text
    unchanged = await client.get(f"{url}/response{selector}", headers=_auth(wf_lc_token))
    assert unchanged.json()["link"]["status"] == "submitted"


@pytest.mark.parametrize("kind, expected_status", [("preliminary", "approved_scoring"), ("final", "approved_final")])
@pytest.mark.parametrize("secondary_company", [False, True])
async def test_lc_draft_and_pdf_survive_explicit_take_before_decision(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_user: User,
    wf_lc_token: str,
    wf_other_lc_company: Company,
    secondary_company: bool,
    kind: str,
    expected_status: str,
) -> None:
    from main import app as fastapi_app

    storage = FakeObjectStorage()
    fastapi_app.dependency_overrides[get_object_storage] = lambda: storage
    application, _ = await _seed(
        db_session, applicant_company=wf_applicant_company,
        lc=wf_leasing_company, lca_status="submitted",
    )
    db_session.add(UserCompany(
        user_id=wf_lc_user.id, company_id=wf_leasing_company.company_id,
        can_view_applications=True, can_create_applications=True,
    ))
    if secondary_company:
        wf_lc_user.company_id = wf_other_lc_company.id
        wf_lc_token, _ = generate_tokens(wf_lc_user.id, wf_lc_user.role, wf_other_lc_company.id)
    await db_session.flush()
    url = f"/api/v1/leasing/applications/{application.id}"
    selector = f"?leasing_company_id={wf_leasing_company.id}"
    headers = _auth(wf_lc_token)
    draft = await client.put(f"{url}/proposals/{kind}{selector}", headers=headers, json={
        "total_amount": 100000, "down_payment": 20000, "down_payment_percent": 20, "lease_term_months": 36,
        "buyout_amount": 0, "monthly_payment": 15000,
    })
    assert draft.status_code == 200, draft.text
    uploaded = await client.post(f"{url}/proposals/{kind}/pdf{selector}", headers=headers, files={"file": ("quote.pdf", b"%PDF-1.4\n", "application/pdf")})
    assert uploaded.status_code == 200, uploaded.text
    forbidden_transition = await client.put(f"{url}/decision{selector}", headers=headers, json={"action": "approve", "kind": kind})
    assert forbidden_transition.status_code == 400, forbidden_transition.text
    assert "submitted →" in forbidden_transition.json()["detail"]
    take = await client.post(f"{url}/take-in-work{selector}", headers=headers)
    assert take.status_code == 200, take.text
    current = await client.get(f"{url}/response{selector}", headers=headers)
    assert current.status_code == 200, current.text
    assert current.json()["can_review"] is True
    assert current.json()["proposals"][0]["pdf_file_name"] == "quote.pdf"
    assert Decimal(str(current.json()["proposals"][0]["monthly_payment"])) == Decimal("15000")
    decision = await client.put(f"{url}/decision{selector}", headers=headers, json={"action": "approve", "kind": kind})
    assert decision.status_code == 200, decision.text
    current = await client.get(f"{url}/response{selector}", headers=headers)
    assert current.json()["link"]["status"] == expected_status
    assert current.json()["proposals"][0]["pdf_file_name"] == "quote.pdf"
    fastapi_app.dependency_overrides.pop(get_object_storage)


async def test_proposal_pdf_slots_remain_independent_and_readable_after_write_permission_revoked(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_user: User,
    wf_lc_token: str,
) -> None:
    from main import app as fastapi_app

    storage = FakeObjectStorage()
    fastapi_app.dependency_overrides[get_object_storage] = lambda: storage
    application, _ = await _seed(
        db_session, applicant_company=wf_applicant_company,
        lc=wf_leasing_company, lca_status="submitted",
    )
    membership = UserCompany(
        user_id=wf_lc_user.id, company_id=wf_leasing_company.company_id,
        can_view_applications=True, can_create_applications=True,
    )
    db_session.add(membership)
    await db_session.flush()
    url = f"/api/v1/leasing/applications/{application.id}"
    selector = f"?leasing_company_id={wf_leasing_company.id}"
    headers = _auth(wf_lc_token)
    for kind, monthly in (("preliminary", 15000), ("final", 25000)):
        draft = await client.put(f"{url}/proposals/{kind}{selector}", headers=headers, json={
            "total_amount": 100000, "down_payment": 20000, "down_payment_percent": 20,
            "lease_term_months": 36, "buyout_amount": 0, "monthly_payment": monthly,
        })
        assert draft.status_code == 200, draft.text
        uploaded = await client.post(f"{url}/proposals/{kind}/pdf{selector}", headers=headers,
            files={"file": (f"{kind}.pdf", f"%PDF-1.4\n{kind}".encode(), "application/pdf")})
        assert uploaded.status_code == 200, uploaded.text
    current = await client.get(f"{url}/response{selector}", headers=headers)
    assert current.status_code == 200, current.text
    assert current.json()["link"]["status"] == "submitted"
    proposals = {item["kind"]: item for item in current.json()["proposals"]}
    assert proposals["preliminary"]["pdf_file_name"] == "preliminary.pdf"
    assert proposals["final"]["pdf_file_name"] == "final.pdf"
    assert Decimal(str(proposals["final"]["monthly_payment"])) == Decimal("25000")
    for kind in ("preliminary", "final"):
        downloaded = await client.get(f"{url}/proposals/{kind}/pdf{selector}", headers=headers)
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == f"%PDF-1.4\n{kind}".encode()
    removed = await client.delete(f"{url}/proposals/preliminary/pdf{selector}", headers=headers)
    assert removed.status_code == 204, removed.text
    current = await client.get(f"{url}/response{selector}", headers=headers)
    proposals = {item["kind"]: item for item in current.json()["proposals"]}
    assert proposals["preliminary"]["pdf_file_name"] is None
    assert proposals["final"]["pdf_file_name"] == "final.pdf"
    membership.can_create_applications = False
    await db_session.flush()
    downloaded = await client.get(f"{url}/proposals/final/pdf{selector}", headers=headers)
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == b"%PDF-1.4\nfinal"
    forbidden_upload = await client.post(f"{url}/proposals/final/pdf{selector}", headers=headers,
        files={"file": ("replacement.pdf", b"%PDF-1.4\nreplacement", "application/pdf")})
    assert forbidden_upload.status_code == 403, forbidden_upload.text
    forbidden_delete = await client.delete(f"{url}/proposals/final/pdf{selector}", headers=headers)
    assert forbidden_delete.status_code == 403, forbidden_delete.text
    downloaded = await client.get(f"{url}/proposals/final/pdf{selector}", headers=headers)
    assert downloaded.content == b"%PDF-1.4\nfinal"
    fastapi_app.dependency_overrides.pop(get_object_storage)


async def test_take_in_work_happy_path(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
) -> None:
    app, _ = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="submitted",
    )

    response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/take-in-work",
        headers=_auth(wf_lc_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["parent_status"] == "active"
    assert body["lca_status"] == "under_review"
    assert body["message"] == "Заявка взята в работу"


async def test_take_in_work_wrong_parent_status(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
) -> None:
    app, _ = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="rejected",
    )

    response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/take-in-work",
        headers=_auth(wf_lc_token),
    )
    assert response.status_code == 200


async def test_take_in_work_foreign_lc(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_other_lc_token: str,
) -> None:
    app, _ = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
    )

    response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/take-in-work",
        headers=_auth(wf_other_lc_token),
    )
    # Other LC has no LCA row on this app → 404
    assert response.status_code == 404


async def test_take_in_work_anon_unauthorized(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
) -> None:
    app, _ = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
    )

    response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/take-in-work",
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# proposals
# ---------------------------------------------------------------------------


async def test_upsert_preliminary_proposal_creates_default_position(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="under_review",
    )

    response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/proposals/preliminary",
        headers=_auth(wf_lc_token),
        json={
            "total_amount": 2284929,
            "down_payment": 411287,
            "down_payment_percent": 18,
            "lease_term_months": 36,
            "buyout_amount": 430938,
            "monthly_payment": 1190485,
            "total_cost": 43699685,
            "rate": None,
            "markup": None,
            "total_interest": None,
            "vat_refund": None,
            "profit_tax_savings": None,
            "total_savings": None,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["leasing_company_application_id"] == str(link.id)
    assert body["kind"] == "preliminary"
    assert body["position"] == 1
    assert Decimal(str(body["total_amount"])) == Decimal("2284929.00")
    assert Decimal(str(body["total_interest"])) == Decimal("41003469.00")


async def test_upsert_proposal_reconstructs_total_cost_for_interest(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
) -> None:
    app, _link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="under_review",
    )

    response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/proposals/final",
        headers=_auth(wf_lc_token),
        json={
            "total_amount": 2000000,
            "down_payment": 400000,
            "lease_term_months": 36,
            "buyout_amount": 100000,
            "monthly_payment": 75000,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert Decimal(str(body["total_cost"])) == Decimal("3200000.00")
    assert Decimal(str(body["total_interest"])) == Decimal("800000.00")


async def test_upsert_proposal_partial_update_recalculates_interest(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
) -> None:
    app, _link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="under_review",
    )

    create_response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/proposals/final",
        headers=_auth(wf_lc_token),
        json={
            "total_amount": 2000000,
            "down_payment": 400000,
            "lease_term_months": 36,
            "buyout_amount": 0,
            "monthly_payment": 75000,
            "total_cost": 3100000,
        },
    )
    assert create_response.status_code == 200, create_response.text

    update_response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/proposals/final",
        headers=_auth(wf_lc_token),
        json={"total_cost": 3300000},
    )

    assert update_response.status_code == 200, update_response.text
    body = update_response.json()
    assert Decimal(str(body["total_amount"])) == Decimal("2000000.00")
    assert Decimal(str(body["total_cost"])) == Decimal("3300000.00")
    assert Decimal(str(body["total_interest"])) == Decimal("900000.00")


async def test_upsert_proposal_partial_update_backfills_missing_total_cost(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="under_review",
    )
    db_session.add(
        LeasingProposal(
            leasing_company_application_id=link.id,
            kind="preliminary",
            position=1,
            total_amount=2_000_000,
            down_payment=400_000,
            lease_term_months=36,
            buyout_amount=100_000,
            monthly_payment=75_000,
            total_cost=None,
            total_interest=None,
        )
    )
    await db_session.flush()

    response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/proposals/preliminary",
        headers=_auth(wf_lc_token),
        json={"total_amount": 2100000},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert Decimal(str(body["total_amount"])) == Decimal("2100000.00")
    assert Decimal(str(body["total_cost"])) == Decimal("3200000.00")
    assert Decimal(str(body["total_interest"])) == Decimal("700000.00")


# ---------------------------------------------------------------------------
# issue
# ---------------------------------------------------------------------------


async def test_issue_happy_path(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="approved_final",
        submitted_at=True,
    )
    # Final КП accepted by client.
    db_session.add(
        LeasingProposal(
            leasing_company_application_id=link.id,
            kind="final",
            position=1,
            client_decision_action="accepted",
        )
    )
    await db_session.flush()

    response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/issue",
        headers=_auth(wf_lc_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "deal"


async def test_issue_creates_idempotent_special_equipment_leasing_order(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_client_user: User,
    wf_lc_token: str,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="approved_final",
        submitted_at=True,
    )
    app.created_by = wf_client_user.id
    mark, model, modification = special_equipment_directory(
        mark_name=f"Issue mark {uuid.uuid4()}",
        model_name="Leasing excavator",
        modification_name="Issue modification",
    )
    db_session.add_all([mark, model, modification])
    await db_session.flush()
    product = SpecialEquipmentProduct(
        code=f"issue-product-{uuid.uuid4()}",
        modification_id=modification.id,
        seller_company_id=wf_applicant_company.id,
        slug=f"issue-product-{uuid.uuid4()}",
        condition="new",
        vin=None,
        no_vin=True,
        owners_count=None,
        price=Decimal("1000000.00"),
        currency_code="RUB",
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    db_session.add(product)
    await db_session.flush()
    db_session.add(
        SpecialEquipmentApplicationItem(
            application_id=app.id,
            product_id=product.id,
            seller_company_id=wf_applicant_company.id,
            unit_price=Decimal("1000000.00"),
            total_price=Decimal("1000000.00"),
            currency_code="RUB",
            item_snapshot={
                "product_id": str(product.id),
                "mark": mark.name,
                "model": model.name,
                "modification": modification.name,
                "currency_code": "RUB",
            },
            item_status="active",
        )
    )
    db_session.add(
        LeasingProposal(
            leasing_company_application_id=link.id,
            kind="final",
            position=1,
            total_amount=Decimal("1000000.00"),
            down_payment=Decimal("200000.00"),
            down_payment_percent=Decimal("20.00"),
            lease_term_months=24,
            monthly_payment=Decimal("50000.00"),
            total_cost=Decimal("1500000.00"),
            total_interest=Decimal("500000.00"),
            buyout_amount=Decimal("100000.00"),
            client_decision_action="accepted",
        )
    )
    await db_session.flush()

    first = await client.post(
        f"/api/v1/leasing/applications/{app.id}/issue",
        headers=_auth(wf_lc_token),
    )
    assert first.status_code == 200, first.text
    assert first.json()["replayed"] is False
    assert len(first.json()["special_equipment_orders"]) == 1

    order = await db_session.scalar(
        sa.select(SpecialEquipmentPurchaseOrder).where(
            SpecialEquipmentPurchaseOrder.leasing_application_id == app.id
        )
    )
    assert order is not None
    assert order.user_id == wf_client_user.id
    assert order.purchase_type == "leasing"
    assert order.status == "leasing_active"
    assert order.total_price == Decimal("1500000.00")
    schedule = list(
        (
            await db_session.scalars(
                sa.select(SpecialEquipmentLeasingPaymentSchedule)
                .where(
                    SpecialEquipmentLeasingPaymentSchedule.purchase_order_id
                    == order.id
                )
                .order_by(
                    SpecialEquipmentLeasingPaymentSchedule.payment_number
                )
            )
        ).all()
    )
    assert len(schedule) == 26
    assert sum((row.amount for row in schedule), Decimal("0.00")) == Decimal(
        "1500000.00"
    )
    assert all(not row.is_paid and row.payment_id is None for row in schedule)
    await db_session.refresh(product)
    assert product.sale_status == "sold"

    replay = await client.post(
        f"/api/v1/leasing/applications/{app.id}/issue",
        headers=_auth(wf_lc_token),
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["special_equipment_orders"][0]["id"] == str(order.id)
    assert await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(SpecialEquipmentPurchaseOrder)
        .where(SpecialEquipmentPurchaseOrder.leasing_application_id == app.id)
    ) == 1
    assert await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(SpecialEquipmentLeasingPaymentSchedule)
        .where(
            SpecialEquipmentLeasingPaymentSchedule.purchase_order_id == order.id
        )
    ) == 26


async def test_issue_requires_client_acceptance(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="approved_final",
        submitted_at=True,
    )
    # Final КП exists but not yet accepted by the client.
    db_session.add(
        LeasingProposal(
            leasing_company_application_id=link.id,
            kind="final",
            position=1,
        )
    )
    await db_session.flush()

    response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/issue",
        headers=_auth(wf_lc_token),
    )
    assert response.status_code == 400


async def test_issue_wrong_lca_status(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        lca_status="under_review",
    )
    db_session.add(
        LeasingProposal(
            leasing_company_application_id=link.id,
            kind="final",
            position=1,
            client_decision_action="accepted",
        )
    )
    await db_session.flush()

    response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/issue",
        headers=_auth(wf_lc_token),
    )
    assert response.status_code == 400


async def test_issue_foreign_lc_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_other_lc_token: str,
) -> None:
    app, _ = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="approved_final",
    )

    response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/issue",
        headers=_auth(wf_other_lc_token),
    )
    assert response.status_code == 404


async def test_issue_selected_lc_returns_400_without_lifecycle_mutation(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="selected_lc",
    )

    response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/issue",
        headers=_auth(wf_lc_token),
    )

    assert response.status_code == 400
    await db_session.refresh(link)
    await db_session.refresh(app)
    assert link.status == "selected_lc"
    assert app.status == "active"
    assert await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(LeasingCompanyApplicationStatusHistory)
        .where(LeasingCompanyApplicationStatusHistory.lca_id == link.id)
    ) == 0


# ---------------------------------------------------------------------------
# confirm-deal
# ---------------------------------------------------------------------------


async def test_confirm_deal_happy_path_records_history_and_events(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="selected_lc",
    )
    lca_events: list[dict[str, object]] = []
    application_events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "application.commands.leasing.confirm_deal.emit_lca_changed",
        lca_events.append,
    )
    monkeypatch.setattr(
        "application.commands.leasing.confirm_deal.emit_leasing_application_changed",
        application_events.append,
    )

    response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/confirm-deal",
        headers=_auth(wf_lc_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "deal"
    assert response.json()["replayed"] is False
    await db_session.refresh(link)
    await db_session.refresh(app)
    assert link.status == "deal"
    assert app.status == "issued"
    history = await db_session.scalar(
        sa.select(LeasingCompanyApplicationStatusHistory).where(
            LeasingCompanyApplicationStatusHistory.lca_id == link.id,
            LeasingCompanyApplicationStatusHistory.old_status == "selected_lc",
            LeasingCompanyApplicationStatusHistory.new_status == "deal",
        )
    )
    assert history is not None
    assert len(lca_events) == 1
    assert len(application_events) == 1


@pytest.mark.parametrize("selector", ["active_company", "query"])
async def test_confirm_deal_uses_authorized_secondary_lc_context(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_other_leasing_company: LeasingCompany,
    wf_lc_user: User,
    monkeypatch: pytest.MonkeyPatch,
    selector: str,
) -> None:
    original_company_id = wf_lc_user.company_id
    db_session.add(UserCompany(
        user_id=wf_lc_user.id,
        company_id=wf_other_leasing_company.company_id,
        can_view_applications=True,
    ))
    primary_app, _ = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        lca_status="selected_lc",
    )
    target_app, _ = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_other_leasing_company,
        lca_status="selected_lc",
    )
    active_company_id = (
        wf_other_leasing_company.company_id
        if selector == "active_company"
        else original_company_id
    )
    token, _ = generate_tokens(wf_lc_user.id, "leasing_company", active_company_id)
    params = (
        {"leasing_company_id": str(wf_other_leasing_company.id)}
        if selector == "query"
        else {}
    )
    monkeypatch.setattr(
        "application.commands.leasing.confirm_deal.emit_lca_changed",
        lambda _payload: None,
    )
    monkeypatch.setattr(
        "application.commands.leasing.confirm_deal.emit_leasing_application_changed",
        lambda _payload: None,
    )

    response = await client.post(
        f"/api/v1/leasing/applications/{target_app.id}/confirm-deal",
        headers=_auth(token),
        params=params,
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "deal"
    assert response.json()["replayed"] is False
    target_state = await client.get(
        f"/api/v1/leasing/applications/{target_app.id}/response",
        headers=_auth(token),
        params=params,
    )
    assert target_state.status_code == 200, target_state.text
    assert target_state.json()["link"]["leasing_company_id"] == str(wf_other_leasing_company.id)
    assert target_state.json()["link"]["status"] == "deal"
    assert target_state.json()["can_confirm_deal"] is False

    primary_token, _ = generate_tokens(wf_lc_user.id, "leasing_company", original_company_id)
    primary_state = await client.get(
        f"/api/v1/leasing/applications/{primary_app.id}/response",
        headers=_auth(primary_token),
    )
    assert primary_state.status_code == 200, primary_state.text
    assert primary_state.json()["link"]["status"] == "selected_lc"
    await db_session.refresh(wf_lc_user)
    assert wf_lc_user.company_id == original_company_id


async def test_confirm_deal_replay_has_no_duplicate_history_or_events(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="selected_lc",
    )
    lca_events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "application.commands.leasing.confirm_deal.emit_lca_changed",
        lca_events.append,
    )
    monkeypatch.setattr(
        "application.commands.leasing.confirm_deal.emit_leasing_application_changed",
        lambda _payload: None,
    )

    first = await client.post(
        f"/api/v1/leasing/applications/{app.id}/confirm-deal",
        headers=_auth(wf_lc_token),
    )
    replay = await client.post(
        f"/api/v1/leasing/applications/{app.id}/confirm-deal",
        headers=_auth(wf_lc_token),
    )

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert len(lca_events) == 1
    assert await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(LeasingCompanyApplicationStatusHistory)
        .where(
            LeasingCompanyApplicationStatusHistory.lca_id == link.id,
            LeasingCompanyApplicationStatusHistory.old_status == "selected_lc",
            LeasingCompanyApplicationStatusHistory.new_status == "deal",
        )
    ) == 1


async def test_confirm_deal_finalizer_failure_emits_no_history_or_dwh_events(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _ = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="selected_lc",
    )
    lca_events: list[dict[str, object]] = []
    application_events: list[dict[str, object]] = []
    parent_status_events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "application.commands.leasing.confirm_deal.create_leasing_orders_for_issued_application",
        AsyncMock(side_effect=RuntimeError("finalization failed")),
    )
    monkeypatch.setattr(
        "application.commands.leasing.confirm_deal.emit_lca_changed",
        lca_events.append,
    )
    monkeypatch.setattr(
        "application.commands.leasing.confirm_deal.emit_leasing_application_changed",
        application_events.append,
    )
    monkeypatch.setattr(
        "infrastructure.repositories.status_history_repository.emit_leasing_app_status_changed",
        lambda **event: parent_status_events.append(event),
    )

    with pytest.raises(RuntimeError, match="finalization failed"):
        await client.post(
            f"/api/v1/leasing/applications/{app.id}/confirm-deal",
            headers=_auth(wf_lc_token),
        )

    assert lca_events == []
    assert application_events == []
    assert parent_status_events == []


async def test_confirm_deal_rejects_foreign_lc_and_client(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_other_lc_token: str,
    wf_client_token: str,
) -> None:
    app, _ = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        lca_status="selected_lc",
    )

    foreign = await client.post(
        f"/api/v1/leasing/applications/{app.id}/confirm-deal",
        headers=_auth(wf_other_lc_token),
    )
    client_response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/confirm-deal",
        headers=_auth(wf_client_token),
    )

    assert foreign.status_code == 404
    assert client_response.status_code == 403


@pytest.mark.parametrize("access", ["foreign", "permission_denied", "inactive_lc"])
async def test_confirm_deal_query_context_requires_current_target_access(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_other_leasing_company: LeasingCompany,
    wf_lc_user: User,
    wf_lc_token: str,
    access: str,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_other_leasing_company,
        lca_status="selected_lc",
    )
    if access != "foreign":
        db_session.add(UserCompany(
            user_id=wf_lc_user.id,
            company_id=wf_other_leasing_company.company_id,
            can_view_applications=access != "permission_denied",
        ))
    if access == "inactive_lc":
        wf_other_leasing_company.is_active = False
    await db_session.flush()

    response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/confirm-deal",
        headers=_auth(wf_lc_token),
        params={"leasing_company_id": str(wf_other_leasing_company.id)},
    )

    assert response.status_code == 403, response.text
    await db_session.refresh(link)
    await db_session.refresh(app)
    assert link.status == "selected_lc"
    assert app.status == "active"
    assert await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(LeasingCompanyApplicationStatusHistory)
        .where(LeasingCompanyApplicationStatusHistory.lca_id == link.id)
    ) == 0


async def test_confirm_deal_unauthenticated_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="selected_lc",
    )

    response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/confirm-deal"
    )

    assert response.status_code == 401
    await db_session.refresh(link)
    await db_session.refresh(app)
    assert link.status == "selected_lc"
    assert app.status == "active"


async def test_confirm_deal_dealer_returns_403_without_lifecycle_mutation(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_dealer_token: str,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="selected_lc",
    )

    response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/confirm-deal",
        headers=_auth(wf_dealer_token),
    )

    assert response.status_code == 403
    await db_session.refresh(link)
    await db_session.refresh(app)
    assert link.status == "selected_lc"
    assert app.status == "active"
    assert await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(LeasingCompanyApplicationStatusHistory)
        .where(LeasingCompanyApplicationStatusHistory.lca_id == link.id)
    ) == 0


async def test_confirm_deal_rejects_non_selected_status(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
) -> None:
    app, _ = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        lca_status="approved_final",
    )

    response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/confirm-deal",
        headers=_auth(wf_lc_token),
    )

    assert response.status_code == 400


async def test_confirm_deal_with_deal_fields_and_get_application(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_company: Company,
    wf_lc_token: str,
    wf_client_token: str,
) -> None:
    app, _ = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="selected_lc",
    )
    vehicle = ApplicationVehicle(
        application_id=app.id,
        quantity=1,
    )
    db_session.add(vehicle)

    doc_agreement = Document(
        company_id=wf_lc_company.id,
        document_type="signed_lease_agreement",
        file_name="lease_agreement.pdf",
        s3_key="agreements/lease_1.pdf",
        file_size=10240,
    )
    doc_act = Document(
        company_id=wf_lc_company.id,
        document_type="acceptance_transfer_act",
        file_name="acceptance_act.pdf",
        s3_key="acts/act_1.pdf",
        file_size=5120,
    )
    db_session.add_all([doc_agreement, doc_act])
    await db_session.commit()

    payload = {
        "deal_date": "2026-10-01",
        "vehicles": [
            {"vehicle_id": str(vehicle.id), "vin": "XTA00000000000001"}
        ],
        "documents": [
            {"file_id": str(doc_agreement.id), "document_type": "signed_lease_agreement"},
            {"file_id": str(doc_act.id), "document_type": "acceptance_transfer_act"},
        ],
    }

    response = await client.post(
        f"/api/v1/leasing/applications/{app.id}/confirm-deal",
        headers=_auth(wf_lc_token),
        json=payload,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "deal"

    await db_session.refresh(app)
    await db_session.refresh(vehicle)
    assert app.deal_date == date(2026, 10, 1)
    assert len(app.deal_documents or []) == 2
    assert vehicle.vin == "XTA00000000000001"

    # Verify GET /api/v1/applications/{app.id} returns deal details
    get_res = await client.get(
        f"/api/v1/applications/{app.id}",
        headers=_auth(wf_client_token),
    )
    assert get_res.status_code == 200, get_res.text
    app_data = get_res.json()
    assert app_data["deal_date"] == "2026-10-01"
    assert app_data["vehicles"][0]["vin"] == "XTA00000000000001"
    deal_docs = app_data["deal_documents"]
    assert len(deal_docs) == 2
    assert deal_docs[0]["file_name"] == "lease_agreement.pdf"
    assert deal_docs[0]["download_url"] == f"/api/v1/documents/{doc_agreement.id}/content"
    assert deal_docs[1]["file_name"] == "acceptance_act.pdf"
    assert deal_docs[1]["download_url"] == f"/api/v1/documents/{doc_act.id}/content"


async def test_confirm_deal_validation_errors(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_company: Company,
    wf_lc_token: str,
) -> None:
    app, _ = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="selected_lc",
    )
    vehicle = ApplicationVehicle(
        application_id=app.id,
        quantity=1,
    )
    db_session.add(vehicle)

    doc_agreement = Document(
        company_id=wf_lc_company.id,
        document_type="signed_lease_agreement",
        file_name="lease_agreement.pdf",
        s3_key="agreements/lease_1.pdf",
        file_size=10240,
    )
    db_session.add(doc_agreement)
    await db_session.commit()

    # 1. Missing required acceptance_transfer_act
    payload_missing_act = {
        "deal_date": "2026-10-01",
        "vehicles": [
            {"vehicle_id": str(vehicle.id), "vin": "XTA00000000000001"}
        ],
        "documents": [
            {"file_id": str(doc_agreement.id), "document_type": "signed_lease_agreement"}
        ],
    }
    res = await client.post(
        f"/api/v1/leasing/applications/{app.id}/confirm-deal",
        headers=_auth(wf_lc_token),
        json=payload_missing_act,
    )
    assert res.status_code == 400
    assert "Необходимо прикрепить подписанный договор лизинга и акт приёма-передачи" in res.text

    # 2. Missing VIN for vehicle
    payload_missing_vin = {
        "deal_date": "2026-10-01",
        "vehicles": [],
        "documents": [
            {"file_id": str(doc_agreement.id), "document_type": "signed_lease_agreement"},
            {"file_id": str(doc_agreement.id), "document_type": "acceptance_transfer_act"},
        ],
    }
    res2 = await client.post(
        f"/api/v1/leasing/applications/{app.id}/confirm-deal",
        headers=_auth(wf_lc_token),
        json=payload_missing_vin,
    )
    assert res2.status_code == 400
    assert "Не указан VIN-номер" in res2.text

    # 3. Document not found
    fake_doc_id = uuid.uuid4()
    payload_doc_not_found = {
        "deal_date": "2026-10-01",
        "vehicles": [
            {"vehicle_id": str(vehicle.id), "vin": "XTA00000000000001"}
        ],
        "documents": [
            {"file_id": str(doc_agreement.id), "document_type": "signed_lease_agreement"},
            {"file_id": str(fake_doc_id), "document_type": "acceptance_transfer_act"},
        ],
    }
    res3 = await client.post(
        f"/api/v1/leasing/applications/{app.id}/confirm-deal",
        headers=_auth(wf_lc_token),
        json=payload_doc_not_found,
    )
    assert res3.status_code == 400
    assert "не найден" in res3.text


async def test_response_state_exposes_confirm_deal_capability(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_lc_token: str,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        lca_status="selected_lc",
    )

    selected = await client.get(
        f"/api/v1/leasing/applications/{app.id}/response",
        headers=_auth(wf_lc_token),
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["can_confirm_deal"] is True
    assert selected.json()["confirm_deal_disabled_reason"] is None

    link.status = "deal"
    await db_session.commit()
    deal = await client.get(
        f"/api/v1/leasing/applications/{app.id}/response",
        headers=_auth(wf_lc_token),
    )
    assert deal.status_code == 200, deal.text
    assert deal.json()["can_confirm_deal"] is False
    assert deal.json()["confirm_deal_disabled_reason"] == "Сделка уже подтверждена"


# ---------------------------------------------------------------------------
# Client accept / reject of a proposal
# ---------------------------------------------------------------------------


async def test_client_accept_proposal_happy_path(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_client_token: str,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="approved_scoring",
    )
    proposal = LeasingProposal(
        leasing_company_application_id=link.id,
        kind="preliminary",
        position=1,
        total_amount=1_000_000,
        down_payment=200_000,
        down_payment_percent=20,
        lease_term_months=24,
        monthly_payment=40_000,
        total_cost=1_200_000,
        rate=10,
    )
    db_session.add(proposal)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/applications/{app.id}/proposals/{proposal.id}/decision",
        json={"action": "accepted", "comment": "Подходит"},
        headers=_auth(wf_client_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["client_decision_action"] == "accepted"
    # Accepting preliminary leaves LCA at prescoring — LC continues to final.
    assert body["lca_status"] == "approved_scoring"


async def test_client_reject_proposal_closes_lca(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_client_token: str,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="approved_scoring",
    )
    proposal = LeasingProposal(
        leasing_company_application_id=link.id,
        kind="preliminary",
        position=1,
        total_amount=1_000_000,
        down_payment=200_000,
        down_payment_percent=20,
        lease_term_months=24,
        monthly_payment=40_000,
        total_cost=1_200_000,
        rate=10,
    )
    db_session.add(proposal)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/applications/{app.id}/proposals/{proposal.id}/decision",
        json={"action": "rejected", "comment": "Не подходит"},
        headers=_auth(wf_client_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["client_decision_action"] == "rejected"
    assert body["lca_status"] == "closed"


async def test_client_decision_already_decided_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_client_token: str,
) -> None:
    from datetime import UTC, datetime

    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        parent_status="active",
        lca_status="approved_scoring",
    )
    proposal = LeasingProposal(
        leasing_company_application_id=link.id,
        kind="preliminary",
        position=1,
        total_amount=1_000_000,
        down_payment=200_000,
        down_payment_percent=20,
        lease_term_months=24,
        monthly_payment=40_000,
        total_cost=1_200_000,
        rate=10,
        client_decision_action="accepted",
        client_decision_at=datetime.now(UTC),
    )
    db_session.add(proposal)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/applications/{app.id}/proposals/{proposal.id}/decision",
        json={"action": "rejected", "comment": "передумал"},
        headers=_auth(wf_client_token),
    )
    assert response.status_code == 409


async def test_client_decision_unknown_proposal_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_client_token: str,
) -> None:
    app, _ = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
    )
    response = await client.post(
        f"/api/v1/applications/{app.id}/proposals/ffffffff-ffff-ffff-ffff-ffffffffffff/decision",
        json={"action": "accepted"},
        headers=_auth(wf_client_token),
    )
    assert response.status_code == 404


async def test_client_decision_foreign_company_returns_403(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    other_token: str,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        lca_status="approved_scoring",
    )
    proposal = LeasingProposal(
        leasing_company_application_id=link.id,
        kind="preliminary",
        position=1,
        total_amount=1_000_000,
        down_payment=200_000,
        down_payment_percent=20,
        lease_term_months=24,
        monthly_payment=40_000,
        total_cost=1_200_000,
        rate=10,
    )
    db_session.add(proposal)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/applications/{app.id}/proposals/{proposal.id}/decision",
        json={"action": "accepted"},
        headers=_auth(other_token),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# LC response PDF download (client view)
# ---------------------------------------------------------------------------


async def test_lc_response_pdf_generates_fallback_when_missing_upload(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_client_token: str,
) -> None:
    app, link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        lca_status="approved_scoring",
    )
    app.display_number = "7700001001-1806-001"
    db_session.add(
        LeasingProposal(
            leasing_company_application_id=link.id,
            kind="preliminary",
            position=1,
            total_amount=1_200_000,
            down_payment=240_000,
            down_payment_percent=20,
            lease_term_months=24,
            monthly_payment=50_000,
            total_cost=1_200_000,
            total_interest=120_000,
            buyout_amount=10_000,
        )
    )
    db_session.add(
        LeasingProposal(
            leasing_company_application_id=link.id,
            kind="final",
            position=1,
            total_amount=1_150_000,
            down_payment=230_000,
            down_payment_percent=20,
            lease_term_months=24,
            monthly_payment=48_000,
            total_cost=1_150_000,
            total_interest=110_000,
            buyout_amount=10_000,
        )
    )
    await db_session.flush()

    response = await client.get(
        f"/api/v1/applications/{app.id}/leasing-responses/"
        f"{wf_leasing_company.id}/pdf",
        headers=_auth(wf_client_token),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        'attachment; filename="leasing-response-lca-7700001001-1806-001.pdf"'
    )
    assert str(app.id) not in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")

    proposal_response = await client.get(
        f"/api/v1/applications/{app.id}/leasing-responses/"
        f"{wf_leasing_company.id}/pdf?proposal_kind=preliminary",
        headers=_auth(wf_client_token),
    )
    assert proposal_response.status_code == 200
    assert proposal_response.headers["content-disposition"] == (
        'attachment; filename="leasing-response-preliminary-7700001001-1806-001.pdf"'
    )
    assert str(app.id) not in proposal_response.headers["content-disposition"]
    assert proposal_response.content.startswith(b"%PDF")


async def test_lc_response_pdf_can_target_exact_lca_when_same_lc_has_multiple_links(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_client_token: str,
) -> None:
    app, first_link = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        lca_status="approved_final",
    )
    app.display_number = "7700001001-1806-002"

    second_link = LeasingCompanyApplication(
        application_id=app.id,
        leasing_company_id=wf_leasing_company.id,
        status="approved_final_another_cond",
    )
    db_session.add(second_link)
    await db_session.flush()

    db_session.add_all(
        [
            LeasingProposal(
                leasing_company_application_id=first_link.id,
                kind="final",
                position=1,
                total_amount=Decimal("1200000.00"),
                down_payment=Decimal("240000.00"),
                down_payment_percent=Decimal("20.00"),
                lease_term_months=24,
                monthly_payment=Decimal("50000.00"),
            ),
            LeasingProposal(
                leasing_company_application_id=second_link.id,
                kind="final",
                position=1,
                total_amount=Decimal("1300000.00"),
                down_payment=Decimal("260000.00"),
                down_payment_percent=Decimal("20.00"),
                lease_term_months=36,
                monthly_payment=Decimal("42000.00"),
            ),
        ]
    )
    await db_session.flush()

    response = await client.get(
        f"/api/v1/applications/{app.id}/leasing-responses/"
        f"{wf_leasing_company.id}/pdf"
        f"?proposal_kind=final&lca_id={second_link.id}",
        headers=_auth(wf_client_token),
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == (
        'attachment; filename="leasing-response-final-7700001001-1806-002.pdf"'
    )
    assert response.content.startswith(b"%PDF")


async def test_lc_response_pdf_without_lca_id_handles_duplicate_lca(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_client_token: str,
) -> None:
    app, _ = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
        lca_status="approved_final",
    )
    db_session.add(
        LeasingCompanyApplication(
            application_id=app.id,
            leasing_company_id=wf_leasing_company.id,
            status="approved_final_another_cond",
        )
    )
    await db_session.flush()

    response = await client.get(
        f"/api/v1/applications/{app.id}/leasing-responses/"
        f"{wf_leasing_company.id}/pdf?proposal_kind=final",
        headers=_auth(wf_client_token),
    )

    assert response.status_code == 404


async def test_lc_response_pdf_unknown_lca_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    wf_applicant_company: Company,
    wf_leasing_company: LeasingCompany,
    wf_other_leasing_company: LeasingCompany,
    wf_client_token: str,
) -> None:
    app, _ = await _seed(
        db_session,
        applicant_company=wf_applicant_company,
        lc=wf_leasing_company,
    )

    # Asking for a different LC's PDF (no LCA row) → 404
    response = await client.get(
        f"/api/v1/applications/{app.id}/leasing-responses/"
        f"{wf_other_leasing_company.id}/pdf",
        headers=_auth(wf_client_token),
    )
    assert response.status_code == 404


async def test_lc_response_pdf_unknown_application_returns_404(
    client: AsyncClient,
    wf_leasing_company: LeasingCompany,
    wf_client_token: str,
) -> None:
    bogus_id = uuid.uuid4()
    response = await client.get(
        f"/api/v1/applications/{bogus_id}/leasing-responses/"
        f"{wf_leasing_company.id}/pdf",
        headers=_auth(wf_client_token),
    )
    assert response.status_code == 404
