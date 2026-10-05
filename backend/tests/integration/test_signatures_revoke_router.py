from __future__ import annotations

from collections.abc import Iterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.contractors import Contractor, LeasingCompanyContractor
from infrastructure.models.users import User
from infrastructure.repositories import signature_request_repository as signatures
from infrastructure.repositories import sopd_operator_snapshot_repository as snapshots
from infrastructure.services import sopd_revoke_renderer
from infrastructure.services.object_storage import set_object_storage
from tests.fakes.object_storage import FakeObjectStorage


@pytest.fixture
def _fake_storage(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeObjectStorage]:
    async def _render_pdf(context: dict) -> bytes:
        return b"%PDF revoke"

    fake = FakeObjectStorage()
    monkeypatch.setattr(sopd_revoke_renderer, "render_pdf", _render_pdf)
    set_object_storage(fake)
    yield fake
    set_object_storage(None)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _signed_sopd_with_snapshot(
    db_session: AsyncSession,
) -> tuple[User, dict, LeasingCompany]:
    user = User(
        phone="+76662150498",
        email="signature-revoke-router@test.local",
        name="Signature Revoke Router",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    request = await signatures.create(
        db_session,
        user_id=user.id,
        application_id=None,
        document_type=signatures.DOC_TYPE_SOPD,
        subject_snapshot={"full_name": user.name},
    )
    signed = await signatures.mark_signed(
        db_session,
        request_id=request["id"],
        method="electronic",
        signed_pdf_s3_key="sopd/signed-router.pdf",
        signing_ip="127.0.0.1",
        signing_user_agent="pytest",
    )
    assert signed is not None

    company = Company(
        name="ООО РЕСО-Лизинг",
        inn="7709401087",
        company_type="leasing_company",
    )
    db_session.add(company)
    await db_session.flush()
    leasing_company = LeasingCompany(company_id=company.id, is_active=True)
    contractor = Contractor(name="ОКБ", inn="7710000001")
    db_session.add_all([leasing_company, contractor])
    await db_session.flush()
    db_session.add(
        LeasingCompanyContractor(
            leasing_company_id=leasing_company.id,
            contractor_id=contractor.id,
        )
    )
    await snapshots.upsert(
        db_session,
        signature_request_id=signed["id"],
        user_id=user.id,
        application_id=None,
        leasing_companies=[
            {
                "id": str(leasing_company.id),
                "company_id": str(company.id),
                "name": company.name,
                "inn": company.inn,
            }
        ],
        contractors=[
            {
                "id": str(contractor.id),
                "name": contractor.name,
                "inn": contractor.inn,
                "leasing_company_ids": [str(leasing_company.id)],
                "leasing_companies": [
                    {
                        "id": str(leasing_company.id),
                        "company_id": str(company.id),
                        "name": company.name,
                        "inn": company.inn,
                    }
                ],
            }
        ],
    )
    await db_session.flush()
    return user, signed, leasing_company


async def test_revoke_options_and_initiate_require_auth_and_selected_lc(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, request, leasing_company = await _signed_sopd_with_snapshot(db_session)
    token, _ = generate_tokens(user.id, "client", None)

    anon = await client.get(f"/api/v1/signatures/{request['id']}/revoke-options")
    assert anon.status_code == 401

    options = await client.get(
        f"/api/v1/signatures/{request['id']}/revoke-options",
        headers=_auth(token),
    )
    assert options.status_code == 200
    body = options.json()
    assert body["leasing_companies"][0]["id"] == str(leasing_company.id)
    assert body["leasing_companies"][0]["disabled"] is False

    empty = await client.post(
        f"/api/v1/signatures/{request['id']}/revoke",
        json={"leasing_company_ids": []},
        headers=_auth(token),
    )
    assert empty.status_code == 422

    initiated = await client.post(
        f"/api/v1/signatures/{request['id']}/revoke",
        json={"leasing_company_ids": [str(leasing_company.id)]},
        headers=_auth(token),
    )
    assert initiated.status_code == 200
    initiated_body = initiated.json()
    assert initiated_body["phone_masked"].endswith("**-98")
    assert initiated_body["revoked_leasing_companies"][0]["id"] == str(
        leasing_company.id
    )
    assert initiated_body["revoked_contractors"][0]["inn"] == "7710000001"


async def test_verify_full_revoke_moves_document_and_downloads_revoke_pdf(
    client: AsyncClient,
    db_session: AsyncSession,
    _fake_storage: FakeObjectStorage,
) -> None:
    user, request, leasing_company = await _signed_sopd_with_snapshot(db_session)
    token, _ = generate_tokens(user.id, "client", None)
    initiated = await client.post(
        f"/api/v1/signatures/{request['id']}/revoke",
        json={"leasing_company_ids": [str(leasing_company.id)]},
        headers=_auth(token),
    )
    assert initiated.status_code == 200

    verified = await client.post(
        f"/api/v1/signatures/{request['id']}/revoke/verify",
        json={"code": "0000"},
        headers=_auth(token),
    )
    assert verified.status_code == 200
    body = verified.json()
    assert body["status"] == signatures.STATUS_REVOKED
    assert body["is_full_revoke"] is True
    assert body["document_s3_key"] in _fake_storage.items

    downloaded = await client.get(
        body["revoke_document_download_url"],
        headers=_auth(token),
    )
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF revoke"

    generic_download = await client.get(
        f"/api/v1/signatures/{request['id']}/download",
        headers=_auth(token),
    )
    assert generic_download.status_code == 200
    assert generic_download.content == b"%PDF revoke"

    listing = await client.get(
        "/api/v1/signatures?status=revoked",
        headers=_auth(token),
    )
    assert listing.status_code == 200
    item = listing.json()["items"][0]
    assert item["sopd_revoke_summary"]["has_partial_revoke"] is False
    assert len(item["sopd_operators"]) == 1
    assert item["sopd_operators"][0]["operator_type"] == "leasing_company"
    assert {operator["status"] for operator in item["sopd_operators"]} == {
        "revoked"
    }
    assert item["sopd_operators"][0]["revoke_document_download_url"] == body[
        "revoke_document_download_url"
    ]
