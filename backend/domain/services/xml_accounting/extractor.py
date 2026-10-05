"""Extract company and period metadata from accounting report XML."""
from __future__ import annotations

import contextlib
import re
import xml.etree.ElementTree as ET

from domain.services.xml_accounting.errors import MissingRequiredFieldError
from domain.services.xml_accounting.models import ExtractedMetadata, ReportTypeInfo


def _strip_ns(tag: str) -> str:
    """Remove XML namespace prefix."""
    for ns in ("{http://v8.1c.ru/8.1/data/enterprise/current-config}",
               "{http://www.w3.org/2001/XMLSchema}"):
        if tag.startswith(ns):
            return tag[len(ns):]
    return tag


def _find_child_text(parent: ET.Element, tag_name: str, default: str | None = None) -> str | None:
    """Find first child with given tag (ignoring namespace) and return its text."""
    for child in parent:
        if _strip_ns(child.tag) == tag_name:
            return child.text.strip() if child.text else default
    return default


def _get_attr(elem: ET.Element, *names: str) -> str | None:
    """Get first matching attribute from element."""
    for name in names:
        val = elem.get(name)
        if val:
            return val.strip()
    return None


def _determine_period(root: ET.Element, report_year: int) -> tuple[int, str]:
    """Determine period_code (31-34) and period_name from XML structure.

    31 = 1 квартал
    32 = полугодие (6 мес)
    33 = 9 месяцев
    34 = годовой
    """
    # Check for explicit period attributes on Документ
    for elem in [root, *[c for c in root if _strip_ns(c.tag) == "Документ"]]:
        period_attr = _get_attr(elem, "Период", "period", "Period")
        if period_attr:
            period_map = {
                "1": (31, f"{report_year} 1 кв."),
                "2": (32, f"{report_year} 1-2 кв."),
                "3": (33, f"{report_year} 1-3 кв."),
                "4": (34, f"{report_year} год"),
                "31": (31, f"{report_year} 1 кв."),
                "32": (32, f"{report_year} полугодие"),
                "33": (33, f"{report_year} 9 мес."),
                "34": (34, f"{report_year} год"),
            }
            if period_attr in period_map:
                return period_map[period_attr]

    # Try to infer from tag structure in capital changes
    # If both Кап31ДекПред (year-2) and Кап31ДекТек (current) exist → annual
    has_year_minus_2 = any(
        _strip_ns(c.tag) in ("Кап31ДекПред", "Кап31ДекПредКор")
        for c in root.iter()
    )
    has_current = any(
        _strip_ns(c.tag) == "Кап31ДекТек"
        for c in root.iter()
    )
    if has_year_minus_2 or has_current:
        return (34, f"{report_year} год")

    # Check for quarterly indicators in other report types
    # Look for quarter-specific tags or attributes
    quarter_tags = {
        "31": ["Квартал1", "Q1", "ПервыйКв"],
        "32": ["Квартал2", "Полугодие", "Q2"],
        "33": ["Квартал3", "9Месяцев", "Q3"],
    }
    for qcode, qtags in quarter_tags.items():
        for tag in qtags:
            if any(_strip_ns(c.tag) == tag for c in root.iter()):
                pcode = int(qcode)
                names = {31: "1 кв.", 32: "полугодие", 33: "9 мес."}
                return (pcode, f"{report_year} {names[pcode]}")

    # Default to annual if we can't determine
    return (34, f"{report_year} год")


def _extract_org(xml_root: ET.Element) -> tuple[str | None, str | None, str | None]:
    """Return (inn, kpp, company_name) from the XML root."""
    for elem in xml_root.iter():
        if _strip_ns(elem.tag) == "Организация":
            inn = _find_child_text(elem, "ИНН")
            kpp = _find_child_text(elem, "КПП")
            company_name = (
                _find_child_text(elem, "НаимОрг")
                or _find_child_text(elem, "Наименование")
                or _find_child_text(elem, "Наим")
            )
            if inn:
                return inn, kpp, company_name
    for elem in xml_root.iter():
        tag = _strip_ns(elem.tag)
        if tag in ("НПЮЛ", "Организация"):
            inn = _get_attr(elem, "ИННЮЛ", "ИНН", "INN")
            kpp = _get_attr(elem, "КПП", "KPP")
            company_name = _get_attr(elem, "НаимОрг", "Наименование", "Name")
            if inn:
                return inn, kpp, company_name
    return None, None, None


def _try_date_doc_year(xml_root: ET.Element) -> int | None:
    for elem in [xml_root, *[c for c in xml_root if _strip_ns(c.tag) == "Документ"]]:
        date_doc = _get_attr(elem, "ДатаДок", "Дата", "Date")
        if date_doc:
            for pattern in [r"(\d{4})", r"\d{2}\.\d{2}\.(\d{4})", r"(\d{4})-\d{2}-\d{2}"]:
                m = re.search(pattern, date_doc)
                if m:
                    return int(m.group(1))
    return None


def _try_capital_changes_year(xml_root: ET.Element) -> int | None:
    for elem in xml_root.iter():
        tag = _strip_ns(elem.tag)
        if tag in ("Кап31Дек", "Кап31ДекТек"):
            year_attr = _get_attr(elem, "Год", "Year", "year")
            if year_attr:
                with contextlib.suppress(ValueError):
                    return int(year_attr)
    return None


def _extract_report_year(
    xml_root: ET.Element, report_type: str
) -> int | None:
    """Determine the report year from the XML root."""
    year_text = _find_child_text(xml_root, "ОтчетГод")
    if not year_text:
        for elem in [xml_root, *[c for c in xml_root if _strip_ns(c.tag) == "Документ"]]:
            year_text = _get_attr(elem, "ОтчетГод", "ОтчетГод")
            if year_text:
                break
    if year_text:
        with contextlib.suppress(ValueError):
            return int(year_text)

    year = _try_date_doc_year(xml_root)
    if year is not None:
        return year

    if report_type == "capital_changes":
        return _try_capital_changes_year(xml_root)
    return None


def extract(xml_root: ET.Element, report_info: ReportTypeInfo) -> ExtractedMetadata:
    """Extract metadata from XML.

    Required fields:
    - INN (ИНН)
    - Report year (ОтчетГод or extracted from ДатаДок)

    Optional fields:
    - KPP, company name, ОКЕИ
    """
    inn, kpp, company_name = _extract_org(xml_root)

    if not inn:
        raise MissingRequiredFieldError(
            "Missing ИНН in XML. Expected <Организация> block with <ИНН> child "
            "or <НПЮЛ> element with ИННЮЛ attribute."
        )
    inn = re.sub(r"\s+", "", inn)
    if kpp:
        kpp = re.sub(r"\s+", "", kpp)

    report_year = _extract_report_year(xml_root, report_info.report_type)
    if report_year is None:
        raise MissingRequiredFieldError(
            "Could not determine report year from XML. "
            "Expected <ОтчетГод> or ДатаДок attribute."
        )

    period_code, period_name = _determine_period(xml_root, report_year)

    okei = None
    for elem in [xml_root, *[c for c in xml_root if _strip_ns(c.tag) == "Документ"]]:
        okei = _get_attr(elem, "ОКЕИ", "ОКЕИКод", "okei")
        if okei:
            break

    return ExtractedMetadata(
        inn=inn,
        kpp=kpp,
        company_name=company_name,
        report_year=report_year,
        period_code=period_code,
        period_name=period_name,
        okei_code=okei,
        okud=report_info.okud,
        source_type="xml_file",
    )
