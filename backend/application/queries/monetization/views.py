"""Scoped projections. Financial rows are removed before leaving the server."""

from __future__ import annotations

from math import ceil
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.queries.monetization.reference_documents import (
    list_reference_documents,
)
from application.services.notification_company_context import (
    require_notification_company_context,
)
from domain.errors import DomainError
from domain.monetization.deals import required_confirmations
from domain.monetization.identifiers import entity_id
from domain.monetization.terms import base_type, calculation_base, effective_terms
from infrastructure.repositories import monetization_repository as repo

ROLE_PARTY = {
    "carcraft_employee": "admin",
    "leasing_company": "leasing",
    "dealer": "dealer",
    "distributor": "distributor",
}


async def resolve_actor(session: AsyncSession, user: dict[str, Any],
                        notification_company_id: UUID | None = None,
                        leasing_company_id: UUID | None = None) -> dict[str, Any]:
    if notification_company_id is not None and user["role"] == "carcraft_employee":
        raise ServiceError("Сотрудник Carcraft не выбирает компанию уведомления", 403)
    selected_company = notification_company_id or user.get("company_id")
    if user["role"] == "leasing_company" and leasing_company_id is not None:
        try:
            context = await require_notification_company_context(
                session, user_id=entity_id(user["id"]), role=user["role"],
                company_id=entity_id(user["company_id"]) if user.get("company_id") else None,
                notification_company_id=notification_company_id,
                leasing_company_id=leasing_company_id,
            )
        except DomainError as exc:
            raise ServiceError("Нет доступа к выбранной лизинговой компании", 403) from exc
        selected_company = context["company_id"]
    actor = await repo.resolve_actor(
        session, entity_id(user["id"]), str(user["role"]),
        entity_id(selected_company) if selected_company else None,
    )
    if actor is None:
        raise ServiceError("Нет доступа к выбранной компании", 403)

    from infrastructure.repositories.user_company_access_repository import (
        get_actor_section_access,
    )

    section_access = await get_actor_section_access(
        session,
        user_id=entity_id(user["id"]),
        company_id=entity_id(selected_company) if selected_company else None,
        role=str(user["role"]),
    )
    can_inc = bool(section_access.get("monetization_income", True))
    can_exp = bool(section_access.get("monetization_expense", True))
    if not can_inc and not can_exp and user["role"] != "carcraft_employee":
        raise ServiceError("У вас нет доступа к этому разделу", 403)
    actor["can_monetization_income"] = can_inc
    actor["can_monetization_expense"] = can_exp
    return actor


def pagination(total: int, page: int, page_size: int) -> dict[str, int]:
    return {"page": page, "page_size": page_size, "total": total,
            "total_pages": ceil(total / page_size)}


def document_view(document: dict[str, Any], *, kind: str,
                  revision: int | None = None) -> dict[str, Any]:
    document_id = document["id"]
    return {
        "id": document_id,
        "file_name": document["filename"],
        "download_url": f"/api/v1/monetization/files/{kind}/{document_id}",
        "uploaded_at": document.get("uploaded_at") or document.get("created_at"),
        "uploaded_by_role": document.get("participant_type"),
        "revision": document.get("revision"),
        "outdated": bool(revision is not None and document.get("revision") != revision),
    }


def support_view(support: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": support["id"], "name": support["name"],
        "documents": [document_view(doc, kind="supports")
                      for doc in support.get("documents", [])],
        "compatible_programs": support.get("compatible_programs", []),
    }


def participant_summary(rows: list[dict[str, Any]], companies: dict[str, Any]) -> list[dict[str, Any]]:
    """Only summarize rows already projected for the requesting company."""
    result = []
    seen: set[tuple[str, str | None]] = set()
    for row in rows:
        party = row["participant_type"]
        company = companies.get(party)
        key = (party, str(company["id"]) if company else None)
        if key not in seen:
            seen.add(key)
            result.append({"participant_type": party, "company": company})
    return result


def program_view(program: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
    result = dict(program)
    party = ROLE_PARTY[actor["role"]]
    result["can_manage"] = bool(party == "admin" and actor["can_write"])
    sources = []
    can_inc = actor.get("can_monetization_income", True)
    can_exp = actor.get("can_monetization_expense", True)
    for source in program.get("sources", []):
        projected = {"id": source["id"], "source_type": source["source_type"]}
        for side in ("expenses", "incomes"):
            if party != "admin":
                if side == "incomes" and not can_inc:
                    projected[side] = []
                    continue
                if side == "expenses" and not can_exp:
                    projected[side] = []
                    continue
            projected[side] = [
                row for row in source.get(side, [])
                if party == "admin" or row["participant_type"] == party
            ]
        sources.append(projected)
    result["sources"] = sources
    companies = {"leasing": program.get("leasing_company"),
                 "dealer": program.get("dealer"), "distributor": program.get("distributor")}
    for side, field in (("expenses", "expense_participants"), ("incomes", "income_participants")):
        if party != "admin":
            if field == "income_participants" and not can_inc:
                result[field] = []
                continue
            if field == "expense_participants" and not can_exp:
                result[field] = []
                continue
        result[field] = participant_summary([row for source in sources for row in source[side]], companies)
    result["contracts"] = [
        document_view(doc, kind="contracts") for doc in program.get("contracts", [])
    ]
    if program.get("support_program"):
        result["support_program"] = support_view(program["support_program"])
    return result


def is_deal_participant(deal: dict[str, Any], actor: dict[str, Any]) -> bool:
    """Group visibility alone does not authorize another company's confirmation."""
    party = ROLE_PARTY[actor["role"]]
    if party == "admin":
        return True
    if party not in required_confirmations(deal):
        return False
    if party == "leasing":
        return deal["leasing_company_id"] in actor["leasing_company_ids"]
    return deal.get(f"{party}_company_id") == actor.get("company_id")


def _amount_view(
    row: dict[str, Any], deal: dict[str, Any], *,
    amounts: dict[Any, dict[str, Any]], can_adjust: bool,
) -> dict[str, Any]:
    history = [
        change for change in deal.get("adjustments", [])
        if change["amount_id"] == row["id"]
    ]
    _, percent, input_mode = effective_terms(row, amounts, deal["base_amount"])
    return {
        **row,
        "original_percent": (
            row.get("condition_value") if row.get("original_calc_type") == "percent"
            else None
        ),
        "original_amount": history[0]["old_value"] if history else row["amount"],
        "applied_limit": (
            row.get(f"condition_{row['clip']}")
            if row.get("clip") in {"min", "max"} else None
        ),
        "percent": percent,
        "input_mode": input_mode,
        "base_type": base_type(row),
        "calculation_base_amount": (
            calculation_base(row, amounts, deal["base_amount"]) if can_adjust else None
        ),
        "has_new_conditions": bool(history),
    }


def deal_view(deal: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
    party = ROLE_PARTY[actor["role"]]
    amounts = deal.get("amounts", [])
    company_ids = actor["leasing_company_ids"] if party == "leasing" else actor.get("company_ids", [])
    can_adjust = bool(party == "admin" and actor["can_write"]
                      and deal["status"] == "pending_approval")
    amount_index = {entity_id(row["id"]): row for row in amounts}
    visible = [
        _amount_view(row, deal, amounts=amount_index, can_adjust=can_adjust)
        for row in amounts if party == "admin"
        or (row["participant_type"] == party and row.get("participant_company_id") in company_ids)
    ]
    if party != "admin":
        can_inc = actor.get("can_monetization_income", True)
        can_exp = actor.get("can_monetization_expense", True)
        if not can_inc:
            visible = [row for row in visible if row["side"] != "income"]
        if not can_exp:
            visible = [row for row in visible if row["side"] != "expense"]
    if party == "dealer":
        # Recipient income is part of the dealer's visible expense detail,
        # independent of permission to view the dealer's own income.
        expenses = {row["id"] for row in visible if row["side"] == "expense"}
        visible_ids = {row["id"] for row in visible}
        visible.extend(
            _amount_view(row, deal, amounts=amount_index, can_adjust=False)
            for row in amounts
            if row["side"] == "income" and row.get("expense_ref_amount_id") in expenses
            and row["id"] not in visible_ids
        )
    confirmations = {}
    for side in ("leasing", "dealer", "distributor"):
        existing = (deal.get("confirmations") or {}).get(side) or {}
        confirmations[side] = {
            "applicable": side != "distributor" or any(
                row["participant_type"] == "distributor" for row in amounts),
            "confirmed_at": existing.get("confirmed_at"),
            "confirmed_by": existing.get("user_id"),
            "confirmed_by_name": existing.get("user_name"),
        }
    return {
        **{key: deal.get(key) for key in (
            "id", "application_number", "application_id", "leasing_company_application_id",
            "exchange_request_id", "source_type", "brand", "program_id", "program_name",
            "leasing_company", "dealer_company", "distributor_company", "client_company", "base_amount",
            "status", "revision", "created_at",
        )},
        "can_adjust": can_adjust,
        "has_new_conditions": deal["revision"] > 1,
        "can_confirm": (
            actor["can_write"] and deal["status"] == "pending_approval" and is_deal_participant(deal, actor)
            and not (deal.get("confirmations") or {}).get(party)
            and (party != "admin" or all(
                (deal.get("confirmations") or {}).get(required, {}).get("revision") == deal["revision"]
                for required in required_confirmations(deal)
            ))
        ),
        "can_upload_documents": actor["can_write"] and deal["status"] == "pending_approval" and is_deal_participant(deal, actor),
        "expenses": [row for row in visible if row["side"] == "expense"],
        "incomes": [row for row in visible if row["side"] == "income"],
        "confirmations": confirmations,
        "documents": [document_view(doc, kind="deals", revision=deal["revision"])
                      for doc in deal.get("documents", [])],
    }


async def get_program(session: AsyncSession, program_id: UUID,
                      actor: dict[str, Any]) -> dict[str, Any]:
    program = await repo.get_program(session, program_id, actor)
    if program is None:
        raise ServiceError("Условия монетизации не найдены", 404)
    result = program_view(program, actor)
    result["reference_documents"] = (await list_reference_documents(session, program_id, actor))["items"]
    return result


async def list_programs(session: AsyncSession, actor: dict[str, Any], *,
                        filters: dict[str, Any], page: int, page_size: int) -> dict[str, Any]:
    result = await repo.list_programs(
        session, actor=actor, filters=filters, offset=(page - 1) * page_size, limit=page_size)
    # The list intentionally never includes any configuration/financial rows.
    keys = ("id", "name", "brand", "period_start", "period_end", "status",
            "expense_participants", "income_participants")
    summaries = [program_view(row, actor) for row in result["items"]]
    if actor["role"] != "carcraft_employee":
        summaries = [
            s for s in summaries
            if s.get("expense_participants") or s.get("income_participants")
        ]
    return {
        "items": [{key: row.get(key) for key in keys} for row in summaries],
        "can_manage": bool(actor["role"] == "carcraft_employee" and actor["can_write"]),
        "pagination": pagination(len(summaries) if actor["role"] != "carcraft_employee" else result["total"], page, page_size),
    }


async def get_deal(session: AsyncSession, deal_id: UUID,
                   actor: dict[str, Any]) -> dict[str, Any]:
    deal = await repo.get_deal(session, deal_id, actor)
    if deal is None:
        raise ServiceError("Сделка монетизации не найдена", 404)
    return deal_view(deal, actor)


def deal_summary(deal: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
    visible = deal_view(deal, actor)
    keys = ("id", "application_number", "source_type", "brand", "leasing_company",
            "dealer_company", "distributor_company", "client_company", "base_amount",
            "status", "confirmations", "created_at")
    result = {key: visible[key] for key in keys}
    companies = {"leasing": visible["leasing_company"], "dealer": visible["dealer_company"],
                 "distributor": visible["distributor_company"]}
    result["expense_participants"] = participant_summary(visible["expenses"], companies)
    party = ROLE_PARTY[actor["role"]]
    own_incomes = visible["incomes"] if party == "admin" else [
        row for row in visible["incomes"]
        if row["participant_type"] == party and actor.get("can_monetization_income", True)
    ]
    result["income_participants"] = participant_summary(own_incomes, companies)
    return result


async def list_deals(session: AsyncSession, actor: dict[str, Any], *,
                     filters: dict[str, Any], page: int, page_size: int) -> dict[str, Any]:
    result = await repo.list_deals(
        session, actor=actor, filters=filters, offset=(page - 1) * page_size, limit=page_size)
    items = [deal_summary(row, actor) for row in result["items"]]
    if actor["role"] != "carcraft_employee":
        items = [
            d for d in items
            if d.get("expense_participants") or d.get("income_participants")
        ]
    return {"items": items,
            "pagination": pagination(len(items) if actor["role"] != "carcraft_employee" else result["total"], page, page_size)}


async def lookup_companies(session: AsyncSession, actor: dict[str, Any],
                           kind: str, query: str,
                           distributor_company_id: UUID | None = None,
                           dealer_company_id: UUID | None = None) -> dict[str, Any]:
    return {"items": await repo.lookup_companies(
        session, actor, kind, query, distributor_company_id, dealer_company_id,
    )}


async def lookup_supports(session: AsyncSession, actor: dict[str, Any],
                          query: str, distributor_company_id: UUID | None = None) -> dict[str, Any]:
    return {"items": await repo.lookup_supports(session, actor, query, distributor_company_id)}


async def get_support(session: AsyncSession, support_id: UUID,
                      actor: dict[str, Any]) -> dict[str, Any]:
    support = await repo.get_support(session, support_id, actor)
    if support is None:
        raise ServiceError("Программа стимулирования не найдена", 404)
    return support_view(support)


async def list_condition_requests(session: AsyncSession, application_id: UUID,
                                  actor: dict[str, Any]) -> dict[str, Any]:
    application = await repo.lock_application(session, application_id, actor, lock=False)
    items = await repo.list_condition_requests(session, application_id, actor)
    return {"items": items,
            "can_negotiate": bool(actor["can_write"] and actor["role"] in {"dealer", "leasing_company"}
                                  and (application or items)),
            "can_request": bool(actor["can_write"] and actor["role"] == "dealer" and application
                                and not application["has_lca"])}


async def list_condition_request_inbox(session: AsyncSession, actor: dict[str, Any], *,
                                       page: int, page_size: int) -> dict[str, Any]:
    result = await repo.list_condition_request_inbox(
        session, actor, offset=(page - 1) * page_size, limit=page_size)
    return {"items": result["items"], "pagination": pagination(result["total"], page, page_size)}
