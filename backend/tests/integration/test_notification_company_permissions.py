"""Notification context must preserve independent create and read permissions."""

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from application.services.notification_company_context import (
    require_notification_company_context,
)
from domain.errors import CompanyAccessDeniedError
from infrastructure.auth import generate_tokens
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company
from infrastructure.models.users import User, UserCompany
from infrastructure.repositories.notification_recipients_repository import (
    candidate_contexts,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def create_only_actor(db_session: AsyncSession) -> dict[str, Any]:
    company = Company(name="Create-only company", company_type="other")
    db_session.add(company)
    await db_session.flush()
    actor = User(phone="+73500000501", role="client", company_id=company.id, is_active=True)
    db_session.add(actor)
    await db_session.flush()
    membership = UserCompany(user_id=actor.id, company_id=company.id,
        sub_role="employee", can_view_applications=False, can_create_applications=True)
    existing = LeasingApplication(company_id=company.id, email="existing@example.test", status="active")
    db_session.add_all([membership, existing])
    await db_session.flush()
    token, _ = generate_tokens(actor.id, "client", company.id)
    return {"actor": actor, "company": company, "membership": membership,
        "existing": existing, "headers": {"Authorization": f"Bearer {token}"}}


async def test_no_selector_preserves_create_only_flags_but_notification_selection_requires_read(
    db_session: AsyncSession, create_only_actor: dict[str, Any],
) -> None:
    actor, company = create_only_actor["actor"], create_only_actor["company"]
    context = await require_notification_company_context(db_session,
        user_id=actor.id, role="client", company_id=company.id)
    assert context == {"company_id": company.id, "sub_role": "employee",
        "can_view_applications": False, "can_create_applications": True}
    with pytest.raises(CompanyAccessDeniedError):
        await require_notification_company_context(db_session, user_id=actor.id,
            role="client", company_id=company.id, notification_company_id=company.id)
    assert await candidate_contexts(db_session, company_ids={company.id}, user_id=actor.id) == []


async def test_create_only_context_can_create_draft_but_cannot_read_another_application(
    client: AsyncClient, db_session: AsyncSession, create_only_actor: dict[str, Any],
) -> None:
    company, headers = create_only_actor["company"], create_only_actor["headers"]
    payload = {"company_id": str(company.id), "vehicles": [
        {"modification_id": "CREATE-ONLY", "quantity": 1, "custom_price": "100.00"},
    ]}
    created = await client.post("/api/v1/applications/draft", json=payload,
        headers=headers | {"Idempotency-Key": "create-only-35"})
    assert created.status_code == 201, created.text
    assert created.json()["application_id"]
    detail = await client.get(f'/api/v1/applications/{create_only_actor["existing"].id}', headers=headers)
    assert detail.status_code == 403, detail.text
    denied_selector = await client.post("/api/v1/applications/draft", json=payload,
        params={"notification_company_id": str(company.id)},
        headers=headers | {"Idempotency-Key": "create-only-selector-35"})
    assert denied_selector.status_code == 403
    create_only_actor["membership"].can_create_applications = False
    await db_session.flush()
    revoked = await client.post("/api/v1/applications/draft", json=payload,
        headers=headers | {"Idempotency-Key": "create-only-revoked-35"})
    assert revoked.status_code == 403
