"""Detect accounting report type(s) from XML root element."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Literal, cast

from domain.services.xml_accounting.errors import UnsupportedReportError
from domain.services.xml_accounting.models import ReportTypeInfo

# Mapping from (KND, OKUD) to internal report type
_KND_OKUD_MAP: dict[tuple[str, str], tuple[Literal["balance_sheet", "financial_result", "capital_changes", "cash_flow", "nds_declaration"], str]] = {
    ("0710001", "0710001"): ("balance_sheet", "Бухгалтерский баланс"),
    ("0710002", "0710002"): ("financial_result", "Отчет о финансовых результатах"),
    ("0710004", "0710004"): ("capital_changes", "Отчет об изменениях капитала"),
    ("0710005", "0710005"): ("cash_flow", "Отчет о движении денежных средств"),
    ("1151001", "1151001"): ("nds_declaration", "Налоговая декларация по НДС"),
}

# Container KNDs that hold multiple reports
_CONTAINER_KNDS = {"0710099"}

# Also map by root tag name for cases where KND is not present
_ROOT_TAG_MAP: dict[str, tuple[str, str, Literal["balance_sheet", "financial_result", "capital_changes", "cash_flow", "nds_declaration"], str]] = {
    "Баланс":       ("0710001", "0710001", "balance_sheet", "Бухгалтерский баланс"),
    "ФинРез":       ("0710002", "0710002", "financial_result", "Отчет о финансовых результатах"),
    "ОтчетИзмКап":  ("0710004", "0710004", "capital_changes", "Отчет об изменениях капитала"),
    "ДвижениеДен":  ("0710005", "0710005", "cash_flow", "Отчет о движении денежных средств"),
    "ОФР":          ("0710002", "0710002", "financial_result", "Отчет о финансовых результатах"),
    "ДекларацияНДС": ("1151001", "1151001", "nds_declaration", "Налоговая декларация по НДС"),
}

# XML namespace used by 1C accounting reports
_NS = {"{http://v8.1c.ru/8.1/data/enterprise/current-config}"}


def _strip_ns(tag: str) -> str:
    """Remove XML namespace prefix from tag name."""
    for ns in _NS:
        if tag.startswith(ns):
            return tag[len(ns):]
    return tag


def _find_document(xml_root: ET.Element) -> ET.Element:
    """Find <Документ> element inside the root (usually <Файл>)."""
    if _strip_ns(xml_root.tag) == "Документ":
        return xml_root
    for child in xml_root:
        if _strip_ns(child.tag) == "Документ":
            return child
    return xml_root


def _scan_for_forms(parent: ET.Element) -> list[ReportTypeInfo]:
    """Scan element and all descendants for supported report forms."""
    found: list[ReportTypeInfo] = []
    seen: set[str] = set()
    for elem in parent.iter():
        tag = _strip_ns(elem.tag)
        if tag in _ROOT_TAG_MAP:
            knd, okud, report_type, name = _ROOT_TAG_MAP[tag]
            if report_type not in seen:
                seen.add(report_type)
                found.append(ReportTypeInfo(knd=knd, okud=okud, report_type=report_type, name=name))
    return found


def detect_all(xml_root: ET.Element) -> list[ReportTypeInfo]:
    """Detect all report types inside the XML (supports containers with multiple forms)."""
    # Try direct root tag match first
    root_tag = _strip_ns(xml_root.tag)
    if root_tag in _ROOT_TAG_MAP:
        knd, okud, report_type, name = _ROOT_TAG_MAP[root_tag]
        return [ReportTypeInfo(knd=knd, okud=okud, report_type=report_type, name=name)]

    # Try attributes on root or Документ element
    doc_elem = _find_document(xml_root)
    doc_knd = doc_elem.get("КНД") or doc_elem.get("knd")
    doc_okud = doc_elem.get("ОКУД") or doc_elem.get("OKUD") or doc_elem.get("okud")

    if doc_knd and doc_knd in _CONTAINER_KNDS:
        # Container file — scan for embedded forms
        forms = _scan_for_forms(doc_elem)
        if forms:
            return forms
        # Also try scanning the root itself
        forms = _scan_for_forms(xml_root)
        if forms:
            return forms

    if doc_knd and doc_okud:
        key = (doc_knd, doc_okud)
        if key in _KND_OKUD_MAP:
            report_type, name = _KND_OKUD_MAP[key]
            return [
                ReportTypeInfo(
                    knd=cast("str", doc_knd),
                    okud=cast("str", doc_okud),
                    report_type=report_type,
                    name=name,
                )
            ]

    # Final fallback: scan any level for known tags
    forms = _scan_for_forms(xml_root)
    if forms:
        return forms
    forms = _scan_for_forms(doc_elem)
    if forms:
        return forms

    raise UnsupportedReportError(
        f"Unsupported report type. KND={doc_knd}, OKUD={doc_okud}, root_tag={root_tag}. "
        f"Supported KND/OKUD pairs: {list(_KND_OKUD_MAP.keys())}"
    )


def detect(xml_root: ET.Element) -> ReportTypeInfo:
    """Detect single report type — backward-compatible alias.

    For container files returns the first (usually balance_sheet) form.
    Use detect_all() when you need every embedded form.
    """
    forms = detect_all(xml_root)
    return forms[0]
