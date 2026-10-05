"""Render a full leasing application snapshot as a single readable PDF.

The rendered document mirrors what the modal «Заявка № …» shows: contact
info, company summary, questionnaire, founders/beneficiaries, vehicles
with per-TS calculations, leasing conditions and the list of attached
documents (names only — their blobs are downloadable separately).

Kept deliberately minimal — clients want the raw data, not a designed
letterhead. If a field is missing we just skip the row rather than print
"—" so the PDF stays compact.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger("carcraft-backend")

_FONT = "DejaVuSans"
_FONT_BOLD = "DejaVuSans-Bold"
class _FontState:
    registered = False


def _register_fonts() -> None:
    if _FontState.registered:
        return
    candidates_regular = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    ]
    candidates_bold = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
    ]
    regular = next((p for p in candidates_regular if p.exists()), None)
    bold = next((p for p in candidates_bold if p.exists()), None)
    if regular is None or bold is None:
        raise RuntimeError("DejaVu fonts not found.")
    pdfmetrics.registerFont(TTFont(_FONT, str(regular)))
    pdfmetrics.registerFont(TTFont(_FONT_BOLD, str(bold)))
    _FontState.registered = True


@dataclass(frozen=True)
class ApplicationExportInput:
    application: dict[str, Any]
    company: dict[str, Any] | None
    owner: dict[str, Any] | None
    questionnaire: dict[str, Any] | None
    vehicles: list[dict[str, Any]]
    vehicle_calculations: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    selected_companies_info: list[dict[str, Any]]


@dataclass(frozen=True)
class LeasingResponseExportInput:
    application: dict[str, Any]
    link: dict[str, Any]
    leasing_company_name: str | None
    proposals: list[dict[str, Any]]
    proposal_kind: str | None = None


_STATUS_LABELS = {
    "active": "Активная",
    "draft": "На распределении",
    "pending_distribution": "На распределении",
    "submitted": "Отправлена",
    "under_review": "На рассмотрении",
    "under_review_with_docs": "На рассмотрении с доп. документами",
    "documents_required": "Запрос дополнительных документов",
    "approved_scoring": "Предварительное КП",
    "approved_scoring_another_cond": "Предварительное КП на других условиях",
    "approved_final": "Итоговое КП",
    "approved_final_another_cond": "Итоговое КП на других условиях",
    "selected_lc": "Выбрана ЛК",
    "deal": "Сделка заключена",
    "rejected_prescoring": "Отклонена на предварительном рассмотрении",
    "rejected_approved": "Отклонена после предварительного КП",
    "rejected_final": "Отклонена после итогового КП",
    "approved": "Одобрена",
    "rejected": "Отклонена",
    "issued": "Выдана",
    "closed": "Закрыта",
}


def render_application_export_pdf(payload: ApplicationExportInput) -> bytes:
    _register_fonts()
    buffer = BytesIO()
    app = payload.application
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Заявка № {app.get('id')}",
        author="CarCraft",
    )

    styles = _styles()
    story: list[Any] = []

    story += _header(payload, styles)
    story += _contacts_block(payload, styles)
    story += _company_block(payload, styles)
    story += _director_block(payload, styles)
    story += _founders_block(payload, styles)
    story += _beneficiaries_block(payload, styles)
    story += _vehicles_block(payload, styles)
    story += _conditions_block(payload, styles)
    story += _leasing_companies_block(payload, styles)
    story += _documents_block(payload, styles)

    doc.build(story)
    return buffer.getvalue()


def render_leasing_response_pdf(payload: LeasingResponseExportInput) -> bytes:
    _register_fonts()
    buffer = BytesIO()
    app = payload.application
    application_number = _display_application_number(app)
    title = _leasing_response_title(payload.proposal_kind)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"{title} по заявке № {application_number}",
        author="CarCraft",
    )

    styles = _styles()
    story: list[Any] = [
        Paragraph(f"{title} по заявке № {application_number}", styles["h1"]),
        Paragraph(
            (
                f"Лизингодатель: {payload.leasing_company_name or '—'}"
                f"  •  Статус: {_status_label(payload.link.get('status'))}"
            ),
            styles["meta"],
        ),
        Spacer(1, 4 * mm),
    ]
    story += _section(
        "Заявка",
        [
            ("Номер заявки", application_number),
            ("Компания-заявитель", _first(app.get("company_name"), app.get("name"))),
            ("Email", _first(app.get("email"))),
            ("Статус заявки", _status_label(app.get("status"))),
            ("Аванс %", _fmt_percent(app.get("down_payment_percent"))),
            ("Аванс ₽", _fmt_money(app.get("down_payment"))),
            ("Срок", _fmt_months(app.get("lease_term_months"))),
            ("Ежемесячный платёж", _fmt_money(app.get("monthly_payment"))),
            ("Общая стоимость", _fmt_money(app.get("total_cost"))),
        ],
        styles,
    )
    story += _section(
        "Лизингодатель",
        [
            ("Название", payload.leasing_company_name),
            ("Статус заявки в ЛК", _status_label(payload.link.get("status"))),
            ("Отправлена", _fmt_dt(payload.link.get("submitted_at"))),
        ],
        styles,
    )
    story += _proposals_block(payload.proposals, styles, payload.proposal_kind)

    doc.build(story)
    return buffer.getvalue()


# ----------------------------------------------------------------------
# Block builders
# ----------------------------------------------------------------------


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    return {
        "h1": ParagraphStyle(
            "H1", parent=base, fontName=_FONT_BOLD, fontSize=16, leading=20,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base, fontName=_FONT_BOLD, fontSize=12, leading=16,
            spaceBefore=6, spaceAfter=3,
        ),
        "label": ParagraphStyle(
            "Label", parent=base, fontName=_FONT, fontSize=9, leading=12,
            textColor="#6b7280",
        ),
        "value": ParagraphStyle(
            "Value", parent=base, fontName=_FONT, fontSize=10, leading=13,
        ),
        "meta": ParagraphStyle(
            "Meta", parent=base, fontName=_FONT, fontSize=8, leading=11,
            textColor="#9ca3af",
        ),
        "body": ParagraphStyle(
            "Body", parent=base, fontName=_FONT, fontSize=10, leading=13,
        ),
    }


def _header(
    payload: ApplicationExportInput, styles: dict[str, ParagraphStyle]
) -> list[Any]:
    app = payload.application
    status = _STATUS_LABELS.get(str(app.get("status") or ""), app.get("status") or "")
    created = _fmt_dt(app.get("created_at"))
    return [
        Paragraph(f"Заявка № {app.get('id')}", styles["h1"]),
        Paragraph(
            f"Статус: {status}  •  Создано: {created or '—'}",
            styles["meta"],
        ),
        Spacer(1, 4 * mm),
    ]


def _contacts_block(
    payload: ApplicationExportInput, styles: dict[str, ParagraphStyle]
) -> list[Any]:
    app = payload.application
    owner = payload.owner or {}
    rows = [
        ("ФИО", _first(app.get("name"), owner.get("name"))),
        ("Телефон", _first(app.get("phone"), owner.get("phone"))),
        ("Email", _first(app.get("email"), owner.get("email"))),
        ("ИНН/Компания", _first(payload.company.get("name") if payload.company else None, payload.company.get("inn") if payload.company else None)),
    ]
    return _section("Контактная информация", rows, styles)


def _company_block(
    payload: ApplicationExportInput, styles: dict[str, ParagraphStyle]
) -> list[Any]:
    q = payload.questionnaire or {}
    c = payload.company or {}
    rows = [
        ("Полное название", _first(q.get("full_company_name"), c.get("name"))),
        ("Краткое название", _first(q.get("short_company_name"))),
        ("Правовая форма", _first(q.get("legal_form"))),
        ("ИНН", _first(q.get("inn"), c.get("inn"))),
        ("КПП", _first(q.get("kpp"), c.get("kpp"))),
        ("ОГРН", _first(q.get("ogrn"), c.get("ogrn"))),
        ("ОКПО", _first(q.get("okpo"))),
        ("ОКВЭД", _first(q.get("okved_main"))),
        ("Система НО", _first(q.get("tax_system"))),
        (
            "Юридический адрес",
            _first(q.get("legal_address"), c.get("legal_address")),
        ),
        (
            "Фактический адрес",
            _first(q.get("actual_address"), c.get("actual_address")),
        ),
        ("Банк", _first(q.get("bank_name"))),
        ("БИК", _first(q.get("bik"))),
        ("Расчётный счёт", _first(q.get("settlement_account"))),
    ]
    return _section("Компания-заявитель", rows, styles)


def _director_block(
    payload: ApplicationExportInput, styles: dict[str, ParagraphStyle]
) -> list[Any]:
    q = payload.questionnaire or {}
    full_name = _first(
        q.get("director_full_name"),
        _joined(
            q.get("director_surname"),
            q.get("director_first_name"),
            q.get("director_patronymic"),
        ),
    )
    rows = [
        ("ФИО", full_name),
        ("Должность", _first(q.get("director_position"))),
        ("Дата рождения", _fmt_date(q.get("director_birth_date"))),
        ("Место рождения", _first(q.get("director_birth_place"))),
        ("Гражданство", _first(q.get("director_citizenship"))),
        ("Паспорт", _passport(q.get("director_passport_series"), q.get("director_passport_number"))),
        ("Кем выдан", _first(q.get("director_passport_issued_by"))),
        ("Прописка", _first(q.get("director_registration_address"))),
        ("Телефон", _first(q.get("director_phone"))),
        ("Email", _first(q.get("director_email"))),
    ]
    return _section("Руководитель", rows, styles)


def _founders_block(
    payload: ApplicationExportInput, styles: dict[str, ParagraphStyle]
) -> list[Any]:
    q = payload.questionnaire or {}
    founders = q.get("founders") if isinstance(q.get("founders"), list) else []
    if not founders:
        return []
    blocks: list[Any] = [Paragraph("Учредители", styles["h2"])]
    for idx, raw in enumerate(founders):
        if not isinstance(raw, dict):
            continue
        share = raw.get("share")
        header = _first(raw.get("full_name"), raw.get("name")) or f"Учредитель {idx + 1}"
        if share not in (None, ""):
            header = f"{header} — доля {share}%"
        rows = [
            ("ИНН", _first(raw.get("inn"))),
            ("ОГРН", _first(raw.get("ogrn"))),
            ("Тип", _first(raw.get("type"), raw.get("founder_type"))),
            (
                "Паспорт",
                _passport(raw.get("passport_series"), raw.get("passport_number"))
                or _first(raw.get("passport")),
            ),
        ]
        blocks.append(
            KeepTogether(
                [
                    Paragraph(header, styles["value"]),
                    _kv_table(rows, styles),
                    Spacer(1, 2 * mm),
                ]
            )
        )
    blocks.append(Spacer(1, 2 * mm))
    return blocks


def _beneficiaries_block(
    payload: ApplicationExportInput, styles: dict[str, ParagraphStyle]
) -> list[Any]:
    q = payload.questionnaire or {}
    items = q.get("beneficiaries") if isinstance(q.get("beneficiaries"), list) else []
    if not items:
        return []
    blocks: list[Any] = [Paragraph("Бенефициары", styles["h2"])]
    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        header = _first(raw.get("full_name"), raw.get("name")) or f"Бенефициар {idx + 1}"
        rows = [
            ("ИНН", _first(raw.get("inn"))),
            ("Дата рождения", _fmt_date(raw.get("birth_date"))),
            (
                "Паспорт",
                _passport(raw.get("passport_series"), raw.get("passport_number"))
                or _first(raw.get("passport")),
            ),
            ("Прописка", _first(raw.get("registration_address"))),
        ]
        blocks.append(
            KeepTogether(
                [
                    Paragraph(header, styles["value"]),
                    _kv_table(rows, styles),
                    Spacer(1, 2 * mm),
                ]
            )
        )
    blocks.append(Spacer(1, 2 * mm))
    return blocks


def _vehicles_block(
    payload: ApplicationExportInput, styles: dict[str, ParagraphStyle]
) -> list[Any]:
    vehicles = payload.vehicles
    if not vehicles:
        return []
    blocks: list[Any] = [Paragraph("Автомобили в заявке", styles["h2"])]
    total = Decimal("0")
    for idx, v in enumerate(vehicles):
        title = _vehicle_title(v) or f"Автомобиль {idx + 1}"
        subtitle = _vehicle_subtitle(v)
        unit_price = _dec(v.get("unit_price"))
        qty = int(v.get("quantity") or 1)
        total_price = _dec(v.get("total_price")) or (unit_price * qty)
        total += total_price
        rows = [
            ("Комплектация", _first(v.get("group_name"))),
            ("Цвет", _first(v.get("color"))),
            ("Год", _first(v.get("vehicle_year"))),
            ("Количество", str(qty)),
            ("Цена за ед.", _fmt_money(unit_price)),
            ("Итого", _fmt_money(total_price)),
            ("VIN", _first(v.get("vin"))),
        ]
        blocks.append(
            KeepTogether(
                [
                    Paragraph(title, styles["value"]),
                    *([Paragraph(subtitle, styles["meta"])] if subtitle else []),
                    _kv_table(rows, styles),
                    Spacer(1, 2 * mm),
                ]
            )
        )
    blocks.append(
        Paragraph(f"Общая стоимость ТС: <b>{_fmt_money(total)}</b>", styles["body"])
    )
    blocks.append(Spacer(1, 3 * mm))
    return blocks


def _conditions_block(
    payload: ApplicationExportInput, styles: dict[str, ParagraphStyle]
) -> list[Any]:
    app = payload.application
    rows = [
        ("Аванс %", _fmt_percent(app.get("down_payment_percent"))),
        ("Аванс ₽", _fmt_money(app.get("down_payment"))),
        ("Срок", _fmt_months(app.get("lease_term_months"))),
        ("Ежемесячный платёж", _fmt_money(app.get("monthly_payment"))),
        ("Ставка удорожания", _fmt_percent(app.get("rate"))),
        ("Сумма договора", _fmt_money(app.get("total_cost"))),
        ("Проценты", _fmt_money(app.get("total_interest"))),
        ("Выкупная стоимость", _fmt_money(app.get("buyout_amount"))),
        ("Возврат НДС", _fmt_money(app.get("vat_refund"))),
        ("Налог на прибыль (экономия)", _fmt_money(app.get("profit_tax_savings"))),
        ("Общая экономия", _fmt_money(app.get("total_savings"))),
    ]
    return _section("Условия лизинга", rows, styles)


def _leasing_companies_block(
    payload: ApplicationExportInput, styles: dict[str, ParagraphStyle]
) -> list[Any]:
    items = payload.selected_companies_info or []
    if not items:
        return []
    names = [str(it.get("company_name")) for it in items if it.get("company_name")]
    if not names:
        return []
    return [
        Paragraph("Лизинговые компании", styles["h2"]),
        Paragraph(", ".join(names), styles["body"]),
        Spacer(1, 3 * mm),
    ]


def _documents_block(
    payload: ApplicationExportInput, styles: dict[str, ParagraphStyle]
) -> list[Any]:
    docs = payload.documents or []
    if not docs:
        return []
    rows = [
        (
            _first(d.get("file_name")) or "—",
            _first(d.get("document_type")) or "",
        )
        for d in docs
    ]
    blocks: list[Any] = [Paragraph("Приложенные документы", styles["h2"])]
    table = Table(
        [["Файл", "Тип документа"], *rows],
        colWidths=[120 * mm, 50 * mm],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
                ("FONTNAME", (0, 1), (-1, -1), _FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, "#e5e7eb"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    blocks.append(table)
    return blocks


def _proposals_block(
    proposals: list[dict[str, Any]],
    styles: dict[str, ParagraphStyle],
    proposal_kind: str | None = None,
) -> list[Any]:
    if not proposals:
        return [Paragraph("КП от лизинговой компании пока не заполнены.", styles["body"])]
    headers = [
        "Тип КП",
        "Ежемесячный платёж",
        "Аванс",
        "Срок",
        "Стоимость договора",
        "Выкуп",
        "Проценты",
    ]
    rows = [
        [
            _proposal_kind_label(proposal.get("kind")),
            _fmt_money(proposal.get("monthly_payment")) or "—",
            _advance_value(proposal),
            _fmt_months(proposal.get("lease_term_months")) or "—",
            _fmt_money(proposal.get("total_amount")) or "—",
            _fmt_money(proposal.get("buyout_amount")) or "—",
            _fmt_money(proposal.get("total_interest")) or "—",
        ]
        for proposal in proposals
    ]
    block_title = "Условия КП"
    if proposal_kind is not None:
        block_title = _leasing_response_title(proposal_kind)
    blocks: list[Any] = [Paragraph(block_title, styles["h2"])]
    table = Table(
        [headers, *rows],
        colWidths=[28 * mm, 28 * mm, 28 * mm, 20 * mm, 32 * mm, 26 * mm, 26 * mm],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
                ("FONTNAME", (0, 1), (-1, -1), _FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("BACKGROUND", (0, 0), (-1, 0), "#f3f4f6"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, "#e5e7eb"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    blocks.append(table)
    return blocks


def _proposal_kind_label(value: Any) -> str:
    labels = {
        "preliminary": "Предварительное КП",
        "final": "Итоговое КП",
    }
    return labels.get(str(value or ""), str(value or "—"))


def _leasing_response_title(proposal_kind: str | None) -> str:
    if proposal_kind == "preliminary":
        return "Предварительное коммерческое предложение"
    if proposal_kind == "final":
        return "Итоговое коммерческое предложение"
    return "Коммерческое предложение лизинговой компании"


def _status_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "—"
    return _STATUS_LABELS.get(raw, raw)


def _display_application_number(app: dict[str, Any]) -> str:
    return _first(app.get("display_number")) or "—"


def _advance_value(proposal: dict[str, Any]) -> str:
    money = _fmt_money(proposal.get("down_payment"))
    percent = _fmt_percent(proposal.get("down_payment_percent"))
    if money and percent:
        return f"{money} ({percent})"
    return money or percent or "—"


# ----------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------


def _section(
    title: str,
    rows: list[tuple[str, Any]],
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    filtered = [(k, v) for k, v in rows if v]
    if not filtered:
        return []
    return [
        Paragraph(title, styles["h2"]),
        _kv_table(filtered, styles),
        Spacer(1, 3 * mm),
    ]


def _kv_table(
    rows: list[tuple[str, Any]],
    styles: dict[str, ParagraphStyle],
) -> Table:
    data = [
        [
            Paragraph(label, styles["label"]),
            Paragraph(str(value), styles["value"]),
        ]
        for label, value in rows
    ]
    table = Table(data, colWidths=[55 * mm, 115 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _vehicle_title(v: dict[str, Any]) -> str:
    mark = _first(v.get("mark_name"), v.get("mark_cyrillic_name"))
    model = _first(v.get("model_name"), v.get("model_cyrillic_name"))
    title = " ".join(p for p in (mark, model) if p).strip()
    if title:
        return title
    if v.get("modification_id") or not v.get("vehicle_id"):
        return "Заказ модели"
    return "Автомобиль"


def _vehicle_subtitle(v: dict[str, Any]) -> str:
    parts = [_first(v.get("group_name")), _first(v.get("vehicle_year")), _first(v.get("color"))]
    return " • ".join(p for p in parts if p)


def _passport(series: Any, number: Any) -> str:
    s = _first(series)
    n = _first(number)
    if s and n:
        return f"{s} {n}"
    return s or n


def _first(*values: Any) -> str:
    for v in values:
        if v is None:
            continue
        text = str(v).strip()
        if text:
            return text
    return ""


def _joined(*parts: Any) -> str:
    chunks: list[str] = []
    for p in parts:
        if p is None:
            continue
        s = str(p).strip()
        if s:
            chunks.append(s)
    return " ".join(chunks)


def _fmt_money(value: Any) -> str:
    n = _dec(value)
    if n == Decimal("0") and (value in (None, "", 0)):
        return ""
    # Space-separated thousands, keep integer rubles in most cases.
    as_int = int(n.quantize(Decimal("1")))
    sign = "-" if as_int < 0 else ""
    digits = f"{abs(as_int):,}".replace(",", " ")
    return f"{sign}{digits} ₽"


def _dec(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError, TypeError):
        return Decimal("0")


def _fmt_percent(value: Any) -> str:
    if value in (None, "", 0):
        return ""
    try:
        return f"{Decimal(str(value))}%"
    except (ValueError, ArithmeticError, TypeError):
        return ""


def _fmt_months(value: Any) -> str:
    if value in (None, "", 0):
        return ""
    return f"{value} мес."


def _fmt_dt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(UTC).strftime("%d.%m.%Y %H:%M UTC")
    return _fmt_date(value)


def _fmt_date(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.date().strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return str(value)


__all__ = [
    "ApplicationExportInput",
    "LeasingResponseExportInput",
    "render_application_export_pdf",
    "render_leasing_response_pdf",
]
