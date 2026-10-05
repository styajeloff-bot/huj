from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.permissions import ensure_application_visible_to
from domain.errors import ApplicationNotFoundError
from infrastructure.repositories import application_repository
from infrastructure.repositories import signature_request_repository as repo


@dataclass(frozen=True)
class GetSopdStatusQuery:
    application_id: UUID
    actor_user_id: UUID
    actor_role: str = ""
    actor_company_id: UUID | None = None
    actor_leasing_company_id: UUID | None = None


@dataclass(frozen=True)
class SopdStatusItem:
    signer_key: str | None
    signer_name: str
    signer_inn: str | None
    status: str
    signature_request_id: UUID


async def handle_get_sopd_status(
    query: GetSopdStatusQuery,
    session: AsyncSession,
) -> list[SopdStatusItem]:
    application = await application_repository.get_by_id(
        session, query.application_id
    )
    if application is None:
        raise ApplicationNotFoundError(query.application_id)
    await ensure_application_visible_to(
        session,
        application=application,
        user_id=query.actor_user_id,
        actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
        actor_leasing_company_id=query.actor_leasing_company_id,
    )
    rows = await repo.list_for_application(session, query.application_id)
    items = []
    # A signature request is already unique.  Never deduplicate persons by
    # mutable display attributes such as FIO/INN.
    for row in rows:
        snap = row.get("subject_snapshot") or {}
        items.append(
            SopdStatusItem(
                signer_key=snap.get("signer_key"),
                signer_name=snap.get("full_name", ""),
                signer_inn=snap.get("inn"),
                status=row["status"],
                signature_request_id=row["id"],
            )
        )
    return items
