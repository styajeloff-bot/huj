from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.users import User
from infrastructure.repositories import signature_request_repository as signatures
from infrastructure.repositories import sopd_operator_snapshot_repository as snapshots

pytestmark = pytest.mark.asyncio


async def test_upsert_sopd_operator_snapshot_links_user_and_signature_request(
    db_session: AsyncSession,
) -> None:
    user = User(
        phone="+76662140541",
        email="sopd-operator-snapshot@test.local",
        name="SOPD Operator Snapshot",
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
    leasing_company_id = uuid.uuid4()
    contractor_id = uuid.uuid4()

    created = await snapshots.upsert(
        db_session,
        signature_request_id=request["id"],
        user_id=user.id,
        application_id=None,
        leasing_companies=[
            {
                "id": str(leasing_company_id),
                "name": "ООО РЕСО-Лизинг",
                "inn": "7709401087",
            }
        ],
        contractors=[
            {
                "id": str(contractor_id),
                "name": "ОКБ",
                "inn": "7710000001",
                "leasing_company_ids": [str(leasing_company_id)],
            }
        ],
    )

    assert created["signature_request_id"] == request["id"]
    assert created["user_id"] == user.id
    assert created["application_id"] is None
    assert created["leasing_companies"][0]["inn"] == "7709401087"
    assert created["contractors"][0]["leasing_company_ids"] == [
        str(leasing_company_id)
    ]

    fetched = await snapshots.get_by_signature_request_id(
        db_session, request["id"]
    )
    assert fetched is not None
    assert fetched["id"] == created["id"]

    listed = await snapshots.list_for_user(db_session, user.id)
    assert [item["id"] for item in listed] == [created["id"]]


async def test_upsert_sopd_operator_snapshot_keeps_one_row_per_signature(
    db_session: AsyncSession,
) -> None:
    user = User(
        phone="+76662140542",
        email="sopd-operator-snapshot-upsert@test.local",
        name="SOPD Operator Snapshot Upsert",
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

    first = await snapshots.upsert(
        db_session,
        signature_request_id=request["id"],
        user_id=user.id,
        application_id=None,
        leasing_companies=[],
        contractors=[],
    )
    second = await snapshots.upsert(
        db_session,
        signature_request_id=request["id"],
        user_id=user.id,
        application_id=None,
        leasing_companies=[
            {
                "id": str(uuid.uuid4()),
                "name": "АО ВТБ Лизинг",
                "inn": "7709378229",
            }
        ],
        contractors=[],
    )

    assert second["id"] == first["id"]
    assert len(second["leasing_companies"]) == 1
    assert (await snapshots.list_for_user(db_session, user.id))[0]["id"] == first["id"]
