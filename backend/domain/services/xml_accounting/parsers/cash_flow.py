"""Parser for cash flow report (Отчет о движении денежных средств, ОКУД 0710005).

1C XML structure: ТекОпер, ИнвОпер, ФинОпер sections with
Поступ and Платеж sub-sections. Attributes: СумОтч, СумПред.
"""
from __future__ import annotations

from typing import ClassVar

from domain.services.xml_accounting.models import ParsedRow
from domain.services.xml_accounting.parsers.base import BaseReportParser, strip_ns


class CashFlowParser(BaseReportParser):
    """Parse 1C XML export for cash flow form."""

    # Map XML tag -> (line_code, line_name, section)
    _TAG_MAP: ClassVar[dict[str, tuple[str, str]]] = {
        # --- Operating activities ---
        "СальдоТек":      ("4100", "Сальдо денежных средств (текущая деятельность)"),
        "Поступ":         ("4110", "Поступления (текущая деятельность)"),
        "ПродПТРУ":       ("4111", "От продажи товаров, работ, услуг"),
        "Платеж":         ("4120", "Платежи (текущая деятельность)"),
        "ПоставСМРУ":     ("4121", "Поставщикам, подрядчикам, за работы, услуги"),
        "Зарплата":       ("4122", "Персоналу по оплате труда"),
        "Налоги":         ("4123", "Налоги и сборы"),
        "ПрочПлатежи":    ("4124", "Прочие платежи"),

        # --- Investing activities ---
        "СальдоИнв":      ("4200", "Сальдо инвестиционной деятельности"),
        "ПоступИнв":      ("4210", "Поступления (инвестиционная деятельность)"),
        "ПродВнАктив":    ("4211", "От продажи внеоборотных активов"),
        "ПлатежИнв":      ("4220", "Платежи (инвестиционная деятельность)"),
        "ПриобрВнАктив":  ("4221", "Приобретение внеоборотных активов"),

        # --- Financing activities ---
        "СальдоФин":      ("4300", "Сальдо финансовой деятельности"),
        "ПоступФин":      ("4310", "Поступления (финансовая деятельность)"),
        "КредЗайм":       ("4311", "Кредиты и займы полученные"),
        "УстВзнос":       ("4312", "Уставный капитал"),
        "ПлатежФин":      ("4320", "Платежи (финансовая деятельность)"),
        "УплДивИн":       ("4321", "Уплата дивидендов и процентов"),
        "ПогашКред":      ("4322", "Погашение кредитов и займов"),

        # --- Totals ---
        "СальдоОтч":      ("4400", "Сальдо за отчетный период"),
        "ОстНачОтч":      ("4500", "Остаток денежных средств на начало"),
        "ОстКонОтч":      ("4500", "Остаток денежных средств на конец"),
        "ВлИзмКурс":      ("4490", "Влияние изменения курса валют"),
    }

    def parse(self) -> list[ParsedRow]:
        """Extract rows from ДвижениеДен element."""
        rows: list[ParsedRow] = []

        # Find ДвижениеДен root
        report_root = self.root
        if strip_ns(self.root.tag) != "ДвижениеДен":
            for child in self.root:
                if strip_ns(child.tag) == "ДвижениеДен":
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
