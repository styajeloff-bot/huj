"""Payload shape, wording and role-safe data of ``fast_deal.*`` notifications.

The payload of an event is built once, from what every addressee may know: a leasing
company never receives support programs, amounts, comments or statuses, so no support
fact enters the payload except in ``fast_deal.support_*``, which are addressed to the
dealer side and the distributor only. Positions go through the same allow-list as the
leasing company's card. The view of one recipient is derived from the payload, the
recipient's role and relation to the event; nothing else is copied to the inbox.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from domain.events.notifications import NotificationEvent
from domain.fast_deals.money import CENT, wire
from domain.fast_deals.projection import project_changes_for_lc, project_vehicle_for_lc
from domain.fast_deals.values import (
    NotifyEvent,
    Role,
    SourceType,
    SupportRequestStatus,
)

MAX_VEHICLES = 10
MAX_CHANGES = 40
MAX_TEXT = 2000
ACTION_LABEL = "Открыть сделку"

_NBSP = " "


class Scope:
    """Payload ``scope``: whom a fact is addressed to; it selects the wording."""

    INVITED_LCS = "invited_leasing_companies"
    DEALER = "dealer"
    INITIATOR = "initiator"
    COUNTERPARTY = "counterparty"
    SELECTED_LC = "selected_leasing_company"
    OTHER_LCS = "other_leasing_companies"
    PREVIOUS_LCS = "previous_leasing_companies"
    ALL_PARTIES = "all_parties"
    ASSIGNMENT = "assignment"
    DISTRIBUTOR = "distributor"


class Relation:
    """How one recipient relates to an assignment fact (set by the recipient resolver)."""

    PRIMARY = "primary"
    ADDITIONAL = "additional"
    ADMINISTRATOR = "administrator"
    REMOVED = "removed"


@dataclass(frozen=True)
class FastDealView:
    """Inbox/e-mail presentation of one event for one recipient."""

    title: str
    message: str
    data: dict[str, Any]
    # False when the card is not (or no longer) readable by this recipient.
    card_visible: bool


# ---------------------------------------------------------------------- payload shaping

def _wire(value: Any) -> Any:
    if isinstance(value, Decimal):
        return wire(value)
    return value


def clip(value: Any) -> str | None:
    """Free text of a user, bounded; ``None`` for blank."""
    text = str(value).strip() if value is not None else ""
    return text[:MAX_TEXT] or None


def payload_vehicles(vehicles: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Positions through the leasing company's allow-list: no support, no breakdown."""
    result: list[dict[str, Any]] = []
    for vehicle in vehicles[:MAX_VEHICLES]:
        projected = project_vehicle_for_lc(vehicle)
        result.append(
            {
                name: _wire(projected.get(name))
                for name in (
                    "vin", "mark_name", "model_name", "modification_name", "final_price",
                )
            }
        )
    return result


def payload_terms(values: Mapping[str, Any], *, prefix: str = "") -> dict[str, Any]:
    """Leasing terms of a deal (``prefix="final_"`` for the final ones) or of an offer."""
    names = {
        "total_amount": f"{prefix}total_amount",
        "down_payment": f"{prefix}down_payment",
        "down_payment_percent": f"{prefix}down_payment_percent",
        "lease_term_months": f"{prefix}lease_term_months",
        "monthly_payment": f"{prefix}monthly_payment",
        "buyout_amount": f"{prefix}buyout_amount",
        "total_cost": f"{prefix}total_cost",
    }
    terms = {key: _wire(values.get(column)) for key, column in names.items()}
    return {key: value for key, value in terms.items() if value is not None}


def payload_requested_terms(deal: Mapping[str, Any]) -> dict[str, Any]:
    """Requested terms of a deal; the financing amount and the contract cost are derived."""
    snapshot: Mapping[str, Any] = deal.get("calc_snapshot") or {}
    return payload_terms(
        {
            **deal,
            "total_amount": snapshot.get("financed_amount"),
            "total_cost": snapshot.get("total_cost"),
        }
    )


def payload_changes(changes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The dealer's changes as the leasing company may see them (final prices, data)."""
    visible = project_changes_for_lc([dict(item) for item in changes])
    return [
        {
            "vehicle_id": str(item["vehicle_id"]),
            "vin": item.get("vin"),
            "field": item["field"],
            "before": _wire(item.get("before")),
            "after": _wire(item.get("after")),
        }
        for item in visible[:MAX_CHANGES]
    ]


def payload_support_request(
    request: Mapping[str, Any], vehicles: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """A support request for its dealer-side/distributor addressees only."""
    # The request carries the position id as a string, the rows carry a UUID.
    vehicle_id = str(request.get("fast_deal_vehicle_id"))
    vehicle = next((item for item in vehicles if str(item["id"]) == vehicle_id), {})
    return {
        "id": str(request["id"]) if request.get("id") else None,
        "status": request.get("status"),
        "requested_amount": _wire(request.get("requested_amount")),
        "decided_amount": _wire(request.get("decided_amount")),
        "comment": clip(request.get("comment")),
        "decision_comment": clip(request.get("decision_comment")),
        "vin": vehicle.get("vin") or request.get("vin"),
        "mark_name": vehicle.get("mark_name"),
        "model_name": vehicle.get("model_name"),
    }


# --------------------------------------------------------------------------- formatting

def money_text(value: Any) -> str | None:
    """``3 500 000,00 ₽`` from an exact decimal string; ``None`` when absent."""
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None
    return f"{amount:,.2f}".replace(",", _NBSP).replace(".", ",") + f"{_NBSP}₽"


def _percent_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        percent = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None
    return f"{percent:f}".replace(".", ",") + f"{_NBSP}%"


def _vehicle_label(vehicle: Mapping[str, Any]) -> str:
    name = " ".join(
        str(vehicle[key])
        for key in ("mark_name", "model_name", "modification_name")
        if vehicle.get(key)
    )
    vin = f"VIN {vehicle['vin']}" if vehicle.get("vin") else ""
    return ", ".join(part for part in (name, vin) if part)


def _party(label: str, name: Any) -> str:
    return f"{label} «{name}»" if name else label


def _plain(value: Any) -> str:
    if value is None or value in ("", []):
        return "—"
    if isinstance(value, list):
        return ", ".join(
            str(item.get("name") or item.get("code") or "—") if isinstance(item, Mapping)
            else str(item)
            for item in value
        )
    return str(value)


_CHANGE_LABELS = {
    "mark_name": "Марка",
    "model_name": "Модель",
    "modification_name": "Модификация",
    "body_color_name": "Цвет",
    "vin": "VIN",
    "final_price": "Цена",
    "equipments": "Оборудование",
    "services": "Услуги",
    "purposes": "Цели использования",
    "regions": "Регионы",
    "item_status": "Статус позиции",
}
_ITEM_STATUS = {"active": "активна", "removed": "удалена", "replaced": "заменена"}
_SUPPORT_OUTCOME: dict[str, str] = {
    SupportRequestStatus.APPROVED: "согласовал",
    SupportRequestStatus.PRE_APPROVED: "предварительно согласовал",
    SupportRequestStatus.CANCELLED: "отклонил",
}
_SUPPORT_STATUS: dict[str, str] = {
    SupportRequestStatus.REQUESTED: "Запрошено",
    SupportRequestStatus.PRE_APPROVED: "Предварительно согласовано",
    SupportRequestStatus.APPROVED: "Согласовано",
    SupportRequestStatus.CANCELLED: "Отклонено",
}
_REASON_EVENTS = frozenset(
    {
        NotifyEvent.LC_REJECTED,
        NotifyEvent.REJECTED,
        NotifyEvent.CHANGES_REJECTED,
        NotifyEvent.CANCELLED,
    }
)


def _change_line(change: Mapping[str, Any]) -> str:
    field = str(change.get("field"))
    values = []
    for key in ("before", "after"):
        value = change.get(key)
        if field == "final_price":
            values.append(money_text(value) or "—")
        elif field == "item_status":
            values.append(_ITEM_STATUS.get(str(value), _plain(value)))
        else:
            values.append(_plain(value))
    where = f"VIN {change['vin']}: " if change.get("vin") else ""
    return f"{where}{_CHANGE_LABELS.get(field, field)}: {values[0]} → {values[1]}"


# ------------------------------------------------------------------------------ wording

def _headline(  # noqa: PLR0911, PLR0912 - one flat table of wordings
    event: NotificationEvent, relation: str | None
) -> tuple[str, str]:
    """Title and first sentence of an event, for its scope and recipient relation."""
    payload = event.payload
    number = f"№{event.request_number}"
    scope = payload["scope"]
    actor = payload.get("actor_company_name")
    kind = event.event_type
    if kind == NotifyEvent.SENT:
        if payload["source_type"] == SourceType.DEALER_TO_LEASING:
            return (
                "Новая сделка на рассмотрение",
                f"{_party('Дилер', actor)} отправил сделку {number} на рассмотрение. "
                "Отправьте коммерческое предложение или откажитесь.",
            )
        return (
            "Сделка на подтверждение",
            f"{_party('Лизинговая компания', actor)} отправила сделку {number} "
            "на подтверждение.",
        )
    if kind == NotifyEvent.OFFER_SENT:
        return (
            "Получено коммерческое предложение",
            f"{_party('Лизинговая компания', actor)} отправила коммерческое "
            f"предложение по сделке {number}.",
        )
    if kind == NotifyEvent.OFFER_SELECTED:
        if scope == Scope.SELECTED_LC:
            return (
                "Ваше предложение выбрано",
                f"Дилер выбрал ваше коммерческое предложение по сделке {number}. "
                "Требуется окончательное подтверждение.",
            )
        return (
            "Выбрано другое предложение",
            f"Дилер выбрал предложение другой лизинговой компании по сделке {number}.",
        )
    if kind == NotifyEvent.SELECTION_WITHDRAWN:
        if scope == Scope.SELECTED_LC:
            return (
                "Выбор предложения снят",
                f"Дилер снял выбор вашего коммерческого предложения по сделке {number}. "
                "Сделка вернулась к рассмотрению предложений.",
            )
        return (
            "Выбор предложения снят",
            f"Дилер снял выбор предложения по сделке {number}. "
            "Рассмотрение предложений продолжается.",
        )
    if kind == NotifyEvent.LC_REJECTED:
        return (
            "Лизинговая компания отказала",
            f"{_party('Лизинговая компания', actor)} отказала по сделке {number}.",
        )
    if kind == NotifyEvent.CONFIRMED:
        return "Сделка подтверждена", f"Сделка {number} подтверждена."
    if kind == NotifyEvent.REJECTED:
        return (
            "Сделка отклонена",
            f"{_party('Контрагент', actor)} отклонил сделку {number}.",
        )
    if kind == NotifyEvent.RESET:
        return (
            "Рассмотрение сделки завершено",
            f"Дилер изменил данные сделки {number} после отправки, рассмотрение "
            "завершено. Ранее отправленные коммерческие предложения не учитываются. "
            "При повторной отправке вы получите новое приглашение.",
        )
    if kind == NotifyEvent.CHANGES_SENT:
        return (
            "Дилер отправил изменения",
            f"{_party('Дилер', actor)} отправил изменения по сделке {number} "
            "на ваше решение.",
        )
    if kind == NotifyEvent.CHANGES_ACCEPTED:
        return (
            "Изменения приняты",
            f"{_party('Лизинговая компания', actor)} приняла изменения по сделке "
            f"{number}. Сделка подтверждена.",
        )
    if kind == NotifyEvent.CHANGES_REJECTED:
        return (
            "Изменения отклонены",
            f"{_party('Лизинговая компания', actor)} отклонила изменения по сделке "
            f"{number}.",
        )
    if kind == NotifyEvent.CANCELLED:
        return (
            "Сделка отменена",
            f"Сделка {number} отменена инициатором"
            + (f" «{actor}»" if actor else "")
            + ".",
        )
    if kind == NotifyEvent.ASSIGNEES_CHANGED:
        return _assignment_headline(payload, number, relation)
    if kind == NotifyEvent.SUPPORT_REQUESTED:
        request = payload.get("support_request") or {}
        return (
            "Запрос поддержки по сделке",
            f"{_party('Дилер', actor)} запросил поддержку по сделке {number}"
            + _support_subject(request)
            + ".",
        )
    request = payload.get("support_request") or {}
    outcome = _SUPPORT_OUTCOME.get(str(request.get("status")), "рассмотрел")
    return (
        "Решение по запросу поддержки",
        f"{_party('Дистрибьютор', actor)} {outcome} запрос поддержки по сделке "
        f"{number}" + _support_subject(request, decided=True) + ".",
    )


def _support_subject(request: Mapping[str, Any], *, decided: bool = False) -> str:
    position = _vehicle_label(request)
    amount = money_text(
        request.get("decided_amount") if decided and request.get("decided_amount")
        else request.get("requested_amount")
    )
    parts = [part for part in (position, f"сумма {amount}" if amount else "") if part]
    return f": {', '.join(parts)}" if parts else ""


def _assignment_headline(
    payload: Mapping[str, Any], number: str, relation: str | None
) -> tuple[str, str]:
    if relation == Relation.PRIMARY:
        return (
            "Вы назначены ответственным",
            f"Вы назначены основным ответственным по сделке {number}.",
        )
    if relation == Relation.ADDITIONAL:
        return (
            "Вы назначены ответственным",
            f"Вы назначены дополнительным ответственным по сделке {number}.",
        )
    if relation == Relation.REMOVED:
        return (
            "Вы больше не ответственный",
            f"Вы больше не назначены ответственным по сделке {number}.",
        )
    named = {
        str(item.get("role")): item.get("name") for item in payload.get("assignees") or []
    }
    parts = [
        f"{label} — {named[role]}"
        for role, label in (("primary", "основной"), ("additional", "дополнительный"))
        if named.get(role)
    ]
    company = _party("компании", payload.get("assignee_company_name"))
    return (
        "Изменены ответственные по сделке",
        f"По сделке {number} изменены ответственные {company}"
        + (f": {'; '.join(parts)}" if parts else "")
        + ".",
    )


def _terms_lines(terms: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    if amount := money_text(terms.get("total_amount")):
        lines.append(f"Сумма финансирования: {amount}")
    if down := money_text(terms.get("down_payment")):
        percent = _percent_text(terms.get("down_payment_percent"))
        lines.append(f"Авансовый платёж: {down}" + (f" ({percent})" if percent else ""))
    if terms.get("lease_term_months") is not None:
        lines.append(f"Срок лизинга: {terms['lease_term_months']} мес.")
    if monthly := money_text(terms.get("monthly_payment")):
        lines.append(f"Ежемесячный платёж: {monthly}")
    if buyout := money_text(terms.get("buyout_amount")):
        lines.append(f"Выкупная стоимость: {buyout}")
    if cost := money_text(terms.get("total_cost")):
        lines.append(f"Общая стоимость договора: {cost}")
    return lines


def _support_lines(request: Mapping[str, Any]) -> list[str]:
    lines = []
    if status := _SUPPORT_STATUS.get(str(request.get("status"))):
        lines.append(f"Статус запроса: {status}")
    if amount := money_text(request.get("requested_amount")):
        lines.append(f"Запрошенная сумма: {amount}")
    if amount := money_text(request.get("decided_amount")):
        lines.append(f"Согласованная сумма: {amount}")
    if request.get("comment"):
        lines.append(f"Комментарий дилера: {request['comment']}")
    if request.get("decision_comment"):
        lines.append(f"Комментарий дистрибьютора: {request['decision_comment']}")
    return lines


def _facts(payload: Mapping[str, Any], role: str) -> dict[str, Any]:
    """What this role may be told about the deal; nothing is copied blindly."""
    facts: dict[str, Any] = {
        "source_type": payload["source_type"],
        "status": payload.get("deal_status"),
    }
    for name in ("client_name", "vehicles", "vehicles_count", "vehicles_total", "comment"):
        if payload.get(name) not in (None, [], ""):
            facts[name] = payload[name]
    changes = payload.get("changes") or []
    if role == Role.LEASING_COMPANY:
        changes = payload_changes(changes)
    if changes:
        facts["changes"] = changes
    # Leasing conditions are the leasing company's and the dealer's business.
    if role != Role.DISTRIBUTOR and payload.get("terms"):
        facts["terms"] = payload["terms"]
    if role in {Role.DEALER, Role.DISTRIBUTOR} and payload.get("support_request"):
        facts["support_request"] = payload["support_request"]
    return facts


def _lines(facts: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    if facts.get("client_name"):
        lines.append(f"Клиент: {facts['client_name']}")
    vehicles = facts.get("vehicles") or []
    for vehicle in vehicles:
        price = money_text(vehicle.get("final_price"))
        lines.append(
            f"Техника: {_vehicle_label(vehicle)}" + (f" — {price}" if price else "")
        )
    hidden = int(facts.get("vehicles_count") or 0) - len(vehicles)
    if hidden > 0:
        lines.append(f"…и ещё позиций: {hidden}")
    if total := money_text(facts.get("vehicles_total")):
        lines.append(f"Сумма по сделке: {total}")
    lines.extend(_terms_lines(facts.get("terms") or {}))
    lines.extend(_support_lines(facts.get("support_request") or {}))
    if facts.get("changes"):
        lines.append("Изменения по позициям:")
        lines.extend(_change_line(change) for change in facts["changes"])
    if facts.get("comment"):
        lines.append(f"Комментарий: {facts['comment']}")
    return lines


def fast_deal_view(
    event: NotificationEvent, *, role: str, relation: str | None = None
) -> FastDealView:
    """Title, message and role-safe data of one event for one recipient.

    Former participants (a previous review cycle, a removed assignee) are told the
    fact only: the deal's business data is not theirs any more.
    """
    scope = event.payload["scope"]
    title, message = _headline(event, relation)
    reason = clip(event.payload.get("reason"))
    if reason and event.event_type in _REASON_EVENTS:
        message += f" Причина: {reason}."
    former = scope == Scope.PREVIOUS_LCS or relation == Relation.REMOVED
    facts = {} if former else _facts(event.payload, role)
    if reason and event.event_type in _REASON_EVENTS and not former:
        facts["reason"] = reason
    data: dict[str, Any] = {"action_label": ACTION_LABEL}
    if facts:
        data["fast_deal"] = facts
        data["summary_lines"] = _lines(facts)
    return FastDealView(title=title, message=message, data=data, card_visible=not former)
