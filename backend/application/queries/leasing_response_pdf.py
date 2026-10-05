"""Download the LC response PDF for a given (application, leasing company).

Used by the application detail view to download a leasing-company response.
Ordinary application visibility is checked first. The full-data guard then
rejects quantity-distribution recipients whose scope omits any application
items or quantities, because the proposal cannot be safely apportioned.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.permissions import (
    ensure_application_full_data_access,
    ensure_application_visible_to,
)
from domain.errors import (
    ApplicationNotFoundError,
    LeasingCompanyApplicationNotFoundError,
)
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repositories import leasing_proposals_repository as proposals_repo
from infrastructure.services.application_export_pdf import (
    LeasingResponseExportInput,
    render_leasing_response_pdf,
)


@dataclass
class GetLcResponsePdfQuery:
    application_id: uuid.UUID
    leasing_company_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None = None
    proposal_kind: Literal["preliminary", "final"] | None = None
    lca_id: UUID | None = None


@dataclass
class LcResponsePdfPayload:
    data: bytes
    content_type: str
    file_name: str


async def handle_get_lc_response_pdf(
    query: GetLcResponsePdfQuery,
    session: AsyncSession,
) -> LcResponsePdfPayload:
    raw = await app_repo.get_by_id(session, query.application_id)
    if raw is None:
        raise ApplicationNotFoundError(query.application_id)
    await ensure_application_visible_to(
        session,
        application=raw,
        user_id=query.actor_id,
        actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
        actor_leasing_company_id=query.actor_leasing_company_id,
    )
    await ensure_application_full_data_access(
        session, application_id=query.application_id, actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
    )

    link = await _resolve_lca_link(session, query)
    if link is None:
        raise LeasingCompanyApplicationNotFoundError(query.application_id)
    if (
        str(link["application_id"]) != str(query.application_id)
        or str(link["leasing_company_id"]) != str(query.leasing_company_id)
    ):
        raise LeasingCompanyApplicationNotFoundError(query.application_id)
    return await _generate_response_pdf(
        session,
        raw,
        link,
        proposal_kind=query.proposal_kind,
    )


async def _resolve_lca_link(
    session: AsyncSession,
    query: GetLcResponsePdfQuery,
) -> dict[str, Any] | None:
    if query.lca_id is not None:
        link = await lca_repo.get_link_by_id(session, query.lca_id)
        return cast("dict[str, Any] | None", link)

    links = cast(
        "list[dict[str, Any]]",
        await lca_repo.list_links_for_app_and_lc(
            session,
            application_id=query.application_id,
            leasing_company_id=query.leasing_company_id,
        ),
    )
    if len(links) != 1:
        return None
    return links[0]


async def _generate_response_pdf(
    session: AsyncSession,
    application: dict[str, Any],
    link: dict[str, Any],
    *,
    proposal_kind: Literal["preliminary", "final"] | None,
) -> LcResponsePdfPayload:
    proposals = await proposals_repo.list_by_lca(session, link["id"])
    if proposal_kind is not None:
        proposals = [
            proposal
            for proposal in proposals
            if proposal.get("kind") == proposal_kind
        ]
    leasing_company_name = await lca_repo.get_leasing_company_display_name(
        session,
        link["leasing_company_id"],
    )
    data = render_leasing_response_pdf(
        LeasingResponseExportInput(
            application=application,
            link=link,
            leasing_company_name=leasing_company_name,
            proposals=proposals,
            proposal_kind=proposal_kind,
        )
    )
    return LcResponsePdfPayload(
        data=data,
        content_type="application/pdf",
        file_name=_pdf_file_name(application, proposal_kind),
    )


def _pdf_file_name(
    application: dict[str, Any],
    proposal_kind: Literal["preliminary", "final"] | None,
) -> str:
    number = _safe_file_token(str(application.get("display_number") or "application"))
    suffix = proposal_kind or "lca"
    return f"leasing-response-{suffix}-{number}.pdf"


def _safe_file_token(value: str) -> str:
    token = re.sub(r"[^\wа-яА-Я-]+", "-", value).strip("-")
    return token or "application"


def _module_attrs() -> dict[str, Any]:
    return {
        "GetLcResponsePdfQuery": GetLcResponsePdfQuery,
        "LcResponsePdfPayload": LcResponsePdfPayload,
        "handle_get_lc_response_pdf": handle_get_lc_response_pdf,
    }


__all__ = [
    "GetLcResponsePdfQuery",
    "LcResponsePdfPayload",
    "handle_get_lc_response_pdf",
]
