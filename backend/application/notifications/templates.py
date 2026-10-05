"""Escaped multipart presentation of the already role-sanitized inbox facts."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from html import escape
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from domain.events.notifications import NotificationEvent
from domain.notification_policy import POLICIES, action_route, notification_data
from infrastructure.settings import settings

FIELD_LABELS = {
    "status": "Статус",
    "lca_status": "Статус у лизинговой компании",
    "car_status": "Статус автомобиля",
    "reserve_expires_at": "Бронирование до",
    "client_decision_action": "Решение клиента",
    "document_status": "Статус документа",
    "equipments": "Оборудование",
    "services": "Услуги",
    "quantity": "Количество",
    "price": "Цена",
    "expiration_at": "Срок заявки",
    "discount": "Скидка",
    "discount_percent": "Скидка, %",
    "discount_value": "Размер скидки",
    "total_price": "Стоимость",
    "discount_type": "Тип скидки",
    "file_name": "Имя вложения",
}


def build_inbox(event: NotificationEvent, recipient: dict[str, Any]) -> dict[str, Any]:
    policy = POLICIES[event.event_type]
    title = policy.title
    if recipient["role"] == "dealer" and event.event_type in {
        "exchange.bid_created",
        "exchange.bid_updated",
        "exchange.bid_withdrawn",
    }:
        verb = {
            "exchange.bid_created": "создал",
            "exchange.bid_updated": "изменил",
            "exchange.bid_withdrawn": "отозвал",
        }[event.event_type]
        title = f"Другой дилер {verb} ставку"
    data = notification_data(event, recipient["role"])
    message = f"{title}. Заявка №{event.request_number}."
    if event.event_type == "document_registry.expiring":
        expiry = date.fromisoformat(event.payload["valid_to"])
        message = (
            f"Срок действия документа «{event.payload['document_type']}» "
            f"№{event.request_number} «{event.payload['document_name']}» "
            f"заканчивается {expiry:%d.%m.%Y}."
        )
    if event.event_type == "monetization.deal_terms_changed":
        message = (
            f"Изменены условия сделки {event.request_number}. "
            "Требуется повторное подтверждение."
        )
    if event.event_type == "leasing.documents_uploads_summary":
        data.update({name: event.payload[name] for name in (
            "document_count", "first_upload_at", "last_upload_at",
        )})
        zone = ZoneInfo(settings.notification_business_timezone)
        first = datetime.fromisoformat(data["first_upload_at"]).astimezone(zone)
        last = datetime.fromisoformat(data["last_upload_at"]).astimezone(zone)
        message += (
            f" Количество документов: {data['document_count']}."
            f" Интервал загрузки: {first:%d.%m.%Y %H:%M} — {last:%d.%m.%Y %H:%M %Z}."
        )
    if data.get("reason"):
        message += f" Причина: {data['reason']}."
    if data.get("confirmed_party"):
        side = {"leasing": "ЛК", "dealer": "дилер", "distributor": "дистрибьютор"}[data["confirmed_party"]]
        message += f" Подтвердившая сторона: {side}."
    if data.get("attachment_changed"):
        message += " Вложение обновлено."
    if recipient["role"] == "dealer" and data.get("overstock_items"):
        for overstock_item in data["overstock_items"]:
            qty = overstock_item.get("quantity", 0)
            name = (
                overstock_item.get("name")
                or f"{overstock_item.get('mark', '')} {overstock_item.get('model', '')} {overstock_item.get('modification', '')}".strip()
            )
            message += f" Клиент запросил сверх наличия: {qty} шт. по позиции «{name}». Эти единицы не включены в заявку."
    return {
        "notification_type": policy.notification_type,
        "title": title,
        "message": message,
        "data": data,
        "action_url": action_route(
            event, recipient["role"], recipient.get("storefront_slug"),
            recipient.get("leasing_company_id"),
            recipient.get("company_id"),
        ),
    }


def next_delivery_at(
    now: datetime, mode: str, *, timezone: str, hour: int, weekday: int
) -> datetime:
    if mode == "immediate":
        return now
    local = now.astimezone(ZoneInfo(timezone))
    scheduled = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if mode == "weekly":
        scheduled += timedelta(days=(weekday - local.weekday()) % 7)
    if scheduled <= local:
        scheduled += timedelta(days=7 if mode == "weekly" else 1)
    return scheduled.astimezone(UTC)


def _value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, list | dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def build_email(
    members: list[dict[str, Any]], *, public_url: str, timezone: str
) -> dict[str, str]:
    origin = urlsplit(public_url)
    if (
        origin.scheme not in {"http", "https"}
        or not origin.hostname
        or origin.username
        or origin.password
    ):
        raise ValueError("Invalid notification public URL")
    subject = (
        members[0]["title"]
        if len(members) == 1
        else f"Сводка уведомлений: {len(members)}"
    )
    plain, html = [], []
    for item in members:
        route = item["action_url"]
        if (
            not isinstance(route, str)
            or not route.startswith("/")
            or route.startswith("//")
            or "\\" in route
        ):
            raise ValueError("Notification action must be an internal route")
        url = public_url.rstrip("/") + route
        data = item["data"]
        stamp = (
            datetime.fromisoformat(data["occurred_at"])
            .astimezone(ZoneInfo(timezone))
            .strftime("%d.%m.%Y %H:%M %Z")
        )
        lines = [item["message"], f"Дата события: {stamp}"]
        if data.get("actor_name"):
            lines.append(f"Автор действия: {data['actor_name']}")
        if data.get("attachment_name"):
            lines.append(f"Вложение: {data['attachment_name']}")
        if data.get("requested_documents"):
            lines.append(
                "Запрошены документы: "
                + ", ".join(str(name) for name in data["requested_documents"])
            )
        lines.extend(
            f"{FIELD_LABELS.get(key, key)}: {_value(data['previous_values'][key])} → {_value(data['new_values'][key])}"
            for key in data["changed_fields"]
        )
        if data.get("expiration_at"):
            lines.append(f"До окончания на момент события: {data['remaining_time']}")
        plain.append("\n".join([*lines, f"Открыть заявку: {url}"]))
        html.append(
            "<section><h2>"
            + escape(item["title"])
            + "</h2>"
            + "".join(f"<p>{escape(line)}</p>" for line in lines)
            + f'<p><a href="{escape(url, quote=True)}" style="display:inline-block;padding:12px 20px;background:#163a5f;color:#ffffff;text-decoration:none;border-radius:4px">Открыть заявку</a></p></section>'
        )
    return {
        "subject": subject,
        "body": "\n\n".join(plain),
        "html": '<!doctype html><html lang="ru"><body>'
        + "".join(html)
        + "</body></html>",
    }
