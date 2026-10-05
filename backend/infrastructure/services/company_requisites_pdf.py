"""Company requisites PDF — single-page summary for leasing applications.

Rendered from the questionnaire (step 3) with a fallback to ``companies``
for the minimum identity fields. No templates — we compose a simple
key/value layout with reportlab so the output is self-contained and
Cyrillic-safe (DejaVu fonts registered once).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
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
    ]
    candidates_bold = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ]
    regular = next((p for p in candidates_regular if p.exists()), None)
    bold = next((p for p in candidates_bold if p.exists()), None)
    if regular is None or bold is None:
        raise RuntimeError(
            "DejaVu fonts not found — install 'fonts-dejavu-core' or provide "
            "alternative Cyrillic TTFs to reportlab."
        )
    pdfmetrics.registerFont(TTFont(_FONT, str(regular)))
    pdfmetrics.registerFont(TTFont(_FONT_BOLD, str(bold)))
    _FontState.registered = True


@dataclass(frozen=True)
class CompanyRequisitesInput:
    """Everything the renderer needs to produce the PDF.

    ``questionnaire`` is the authoritative source; ``company`` is the
    fallback when step 3 wasn't filled in (legacy / short draft flow).
    """

    questionnaire: dict[str, Any] | None
    company: dict[str, Any] | None


def render_company_requisites_pdf(payload: CompanyRequisitesInput) -> bytes:
    _register_fonts()

    rows = _collect_rows(payload)
    if not rows:
        # We still emit a minimal document rather than raise — keeps the
        # caller's happy path unconditional. Readers see a friendly notice.
        rows = [("Информация", "Данные о компании не были предоставлены.")]

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Реквизиты компании",
        author="CarCraft",
    )

    base = getSampleStyleSheet()["Normal"]
    h_style = ParagraphStyle(
        "H1", parent=base, fontName=_FONT_BOLD, fontSize=16, leading=20,
    )
    meta_style = ParagraphStyle(
        "Meta", parent=base, fontName=_FONT, fontSize=9, leading=12,
        textColor="#6b7280",
    )
    label_style = ParagraphStyle(
        "Label", parent=base, fontName=_FONT, fontSize=9, leading=12,
        textColor="#6b7280",
    )
    value_style = ParagraphStyle(
        "Value", parent=base, fontName=_FONT, fontSize=10, leading=13,
    )

    story: list[Any] = [
        Paragraph("Реквизиты компании", h_style),
        Paragraph(_title_inn(payload), meta_style),
        Spacer(1, 6 * mm),
    ]

    table_data = [
        [Paragraph(label, label_style), Paragraph(str(value), value_style)]
        for label, value in rows
    ]
    table = Table(
        table_data,
        colWidths=[55 * mm, 115 * mm],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, "#e5e7eb"),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            f"Сформировано: {datetime.now(UTC).strftime('%d.%m.%Y %H:%M UTC')}",
            meta_style,
        )
    )

    doc.build(story)
    return buffer.getvalue()


def _title_inn(payload: CompanyRequisitesInput) -> str:
    inn = _first(
        _get(payload.questionnaire, "inn"),
        _get(payload.company, "inn"),
    )
    return f"ИНН: {inn}" if inn else "ИНН не указан"


def _collect_rows(
    payload: CompanyRequisitesInput,
) -> list[tuple[str, str]]:
    q = payload.questionnaire or {}
    c = payload.company or {}
    raw = [
        ("Полное название", _first(q.get("full_company_name"), c.get("name"))),
        ("Краткое название", _first(q.get("short_company_name"))),
        ("Правовая форма", _first(q.get("legal_form"))),
        ("ИНН", _first(q.get("inn"), c.get("inn"))),
        ("КПП", _first(q.get("kpp"), c.get("kpp"))),
        ("ОГРН", _first(q.get("ogrn"), c.get("ogrn"))),
        ("ОКПО", _first(q.get("okpo"))),
        ("ОКАТО", _first(q.get("okato"))),
        ("ОКВЭД (основной)", _first(q.get("okved_main"))),
        ("ОКВЭД (дополнительные)", _first(q.get("okved_additional"))),
        ("Система налогообложения", _first(q.get("tax_system"))),
        (
            "Юридический адрес",
            _first(q.get("legal_address"), c.get("legal_address")),
        ),
        (
            "Фактический адрес",
            _first(q.get("actual_address"), c.get("actual_address")),
        ),
        ("Почтовый адрес", _first(q.get("postal_address"))),
        (
            "Телефон",
            _first(q.get("phone"), c.get("phone")),
        ),
        ("Факс", _first(q.get("fax"))),
        (
            "Email",
            _first(q.get("email"), c.get("email")),
        ),
        ("Сайт", _first(q.get("website"))),
        ("Банк", _first(q.get("bank_name"))),
        ("БИК", _first(q.get("bik"))),
        ("Расчётный счёт", _first(q.get("settlement_account"))),
        (
            "Руководитель",
            _first(
                q.get("director_full_name"),
                _joined(q.get("director_surname"), q.get("director_first_name"), q.get("director_patronymic")),
            ),
        ),
        ("Должность", _first(q.get("director_position"))),
    ]
    return [(label, value) for label, value in raw if value]


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


def _get(source: dict[str, Any] | None, key: str) -> Any:
    if not source:
        return None
    return source.get(key)
