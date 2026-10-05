"""Parser for capital changes report (Отчет об изменениях капитала, ОКУД 0710004).

1C XML structure: ИзмКапПред / ИзмКапОтч sections with
year-level tags (Кап31ДекПред, Кап31ДекПредКор, НаДатуОкон, etc.)
that have capital-component attributes (УстКапитал, СобВыкупАкц, etc.).
"""
from __future__ import annotations

from typing import ClassVar

from domain.services.xml_accounting.models import ParsedRow
from domain.services.xml_accounting.parsers.base import BaseReportParser, strip_ns


class CapitalChangesParser(BaseReportParser):
    """Parse 1C XML export for capital changes form."""

    # Component mapping: XML attribute name -> (line_code, human name)
    _COMPONENTS: ClassVar[dict[str, tuple[str, str]]] = {
        "УстКапитал":  ("3100", "Уставный капитал"),
        "СобВыкупАкц": ("3200", "Собственные выкупленные акции (доли)"),
        "НакопДооц":   ("3600", "Накопленные дооценки (дооценка)"),
        "ДобКапитал":  ("3300", "Добавочный капитал"),
        "РезКапитал":  ("3400", "Резервный капитал"),
        "НераспПриб":  ("3500", "Нераспределенная прибыль (непокрытый убыток)"),
        "Итог":        ("3700", "Итого"),
    }

    # Year tag mapping: XML tag -> year offset from report_year
    # For ИзмКапОтч (current report): Кап31ДекПред = year-1, Кап31ДекПредКор = year-1 corrected
    # НаОтчетДат = current year
    _YEAR_OFFSETS: ClassVar[dict[str, int]] = {
        "Кап31ДекПред": -1,      # Previous year
        "Кап31ДекПредКор": -1,   # Corrected previous year
        "НаДатуОкон": 0,          # Current (report date)
        "НаОтчетДат": 0,          # Current (report date)
    }

    def parse(self) -> list[ParsedRow]:
        """Extract rows: each component × each year section = one row."""
        rows: list[ParsedRow] = []

        # Find ОтчетИзмКап root (may be nested)
        report_root = self.root
        if strip_ns(self.root.tag) != "ОтчетИзмКап":
            for elem in self.root.iter():
                if strip_ns(elem.tag) == "ОтчетИзмКап":
                    report_root = elem
                    break

        # Iterate sections: ИзмКапОтч (current year) and ИзмКапПред (previous year)
        for section in report_root:
            section_tag = strip_ns(section.tag)
            if section_tag == "ИзмКапОтч":
                year = self.meta.report_year
            elif section_tag == "ИзмКапПред":
                year = self.meta.report_year - 1
            else:
                continue

            # Find the "final state" tags for this year
            # НаОтчетДат / НаДатуОкон = final values for the year
            final_tags = ("НаОтчетДат", "НаДатуОкон", "Кап31ДекПредКор")
            for year_tag_elem in section:
                year_tag = strip_ns(year_tag_elem.tag)
                if year_tag not in final_tags:
                    continue

                # Extract each component from attributes
                for comp_attr, (comp_code, comp_name) in self._COMPONENTS.items():
                    val = self._get_attr(year_tag_elem, comp_attr)
                    if val is None:
                        continue

                    amount = self._get_amount(val)

                    rows.append(
                        ParsedRow(
                            line_code=comp_code,
                            line_name=comp_name,
                            amount=amount,
                            component_code=comp_attr,
                            component_name=comp_name,
                            xml_raw={
                                "year_tag": year_tag,
                                "year": year,
                                "component_attr": comp_attr,
                                "raw_value": val,
                            },
                        )
                    )

        return self._ensure_rows(rows, allow_empty=True)
