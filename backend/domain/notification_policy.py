"""Business notification matrix and role-safe presentation rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from domain.events.notifications import NotificationEvent


@dataclass(frozen=True)
class EventPolicy:
    title: str
    notification_type: str
    roles: frozenset[str]
    category: str | None


def _policy(
    title: str,
    kind: str,
    roles: str,
    category: str | None = None,
    *,
    in_app_only: bool = False,
) -> EventPolicy:
    return EventPolicy(
        title,
        kind,
        frozenset(roles.split()),
        None if in_app_only else category or f"{kind}_emails",
    )


POLICIES = {
    "document_registry.expiring": _policy(
        "Истекает срок действия документа",
        "document_status",
        "leasing_company dealer distributor carcraft_employee",
        in_app_only=True,
    ),
    "monetization.deal_created": _policy(
        "Новая сделка монетизации",
        "system",
        "leasing_company dealer distributor",
        in_app_only=True,
    ),
    "monetization.party_confirmed": _policy(
        "Участник подтвердил монетизацию",
        "system",
        "carcraft_employee",
        in_app_only=True,
    ),
    "monetization.deal_paid": _policy(
        "Монетизация сделки подтверждена",
        "system",
        "leasing_company dealer distributor",
        in_app_only=True,
    ),
    "monetization.deal_terms_changed": _policy(
        "Изменены условия сделки",
        "system",
        "leasing_company dealer distributor carcraft_employee",
        in_app_only=True,
    ),
    "monetization.capture_failed": _policy(
        "Не удалось подобрать условия монетизации",
        "system",
        "carcraft_employee",
        in_app_only=True,
    ),
    "monetization.condition_requested": _policy(
        "Запрошена дополнительная комиссия",
        "system",
        "leasing_company",
        in_app_only=True,
    ),
    "monetization.condition_responded": _policy(
        "Получен ответ по дополнительной комиссии", "system", "dealer", in_app_only=True
    ),
    "monetization.condition_decided": _policy(
        "Дилер принял решение по комиссии",
        "system",
        "leasing_company",
        in_app_only=True,
    ),
    "leasing.application_created": _policy(
        "Создана заявка на лизинг", "application_status", "dealer carcraft_employee"
    ),
    "leasing.vehicle_reserved": _policy(
        "Автомобиль забронирован",
        "application_status",
        "client leasing_company distributor carcraft_employee",
    ),
    "leasing.vehicle_reservation_expired": _policy(
        "Срок бронирования автомобиля истёк",
        "application_status",
        "client leasing_company distributor carcraft_employee",
    ),
    "leasing.vehicle_cancelled": _policy(
        "Автомобиль отменён дилером",
        "application_status",
        "client leasing_company distributor carcraft_employee",
    ),
    "leasing.additional_price_changed": _policy(
        "Изменилась стоимость опций и услуг",
        "application_status",
        "client leasing_company",
    ),
    "leasing.company_assigned": _policy(
        "Вам назначена заявка", "leasing_approval", "leasing_company"
    ),
    "leasing.application_status_changed": _policy(
        "Изменён статус заявки", "application_status", "carcraft_employee"
    ),
    "leasing.company_selected": _policy(
        "Клиент выбрал лизинговую компанию",
        "leasing_approval",
        "leasing_company carcraft_employee",
    ),
    "leasing.company_not_selected": _policy(
        "Клиент выбрал другую лизинговую компанию",
        "leasing_approval",
        "leasing_company",
    ),
    "leasing.preliminary_offer_accepted": _policy(
        "Принято предварительное предложение",
        "leasing_approval",
        "leasing_company dealer distributor",
    ),
    "leasing.final_offer_accepted": _policy(
        "Принято итоговое предложение",
        "leasing_approval",
        "leasing_company dealer distributor",
    ),
    "leasing.application_cancelled": _policy(
        "Клиент отменил заявку",
        "application_status",
        "client dealer leasing_company distributor carcraft_employee",
    ),
    "leasing.company_decision_received": _policy(
        "Получено решение лизинговой компании",
        "leasing_approval",
        "client dealer distributor carcraft_employee",
    ),
    "leasing.documents_requested": _policy(
        "Запрошены дополнительные документы", "document_request", "client dealer"
    ),
    "leasing.documents_uploaded": _policy(
        "Загружены запрошенные документы", "document_status", "leasing_company"
    ),
    "leasing.documents_uploads_summary": _policy(
        "Клиент загрузил запрошенные документы", "document_status", "leasing_company"
    ),
    "leasing.application_finalized": _policy(
        "Заявка завершена",
        "application_status",
        "client dealer leasing_company distributor carcraft_employee",
    ),
    "exchange.request_published": _policy(
        "Новая заявка на Бирже", "exchange_new_request", "dealer", "exchange_emails"
    ),
    "exchange.bid_created": _policy(
        "Создана ставка на Бирже",
        "exchange_new_bid",
        "leasing_company distributor dealer",
        "exchange_emails",
    ),
    "exchange.bid_updated": _policy(
        "Изменена ставка на Бирже",
        "exchange_bid_updated",
        "leasing_company distributor dealer",
        "exchange_emails",
    ),
    "exchange.bid_withdrawn": _policy(
        "Ставка на Бирже отозвана",
        "exchange_bid_withdrawn",
        "leasing_company distributor dealer",
        "exchange_emails",
    ),
    "exchange.request_changed": _policy(
        "Изменена заявка Биржи",
        "exchange_request_changed",
        "dealer distributor",
        "exchange_emails",
    ),
    "exchange.deadline_24h": _policy(
        "До окончания заявки Биржи — менее суток",
        "exchange_deadline",
        "dealer",
        "exchange_emails",
    ),
    "exchange.deadline_1h": _policy(
        "До окончания заявки Биржи — менее часа",
        "exchange_deadline",
        "dealer",
        "exchange_emails",
    ),
    "exchange.request_finalized": _policy(
        "Заявка Биржи завершена",
        "exchange_request_finalized",
        "dealer leasing_company distributor",
        "exchange_emails",
    ),
    "exchange.bid_selected": _policy(
        "Ваша ставка выбрана", "exchange_bid_accepted", "dealer", "exchange_emails"
    ),
    "exchange.bid_not_selected": _policy(
        "Выбрана ставка другого дилера",
        "exchange_bid_not_selected",
        "dealer",
        "exchange_emails",
    ),
}


def _targets_leasing_company(
    event: NotificationEvent, recipient: dict[str, Any]
) -> bool:
    lc_id = recipient.get("leasing_company_id")
    target = event.payload.get("leasing_company_id")
    selected = event.payload.get("selected_leasing_company_id")
    if event.event_type == "leasing.company_not_selected":
        return selected is not None and str(lc_id) != str(selected)
    if event.event_type in {
        "leasing.company_assigned",
        "leasing.company_selected",
        "leasing.preliminary_offer_accepted",
        "leasing.final_offer_accepted",
        "leasing.documents_uploaded",
        "leasing.documents_uploads_summary",
    }:
        return target is not None and str(lc_id) == str(target)
    if event.event_type == "leasing.additional_price_changed" and target is not None:
        return str(lc_id) == str(target)
    return True


def targets_context(
    event: NotificationEvent, recipient: dict[str, Any], context: dict[str, Any]
) -> bool:
    """Candidate selection, NOT an authorization decision."""
    role = recipient["role"]
    if role not in POLICIES[event.event_type].roles:
        return False
    if event.event_type.startswith(("monetization.", "document_registry.")):
        return True
    if event.event_type.startswith("leasing."):
        return role != "leasing_company" or _targets_leasing_company(event, recipient)
    return _targets_exchange_context(event, recipient, context)


def _targets_exchange_context(
    event: NotificationEvent, recipient: dict[str, Any], context: dict[str, Any]
) -> bool:
    role, company = recipient["role"], recipient.get("company_id")
    if event.event_type in {
        "exchange.bid_created",
        "exchange.bid_updated",
        "exchange.bid_withdrawn",
    } and (
        recipient["user_id"] == event.actor_user_id
        or (
            role == "dealer"
            and str(company) == str(event.payload.get("dealer_company_id"))
        )
    ):
        return False
    if (
        event.event_type == "exchange.request_changed"
        and recipient["user_id"] == event.actor_user_id
    ):
        return False
    selected_dealer = event.payload.get("selected_dealer_company_id")
    if (
        event.event_type == "exchange.request_finalized"
        and event.new_values.get("status") == "deal"
        and role == "dealer"
        and company in context.get("bidding_dealer_company_ids", [])
    ):
        # Bidder companies receive their targeted selected/not-selected fact.
        return False
    if event.event_type == "exchange.bid_selected":
        return selected_dealer is not None and str(company) == str(selected_dealer)
    if event.event_type == "exchange.bid_not_selected":
        return (
            selected_dealer is not None
            and str(company) != str(selected_dealer)
            and company in context.get("bidding_dealer_company_ids", [])
        )
    return True


def action_route(
    event: NotificationEvent, role: str, storefront_slug: str | None = None,
    leasing_company_id: UUID | None = None,
    company_id: UUID | None = None,
) -> str:
    company_query = f"notification_company_id={company_id}" if company_id else ""
    if event.event_type == "document_registry.expiring":
        context = f"&{company_query}" if company_query else ""
        return f"/workspace/document-registry?document={event.entity_id}{context}"
    if event.event_type.startswith("monetization."):
        if event.entity_type == "monetization_deal":
            route = f"/workspace/monetization?deal={event.entity_id}"
        elif event.application_id is not None:
            section = "applications" if event.event_type == "monetization.capture_failed" else "monetization"
            route = f"/workspace/{section}?application={event.application_id}"
        elif event.payload.get("exchange_request_id"):
            route = (
                f"/workspace/exchange?request={event.payload['exchange_request_id']}"
            )
        elif event.payload.get("fast_deal_id"):
            route = f"/workspace/fast-deals/{event.payload['fast_deal_id']}"
        else:
            route = "/workspace/monetization"
        return route + (
            ("&" if "?" in route else "?") + company_query if company_query else ""
        )
    if event.event_type.startswith("exchange."):
        context = f"&{company_query}" if company_query else ""
        return f"/workspace/exchange?request={event.aggregate_id}{context}"
    if role == "client":
        prefix = f"/{storefront_slug}" if storefront_slug else ""
        section = client_notification_section(event.event_type, event.new_values)
        query_parts = [company_query] if company_query else []
        if section is not None:
            query_parts.append(f"section={section}")
        context = "?" + "&".join(query_parts) if query_parts else ""
        return f"{prefix}/application/{event.aggregate_id}{context}"
    if role == "leasing_company":
        context = f"?leasing_company_id={leasing_company_id}" if leasing_company_id else ""
        return f"/workspace/leasing-applications/{event.aggregate_id}{context}"
    context = f"&{company_query}" if company_query else ""
    return f"/workspace/applications?application={event.aggregate_id}{context}"


def client_notification_section(event_type: str, new_values: dict[str, Any]) -> str | None:
    """A business fact selects a section, never changes access or LCA state."""
    if event_type == "leasing.documents_requested":
        return "documents"
    if event_type != "leasing.company_decision_received":
        return None
    return {
        "approved_scoring": "preliminary",
        "approved_scoring_another_cond": "preliminary",
        "approved_final": "final",
        "approved_final_another_cond": "final",
    }.get(str(new_values.get("lca_status", "")))


def normalize_inbox_action_url(
    action_url: str | None, application_id: UUID | None, data: dict[str, Any] | None,
) -> str | None:
    """Read-only projection of structured historical links; manual URLs stay intact."""
    if (not action_url or application_id is None or not isinstance(data, dict)
        or not action_url.startswith("/") or action_url.startswith("//")):
        return action_url
    if data.get("entity_type") != "leasing_application" or data.get("entity_id") != str(application_id):
        return action_url
    values = data.get("new_values")
    section = client_notification_section(
        str(data.get("event_type", "")), values if isinstance(values, dict) else {},
    )
    if section is None or re.search(
        r"[\s\\\\\x00-\x1f\x7f]|%(?:[01][0-9a-f]|5c|7f)", action_url, re.IGNORECASE,
    ):
        return action_url
    parsed = urlsplit(action_url)
    if parsed.scheme or parsed.netloc or not re.fullmatch(
        rf"/(?:[a-z0-9][a-z0-9-]*/)?application/{application_id}", parsed.path,
    ):
        return action_url
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if (
        not any(key == "step" for key, _ in query_pairs)
        or any(key == "section" for key, _ in query_pairs)
    ):
        return action_url
    query = urlencode(
        [(key, value) for key, value in query_pairs if key != "step"] + [("section", section)]
    )
    return urlunsplit(("", "", parsed.path, query, parsed.fragment))


# Explicit field allowlists, never copy arbitrary Kafka dictionaries to inbox.
PUBLIC_CHANGES = frozenset(
    {
        "status",
        "lca_status",
        "car_status",
        "reserve_expires_at",
        "client_decision_action",
        "document_status",
        "equipments",
        "services",
        "quantity",
        "price",
        "expiration_at",
        "discount",
        "discount_percent",
        "discount_value",
        "total_price",
        "discount_type",
        "file_name",
    }
)
COMPETITOR_CHANGES = frozenset({"price", "quantity", "status"})


def notification_data(event: NotificationEvent, role: str) -> dict[str, Any]:
    competitor = role == "dealer" and event.event_type in {
        "exchange.bid_created",
        "exchange.bid_updated",
        "exchange.bid_withdrawn",
    }
    allowed = COMPETITOR_CHANGES if competitor else PUBLIC_CHANGES
    # Selected-other events must not expose a competitor's LC branch outcome.
    fields = (
        []
        if event.event_type == "leasing.company_not_selected"
        else [name for name in event.changed_fields if name in allowed]
    )
    result: dict[str, Any] = {
        "event_type": event.event_type,
        "entity_type": event.entity_type,
        "entity_id": str(event.entity_id),
        "event_id": str(event.event_id),
        "request_number": event.request_number,
        "occurred_at": event.occurred_at.isoformat(),
        "changed_fields": fields,
        "previous_values": {
            name: _public_value(name, event.previous_values.get(name))
            for name in fields
        },
        "new_values": {
            name: _public_value(name, event.new_values.get(name)) for name in fields
        },
    }
    if event.event_type == "document_registry.expiring":
        result.update({name: event.payload[name] for name in (
            "version_id", "valid_to", "document_type", "document_name",
        )})
    if (
        event.event_type == "leasing.application_created"
        and role == "dealer"
        and event.payload
        and event.payload.get("overstock_items")
    ):
        result["overstock_items"] = event.payload["overstock_items"]
    if event.event_type == "monetization.deal_terms_changed":
        result["revision"] = event.payload["revision"]
    if event.event_type.startswith("monetization.") and role == "carcraft_employee":
        if event.event_type == "monetization.capture_failed":
            result["reason"] = str(event.payload["reason"])
        if event.event_type == "monetization.party_confirmed":
            result["confirmed_party"] = event.payload["confirmed_party"]
    if event.event_type == "exchange.request_changed" and {"file_url", "file_name"}.intersection(event.changed_fields):
        result["attachment_changed"] = True
        result["attachment_name"] = _public_value(
            "file_name", event.new_values.get("file_name", event.payload.get("attachment_name")),
        )
    if event.event_type.startswith("exchange."):
        expiry = event.payload.get("expiration_at")
        seconds = (
            max(
                0,
                int(
                    (datetime.fromisoformat(expiry) - event.occurred_at).total_seconds()
                ),
            )
            if expiry
            else None
        )
        result.update(
            expiration_at=expiry,
            remaining_seconds=seconds,
            remaining_time=f"{seconds // 3600} ч {(seconds % 3600) // 60} мин"
            if seconds is not None
            else None,
        )
    return result


def _public_value(name: str, value: Any) -> Any:
    if name == "file_name":
        if not isinstance(value, str):
            return None
        # Filenames may accidentally contain a storage path or signed URL. Only
        # the display basename belongs to inbox/email, never folders or queries.
        return value.replace("\\", "/").split("?", 1)[0].split("#", 1)[0].rsplit("/", 1)[-1] or None
    if name in {"equipments", "services"}:
        if not isinstance(value, list):
            return None
        return [
            {
                key: item[key]
                for key in ("equipment_code", "service_code", "name", "price")
                if key in item and isinstance(item[key], str | int)
            }
            for item in value
            if isinstance(item, dict)
        ]
    return value if value is None or isinstance(value, str | int | bool) else None
