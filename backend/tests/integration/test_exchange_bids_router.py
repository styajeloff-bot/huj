"""Integration tests for /api/v1/exchange/bids (Phase 5 E2)."""
from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import cast
from urllib.parse import quote
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.companies import Company
from infrastructure.models.exchange import ExchangeBid
from infrastructure.models.users import User, UserCompany
from infrastructure.models.vehicles import City, Warehouse
from infrastructure.services.object_storage import set_object_storage
from tests.fakes.object_storage import FakeObjectStorage
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


@pytest.fixture
def _fake_storage() -> Iterator[FakeObjectStorage]:
    fake = FakeObjectStorage()
    set_object_storage(fake)
    yield fake
    set_object_storage(None)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _company_id(user: User) -> UUID:
    assert user.company_id is not None
    return user.company_id


@pytest_asyncio.fixture
async def bids_lc(db_session: AsyncSession) -> User:
    company = Company(name="Exchange LC", company_type="leasing_company")
    db_session.add(company)
    await db_session.flush()
    user = User(
        company_id=company.id,
        phone="+76660000001",
        email="bidslc@test.local",
        name="Bids LC",
        role="leasing_company",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def bids_lc_token(bids_lc: User) -> str:
    token, _ = generate_tokens(bids_lc.id, "leasing_company", None)
    return token


@pytest_asyncio.fixture
async def bids_dealer(
    db_session: AsyncSession, bids_dealer_company: Company
) -> User:
    user = User(
        phone="+76600000002",
        email="bidsdealer@test.local",
        name="Bids Dealer",
        role="dealer",
        company_id=bids_dealer_company.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def bids_dealer_token(bids_dealer: User) -> str:
    token, _ = generate_tokens(
        bids_dealer.id, "dealer", _company_id(bids_dealer)
    )
    return token


@pytest_asyncio.fixture
async def bids_vehicle(db_session: AsyncSession) -> Vehicle:
    v = Vehicle(
        status="available", is_available=True, base_price=Decimal("3000000")
    )
    db_session.add(v)
    await db_session.flush()
    return v


@pytest_asyncio.fixture
async def bids_dealer_company(db_session: AsyncSession) -> Company:
    company = Company(
        name="BidsDealerCo",
        inn="1122334455",
        ogrn="1122334455667",
        legal_address="BidsLegalAddr",
        actual_address="BidsActualAddr",
        company_type="dealer",
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def bids_warehouse(
    db_session: AsyncSession, bids_dealer_company: Company
) -> Warehouse:
    city = City(name="BidsCity")
    db_session.add(city)
    await db_session.flush()
    wh = Warehouse(
        address="BidsWh",
        brand="BidsBrand",
        city_id=city.id,
        dealer_id=bids_dealer_company.id,
    )
    db_session.add(wh)
    await db_session.flush()
    return wh


async def _create_request(
    client: AsyncClient,
    lc_token: str,
    vehicle_id: UUID,
    warehouse_id: UUID,
    dealer_id: UUID,
) -> UUID:
    response = await client.post(
        "/api/v1/exchange/requests/",
        headers=_auth(lc_token),
        json={
            "vehicle_id": vehicle_id,
            "quantity": 3,
            "warehouses": [
                {"warehouse_id": warehouse_id, "dealer_id": dealer_id}
            ],
        },
    )
    assert response.status_code == 201
    return cast("UUID", response.json()["request"]["id"])


# ---------------------------------------------------------------------------
# Create / list / update
# ---------------------------------------------------------------------------


async def test_create_bid_happy_path(
    client: AsyncClient,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
) -> None:
    rid = await _create_request(
        client,
        bids_lc_token,
        bids_vehicle.id,
        bids_warehouse.id,
        _company_id(bids_dealer),
    )
    response = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000.00", "quantity": 1},
    )
    assert response.status_code == 201
    assert response.json()["bid"]["request_id"] == rid


async def test_create_bid_persists_defaults_with_migration_schema(
    client: AsyncClient,
    db_session: AsyncSession,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
) -> None:
    rid = await _create_request(
        client,
        bids_lc_token,
        bids_vehicle.id,
        bids_warehouse.id,
        _company_id(bids_dealer),
    )

    # The initial Alembic migration used Python-side ``default`` values, so
    # existing databases have NOT NULL columns without server-side defaults.
    # Metadata-created test schemas otherwise hide that production contract.
    await db_session.execute(
        text(
            "ALTER TABLE exchange_bids "
            "ALTER COLUMN is_accepted DROP DEFAULT, "
            "ALTER COLUMN kp_status DROP DEFAULT"
        )
    )

    response = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000.00", "quantity": 1},
    )

    assert response.status_code == 201, response.text
    body = response.json()["bid"]
    assert body["is_accepted"] is False

    stored = await db_session.get(ExchangeBid, UUID(body["id"]))
    assert stored is not None
    assert stored.request_id == UUID(str(rid))
    assert stored.dealer_id == bids_dealer.id
    assert stored.is_accepted is False
    assert stored.kp_status == "none"


async def test_create_bid_anon_unauthorized(
    client: AsyncClient, bids_vehicle: Vehicle
) -> None:
    response = await client.post(
        "/api/v1/exchange/bids/",
        json={"request_id": 1, "price": "1000000"},
    )
    assert response.status_code == 401


FAKE_UUID = "00000000-0000-0000-0000-000000000000"


async def test_create_bid_lc_forbidden(
    client: AsyncClient, bids_lc_token: str
) -> None:
    response = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_lc_token),
        json={"request_id": FAKE_UUID, "price": "1000000"},
    )
    assert response.status_code == 403


async def test_duplicate_bid_returns_409(
    client: AsyncClient,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
) -> None:
    rid = await _create_request(
        client,
        bids_lc_token,
        bids_vehicle.id,
        bids_warehouse.id,
        _company_id(bids_dealer),
    )
    first = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000"},
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1100000"},
    )
    assert second.status_code == 409


async def test_update_bid(
    client: AsyncClient,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
) -> None:
    rid = await _create_request(
        client,
        bids_lc_token,
        bids_vehicle.id,
        bids_warehouse.id,
        _company_id(bids_dealer),
    )
    created = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000"},
    )
    bid_id = created.json()["bid"]["id"]
    updated = await client.put(
        f"/api/v1/exchange/bids/{bid_id}",
        headers=_auth(bids_dealer_token),
        json={"price": "1500000", "quantity": 2},
    )
    assert updated.status_code == 200
    assert updated.json()["bid"]["quantity"] == 2


async def test_list_own_bids(
    client: AsyncClient,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
) -> None:
    rid = await _create_request(
        client,
        bids_lc_token,
        bids_vehicle.id,
        bids_warehouse.id,
        _company_id(bids_dealer),
    )
    await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "900000"},
    )
    response = await client.get(
        "/api/v1/exchange/bids/", headers=_auth(bids_dealer_token)
    )
    assert response.status_code == 200
    assert len(response.json()["bids"]) >= 1


# ---------------------------------------------------------------------------
# Approve / reject — full cascade through the KP flow
# ---------------------------------------------------------------------------


async def test_full_flow_lc_creates_dealer_bids_lc_approves(
    client: AsyncClient,
    db_session: AsyncSession,
    bids_lc: User,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
) -> None:
    rid = await _create_request(
        client,
        bids_lc_token,
        bids_vehicle.id,
        bids_warehouse.id,
        _company_id(bids_dealer),
    )
    created = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000"},
    )
    bid_id = created.json()["bid"]["id"]

    # Simulate dealer accepting KP — bypass dealer KP endpoint (not exposed
    # in Phase 5 E2 scope). Mark kp_status=accepted directly.
    bid_row = await db_session.get(ExchangeBid, bid_id)
    assert bid_row is not None
    bid_row.kp_status = "accepted"
    await db_session.flush()

    approved = await client.put(
        f"/api/v1/exchange/bids/{bid_id}/approve",
        headers=_auth(bids_lc_token),
    )
    assert approved.status_code == 200
    assert approved.json()["bid"]["is_accepted"] is True

    # Request must have moved to `deal`.
    detail = await client.get(
        f"/api/v1/exchange/requests/{rid}",
        headers=_auth(bids_lc_token),
    )
    assert detail.status_code == 200
    assert detail.json()["request"]["status"] == "deal"


async def test_approve_without_kp_accepted_succeeds(
    client: AsyncClient,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
) -> None:
    """KP acceptance is optional — the LC can approve directly."""
    rid = await _create_request(
        client,
        bids_lc_token,
        bids_vehicle.id,
        bids_warehouse.id,
        _company_id(bids_dealer),
    )
    created = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000"},
    )
    bid_id = created.json()["bid"]["id"]
    response = await client.put(
        f"/api/v1/exchange/bids/{bid_id}/approve",
        headers=_auth(bids_lc_token),
    )
    assert response.status_code == 200
    assert response.json()["bid"]["is_accepted"] is True


async def test_approve_denied_for_dealer(
    client: AsyncClient,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
) -> None:
    rid = await _create_request(
        client,
        bids_lc_token,
        bids_vehicle.id,
        bids_warehouse.id,
        _company_id(bids_dealer),
    )
    created = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000"},
    )
    bid_id = created.json()["bid"]["id"]
    response = await client.put(
        f"/api/v1/exchange/bids/{bid_id}/approve",
        headers=_auth(bids_dealer_token),
    )
    assert response.status_code == 403


async def test_add_bid_comment(
    client: AsyncClient,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
) -> None:
    rid = await _create_request(
        client,
        bids_lc_token,
        bids_vehicle.id,
        bids_warehouse.id,
        _company_id(bids_dealer),
    )
    created = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000"},
    )
    bid_id = created.json()["bid"]["id"]
    response = await client.post(
        f"/api/v1/exchange/bids/{bid_id}/comments",
        headers=_auth(bids_lc_token),
        json={"comment": "проверьте"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Комментарий добавлен"
    assert body["comment"]["comment"] == "проверьте"
    assert body["comment"]["bid_id"] == bid_id


# ---------------------------------------------------------------------------
# Phase 14 G2 — bid file upload, KP upload, KP respond
# ---------------------------------------------------------------------------


async def test_dealer_uploads_bid_file(
    client: AsyncClient,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
    _fake_storage: FakeObjectStorage,
) -> None:
    rid = await _create_request(
        client,
        bids_lc_token,
        bids_vehicle.id,
        bids_warehouse.id,
        _company_id(bids_dealer),
    )
    created = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000"},
    )
    bid_id = created.json()["bid"]["id"]

    response = await client.post(
        f"/api/v1/exchange/bids/{bid_id}/file",
        headers=_auth(bids_dealer_token),
        files={"file": ("bid.pdf", b"pdf-data", "application/pdf")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bid"]["bid_file_name"] == "bid.pdf"
    # URL is now a backend proxy link — the raw S3 key lives only in the DB.
    assert body["bid"]["bid_file_url"] == f"/api/v1/exchange/bids/{bid_id}/file"


@pytest.mark.parametrize("kind", ["file", "kp"])
@pytest.mark.parametrize("filename", ["bid.pdf", "Тест пустой.xlsx"])
async def test_request_bid_attachment_download_contract(
    client: AsyncClient,
    db_session: AsyncSession,
    bids_lc: User,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
    _fake_storage: FakeObjectStorage,
    kind: str,
    filename: str,
) -> None:
    rid = await _create_request(
        client, bids_lc_token, bids_vehicle.id, bids_warehouse.id,
        _company_id(bids_dealer),
    )
    created = await client.post(
        "/api/v1/exchange/bids/", headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000"},
    )
    assert created.status_code == 201, created.text
    bid_id = created.json()["bid"]["id"]
    url = f"/api/v1/exchange/bids/{bid_id}/{kind}"
    field = "bid_file_url" if kind == "file" else "kp_file_url"
    upload_url = url if kind == "file" else f"/api/v1/exchange/requests/{rid}/bids/{bid_id}/kp"
    uploaded = await client.post(
        upload_url,
        headers=_auth(bids_dealer_token if kind == "file" else bids_lc_token),
        files={"file": (filename, b"attachment-content", "application/octet-stream")},
    )
    assert uploaded.status_code == 200, uploaded.text

    detail = await client.get(f"/api/v1/exchange/requests/{rid}", headers=_auth(bids_lc_token))
    assert detail.status_code == 200, detail.text
    assert detail.json()["request"]["bids"][0][field] == url
    assert detail.json()["bids"][0][field] == url
    listing = await client.get("/api/v1/exchange/requests/", headers=_auth(bids_lc_token))
    assert listing.status_code == 200, listing.text
    assert listing.json()["requests"][0]["bids"][0][field] == url

    for token in (bids_lc_token, bids_dealer_token):
        downloaded = await client.get(detail.json()["bids"][0][field], headers=_auth(token))
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == b"attachment-content"
        assert downloaded.headers["content-type"] == "application/octet-stream"
        assert downloaded.headers["content-disposition"] == (
            f"inline; filename*=UTF-8''{quote(filename, safe='')}"
        )

    client.cookies.clear()
    unauthenticated = await client.get(url)
    assert unauthenticated.status_code == 401
    unrelated_company = Company(name="Unrelated LC", company_type="leasing_company")
    db_session.add(unrelated_company)
    await db_session.flush()
    unrelated_lc = User(
        phone="+76660000003", role="leasing_company", company_id=unrelated_company.id,
        is_active=True,
    )
    db_session.add(unrelated_lc)
    await db_session.flush()
    unrelated_token, _ = generate_tokens(unrelated_lc.id, "leasing_company", unrelated_company.id)
    denied = await client.get(url, headers=_auth(unrelated_token))
    assert denied.status_code == 404
    forged_context = await client.get(url, headers=_auth(unrelated_token),
        params={"notification_company_id": str(_company_id(bids_lc))})
    assert forged_context.status_code == 403

    # A member of two LCs may follow the notification without switching cabinets.
    db_session.add(UserCompany(user_id=bids_lc.id, company_id=unrelated_company.id,
        can_view_applications=True, can_create_applications=True))
    await db_session.flush()
    other_context_token, _ = generate_tokens(bids_lc.id, "leasing_company", unrelated_company.id)
    wrong_context = await client.get(url, headers=_auth(other_context_token))
    assert wrong_context.status_code == 404
    selected = {"notification_company_id": str(_company_id(bids_lc))}
    context_detail = await client.get(f"/api/v1/exchange/requests/{rid}",
        headers=_auth(other_context_token), params=selected)
    assert context_detail.status_code == 200, context_detail.text
    context_download = await client.get(context_detail.json()["bids"][0][field],
        headers=_auth(other_context_token), params=selected)
    assert context_download.status_code == 200, context_download.text
    still_wrong_context = await client.get(url, headers=_auth(other_context_token))
    assert still_wrong_context.status_code == 404

    # Stored metadata whose object was deleted must remain a normal API 404.
    for key in list(_fake_storage.items):
        await _fake_storage.delete(key)
    missing_object = await client.get(url, headers=_auth(other_context_token), params=selected)
    assert missing_object.status_code == 404


async def test_request_bid_without_attachments_has_no_download_links(
    client: AsyncClient,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
    _fake_storage: FakeObjectStorage,
) -> None:
    rid = await _create_request(client, bids_lc_token, bids_vehicle.id,
        bids_warehouse.id, _company_id(bids_dealer))
    created = await client.post("/api/v1/exchange/bids/", headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000"})
    assert created.status_code == 201, created.text
    bid_id = created.json()["bid"]["id"]
    detail = await client.get(f"/api/v1/exchange/requests/{rid}", headers=_auth(bids_lc_token))
    assert detail.status_code == 200, detail.text
    assert detail.json()["bids"][0]["bid_file_url"] is None
    assert detail.json()["bids"][0]["kp_file_url"] is None
    for kind in ("file", "kp"):
        missing = await client.get(f"/api/v1/exchange/bids/{bid_id}/{kind}",
            headers=_auth(bids_lc_token))
        assert missing.status_code == 404


async def test_bid_file_upload_denied_for_lc(
    client: AsyncClient,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
    _fake_storage: FakeObjectStorage,
) -> None:
    rid = await _create_request(
        client,
        bids_lc_token,
        bids_vehicle.id,
        bids_warehouse.id,
        _company_id(bids_dealer),
    )
    created = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000"},
    )
    bid_id = created.json()["bid"]["id"]

    response = await client.post(
        f"/api/v1/exchange/bids/{bid_id}/file",
        headers=_auth(bids_lc_token),
        files={"file": ("bid.pdf", b"x", "application/pdf")},
    )
    assert response.status_code == 403


async def test_lc_uploads_kp_to_bid(
    client: AsyncClient,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
    _fake_storage: FakeObjectStorage,
) -> None:
    rid = await _create_request(
        client,
        bids_lc_token,
        bids_vehicle.id,
        bids_warehouse.id,
        _company_id(bids_dealer),
    )
    created = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000"},
    )
    bid_id = created.json()["bid"]["id"]

    response = await client.post(
        f"/api/v1/exchange/requests/{rid}/bids/{bid_id}/kp",
        headers=_auth(bids_lc_token),
        files={"file": ("kp.pdf", b"kp-data", "application/pdf")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bid"]["kp_status"] == "sent"
    assert body["bid"]["kp_file_name"] == "kp.pdf"
    assert body["bid"]["kp_sent_at"] is not None


async def test_lc_kp_upload_rejected_for_dealer(
    client: AsyncClient,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
    _fake_storage: FakeObjectStorage,
) -> None:
    rid = await _create_request(
        client,
        bids_lc_token,
        bids_vehicle.id,
        bids_warehouse.id,
        _company_id(bids_dealer),
    )
    created = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000"},
    )
    bid_id = created.json()["bid"]["id"]
    response = await client.post(
        f"/api/v1/exchange/requests/{rid}/bids/{bid_id}/kp",
        headers=_auth(bids_dealer_token),
        files={"file": ("kp.pdf", b"x", "application/pdf")},
    )
    assert response.status_code == 403


async def test_dealer_responds_accepted_to_kp(
    client: AsyncClient,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
    _fake_storage: FakeObjectStorage,
) -> None:
    rid = await _create_request(
        client,
        bids_lc_token,
        bids_vehicle.id,
        bids_warehouse.id,
        _company_id(bids_dealer),
    )
    created = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000"},
    )
    bid_id = created.json()["bid"]["id"]

    # LC sends KP first (moves kp_status → sent)
    kp = await client.post(
        f"/api/v1/exchange/requests/{rid}/bids/{bid_id}/kp",
        headers=_auth(bids_lc_token),
        files={"file": ("kp.pdf", b"kp-data", "application/pdf")},
    )
    assert kp.status_code == 200

    response = await client.post(
        f"/api/v1/exchange/bids/{bid_id}/kp/respond",
        headers=_auth(bids_dealer_token),
        json={"action": "accepted", "comment": "ok"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bid"]["kp_status"] == "accepted"
    assert body["bid"]["kp_dealer_comment"] == "ok"


async def test_dealer_cannot_respond_without_kp_sent(
    client: AsyncClient,
    bids_lc_token: str,
    bids_dealer_token: str,
    bids_vehicle: Vehicle,
    bids_warehouse: Warehouse,
    bids_dealer: User,
) -> None:
    rid = await _create_request(
        client,
        bids_lc_token,
        bids_vehicle.id,
        bids_warehouse.id,
        _company_id(bids_dealer),
    )
    created = await client.post(
        "/api/v1/exchange/bids/",
        headers=_auth(bids_dealer_token),
        json={"request_id": rid, "price": "1000000"},
    )
    bid_id = created.json()["bid"]["id"]

    response = await client.post(
        f"/api/v1/exchange/bids/{bid_id}/kp/respond",
        headers=_auth(bids_dealer_token),
        json={"action": "rejected"},
    )
    assert response.status_code == 400
