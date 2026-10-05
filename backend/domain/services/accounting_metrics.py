"""Pure financial-ratio computations on top of `AccountingReport`.

No I/O, no external deps — trivially unit-testable.

Code references (Russian РСБУ):
- 1100 — Итого внеоборотные активы
- 1200 — Итого оборотные активы
- 1250 — Денежные средства
- 1300 — Капитал и резервы (собственный капитал)
- 1400 — Итого долгосрочные обязательства
- 1500 — Итого краткосрочные обязательства
- 1600 — Баланс (актив)
- 1700 — Баланс (пассив)
- 2110 — Выручка
- 2400 — Чистая прибыль
"""
from __future__ import annotations

from domain.values_accounting import (
    AccountingReport,
    AccountingRow,
    FinancialRatio,
    RatioBand,
)


def compute_ratios(report: AccountingReport) -> list[FinancialRatio]:
    """Return a fixed set of high-signal ratios for the latest reported year.

    Ratios with missing inputs get `band='unknown'` and `value=None` so the
    UI can still show the row with an explanation.
    """
    latest = _latest_year(report)
    prev = _prev_year(report, latest)

    balance = _index_by_code(report.balance_sheet)
    fin_result = _index_by_code(report.financial_result)

    current_assets = _get(balance, "1200", latest)
    current_liab = _get(balance, "1500", latest)
    long_liab = _get(balance, "1400", latest)
    equity = _get(balance, "1300", latest)
    total_assets = _get(balance, "1600", latest)
    revenue = _get(fin_result, "2110", latest)
    net_profit = _get(fin_result, "2400", latest)
    revenue_prev = _get(fin_result, "2110", prev) if prev else None

    ratios: list[FinancialRatio] = [
        _current_ratio(current_assets, current_liab),
        _autonomy(equity, total_assets),
        _debt_to_equity(long_liab, current_liab, equity),
        _ros(net_profit, revenue),
        _roa(net_profit, total_assets),
        _revenue_growth(revenue, revenue_prev),
    ]
    return ratios


def _current_ratio(
    current_assets: int | None, current_liab: int | None
) -> FinancialRatio:
    if current_assets is None or not current_liab:
        return _unknown(
            "current_ratio",
            "Текущая ликвидность",
            "Оборотные активы / Краткосрочные обязательства",
        )
    value = current_assets / current_liab
    if value >= 1.5:
        band: RatioBand = "good"
        hint = "Достаточный запас ликвидности."
    elif value >= 1.0:
        band = "warn"
        hint = "Пограничная ликвидность — контролировать оборачиваемость."
    else:
        band = "bad"
        hint = "Оборотных активов не хватает на покрытие краткосрочных обязательств."
    return FinancialRatio(
        key="current_ratio",
        name="Текущая ликвидность",
        value=round(value, 2),
        band=band,
        hint=hint,
        formula="стр. 1200 / стр. 1500",
    )


def _autonomy(equity: int | None, total_assets: int | None) -> FinancialRatio:
    if equity is None or not total_assets:
        return _unknown(
            "autonomy",
            "Коэффициент автономии",
            "Собственный капитал / Валюта баланса",
        )
    value = equity / total_assets
    if equity < 0:
        return FinancialRatio(
            key="autonomy",
            name="Коэффициент автономии",
            value=round(value, 2),
            band="bad",
            hint="Отрицательный собственный капитал — критический риск.",
            formula="стр. 1300 / стр. 1700",
        )
    if value >= 0.5:
        band: RatioBand = "good"
        hint = "Компания финансируется преимущественно собственными средствами."
    elif value >= 0.3:
        band = "warn"
        hint = "Умеренная зависимость от заёмных средств."
    else:
        band = "bad"
        hint = "Высокая закредитованность — большая часть активов на заёмные."
    return FinancialRatio(
        key="autonomy",
        name="Коэффициент автономии",
        value=round(value, 2),
        band=band,
        hint=hint,
        formula="стр. 1300 / стр. 1700",
    )


def _debt_to_equity(
    long_liab: int | None, current_liab: int | None, equity: int | None
) -> FinancialRatio:
    total_debt = (long_liab or 0) + (current_liab or 0)
    if equity is None or equity <= 0:
        return FinancialRatio(
            key="debt_to_equity",
            name="Долг / Капитал (D/E)",
            value=None,
            band="bad" if equity is not None and equity <= 0 else "unknown",
            hint=(
                "Отрицательный или нулевой собственный капитал — коэффициент"
                " не рассчитывается, компания в критической зоне."
                if equity is not None and equity <= 0
                else "Нет данных по собственному капиталу."
            ),
            formula="(стр. 1400 + стр. 1500) / стр. 1300",
        )
    value = total_debt / equity
    if value <= 1.0:
        band: RatioBand = "good"
        hint = "Долговая нагрузка умеренная."
    elif value <= 2.0:
        band = "warn"
        hint = "Повышенная долговая нагрузка — проверить обслуживание долга."
    else:
        band = "bad"
        hint = "Критическая долговая нагрузка."
    return FinancialRatio(
        key="debt_to_equity",
        name="Долг / Капитал (D/E)",
        value=round(value, 2),
        band=band,
        hint=hint,
        formula="(стр. 1400 + стр. 1500) / стр. 1300",
    )


def _ros(net_profit: int | None, revenue: int | None) -> FinancialRatio:
    if net_profit is None or not revenue:
        return _unknown(
            "ros", "Рентабельность продаж (ROS)", "Чистая прибыль / Выручка"
        )
    value = net_profit / revenue
    if value >= 0.08:
        band: RatioBand = "good"
        hint = "Бизнес с хорошей маржой."
    elif value >= 0.02:
        band = "warn"
        hint = "Низкая маржа — устойчивость к шокам ограничена."
    else:
        band = "bad"
        hint = "Убыточный или околонулевой результат."
    return FinancialRatio(
        key="ros",
        name="Рентабельность продаж (ROS)",
        value=round(value * 100, 2),
        band=band,
        hint=hint,
        formula="стр. 2400 / стр. 2110 × 100%",
    )


def _roa(net_profit: int | None, total_assets: int | None) -> FinancialRatio:
    if net_profit is None or not total_assets:
        return _unknown(
            "roa",
            "Рентабельность активов (ROA)",
            "Чистая прибыль / Активы",
        )
    value = net_profit / total_assets
    if value >= 0.05:
        band: RatioBand = "good"
        hint = "Активы работают эффективно."
    elif value >= 0.01:
        band = "warn"
        hint = "Средняя отдача от активов."
    else:
        band = "bad"
        hint = "Активы не приносят отдачи."
    return FinancialRatio(
        key="roa",
        name="Рентабельность активов (ROA)",
        value=round(value * 100, 2),
        band=band,
        hint=hint,
        formula="стр. 2400 / стр. 1600 × 100%",
    )


def _revenue_growth(
    revenue: int | None, revenue_prev: int | None
) -> FinancialRatio:
    if revenue is None or not revenue_prev:
        return _unknown(
            "revenue_growth",
            "Рост выручки YoY",
            "(Выручка_t − Выручка_t-1) / Выручка_t-1",
        )
    value = (revenue - revenue_prev) / revenue_prev
    if value >= 0.1:
        band: RatioBand = "good"
        hint = "Выручка растёт двузначными темпами."
    elif value >= 0:
        band = "warn"
        hint = "Выручка стагнирует или слабо растёт."
    else:
        band = "bad"
        hint = "Выручка снижается год к году."
    return FinancialRatio(
        key="revenue_growth",
        name="Рост выручки YoY",
        value=round(value * 100, 2),
        band=band,
        hint=hint,
        formula="(стр. 2110_t − стр. 2110_t-1) / стр. 2110_t-1 × 100%",
    )


def _unknown(key: str, name: str, formula: str) -> FinancialRatio:
    return FinancialRatio(
        key=key,
        name=name,
        value=None,
        band="unknown",
        hint="Недостаточно данных для расчёта.",
        formula=formula,
    )


def _index_by_code(rows: list[AccountingRow]) -> dict[str, AccountingRow]:
    return {row.code: row for row in rows}


def _get(
    index: dict[str, AccountingRow], code: str, year: str | None
) -> int | None:
    if year is None:
        return None
    row = index.get(code)
    if row is None:
        return None
    return row.values.get(year)


def _latest_year(report: AccountingReport) -> str | None:
    if not report.period_years:
        return None
    return str(max(report.period_years))


def _prev_year(report: AccountingReport, latest: str | None) -> str | None:
    if latest is None or not report.period_years:
        return None
    latest_int = int(latest)
    earlier = [y for y in report.period_years if y < latest_int]
    if not earlier:
        return None
    return str(max(earlier))
