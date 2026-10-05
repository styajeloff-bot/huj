"""Base parser for all accounting report forms."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from typing import Final

from domain.services.xml_accounting.errors import NoDataExtractedError
from domain.services.xml_accounting.models import ExtractedMetadata, ParsedRow

# 1C namespace patterns
_NS_PATTERNS: Final = (
    "{http://v8.1c.ru/8.1/data/enterprise/current-config}",
    "{http://www.w3.org/2001/XMLSchema}",
)


def strip_ns(tag: str) -> str:
    """Remove XML namespace prefix from tag name."""
    for ns in _NS_PATTERNS:
        if tag.startswith(ns):
            return tag[len(ns):]
    return tag


class BaseReportParser(ABC):
    """Abstract base for all form-specific parsers."""

    def __init__(self, metadata: ExtractedMetadata, xml_root: ET.Element) -> None:
        self.meta = metadata
        self.root = xml_root
        self._okei_multiplier = 1000 if metadata.okei_code == "384" else 1

    def _get_amount(self, value: str | None) -> float | None:
        """Parse numeric value, applying ОКЕИ multiplier."""
        if not value:
            return None
        cleaned = value.replace(" ", "").replace("\xa0", "").replace(",", ".")
        try:
            return float(cleaned) * self._okei_multiplier
        except ValueError:
            return None

    def _find_tag(self, parent: ET.Element, *tag_names: str) -> ET.Element | None:
        """Find first child matching any of the tag names (ignoring namespace)."""
        for child in parent:
            stripped = strip_ns(child.tag)
            if stripped in tag_names:
                return child
        return None

    def _find_all_tags(self, parent: ET.Element, *tag_names: str) -> list[ET.Element]:
        """Find all children matching any of the tag names."""
        return [c for c in parent if strip_ns(c.tag) in tag_names]

    def _get_attr(self, elem: ET.Element, *names: str) -> str | None:
        """Get first matching attribute."""
        for name in names:
            val = elem.get(name)
            if val:
                return val.strip()
        return None

    def _collect_rows(self, parent: ET.Element) -> list[tuple[str, str, str | None, str | None, str | None]]:
        """Collect raw rows from Строка elements.

        Returns list of (code, name, current, prev, before_prev) tuples.
        """
        rows: list[tuple[str, str, str | None, str | None, str | None]] = []
        for child in parent.iter():
            if strip_ns(child.tag) != "Строка":
                continue
            code = self._get_attr(child, "Код", "Code")
            name = self._get_attr(child, "Наименование", "Наим", "Name")
            if not code and not name:
                continue
            current = self._get_attr(child, "СумОтч", "СумТек", "SumCurrent")
            prev = self._get_attr(child, "СумПрдщ", "СумПред", "SumPrev")
            before_prev = self._get_attr(child, "СумПрдшв", "СумПредПред", "SumBeforePrev")
            rows.append((code or "", name or "", current, prev, before_prev))
        return rows

    @abstractmethod
    def parse(self) -> list[ParsedRow]:
        """Parse XML and return list of rows for DB upsert."""
        ...

    def _ensure_rows(self, rows: list[ParsedRow], *, allow_empty: bool = False) -> list[ParsedRow]:
        """Validate that at least one row was extracted.

        Args:
            rows: Parsed rows to validate.
            allow_empty: If True, skip the non-empty check (useful for forms
                where amounts may legitimately be 0 or missing).
        """
        if not rows and not allow_empty:
            raise NoDataExtractedError(
                f"No data rows extracted from {self.meta.okud} report for INN {self.meta.inn}"
            )
        return rows
