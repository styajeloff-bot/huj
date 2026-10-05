"""NDS (VAT) declaration parser — КНД 1151001."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from domain.services.xml_accounting.models import ParsedRow
from domain.services.xml_accounting.parsers.base import BaseReportParser, strip_ns


class NDSDeclarationParser(BaseReportParser):
    """Parse NDS (VAT) declaration XML (КНД 1151001)."""

    def _find_by_local_name(self, local_name: str) -> ET.Element | None:
        """Find first descendant with the given local tag name."""
        for elem in self.root.iter():
            if strip_ns(elem.tag) == local_name:
                return elem
        return None

    def _findall_by_local_name(self, local_name: str) -> list[ET.Element]:
        """Find all descendants with the given local tag name."""
        return [elem for elem in self.root.iter() if strip_ns(elem.tag) == local_name]

    def parse(self) -> list[ParsedRow]:
        """Extract NDS per-rate rows and totals."""
        doc = self._find_by_local_name("Документ") or self.root

        total_tax_payable = self._get_amount(doc.get("СумУпл164"))
        total_deductions = self._get_amount(doc.get("СумНалВыч"))
        total_recovered = self._get_amount(doc.get("СумНалОб"))

        # Try to find totals inside СумНалОб wrapper if not on Документ
        sum_nal_ob = self._find_by_local_name("СумНалОб")
        if sum_nal_ob is not None:
            if total_tax_payable is None:
                total_tax_payable = self._get_amount(sum_nal_ob.get("СумУпл164"))
            if total_deductions is None:
                total_deductions = self._get_amount(sum_nal_ob.get("СумНалВыч"))
            if total_recovered is None:
                total_recovered = self._get_amount(sum_nal_ob.get("СумНалОб"))
            children = list(sum_nal_ob)
        else:
            children = []
            for tag in (
                "РеалТов20",
                "РеалТов10",
                "РеалТов7",
                "РеалТов5",
                "РеалТов120",
                "РеалТов110",
                "РеалТов107",
                "РеалТов105",
                "РеалТов18",
                "РеалТов118",
                "РеалТов16.67",
                "РеалТов9.09",
                "ВыпСтрРаб",
                "ОплПредПост",
            ):
                found = self._findall_by_local_name(tag)
                children.extend(found)

        rows: list[ParsedRow] = []
        seen: set[str] = set()

        for child in children:
            tag_name = strip_ns(child.tag)
            if tag_name in seen:
                continue
            seen.add(tag_name)

            tax_base = self._get_amount(self._get_attr(child, "НалБаза"))
            tax_amount = self._get_amount(self._get_attr(child, "СумНал"))

            if tax_base is None and tax_amount is None:
                continue

            rows.append(
                ParsedRow(
                    line_code=tag_name,
                    line_name=tag_name,
                    amount=tax_base,
                    tax_amount=tax_amount,
                    total_tax_payable=total_tax_payable,
                    total_deductions=total_deductions,
                    total_recovered=total_recovered,
                    xml_raw={
                        "tag": tag_name,
                        "НалБаза": self._get_attr(child, "НалБаза"),
                        "СумНал": self._get_attr(child, "СумНал"),
                    },
                )
            )

        return self._ensure_rows(rows)
