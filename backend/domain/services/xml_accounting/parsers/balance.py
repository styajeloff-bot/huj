"""Parser for balance sheet (Бухгалтерский баланс, ОКУД 0710001).

Handles 1C container XML where each line is a tag with СумОтч/СумПрдщ/СумПрдшв
attributes instead of Строка elements.
"""
from __future__ import annotations

from typing import ClassVar

from domain.services.xml_accounting.models import ParsedRow
from domain.services.xml_accounting.parsers.base import BaseReportParser, strip_ns


class BalanceSheetParser(BaseReportParser):
    """Parse 1C XML export for balance sheet form."""

    # Map XML tag name -> (line_code, line_name)
    # Tags found inside Актив/ВнеОбА
    _TAG_MAP: ClassVar[dict[str, tuple[str, str]]] = {
        # --- Актив totals ---
        "Актив":        ("1600", "БАЛАНС (актив)"),
        "Пассив":       ("1700", "БАЛАНС (пассив)"),

        # --- Актив -> Внеоборотные активы ---
        "ВнеОбА":       ("1110", "Внеоборотные активы"),
        "НематАкт":     ("1160", "Нематериальные, финансовые и другие внеоборотные активы"),
        "ОснСр":        ("1150", "Основные средства"),
        "ФинВлож":      ("1170", "Финансовые вложения"),
        "ОтлНалАкт":    ("1180", "Отложенные налоговые активы"),
        "ПрочВнеОбА":   ("1190", "Прочие внеоборотные активы"),

        # --- Актив -> Оборотные активы ---
        "Запасы":       ("1210", "Запасы"),
        "ДебЗад":       ("1230", "Дебиторская задолженность"),
        "ДенежнСр":     ("1250", "Денежные средства и денежные эквиваленты"),
        "ПрочОбА":      ("1260", "Прочие оборотные активы"),

        # --- Пассив -> Капитал ---
        "УставКапитал": ("1310", "Уставный капитал"),
        "СобствАкции":  ("1320", "Собственные акции (доля)"),
        "ДобКапитал":   ("1350", "Добавочный капитал (без уставного)"),
        "РезКапитал":   ("1360", "Резервный капитал"),
        "НераспПриб":   ("1370", "Нераспределенная прибыль (непокрытый убыток)"),

        # --- Пассив -> Долгосрочные обязательства ---
        "ДолгосрОбяз":  ("1410", "Долгосрочные заемные средства"),
        "ОтлНалОбяз":   ("1420", "Отложенные налоговые обязательства"),
        "ОценОбяз":     ("1430", "Оценочные обязательства"),
        "ПрочДолгОбяз": ("1450", "Прочие долгосрочные обязательства"),

        # --- Пассив -> Краткосрочные обязательства ---
        "КраткосрОбяз": ("1510", "Краткосрочные заемные средства"),
        "КредитЗадолж": ("1520", "Кредиторская задолженность"),
        "ДохБудПер":    ("1530", "Доходы будущих периодов"),
        "ОценОбязКр":   ("1540", "Оценочные обязательства"),
        "ПрочКратОбяз": ("1550", "Прочие краткосрочные обязательства"),
    }

    # Section totals (tags that represent rolled-up totals)
    _TOTAL_TAGS: ClassVar[set[str]] = {
        "Актив", "Пассив", "Капитал",
        "ДолгосрОбяз", "КраткосрОбяз",
    }

    def parse(self) -> list[ParsedRow]:
        """Extract rows from Баланс element inside the XML."""
        rows: list[ParsedRow] = []

        # Find Баланс root
        balance_root = self.root
        if strip_ns(self.root.tag) != "Баланс":
            for child in self.root:
                if strip_ns(child.tag) == "Баланс":
                    balance_root = child
                    break

        # Parse all supported tags recursively under Баланс
        for elem in balance_root.iter():
            tag = strip_ns(elem.tag)
            if tag not in self._TAG_MAP:
                continue

            code, name = self._TAG_MAP[tag]
            current = self._get_amount(self._get_attr(elem, "СумОтч", "СумТек"))
            prev = self._get_amount(self._get_attr(elem, "СумПрдщ", "СумПред"))
            before_prev = self._get_amount(self._get_attr(elem, "СумПрдшв"))

            # Skip totals that duplicate detailed rows when detailed exist
            # But keep Актив (1600) and Пассив (1700) as report-level totals
            is_total = tag in self._TOTAL_TAGS
            if is_total and tag not in ("Актив", "Пассив"):
                # Check if we already have children with data
                has_children = any(
                    strip_ns(c.tag) in self._TAG_MAP
                    for c in elem
                )
                if has_children:
                    continue

            xml_raw = {
                "tag": tag,
                "raw_amounts": {
                    "СумОтч": self._get_attr(elem, "СумОтч"),
                    "СумПрдщ": self._get_attr(elem, "СумПрдщ"),
                    "СумПрдшв": self._get_attr(elem, "СумПрдшв"),
                },
            }

            rows.append(
                ParsedRow(
                    line_code=code,
                    line_name=name,
                    amount=current,
                    amount_prev=prev,
                    amount_before_prev=before_prev,
                    xml_raw=xml_raw,
                )
            )

        # If we only got totals with no detail, include the totals
        if not rows:
            # Try Актив / Пассив totals
            for total_tag, total_code, total_name in [
                ("Актив", "1600", "БАЛАНС (актив)"),
                ("Пассив", "1700", "БАЛАНС (пассив)"),
            ]:
                total_elem = self._find_tag(balance_root, total_tag)
                if total_elem is not None:
                    current = self._get_amount(self._get_attr(total_elem, "СумОтч"))
                    prev = self._get_amount(self._get_attr(total_elem, "СумПрдщ"))
                    before_prev = self._get_amount(self._get_attr(total_elem, "СумПрдшв"))
                    rows.append(
                        ParsedRow(
                            line_code=total_code,
                            line_name=total_name,
                            amount=current,
                            amount_prev=prev,
                            amount_before_prev=before_prev,
                        )
                    )

        return self._ensure_rows(rows)
