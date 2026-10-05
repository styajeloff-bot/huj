"""Render printable SOPD revoke PDFs."""
from __future__ import annotations

import asyncio
import html
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from infrastructure.settings import settings


def build_revoke_document_key(*, user_id: UUID, revoke_request_id: UUID) -> str:
    prefix = settings.document_storage_prefix.rstrip("/")
    return f"{prefix}/user_{user_id}/signatures/{revoke_request_id}-sopd-revoke.pdf"


async def render_pdf(context: dict[str, Any]) -> bytes:
    return await asyncio.to_thread(_render_sync, context)


def _render_sync(context: dict[str, Any]) -> bytes:
    from weasyprint import CSS, HTML

    html_source = _build_html(context)
    css = """
    @page { size: A4; margin: 2cm; }
    body {
        font-family: "DejaVu Sans", sans-serif;
        font-size: 11pt;
        line-height: 1.45;
        color: #111;
    }
    h1 { font-size: 15pt; text-align: center; margin: 0 0 18px; }
    p { margin: 0 0 10px; }
    ol { margin: 4px 0 12px 22px; padding: 0; }
    li { margin: 0 0 6px; }
    .field { font-weight: 600; }
    .signature { margin-top: 30px; }
    .note { font-size: 10pt; color: #333; }
    """
    return HTML(string=html_source).write_pdf(stylesheets=[CSS(string=css)])  # type: ignore[no-any-return]


def _build_html(context: dict[str, Any]) -> str:
    subject = context.get("subject") or {}
    source_document = context.get("source_document") or {}
    operators = context.get("operators") or []
    confirmed_at = context.get("confirmed_at") or datetime.now(UTC)
    document_date = _format_date_words(confirmed_at, short_year_suffix="г.")
    basis = _source_document_text(source_document)
    passport_series, passport_number = _passport_parts(
        subject.get("passport_series_number")
    )
    operators_list = "\n".join(
        f"<li>{_operator_text(item)}</li>" for item in operators
    )
    operators_block = f"<ol>{operators_list}</ol>" if operators_list else ""
    return f"""
    <!doctype html>
    <html lang="ru">
    <head><meta charset="utf-8"><title>Отзыв СОПД</title></head>
    <body>
      <h1>ОТЗЫВ СОГЛАСИЯ НА ОБРАБОТКУ ПЕРСОНАЛЬНЫХ ДАННЫХ</h1>
      <p>Я, <span class="field">{_escape(subject.get("full_name"))}</span>,</p>
      <p>Зарегистрированный по адресу <span class="field">{_escape(subject.get("address"))}</span>,</p>
      <p>
        паспорт серия <span class="field">{_escape(passport_series)}</span>
        № <span class="field">{_escape(passport_number)}</span>,
        выдан <span class="field">{_escape(_format_date_words(subject.get("passport_issued_at"), short_year_suffix="года"))}</span>
        <span class="field">{_escape(subject.get("passport_issued_by"))}</span>,
        код подразделения <span class="field">{_escape(subject.get("passport_code"))}</span>,
      </p>
      <p>
        в соответствии со статьей 9 Федерального закона от 27.07.2006 № 152-ФЗ
        «О персональных данных» отзываю своё согласие на обработку персональных
        данных, данное мною ранее на основании <span class="field">{_escape(basis)}</span>.
      </p>
      <p>Настоящий отзыв касается следующих операторов персональных данных:</p>
      {operators_block}
      <p>Контактный телефон <span class="field">{_escape(subject.get("phone"))}</span></p>
      <p>Почтовый адрес <span class="field">{_escape(subject.get("postal_address") or subject.get("address"))}</span></p>
      <p>{_escape(document_date)}</p>
      <p class="signature">
        Подтверждено простой электронной подписью посредством ввода
        одноразового SMS-кода / <span class="field">{_escape(subject.get("full_name"))}</span>
      </p>
      <p class="note">(подпись) (расшифровка подписи)</p>
    </body>
    </html>
    """


def _operator_text(item: dict[str, Any]) -> str:
    base = _format_name_inn(item)
    if item.get("operator_type") != "contractor":
        return _escape(base)
    leasing_companies = [
        _format_name_inn(lc)
        for lc in item.get("leasing_companies") or []
        if isinstance(lc, dict)
    ]
    if not leasing_companies:
        return _escape(f"{base} (подрядчик)")
    linked = ", ".join(leasing_companies)
    return _escape(f"{base} (подрядчик лизинговых компаний: {linked})")


def _format_name_inn(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip()
    inn = str(item.get("inn") or "").strip()
    if name and inn:
        return f"{name}, ИНН {inn}"
    return name or (f"ИНН {inn}" if inn else "")


def _format_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if value:
        return str(value)
    return "—"


def _source_document_text(source_document: dict[str, Any]) -> str:
    document_id = str(
        source_document.get("display_number")
        or source_document.get("number")
        or source_document.get("id")
        or ""
    ).strip()
    signed_at = _format_date_words(
        source_document.get("signed_at"),
        short_year_suffix="г",
    )
    if document_id and signed_at:
        return f"СОПД № {document_id} от {signed_at}"
    if document_id:
        return f"СОПД № {document_id}"
    return "СОПД"


def _passport_parts(value: Any) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", ""
    parts = text.replace("№", " ").split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 10:
        return digits[:4], digits[4:]
    return text, ""


def _format_date_words(value: Any, *, short_year_suffix: str = "г.") -> str:
    parsed = _parse_date(value)
    if parsed is None:
        return str(value or "").strip()
    months = (
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    )
    suffix = short_year_suffix.strip()
    return f"«{parsed.day:02d}» {months[parsed.month - 1]} {parsed.year} {suffix}"


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if "." in text[:10]:
            return _parse_dot_date(text[:10])
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_dot_date(value: str) -> date:
    day, month, year = value.split(".", maxsplit=2)
    return date(int(year), int(month), int(day))


def _escape(value: Any) -> str:
    return html.escape(str(value or "").strip())
