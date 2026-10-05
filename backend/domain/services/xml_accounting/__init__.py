"""XML accounting report parser — public API.

Entry point: parse_xml(xml_content) -> list[ParsedReport]

Supports both single-form XML and container files (1C export with КНД 0710099
that embeds balance_sheet + financial_result + capital_changes + cash_flow).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Final, cast

from defusedxml import ElementTree as DefusedElementTree
from defusedxml.common import DefusedXmlException

from domain.services.xml_accounting.detector import detect_all
from domain.services.xml_accounting.errors import XMLValidationError
from domain.services.xml_accounting.extractor import extract
from domain.services.xml_accounting.models import (
    ExtractedMetadata,
    ParsedReport,
    ParsedRow,
)
from domain.services.xml_accounting.parsers.balance import BalanceSheetParser
from domain.services.xml_accounting.parsers.capital_changes import CapitalChangesParser
from domain.services.xml_accounting.parsers.cash_flow import CashFlowParser
from domain.services.xml_accounting.parsers.financial_result import (
    FinancialResultParser,
)
from domain.services.xml_accounting.parsers.nds import NDSDeclarationParser

_PARSER_MAP: Final = {
    "balance_sheet": BalanceSheetParser,
    "financial_result": FinancialResultParser,
    "capital_changes": CapitalChangesParser,
    "cash_flow": CashFlowParser,
    "nds_declaration": NDSDeclarationParser,
}


def parse_xml(xml_content: str | bytes) -> list[ParsedReport]:
    """Parse 1C XML accounting report and return structured data.

    Args:
        xml_content: Raw XML string or bytes

    Returns:
        List of ParsedReport (one per detected form). For single-form XML
        the list has one element; for 1C container files (КНД 0710099) it
        can contain up to 4 forms.

    Raises:
        UnsupportedReportError: If no supported KND/OKUD is found
        XMLValidationError: If XML structure is invalid
        MissingRequiredFieldError: If INN or year is missing
        NoDataExtractedError: If no rows could be parsed
    """
    try:
        root = DefusedElementTree.fromstring(xml_content)
    except (DefusedXmlException, ET.ParseError) as exc:
        raise XMLValidationError("Некорректная или небезопасная XML-структура") from exc

    # Detect all report forms inside the XML
    report_infos = detect_all(root)

    results: list[ParsedReport] = []
    for info in report_infos:
        # Extract metadata
        metadata = extract(root, info)

        # Select and run parser for this form
        parser_cls = _PARSER_MAP[info.report_type]
        parser = cast("Any", parser_cls)(metadata, root)
        rows = parser.parse()

        results.append(ParsedReport(metadata=metadata, rows=rows))

    return results


__all__ = [
    "ExtractedMetadata",
    "ParsedReport",
    "ParsedRow",
    "parse_xml",
]
