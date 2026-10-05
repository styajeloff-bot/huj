"""Unified questionnaire writes, authorized reads and retryable source refresh."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.permissions import (
    ensure_application_owned_by,
    require_can_mutate_application,
)
from application.queries.applications.get_application import (
    ApplicationAccessQuery,
    get_authorized_application,
)
from domain.errors import CompanyLookupUnavailableError
from domain.questionnaire import normalize_questionnaire_payload, questionnaire_progress
from domain.questionnaire_people import (
    normalize_incoming_people,
    normalize_stored_people,
)
from domain.questionnaire_sources import company_values, fns_values
from infrastructure.repositories import application_repository as repo
from infrastructure.repositories import company_repository as company_repo
from infrastructure.repositories import (
    questionnaire_dictionaries_repository as dictionary_repo,
)
from infrastructure.repositories.dadata_normalization import normalize_dadata_payload
from infrastructure.services.company_lookup import get_company_lookup_provider
from infrastructure.services.questionnaire_fns import fetch_fns_company


async def _validate_choice(
    session: AsyncSession, kind: str, value: Any, old: Any, details: Any
) -> None:
    if value is None or value == "":
        return
    try:
        identifier = UUID(str(value))
    except ValueError as exc:
        raise ServiceError("Некорректный идентификатор справочника", 422) from exc
    row = await dictionary_repo.get_item(session, kind, identifier)
    if row is None or (not row["is_active"] and str(value) != str(old)):
        raise ServiceError("Выберите действующее значение справочника", 422)
    if row["code"] in {"other", "other_control_basis"} and not (
        isinstance(details, str) and details.strip()
    ):
        raise ServiceError("Укажите причину", 422)


async def write_questionnaire(
    session: AsyncSession,
    application_id: UUID,
    payload: dict[str, Any],
    *,
    source: str = "manual",
) -> dict[str, Any]:
    current = (
        await repo.get_questionnaire(session, application_id, for_update=True) or {}
    )
    if source == "manual":
        try:
            current = normalize_stored_people(current, application_id)
            payload = normalize_questionnaire_payload(current, payload)
            payload, _ = normalize_incoming_people(current, payload, explicit=True)
        except (ValueError, TypeError) as exc:
            raise ServiceError(str(exc), 422) from exc
        merged = {**current, **payload}
        if {
            "no_beneficial_owner_reason",
            "no_beneficial_owner_reason_details",
            "has_beneficiary",
        } & payload.keys():
            await _validate_choice(
                session,
                "beneficial_owner_absence_reasons",
                merged.get("no_beneficial_owner_reason"),
                current.get("no_beneficial_owner_reason"),
                merged.get("no_beneficial_owner_reason_details"),
            )
        if "beneficiaries" in payload:
            previous = {
                str(item.get("id")): item
                for item in (current.get("beneficiaries") or [])
                if isinstance(item, dict)
            }
            for person in payload["beneficiaries"]:
                await _validate_choice(
                    session,
                    "beneficial_owner_bases",
                    person.get("beneficial_owner_basis"),
                    previous.get(str(person.get("id")), {}).get(
                        "beneficial_owner_basis"
                    ),
                    person.get("beneficial_owner_basis_details"),
                )
    await repo.upsert_questionnaire(
        session, application_id=application_id, payload=payload, source=source
    )
    questionnaire = await repo.get_questionnaire(session, application_id) or {}
    progress, completed = questionnaire_progress(questionnaire)
    await repo.update_application_fields(
        session,
        application_id,
        fields={
            "questionnaire_progress": progress,
            "questionnaire_completed": completed,
        },
    )
    return questionnaire


async def read_questionnaire(
    session: AsyncSession, query: ApplicationAccessQuery
) -> dict[str, Any]:
    await get_authorized_application(query, session)
    data = await repo.get_questionnaire(session, query.application_id) or {"application_id": query.application_id}
    if query.actor_role == "leasing_company":
        if query.actor_leasing_company_id is None:
            raise ServiceError("Лизинговая компания не определена", 403)
        from application.services.questionnaire_delivery import (
            project_for_leasing_company,
        )

        data = await project_for_leasing_company(
            session, data, query.actor_leasing_company_id
        )
    else:
        data.pop("field_sources", None)
        data.pop("people_identity_map", None)
    return {"questionnaire": data}


async def authorized_refresh_questionnaire(
    session: AsyncSession, query: ApplicationAccessQuery
) -> dict[str, Any]:
    app, _ = await get_authorized_application(query, session)
    await require_can_mutate_application(
        session,
        user_id=query.actor_id,
        actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
        application=app,
    )
    entity = await ensure_application_owned_by(
        session,
        application=app,
        user_id=query.actor_id,
        actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
    )
    if query.actor_role == "client":
        entity.ensure_editable(
            has_lc_children=await repo.has_lc_children(session, query.application_id)
        )
    return await refresh_questionnaire(session, query.application_id)


async def refresh_questionnaire(
    session: AsyncSession, application_id: UUID
) -> dict[str, Any]:
    """Retain draft on source outages and allow explicit retry without duplicates."""
    app = await repo.get_by_id(session, application_id)
    if app is None:
        raise ServiceError("Заявка не найдена", 404)
    company = await company_repo.get_company_by_id(session, app["company_id"])
    sources: dict[str, str] = {"fns": "unavailable", "dadata": "unavailable"}
    if company:
        current = await repo.get_questionnaire(session, application_id) or {}
        fallback = {
            key: value
            for key, value in company_values(dict(company), application_id).items()
            if current.get(key) in (None, "", [])
        }
        await repo.upsert_questionnaire(
            session, application_id=application_id, payload=fallback, source="company"
        )
        inn = company.get("inn")
        if inn:
            try:
                raw = await get_company_lookup_provider().enrich_by_inn(inn)
                if raw:
                    normalized = normalize_dadata_payload(raw)
                    normalized["legal_address"] = normalized.pop(
                        "legal_address_string", None
                    )
                    payload = company_values(normalized, application_id)
                    managers = raw.get("managers")
                    if isinstance(managers, list):
                        legal_managers = [
                            m
                            for m in managers
                            if isinstance(m, dict) and m.get("type") == "LEGAL"
                        ]
                        if legal_managers:
                            payload["management_company_details"] = {"requisites": [
                                {
                                    "name": m.get("name"),
                                    "inn": m.get("inn"),
                                    "ogrn": m.get("ogrn"),
                                }
                                for m in legal_managers
                            ]}
                    await repo.upsert_questionnaire(
                        session,
                        application_id=application_id,
                        payload=payload,
                        source="dadata",
                    )
                    sources["dadata"] = "updated"
                else:
                    sources["dadata"] = "not_found"
            except CompanyLookupUnavailableError:
                sources["dadata"] = "unavailable"
        sources["fns"], fns = await fetch_fns_company(inn=inn, ogrn=company.get("ogrn"))
        if fns:
            await repo.upsert_questionnaire(
                session,
                application_id=application_id,
                payload=fns_values(fns, application_id),
                source="fns",
            )
        from application.services.egrul_attachment import attach_egrul_to_application

        sources["egrul"] = await attach_egrul_to_application(
            session,
            application_id=application_id,
            company_id=app["company_id"],
            inn=inn,
            ogrn=company.get("ogrn"),
        )
    from application.services.questionnaire_bank import refresh_bank_counterparties
    from application.services.questionnaire_consents import refresh_consent_projection

    await refresh_bank_counterparties(session, application_id)

    await refresh_consent_projection(session, application_id)
    data = await repo.get_questionnaire(session, application_id) or {}
    data.pop("field_sources", None)
    data.pop("people_identity_map", None)
    return {"questionnaire": data, "sources": sources}
