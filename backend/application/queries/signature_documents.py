"""Read-side: preview / download of a signature_request's PDF.

The preview for ``DOC_TYPE_SOPD`` flows through the async render pipeline
(``application.queries.sopd_cache.resolve_sopd_pdf``) — the PDF is
rendered by a taskiq worker from ``sopd.md`` and cached in S3
keyed by ``(template_hash, context_hash)``. The handler returns a
discriminated result so the router can map "not yet rendered" to HTTP
202 with Retry-After.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.queries.signer_sopd_context import build_signer_context
from application.queries.sopd_cache import (
    SopdPdfPending,
    SopdPdfReady,
    SopdTemplateMissing,
    ensure_sopd_pdf,
    resolve_sopd_pdf,
    wait_for_sopd_pdf,
)
from application.queries.sopd_operators import (
    SopdOperatorSnapshotData,
    resolve_sopd_operator_snapshot,
)
from domain.services.object_storage import ObjectStorage
from infrastructure.repositories import (
    director_signing_invitation_repository as dir_invite_repo,
)
from infrastructure.repositories import (
    documents_repository as docs_repo,
)
from infrastructure.repositories import (
    signature_request_repository as repo,
)
from infrastructure.repositories import (
    sopd_operator_snapshot_repository as snapshot_repo,
)
from infrastructure.repositories import (
    sopd_passport_snapshot_repository as passport_snapshot_repo,
)
from infrastructure.repositories import sopd_revoke_repository as revoke_repo
from infrastructure.services import document_storage


@dataclass(frozen=True)
class SignaturePreviewQuery:
    request_id: UUID
    actor_user_id: UUID


@dataclass(frozen=True)
class SignatureDownloadQuery:
    request_id: UUID
    actor_user_id: UUID


@dataclass(frozen=True)
class RevokeDocumentDownloadQuery:
    request_id: UUID
    revoke_request_id: UUID
    actor_user_id: UUID


SignaturePreviewResult = SopdPdfReady | SopdPdfPending | SopdTemplateMissing


async def handle_signature_preview(
    query: SignaturePreviewQuery,
    session: AsyncSession,
    storage: ObjectStorage,
) -> SignaturePreviewResult:
    request = await _load_owned(session, query.request_id, query.actor_user_id)
    doc_type = request["document_type"]
    if doc_type == repo.DOC_TYPE_SOPD:
        context = await _build_current_sopd_context(
            session,
            request=request,
        )
        result = await resolve_sopd_pdf(
            session=session, storage=storage, context=context
        )
        # On cache miss, wait briefly for the render worker so the
        # preview never flickers through a 202 «Документ готовится…»
        # for typical renders. The router falls back to the static
        # sopd.pdf if this still returns pending.
        if isinstance(result, SopdPdfPending):
            pdf_bytes = await wait_for_sopd_pdf(
                session=session,
                storage=storage,
                context=context,
                timeout_seconds=3.0,
            )
            if pdf_bytes is not None:
                return SopdPdfReady(data=pdf_bytes)
        return result
    if repo.is_director_doc_type(doc_type):
        invitation = await dir_invite_repo.get_by_signature_request_id(
            session, query.request_id
        )
        if invitation is None or invitation.get("document_id") is None:
            raise ServiceError("Оригинальный документ не найден", 404)
        document = await docs_repo.get_by_id(
            session, invitation["document_id"]
        )
        if document is None or not document.get("s3_key"):
            raise ServiceError("Оригинальный документ не найден", 404)
        data = await document_storage.get_document(str(document["s3_key"]))
        if data is None:
            raise ServiceError("Оригинальный документ не найден", 404)
        return SopdPdfReady(data=data, media_type="application/xml")
    raise ServiceError(f"Неизвестный тип документа: {doc_type}", 400)


async def handle_signature_download(
    query: SignatureDownloadQuery, session: AsyncSession, storage: ObjectStorage
) -> bytes:
    request = await _load_owned(session, query.request_id, query.actor_user_id)
    if request["document_type"] == repo.DOC_TYPE_SOPD:
        revoke_document = await _load_full_revoke_document(
            session,
            storage=storage,
            request=request,
        )
        if revoke_document is not None:
            return revoke_document
        current = await _render_current_sopd_pdf_if_revoked(
            session,
            storage=storage,
            request=request,
        )
        if current is not None:
            return current

    key = request["signed_pdf_s3_key"]
    if not key:
        raise ServiceError("Документ ещё не подписан", 404)
    data = await document_storage.get_document(key)
    if data is None:
        raise ServiceError("Файл не найден в хранилище", 410)
    return data


async def handle_revoke_document_download(
    query: RevokeDocumentDownloadQuery,
    session: AsyncSession,
    storage: ObjectStorage,
) -> tuple[bytes, str]:
    await _load_owned(session, query.request_id, query.actor_user_id)
    revoke_request = await revoke_repo.get_by_id(
        session, revoke_request_id=query.revoke_request_id
    )
    if (
        revoke_request is None
        or revoke_request["signature_request_id"] != query.request_id
        or revoke_request["status"] != revoke_repo.STATUS_CONFIRMED
        or not revoke_request.get("document_s3_key")
    ):
        raise ServiceError("Документ отзыва не найден", 404)
    stored = await storage.get(str(revoke_request["document_s3_key"]))
    if stored is None:
        raise ServiceError("Документ отзыва не найден", 404)
    return stored.data, stored.content_type or "application/pdf"


async def _load_owned(
    session: AsyncSession, request_id: UUID, actor_user_id: UUID
) -> dict:
    request = await repo.get_by_id(session, request_id)
    if request is None:
        raise ServiceError("Документ не найден", 404)
    if request["user_id"] != actor_user_id:
        raise ServiceError("Нет доступа к документу", 403)
    return cast("dict[Any, Any]", request)


async def _render_current_sopd_pdf_if_revoked(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    request: dict[str, Any],
) -> bytes | None:
    facts = await revoke_repo.list_revoked_operators(
        session,
        signature_request_id=request["id"],
    )
    if not facts:
        return None
    context = await _build_current_sopd_context(
        session,
        request=request,
        revoked_facts=facts,
    )
    return await ensure_sopd_pdf(
        session=session,
        storage=storage,
        context=context,
    )


async def _load_full_revoke_document(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    request: dict[str, Any],
) -> bytes | None:
    if request["status"] != repo.STATUS_REVOKED:
        return None
    revoke_request = await revoke_repo.get_latest_confirmed_for_signature(
        session,
        signature_request_id=request["id"],
    )
    if revoke_request is None or not revoke_request.get("document_s3_key"):
        raise ServiceError("Документ отзыва не найден", 404)
    stored = await storage.get(str(revoke_request["document_s3_key"]))
    if stored is None:
        raise ServiceError("Документ отзыва не найден", 410)
    return stored.data


async def _build_current_sopd_context(
    session: AsyncSession,
    *,
    request: dict[str, Any],
    revoked_facts: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    passport_snapshot = await passport_snapshot_repo.get_for_request(session, request["id"])
    if passport_snapshot is None or not passport_snapshot.get("confirmed_fields"):
        raise ServiceError("Подтверждённый снимок паспорта отсутствует", 409)
    if passport_snapshot.get("has_unsaved_changes"):
        raise ServiceError("Есть несохранённые изменения паспортных данных", 409)
    context = _context_from_confirmed_passport(passport_snapshot["confirmed_fields"])
    context.update(await build_signer_context(
        session,
        user_id=request["user_id"],
        subject_snapshot=request.get("subject_snapshot"),
        application_id=request.get("application_id"),
    ))
    context.update(_context_from_confirmed_passport(passport_snapshot["confirmed_fields"]))
    facts = (
        revoked_facts
        if revoked_facts is not None
        else await revoke_repo.list_revoked_operators(
            session,
            signature_request_id=request["id"],
        )
    )
    if not facts:
        return context

    snapshot = await snapshot_repo.get_by_signature_request_id(session, request["id"])
    if snapshot is None:
        resolved = await resolve_sopd_operator_snapshot(
            session,
            application_id=request.get("application_id"),
        )
        leasing_companies = resolved.leasing_companies
        contractors = resolved.contractors
    else:
        leasing_companies = cast("list[dict[str, Any]]", snapshot["leasing_companies"])
        contractors = cast("list[dict[str, Any]]", snapshot["contractors"])

    active = _active_sopd_operator_data(
        leasing_companies=leasing_companies,
        contractors=contractors,
        revoked_facts=facts,
    )
    context["leasing_companies"] = active.leasing_companies_text
    context["contractors"] = active.contractors_text
    return context


def _context_from_confirmed_passport(fields: dict[str, Any]) -> dict[str, str]:
    """The legal document may only receive this immutable, user-confirmed snapshot."""
    def text(key: str) -> str:
        return str(fields.get(key) or "").strip()

    return {
        "full_name": " ".join(part for part in (text("surname"), text("name"), text("patronymic")) if part),
        "gender": "Мужской" if text("gender") == "male" else "Женский" if text("gender") == "female" else "",
        "birth_date": text("birthDate"), "birth_place": text("birthPlace"),
        "passport_series_number": " ".join(part for part in (text("passportSeries"), text("passportNumber")) if part),
        "passport_issued_by": text("givenWhom"), "passport_issued_at": text("givenDate"),
        "passport_code": text("code"),
    }


def _active_sopd_operator_data(
    *,
    leasing_companies: list[dict[str, Any]],
    contractors: list[dict[str, Any]],
    revoked_facts: list[dict[str, Any]],
) -> SopdOperatorSnapshotData:
    revoked_lc_ids = {
        str(fact["leasing_company_id"])
        for fact in revoked_facts
        if fact.get("operator_type") == revoke_repo.TYPE_LEASING_COMPANY
        and fact.get("leasing_company_id") is not None
    }
    revoked_contractor_ids = {
        str(fact["contractor_id"])
        for fact in revoked_facts
        if fact.get("operator_type") == revoke_repo.TYPE_CONTRACTOR
        and fact.get("contractor_id") is not None
    }
    active_lcs = [
        item
        for item in leasing_companies
        if str(item.get("id") or "") not in revoked_lc_ids
    ]
    active_lc_ids = {str(item.get("id") or "") for item in active_lcs}

    active_contractors: list[dict[str, Any]] = []
    for contractor in contractors:
        contractor_id = str(contractor.get("id") or "")
        if contractor_id and contractor_id in revoked_contractor_ids:
            continue
        linked_ids = [
            str(value)
            for value in contractor.get("leasing_company_ids") or []
            if str(value) in active_lc_ids
        ]
        linked_lcs = [
            lc
            for lc in contractor.get("leasing_companies") or []
            if isinstance(lc, dict) and str(lc.get("id") or "") in active_lc_ids
        ]
        if (contractor.get("leasing_company_ids") or []) and not linked_ids:
            continue
        active_contractors.append(
            {
                **contractor,
                "leasing_company_ids": linked_ids,
                "leasing_companies": linked_lcs,
            }
        )

    return SopdOperatorSnapshotData(
        leasing_companies=active_lcs,
        contractors=active_contractors,
        source="active_after_revoke",
    )
