"""Pure rules for the legal document registry."""
from datetime import date
from typing import Any

TYPES = {
    "contract": "Договор", "agreement": "Соглашение",
    "additional_agreement": "Доп. соглашение", "invoice": "Счёт",
    "act": "Акт", "power_of_attorney": "Доверенность", "other": "Прочее",
}
ROLES = ("leasing_company", "distributor", "dealer")
STATUS_LABELS = {"active": "Действует", "expiring": "Истекает", "pending": "Ещё не наступил", "expired": "Истёк", "deactivated": "Деактивирован"}


def normalize_number(number: str) -> str:
    return "".join(number.split()).casefold()


def validate_identity(document_type: str, number: str, name: str) -> None:
    if document_type not in TYPES:
        raise ValueError("Неизвестный тип документа")
    if not normalize_number(number) or len(number) > 100 or len(normalize_number(number)) > 100:
        raise ValueError("Номер обязателен и должен содержать не более 100 символов")
    if not name.strip() or len(name.strip()) > 255:
        raise ValueError("Название обязательно и должно содержать не более 255 символов")


def validate_period(valid_from: date, valid_to: date | None) -> None:
    if valid_to is not None and valid_to < valid_from:
        raise ValueError("Дата окончания не может быть раньше начала")


def status(valid_from: date, valid_to: date | None, deactivated: bool, today: date) -> str:
    if deactivated:
        return "deactivated"
    if valid_from > today:
        return "pending"
    if valid_to is not None and valid_to < today:
        return "expired"
    if valid_to is not None and (valid_to - today).days <= 30:
        return "expiring"
    return "active"


def inherit_related(supplied: dict[str, Any], parent: dict[str, Any]) -> dict[str, Any]:
    result = dict(supplied)
    for role in ROLES:
        key = f"{role}_ids" if role == "leasing_company" else f"{role}_company_ids"
        if not result.get(key):
            result[key] = parent.get(key, [])
    if result.get("platform_ml") is None:
        result["platform_ml"] = parent.get("platform_ml", False)
    return result


def matches_context(participants: dict[str, Any], context: dict[str, Any]) -> bool:
    """One positive match is enough; absent criteria never count as a match."""
    for role in ROLES:
        field = f"{role}_id" if role == "leasing_company" else f"{role}_company_id"
        value = context.get(field)
        if value is not None and value in participants.get(f"{field}s", []):
            return True
    for field in ("mark_id", "model_id"):
        value = participants.get(field)
        if value is not None and value == context.get(field):
            return True
    return participants.get("platform_ml") is True and context.get("platform_ml") is True


def validate_participants(payload: dict[str, Any]) -> None:
    if not any(payload.get(key) for key in ("platform_ml", "leasing_company_ids", "dealer_company_ids", "distributor_company_ids", "mark_id")):
        raise ValueError("Укажите хотя бы одного участника или марку")
