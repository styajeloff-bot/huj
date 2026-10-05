"""Monetization bases come from completed source deals, never the calculator."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from domain.monetization.errors import MonetizationValidation
from domain.monetization.programs import SOURCES, positive_decimal


def build_source_context(
    facts: dict[str, Any], occurred_at: datetime
) -> dict[str, Any]:
    if facts.get("source_type") not in SOURCES:
        raise MonetizationValidation(
            "Источник заявки не зафиксирован или пока не поддерживается"
        )
    if facts.get("source_status") != "deal":
        raise MonetizationValidation("Исходная заявка ещё не перешла в сделку")
    if not facts.get("leasing_company_id"):
        raise MonetizationValidation(
            "Не определена лизинговая компания исходной сделки"
        )
    if not facts.get("dealer_company_id"):
        raise MonetizationValidation("Не определён дилер исходной сделки")
    if facts.get("participant_conflict"):
        raise MonetizationValidation(
            "Участники исходной сделки определены неоднозначно"
        )
    if facts["source_type"] == "exchange":
        if not facts.get("accepted_bid_id") or not facts.get("bid_is_accepted"):
            raise MonetizationValidation("Принятая ставка биржи не зафиксирована")
        quantity = facts.get("bid_quantity")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            raise MonetizationValidation(
                "Не зафиксировано положительное количество принятой ставки"
            )
        base = positive_decimal(
            facts.get("bid_price"), "Цена принятой ставки"
        ) * Decimal(quantity)
    else:
        if not facts.get("final_proposal_id"):
            raise MonetizationValidation(
                "Отсутствует стоимость имущества из итогового КП"
            )
        base = positive_decimal(
            facts.get("final_amount"), "Стоимость имущества из итогового КП"
        )
    return {**facts, "base_amount": base, "occurred_at": occurred_at}


def support_origin(
    program: dict[str, Any], dealer_company_id: Any, distributor_company_id: Any = None
) -> dict[str, Any]:
    """Keep only unambiguous support ownership from its explicit company relations."""
    distributors = program.get("distributor_ids") or []
    if not distributors and program.get("distributor_id") is not None:
        distributors = [program["distributor_id"]]
    unique = {str(value): value for value in distributors}
    distributor = None
    if distributor_company_id is not None and str(distributor_company_id) in unique:
        distributor = distributor_company_id
    elif len(unique) == 1:
        distributor = next(iter(unique.values()))
    return {
        "dealer_company_id": dealer_company_id,
        "distributor_company_id": distributor,
    }
