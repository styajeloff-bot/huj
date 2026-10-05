"""Commission negotiation does not modify any financial snapshot."""

from copy import deepcopy
from decimal import Decimal
from typing import Any

from domain.monetization.errors import (
    MonetizationAccessDenied,
    MonetizationConflict,
    MonetizationValidation,
)
from domain.monetization.programs import positive_decimal


def validate_commission_request(
    request: dict[str, Any], action: str, role: str
) -> None:
    """Validate creation or response according to the negotiation state."""
    if action == "create":
        if role != "dealer":
            raise MonetizationAccessDenied("Запросить комиссию может только дилер")
        if not isinstance(request.get("has_lca"), bool):
            raise MonetizationValidation(
                "Перед запросом комиссии проверьте отсутствие заявок в ЛК"
            )
        if request["has_lca"]:
            raise MonetizationConflict(
                "Комиссию можно запросить только до первой заявки в ЛК"
            )
        _validate_value(
            request.get("requested_calc_type"), request.get("requested_value")
        )
        return
    if request.get("status") in {"accepted", "rejected"}:
        raise MonetizationConflict("Запрос комиссии уже закрыт")
    if role == "leasing":
        if action not in {"accepted", "rejected", "countered"}:
            raise MonetizationValidation("Недопустимое решение лизинговой компании")
        if request.get("status") != "sent":
            raise MonetizationConflict("Ответить можно только на отправленный запрос")
    elif role == "dealer":
        if action not in {"accept_counter", "reject"}:
            raise MonetizationAccessDenied(
                "Дилер принимает решение только по встречному предложению"
            )
        if request.get("status") != "countered":
            raise MonetizationConflict("В запросе нет встречного предложения")
    else:
        raise MonetizationAccessDenied("Эта роль не участвует в согласовании комиссии")


def _validate_value(calc_type: Any, value: Any) -> None:
    if calc_type not in {"percent", "amount"}:
        raise MonetizationValidation(
            "Выберите процент или фиксированную сумму комиссии"
        )
    positive_decimal(value, "Размер комиссии")


def transition_condition_request(
    request: dict[str, Any],
    action: str,
    role: str,
    value: Decimal | None = None,
    calc_type: str | None = None,
) -> dict[str, Any]:
    """Return a new negotiation state; counter offers require a dealer decision."""
    validate_commission_request(request, action, role)
    updated = deepcopy(request)
    if action == "countered":
        _validate_value(calc_type, value)
        updated["counter_calc_type"] = calc_type
        updated["counter_value"] = value
    elif value is not None or calc_type is not None:
        raise MonetizationValidation(
            "Новые условия допустимы только во встречном предложении"
        )
    if action == "accept_counter":
        _validate_value(request.get("counter_calc_type"), request.get("counter_value"))
        updated["status"] = "accepted"
    elif action == "reject":
        updated["status"] = "rejected"
    else:
        updated["status"] = action
    return updated
