"""Per-LC questionnaire settings, disclosure, and the delivery gate."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.services.questionnaire_consents import build_consent_projection
from application.services.questionnaire_documents import DOCUMENT_STATUS_FIELDS
from domain.errors import LeasingCompanyNotFoundError
from domain.questionnaire import (
    QUESTIONNAIRE_FIELDS,
    QUESTIONNAIRE_REQUIRED_UNAVAILABLE_REASONS,
)
from domain.questionnaire_readiness import field_is_present
from infrastructure.repositories import application_documents_repository as documents
from infrastructure.repositories import application_repository as applications
from infrastructure.repositories import questionnaire_settings_repository as settings

_METADATA = frozenset({"id", "application_id", "created_at", "updated_at"})


async def get_settings(session: AsyncSession, leasing_company_id: UUID) -> dict[str, Any]:
    if not await applications.leasing_company_exists(session, leasing_company_id):
        raise LeasingCompanyNotFoundError(leasing_company_id)
    overrides = await settings.get_fields(session, leasing_company_id)
    return {
        "leasing_company_id": leasing_company_id,
        "fields": [
            {
                "field": name,
                "label": label,
                "enabled": overrides.get(name, {}).get("enabled", True),
                "required": name not in QUESTIONNAIRE_REQUIRED_UNAVAILABLE_REASONS
                and overrides.get(name, {}).get("required", False),
                "required_available": name not in QUESTIONNAIRE_REQUIRED_UNAVAILABLE_REASONS,
                "required_unavailable_reason": QUESTIONNAIRE_REQUIRED_UNAVAILABLE_REASONS.get(name),
            }
            for name, label in QUESTIONNAIRE_FIELDS.items()
        ],
    }


async def save_settings(
    session: AsyncSession, leasing_company_id: UUID, fields: list[dict[str, Any]]
) -> dict[str, Any]:
    await get_settings(session, leasing_company_id)
    overrides: dict[str, Any] = {}
    for item in fields:
        name = item["field"]
        if name not in QUESTIONNAIRE_FIELDS:
            raise ServiceError(f"Неизвестное поле анкеты: {name}", status_code=422)
        if name in overrides:
            raise ServiceError(f"Поле анкеты повторяется: {name}", status_code=422)
        if item["required"] and name in QUESTIONNAIRE_REQUIRED_UNAVAILABLE_REASONS:
            raise ServiceError(
                f"{QUESTIONNAIRE_FIELDS[name]}: {QUESTIONNAIRE_REQUIRED_UNAVAILABLE_REASONS[name]}",
                status_code=422,
            )
        if item["required"] and not item["enabled"]:
            raise ServiceError(f"Обязательное поле должно быть включено: {QUESTIONNAIRE_FIELDS[name]}", status_code=422)
        overrides[name] = {"enabled": item["enabled"], "required": item["required"]}
    await settings.replace_fields(session, leasing_company_id, overrides)
    return await get_settings(session, leasing_company_id)


async def project_for_leasing_company(
    session: AsyncSession, questionnaire: dict[str, Any], leasing_company_id: UUID
) -> dict[str, Any]:
    # TODO(TZ40): "Использовать" controls disclosure, not requiredness.
    # Map TZ40 names explicitly (ceo_appointment_document -> director_appointment_document).
    # Inclusion must preserve the consent and document-owner restrictions below.
    # See specs/task_2026-09-30_16-03-41_MSK.md,
    # section "Отложенное ТЗ №40 и устранение блокировки дозапросов".
    rules = await get_settings(session, leasing_company_id)
    enabled = {item["field"] for item in rules["fields"] if item["enabled"]}
    result = {
        key: value for key, value in questionnaire.items()
        if key in enabled or key in _METADATA
    }
    application_id = UUID(str(questionnaire["application_id"]))
    consents = await build_consent_projection(session, application_id, leasing_company_id)
    result.update({key: value for key, value in consents.items() if key in enabled})
    owners = await documents.list_request_owner_leasing_company_ids_for_documents(
        session, application_id=application_id
    )

    def visible(reference: dict[str, Any]) -> bool:
        try:
            document_id = UUID(str(reference["document_id"]))
        except (ValueError, KeyError, TypeError):
            return False
        owner_ids = owners.get(document_id)
        return owner_ids is None or owner_ids == {leasing_company_id}

    for field, _ in DOCUMENT_STATUS_FIELDS.values():
        value = result.get(field)
        if not isinstance(value, dict) or value.get("status") != "attached":
            continue
        refs = [item for item in value.get("documents", []) if isinstance(item, dict) and visible(item)]
        if refs:
            result[field] = {
                **value,
                "documents": refs,
                "text": "Файл приложен: " + "; ".join(item["user_title"] for item in refs),
            }
        else:
            result.pop(field, None)
    management = result.get("management_company_details")
    if isinstance(management, dict):
        refs = [
            item for item in management.get("documents", [])
            if isinstance(item, dict) and visible(item)
        ]
        # Keep common company requisites while hiding another LC's document.
        result["management_company_details"] = {
            "requisites": management.get("requisites"),
            "status": "file_attached" if refs else "not_provided",
            "file_name": "; ".join(item["user_title"] for item in refs) or None,
            "documents": refs,
        }
    licenses = result.get("licenses_or_sro_membership")
    if isinstance(licenses, list):
        result["licenses_or_sro_membership"] = [
            item for item in licenses if isinstance(item, dict) and visible(item)
        ]
    return result


async def assert_ready_for_delivery(
    session: AsyncSession, application_id: UUID, leasing_company_ids: list[UUID]
) -> None:
    # TODO(TZ40): Requiredness and its stage remain an open product decision;
    # document requests currently need an assigned LCA. Define a reachable
    # collection flow before restoring excluded requirements, independently of
    # "Использовать". See the deferred-TZ40 spec section referenced above.
    questionnaire = await applications.get_questionnaire(session, application_id)
    failures = []
    for leasing_company_id in leasing_company_ids:
        rules = await get_settings(session, leasing_company_id)
        projection = await project_for_leasing_company(
            session, questionnaire or {"application_id": application_id}, leasing_company_id
        )
        missing = [
            item["label"] for item in rules["fields"]
            if item["enabled"] and item["required"]
            and not field_is_present(item["field"], projection.get(item["field"]), questionnaire or {})
        ]
        if missing:
            failures.append(f"ЛК {leasing_company_id}: {', '.join(missing)}")
    if failures:
        raise ServiceError("Заполните обязательные поля анкеты. " + "; ".join(failures), status_code=422)
