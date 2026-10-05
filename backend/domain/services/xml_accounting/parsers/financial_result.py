"""Parser for financial result report (Отчет о финансовых результатах, ОКУД 0710002).

1C XML structure uses tag names like Выруч, СебестПрод, ПрибПрод with
attributes СумОтч (current year) and СумПред (previous year).
"""
from __future__ import annotations

from typing import ClassVar

from domain.services.xml_accounting.models import ParsedRow
from domain.services.xml_accounting.parsers.base import BaseReportParser, strip_ns


class FinancialResultParser(BaseReportParser):
    """Parse 1C XML export for financial result (P&L) form."""

    # Map XML tag name -> (line_code, line_name)
    _TAG_MAP: ClassVar[dict[str, tuple[str, str]]] = {
        "Выруч":            ("2110", "Выручка"),
        "СебестПрод":       ("2120", "Себестоимость продаж"),
        "ВаловаяПрибыль":   ("2100", "Валовая прибыль (убыток)"),
        "КомРасход":        ("2210", "Коммерческие расходы"),
        "УпрРасход":        ("2220", "Управленческие расходы"),
        "ПрибПрод":         ("2200", "Прибыль (убыток) от продаж"),
        "ДоходОтУчаст":     ("2310", "Доходы от участия в других организациях"),
        "ПроцПолуч":        ("2320", "Проценты к получению"),
        "ПроцУпл":          ("2330", "Проценты к уплате"),
        "ПрочДоход":        ("2340", "Прочие доходы"),
        "ПрочРасход":       ("2350", "Прочие расходы"),
        "ПрибУбДоНал":      ("2300", "Прибыль (убыток) до налогообложения"),
        "НалПриб":          ("2410", "Налог на прибыль"),
        "ТекНалПриб":       ("2411", "Текущий налог на прибыль"),
        "ОтложНалПриб":     ("2412", "Отложенный налог на прибыль"),
        "ПрибУбытПрек":     ("2420", "Прибыль (убыток) от прекращенной деятельности"),
        "Прочее":           ("2430", "Прочее"),
        "ЧистПрибУб":       ("2400", "Чистая прибыль (убыток)"),
        "РезПрцВОАНеЧист": ("2510", "Результат от переоценки внеоборотных активов"),
        "РезПрОпНеЧист":    ("2520", "Результат от прочих операций"),
        "НалПрибОпНеЧист":  ("2530", "Налог на прибыль по операциям"),
        "СовФинРез":        ("2500", "Совокупный финансовый результат"),
    }

    def parse(self) -> list[ParsedRow]:
        """Extract rows from ФинРез element."""
        rows: list[ParsedRow] = []

        # Find ФинРез root
        report_root = self.root
        if strip_ns(self.root.tag) not in ("ФинРез", "ОФР", "ОтчетОФинансовыхРезультатах"):
            for child in self.root:
                if strip_ns(child.tag) in ("ФинРез", "ОФР", "ОтчетОФинансовыхРезультатах"):
                    report_root = child
                    break

        # Collect all supported tags
        for elem in report_root.iter():
            tag = strip_ns(elem.tag)
            if tag not in self._TAG_MAP:
                continue

            code, name = self._TAG_MAP[tag]
            current = self._get_amount(self._get_attr(elem, "СумОтч", "СумТек"))
            prev = self._get_amount(self._get_attr(elem, "СумПред", "СумПрдщ"))

            xml_raw = {
                "tag": tag,
                "raw_amounts": {
                    "СумОтч": self._get_attr(elem, "СумОтч"),
                    "СумПред": self._get_attr(elem, "СумПред"),
                },
            }

            rows.append(
                ParsedRow(
                    line_code=code,
                    line_name=name,
                    amount=current,
                    amount_prev=prev,
                    xml_raw=xml_raw,
                )
            )

        return self._ensure_rows(rows)
