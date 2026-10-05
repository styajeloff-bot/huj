"""Create a draft deal: the client is a company and a phone, the direction follows the role."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.access import ensure_membership
from application.fast_deals.actor import Actor
from application.fast_deals.card import build_card
from application.fast_deals.history import bump_and_log
from application.fast_deals.numbering import allocate_display_number
from domain.fast_deals.errors import FastDealAccessDeniedError, FastDealValidationError
from domain.fast_deals.numbering import normalize_client_inn
from domain.fast_deals.values import DealStatus, HistoryEvent, Role, SourceType
from infrastructure.repositories import company_registration_repository as company_repo
from infrastructure.repositories import fast_deal_access_repository as access_repo
from infrastructure.repositories import fast_deal_repository as repo

Record = dict[str, Any]

_PHONE = re.compile(r"^\+7\d{10}$")


@dataclass
class CreateFastDealCommand:
    actor: Actor
    company_id: UUID | None  # an existing company of the client, XOR ``company``
    company: dict[str, Any] | None  # the company object selected in the autocomplete
    client_phone: str


async def handle_create_fast_deal(
    cmd: CreateFastDealCommand, session: AsyncSession
) -> dict[str, Any]:
    """Create a draft; the author becomes the primary assignee of the initiator company.

    A dealer creates a DD (it is the dealer of the deal), a leasing company creates a DL
    (it is the leasing company). The client gets no user, no SMS and no access: only a
    company row is created when the selected company is not known yet.
    """
    actor = cmd.actor
    source_type = _direction(actor)
    await ensure_membership(session, actor)
    phone = _validate_phone(cmd.client_phone)
    client = await _resolve_client(session, cmd)
    if client["id"] == actor.company_id:
        raise FastDealValidationError(
            "Клиентом сделки не может быть ваша собственная компания", field="company"
        )
    number = await allocate_display_number(session, source_type, client["inn"])
    parties: Record = (
        {"dealer_company_id": actor.company_id}
        if source_type == SourceType.DEALER_TO_LEASING
        else {"leasing_company_id": actor.company_id}
    )
    deal = await repo.insert_deal(
        session,
        {
            "display_number": number,
            "source_type": source_type.value,
            "status": DealStatus.DRAFT.value,
            "client_company_id": client["id"],
            "client_phone": phone,
            "initiator_company_id": actor.company_id,
            "created_by": actor.user_id,
            "version": 1,
            "review_cycle": 1,
            **parties,
        },
    )
    await access_repo.replace_company_assignees(
        session,
        deal_id=deal["id"],
        company_id=actor.company_id,
        primary_user_id=actor.user_id,
        additional_user_id=None,
        assigned_by=actor.user_id,
    )
    # The deal starts at version 1: the history row describes it without a bump.
    await bump_and_log(
        session, deal, actor, HistoryEvent.CREATED,
        to_status=DealStatus.DRAFT.value, version=deal["version"],
    )
    return {"deal": await build_card(session, actor, deal["id"])}


def _direction(actor: Actor) -> SourceType:
    if actor.role == Role.DEALER:
        source_type = SourceType.DEALER_TO_LEASING
    elif actor.role == Role.LEASING_COMPANY:
        source_type = SourceType.LEASING_TO_DEALER
    else:
        raise FastDealAccessDeniedError(
            "Регистрировать сделки могут только дилеры и лизинговые компании"
        )
    if actor.company_id is None:
        raise FastDealAccessDeniedError("Выберите компанию, от имени которой создаётся сделка")
    return source_type


def _validate_phone(value: str | None) -> str:
    phone = (value or "").strip()
    if not _PHONE.fullmatch(phone):
        raise FastDealValidationError(
            "Телефон клиента: +7 и 10 цифр, например +79991234567", field="client_phone"
        )
    return phone


def _client_inn(value: Any, field: str) -> str:
    try:
        return normalize_client_inn(value)
    except FastDealValidationError as exc:
        raise FastDealValidationError(str(exc), field=field) from exc


async def _resolve_client(session: AsyncSession, cmd: CreateFastDealCommand) -> Record:
    """The client company: an existing one by id, or the selected object (created if new)."""
    if (cmd.company_id is None) == (cmd.company is None):
        raise FastDealValidationError(
            "Укажите клиента: существующую компанию либо выбранную компанию целиком",
            field="company",
        )
    if cmd.company_id is not None:
        brief = (await access_repo.company_briefs(session, [cmd.company_id])).get(cmd.company_id)
        if brief is None:
            raise FastDealValidationError("Компания клиента не найдена", field="company_id")
        return {"id": brief["id"], "inn": _client_inn(brief["inn"], "company_id")}
    payload = dict(cmd.company or {})
    payload["inn"] = _client_inn(payload.get("inn"), "company")
    try:
        company: Record | None = await company_repo.create_or_get_company(
            session, cast("company_repo.CompanyPayload", payload)
        )
    except ValueError as exc:
        raise FastDealValidationError(
            "Адрес компании клиента не может быть пустым", field="company"
        ) from exc
    if company is None or company.get("id") is None:
        raise FastDealValidationError("Не удалось сохранить компанию клиента", field="company")
    return {"id": company["id"], "inn": payload["inn"]}
