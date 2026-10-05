
"""Upload a document attached to a specific leasing application.

Mirrors :mod:`upload_document` but additionally:
- Verifies the application exists and the actor's company matches it.
- Stores the file under the application-prefixed S3 key.
- Inserts a row in ``document_applications`` linking the new document to
  the application id.
- For director-signed slot types (Бух. отчётность / Декларации по налогу
  на прибыль / НДС / УСН) — fires a best-effort SMS to the company general
  director with a one-shot signing link.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.documents.upload_document import (
    UploadedDocumentFile,
)
from application.commands.leasing.document_request_forms import validate_form_data
from application.common import _isoformat
from application.document_recognition import (
    SessionFactory,
    schedule_recognition,
)
from application.errors import ServiceError
from application.notifications.leasing_events import record_leasing_event
from application.services.director_signing import (
    dispatch_director_signing_invitation,
    is_director_signed_slot,
)
from application.services.questionnaire_documents import (
    OPTIONAL_REQUEST_FILE_TYPES,
    project_document_answer,
)
from domain.entities.document import (
    RECOGNIZED_DOCUMENT_TYPES,
    Document,
    DocumentTypeConfig,
)
from domain.entities.leasing_company_application import (
    LCA_STATUS_DOCUMENTS_REQUIRED,
    LCA_STATUS_UNDER_REVIEW_WITH_DOCS,
    LeasingCompanyApplication,
)
from domain.errors import (
    ApplicationNotFoundError,
    CompanyNotFoundError,
    DocumentAccessDeniedError,
    DocumentRequestNotFoundError,
)
from domain.services.object_storage import ObjectStorage
from infrastructure.messaging.dwh_events import emit_document_changed
from infrastructure.repositories import (
    application_documents_repository as app_docs_repo,
)
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import (
    document_types_repository as types_repo,
)
from infrastructure.repositories import (
    documents_repository as docs_repo,
)
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repositories import status_history_repository as hist_repo
from infrastructure.services.document_storage import build_application_key

logger = logging.getLogger("carcraft-backend")

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(original: str) -> str:
    name = original.strip().split("/")[-1].split("\\")[-1] or "file"
    return _SAFE_FILENAME.sub("_", name)[:120]


@dataclass
class UploadDocumentForApplicationCommand:
    actor_user_id: UUID
    actor_company_id: UUID | None
    actor_role: str
    application_id: uuid.UUID
    document_type: str | None
    file: UploadedDocumentFile | None
    # A list (including an empty one) denotes one atomic response package.
    files: list[UploadedDocumentFile] | None = None
    user_titles: list[str] | None = None
    period_label: str | None = None
    document_request_id: UUID | None = None
    form_data: dict[str, Any] | None = None
    idempotency_key: str | None = None
    # Internal tracking for transaction-level object-storage compensation.
    uploaded_storage_keys: list[str] | None = None


async def handle_upload_document_for_application(  # noqa: PLR0912, PLR0915 - one transactional document-upload use case
    cmd: UploadDocumentForApplicationCommand,
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    session_factory: SessionFactory | None = None,
) -> dict:
    if cmd.files is not None:
        return await _handle_requested_document_package(cmd, session, storage)
    if cmd.file is None:
        raise ServiceError("Не передан файл документа", status_code=422)
    if cmd.actor_company_id is None and cmd.actor_role != "carcraft_employee":
        raise CompanyNotFoundError("Компания не привязана к пользователю")

    application = await app_repo.get_by_id(
        session, cmd.application_id, for_update=True,
    )
    if application is None:
        raise ApplicationNotFoundError(cmd.application_id)
    if cmd.actor_role != "carcraft_employee" and (
        cmd.actor_company_id is None
        or application["company_id"] != cmd.actor_company_id
    ):
        raise DocumentAccessDeniedError()

    document_type, document_request = await _resolve_document_request(
        session=session,
        cmd=cmd,
    )
    if document_request is not None and document_request.get("status") == "provided":
        if cmd.idempotency_key == document_request.get("idempotency_key"):
            replay = await app_docs_repo.get_response_document_for_request(session, document_request["id"])
            if replay is not None:
                return {"message": "Документ успешно загружен", "document": replay, "application_id": cmd.application_id}
        raise ServiceError("Запрос документа уже выполнен", status_code=409)

    type_row = await types_repo.get_by_type_code(session, document_type)
    type_config = DocumentTypeConfig.from_dict(type_row)
    if document_request is not None:
        if cmd.idempotency_key is None:
            raise ServiceError("Idempotency-Key обязателен", status_code=422)
        if document_request.get("has_form"):
            if cmd.form_data is None:
                raise ServiceError("Для этого запроса требуется form_data", status_code=422)
            try:
                form_data = validate_form_data(document_request["form_schema"], cmd.form_data)
            except ValueError as exc:
                raise ServiceError(str(exc), status_code=422) from None
        elif cmd.form_data is not None:
            raise ServiceError("Для этого запроса form_data не допускается", status_code=422)
        else:
            form_data = None
        await app_docs_repo.save_request_form_data_and_idempotency(
            session, request_id=document_request["id"], form_data=form_data,
            idempotency_key=cmd.idempotency_key,
        )
    Document.ensure_allowed_file_type(
        cmd.file.content_type, type_row, filename=cmd.file.filename
    )
    Document.ensure_file_size_ok(len(cmd.file.data), type_row)

    safe = _safe_filename(cmd.file.filename)
    unique = f"{uuid.uuid4().hex[:8]}_{safe}"
    company_for_key = (
        cmd.actor_company_id
        if cmd.actor_company_id is not None
        else application["company_id"]
    )
    key = build_application_key(cmd.application_id, unique)
    stored = await storage.put(key, cmd.file.data, cmd.file.content_type)
    if cmd.uploaded_storage_keys is not None:
        cmd.uploaded_storage_keys.append(key)

    auto_approve = bool(type_config.auto_approve) if type_config else False
    initial_review_status = "approved" if auto_approve else "pending"

    document_id = await docs_repo.create_document(
        session,
        company_id=company_for_key,
        document_type=document_type,
        file_name=unique,
        s3_key=key,
        file_path=stored,
        file_size=len(cmd.file.data),
        related_application_id=cmd.application_id,
        review_status=initial_review_status,
        period_label=cmd.period_label,
    )
    await docs_repo.link_to_application(
        session,
        document_id=document_id,
        application_id=cmd.application_id,
    )

    if document_request is not None:
        await _link_requested_document(
            session=session,
            cmd=cmd,
            document_request=document_request,
            document_id=document_id,
            review_status=initial_review_status,
        )
        await project_document_answer(
            session, application_id=cmd.application_id, document_type=document_type,
            form_data=form_data,
            documents=[{"id": document_id, "user_title": cmd.file.filename[:255]}],
        )
        await record_leasing_event(
            session, application={**application, "id": cmd.application_id},
            event_type="leasing.documents_uploaded", actor_user_id=cmd.actor_user_id,
            previous_values={"document_status": document_request["status"]},
            new_values={"document_status": "provided"},
            payload={
                "leasing_company_id": document_request["leasing_company_id"],
                "document_request_id": cmd.document_request_id,
                "request_batch_id": document_request["request_batch_id"],
                "document_id": document_id, "document_type": document_type,
            },
            occurrence_key=f"leasing.documents_uploaded:{cmd.document_request_id}:{document_id}",
        )

    if is_director_signed_slot(document_type):
        # Run inside a SAVEPOINT so that any failure during dispatch
        # (string truncation, magic-link issue, SMS provider hiccup) only
        # rolls back the dispatch's writes — the document upload itself
        # stays committable. Without this, a failed flush inside dispatch
        # would poison the outer transaction and the upload would 500
        # despite the file being safely on S3.
        try:
            async with session.begin_nested():
                await dispatch_director_signing_invitation(
                    session,
                    application_id=cmd.application_id,
                    document_type=document_type,
                    period_label=cmd.period_label,
                    document_id=document_id,
                    company_id=application["company_id"],
                    actor_user_id=cmd.actor_user_id,
                )
        except Exception as exc:
            # SMS dispatch is best-effort — never fail the upload because
            # of an issue with magic-link / SMS / user provisioning.
            logger.warning(
                "director-signing dispatch failed application_id=%s "
                "document_type=%s period=%s exc=%s",
                cmd.application_id,
                document_type,
                cmd.period_label,
                exc,
            )
    if auto_approve:
        await hist_repo.append_document_status_history(
            document_id=document_id,
            old_status=None,
            new_status="approved",
            changed_by=cmd.actor_user_id,
            comments="auto-approved on upload",
        )

    if (
        document_type in RECOGNIZED_DOCUMENT_TYPES
        and session_factory is not None
    ):
        schedule_recognition(
            document_id=document_id,
            user_id=cmd.actor_user_id,
            document_type=document_type,
            file_bytes=cmd.file.data,
            filename=safe,
            content_type=cmd.file.content_type,
            auto_approve=auto_approve,
            session_factory=session_factory,
        )

    persisted = await docs_repo.get_by_id(session, document_id)
    if persisted is not None:
        emit_document_changed({
            "document_id": persisted["id"],
            "company_id": persisted["company_id"],
            "document_type": persisted.get("document_type"),
            "file_path": persisted.get("file_path"),
            "file_name": persisted.get("file_name"),
            "file_size": persisted.get("file_size"),
            "s3_key": persisted.get("s3_key"),
            "period_label": persisted.get("period_label"),
            "comments": persisted.get("comments"),
            "is_required": persisted.get("is_required"),
            "status": persisted.get("status"),
            "version": persisted.get("version"),
            "parent_document_id": persisted.get("parent_document_id"),
            "is_current_version": persisted.get("is_current_version"),
            "related_application_id": str(persisted["related_application_id"]) if persisted.get("related_application_id") else None,
            "approved_by_leasing_company": persisted.get("approved_by_leasing_company"),
            "leasing_company_status": persisted.get("leasing_company_status"),
            "leasing_company_comments": persisted.get("leasing_company_comments"),
            "leasing_company_reviewed_at": _isoformat(persisted.get("leasing_company_reviewed_at")),
            "extracted_data": persisted.get("extracted_data"),
            "recognition_status": persisted.get("recognition_status"),
            "recognition_error": persisted.get("recognition_error"),
            "dbrain_task_id": persisted.get("dbrain_task_id"),
            "recognized_at": _isoformat(persisted.get("recognized_at")),
            "uploaded_at": _isoformat(persisted.get("uploaded_at")),
            "verified_at": _isoformat(persisted.get("verified_at")),
            "verified_by": persisted.get("verified_by"),
            "created_at": _isoformat(persisted.get("created_at")),
            "updated_at": _isoformat(persisted.get("updated_at")),
            "_deleted": False,
        })
    return {
        "message": "Документ успешно загружен",
        "document": persisted,
        "application_id": cmd.application_id,
    }


async def _handle_requested_document_package(
    cmd: UploadDocumentForApplicationCommand,
    session: AsyncSession,
    storage: ObjectStorage,
) -> dict[str, Any]:
    """Create one all-or-nothing response package under the locked request row."""
    application, request = await _load_response_context(cmd, session)
    if request["status"] == "provided":
        if cmd.idempotency_key == request.get("idempotency_key"):
            documents = await app_docs_repo.list_response_documents_for_request(session, request["id"])
            return {
                "message": "Ответ на запрос сохранён",
                "documents": documents,
                "application_id": cmd.application_id,
            }
        raise ServiceError("Запрос документа уже выполнен", status_code=409)
    if request["status"] != "requested":
        raise ServiceError("Загрузка доступна только для актуального запроса", status_code=409)
    if cmd.idempotency_key is None:
        raise ServiceError("Idempotency-Key обязателен", status_code=422)

    form_data = _response_form_data(request, cmd.form_data)

    document_type = str(request["document_type"])
    documents = await _store_response_files(cmd, session, storage, application, request)

    await project_document_answer(
        session, application_id=cmd.application_id, document_type=document_type,
        form_data=form_data, documents=documents,
    )
    await app_docs_repo.save_request_form_data_and_idempotency(
        session, request_id=request["id"], form_data=form_data, idempotency_key=cmd.idempotency_key,
    )
    if not await app_docs_repo.mark_request_provided(
        session, request_id=request["id"], provided_at=datetime.now(UTC)
    ):
        raise ServiceError("Запрос документа уже не актуален", status_code=409)
    if not await app_docs_repo.has_pending_required_requests(
        session, application_id=cmd.application_id,
        leasing_company_id=cast("UUID", request["leasing_company_id"]),
    ):
        await _complete_document_request_review(
            session=session, application_id=cmd.application_id,
            leasing_company_id=cast("UUID", request["leasing_company_id"]),
            actor_user_id=cmd.actor_user_id,
        )
    await record_leasing_event(
        session, application={**application, "id": cmd.application_id},
        event_type="leasing.documents_uploaded", actor_user_id=cmd.actor_user_id,
        previous_values={"document_status": request["status"]},
        new_values={"document_status": "provided"},
        payload={"leasing_company_id": request["leasing_company_id"], "document_request_id": request["id"], "request_batch_id": request["request_batch_id"], "document_ids": [d["id"] for d in documents], "document_type": document_type},
        occurrence_key=f"leasing.documents_uploaded:{request['id']}:{cmd.idempotency_key}",
    )
    return {"message": "Документы успешно загружены", "documents": documents, "application_id": cmd.application_id}


async def _resolve_document_request(
    *,
    session: AsyncSession,
    cmd: UploadDocumentForApplicationCommand,
) -> tuple[str, dict[str, Any] | None]:
    if cmd.document_request_id is None:
        if not cmd.document_type:
            raise ServiceError(
                "Необходимо указать тип документа", status_code=400
            )
        return cmd.document_type, None

    document_request = await app_docs_repo.get_request_by_id_for_update(
        session, cmd.document_request_id
    )
    if document_request is None:
        raise DocumentRequestNotFoundError(cmd.document_request_id)
    if document_request["application_id"] != cmd.application_id:
        raise DocumentAccessDeniedError(
            "Запрос документа не принадлежит указанной заявке"
        )
    if document_request.get("status") not in {"requested", "provided"}:
        raise ServiceError(
            "Загрузка доступна только для актуального запроса",
            status_code=409,
        )
    return str(document_request["document_type"]), document_request


async def _link_requested_document(
    *,
    session: AsyncSession,
    cmd: UploadDocumentForApplicationCommand,
    document_request: dict[str, Any],
    document_id: UUID,
    review_status: str,
) -> None:
    request_id = cmd.document_request_id
    if request_id is None:
        return
    leasing_company_id = cast("UUID", document_request["leasing_company_id"])
    application_document_status = (
        "approved" if review_status == "approved" else "submitted"
    )
    await app_docs_repo.upsert_application_document(
        session,
        application_id=cmd.application_id,
        document_id=document_id,
        leasing_company_id=leasing_company_id,
        status=application_document_status,
        document_request_id=request_id,
        user_title=cmd.file.filename[:255] if cmd.file else None,
    )
    if review_status == "approved":
        request_updated = await app_docs_repo.mark_request_approved(
            session,
            request_id=request_id,
        )
    else:
        request_updated = await app_docs_repo.mark_request_provided(
            session,
            request_id=request_id,
            provided_at=datetime.now(UTC),
        )
    if not request_updated:
        raise ServiceError(
            "Запрос документа уже не актуален",
            status_code=409,
        )
    has_pending = await app_docs_repo.has_pending_required_requests(
        session,
        application_id=cmd.application_id,
        leasing_company_id=leasing_company_id,
    )
    if not has_pending:
        await _complete_document_request_review(
            session=session,
            application_id=cmd.application_id,
            leasing_company_id=leasing_company_id,
            actor_user_id=cmd.actor_user_id,
        )


async def _complete_document_request_review(
    *,
    session: AsyncSession,
    application_id: UUID,
    leasing_company_id: UUID,
    actor_user_id: UUID,
) -> None:
    link_raw = await lca_repo.get_link_for_app_and_lc(
        session,
        application_id=application_id,
        leasing_company_id=leasing_company_id,
    )
    if link_raw is None or link_raw.get("status") != LCA_STATUS_DOCUMENTS_REQUIRED:
        return

    link = LeasingCompanyApplication.from_dict(link_raw)
    link.ensure_can_change_status(LCA_STATUS_UNDER_REVIEW_WITH_DOCS)
    await lca_repo.update_link_status(
        session,
        link_id=link.id,
        new_status=LCA_STATUS_UNDER_REVIEW_WITH_DOCS,
    )
    await hist_repo.append_lca_status_history(
        session,
        lca_id=link.id,
        application_id=application_id,
        old_status=LCA_STATUS_DOCUMENTS_REQUIRED,
        new_status=LCA_STATUS_UNDER_REVIEW_WITH_DOCS,
        changed_by=actor_user_id,
    )


def _validated_user_titles(
    supplied: list[str] | None, files: list[UploadedDocumentFile]
) -> list[str]:
    if supplied is not None and len(supplied) != len(files):
        raise ServiceError("user_titles должен соответствовать числу файлов", status_code=422)
    values = supplied if supplied is not None else [file.filename[:255] for file in files]
    titles = []
    for value in values:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 255:
            raise ServiceError("Название документа должно содержать от 1 до 255 символов", status_code=422)
        titles.append(value.strip())
    return titles


async def _load_response_context(
    cmd: UploadDocumentForApplicationCommand, session: AsyncSession
) -> tuple[dict[str, Any], dict[str, Any]]:
    files = cmd.files or []
    if len(files) > 10 or cmd.document_request_id is None:
        raise ServiceError("Для ответа на запрос допускается до 10 файлов", status_code=422)
    if cmd.actor_company_id is None and cmd.actor_role != "carcraft_employee":
        raise CompanyNotFoundError("Компания не привязана к пользователю")

    application = await app_repo.get_by_id(session, cmd.application_id, for_update=True)
    if application is None:
        raise ApplicationNotFoundError(cmd.application_id)
    if cmd.actor_role != "carcraft_employee" and application["company_id"] != cmd.actor_company_id:
        raise DocumentAccessDeniedError()

    request = await app_docs_repo.get_request_by_id_for_update(session, cmd.document_request_id)
    if request is None:
        raise DocumentRequestNotFoundError(cmd.document_request_id)
    if request["application_id"] != cmd.application_id:
        raise DocumentAccessDeniedError("Запрос документа не принадлежит указанной заявке")
    return application, request


def _response_form_data(
    request: dict[str, Any], form_data: dict[str, Any] | None
) -> dict[str, Any] | None:
    if request.get("has_form"):
        if form_data is None:
            raise ServiceError("Для этого запроса требуется form_data", status_code=422)
        try:
            return validate_form_data(request["form_schema"], form_data)
        except ValueError as exc:
            raise ServiceError(str(exc), status_code=422) from None
    elif form_data is not None:
        raise ServiceError("Для этого запроса form_data не допускается", status_code=422)
    return None



async def _store_response_files(
    cmd: UploadDocumentForApplicationCommand,
    session: AsyncSession,
    storage: ObjectStorage,
    application: dict[str, Any],
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    files = cmd.files or []
    document_type = str(request["document_type"])
    if not files and not request.get("has_form") and document_type not in OPTIONAL_REQUEST_FILE_TYPES:
        raise ServiceError("Для этого запроса требуется хотя бы один файл", status_code=422)
    titles = _validated_user_titles(cmd.user_titles, files)
    type_row = await types_repo.get_by_type_code(session, document_type)
    type_config = DocumentTypeConfig.from_dict(type_row)
    # Validate the whole package before the first S3 write.
    for upload in files:
        Document.ensure_allowed_file_type(upload.content_type, type_row, filename=upload.filename)
        Document.ensure_file_size_ok(len(upload.data), type_row)

    company_for_key = cmd.actor_company_id or application["company_id"]
    review_status = "approved" if (bool(type_config.auto_approve) if type_config else False) else "pending"
    association_status = "approved" if review_status == "approved" else "submitted"
    documents: list[dict[str, Any]] = []
    for upload, user_title in zip(files, titles, strict=True):
        safe = _safe_filename(upload.filename)
        unique = f"{uuid.uuid4().hex[:8]}_{safe}"
        key = build_application_key(cmd.application_id, unique)
        stored = await storage.put(key, upload.data, upload.content_type)
        if cmd.uploaded_storage_keys is not None:
            cmd.uploaded_storage_keys.append(key)
        document_id = await docs_repo.create_document(
            session, company_id=company_for_key, document_type=document_type,
            file_name=unique, s3_key=key, file_path=stored, file_size=len(upload.data),
            related_application_id=cmd.application_id, review_status=review_status,
        )
        await docs_repo.link_to_application(session, document_id=document_id, application_id=cmd.application_id)
        await app_docs_repo.upsert_application_document(
            session, application_id=cmd.application_id, document_id=document_id,
            leasing_company_id=cast("UUID", request["leasing_company_id"]),
            status=association_status, document_request_id=request["id"],
            user_title=user_title,
        )
        persisted = await docs_repo.get_by_id(session, document_id)
        if persisted is not None:
            documents.append({**persisted, "user_title": user_title})

    return documents
