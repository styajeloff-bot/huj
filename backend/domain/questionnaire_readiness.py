"""Pure completeness rules for questionnaire delivery."""
from __future__ import annotations

from typing import Any

_REQUIRED_DOCUMENT_FIELDS = frozenset({"director_appointment_document", "state_defense_order"})


def field_is_present(field: str, value: Any, questionnaire: dict[str, Any]) -> bool:
    if field == "has_beneficiary" and value is False:
        return _present(questionnaire.get("no_beneficial_owner_reason"))
    if field == "questionnaire_completed_at":
        # Successful delivery writes this value in the same transaction.
        return True
    if field in _REQUIRED_DOCUMENT_FIELDS:
        return isinstance(value, dict) and value.get("status") == "attached" and bool(value.get("documents"))
    if isinstance(value, dict) and value.get("status") == "missing":
        return field in {"loans_credits_leasing", "third_party_guarantees", "additional_collateral_available"}
    if field == "contact_person":
        return isinstance(value, dict) and all(
            _present(value.get(key)) for key in ("name", "position", "phone", "email")
        )
    return _composite_is_present(field, value)


def _record_has(value: Any, keys: tuple[str, ...]) -> bool:
    return isinstance(value, dict) and all(_present(value.get(key)) for key in keys)


def _selection_is_present(field: str, value: Any) -> bool:
    if field == "vehicle_purchase_purpose":
        vehicles = value.get("vehicles") if isinstance(value, dict) else None
        return isinstance(vehicles, list) and bool(vehicles) and all(
            isinstance(row, dict) and isinstance(row.get("purposes"), list)
            and bool(row["purposes"]) and all(
                isinstance(purpose, str) and bool(purpose.strip())
                for purpose in row["purposes"]
            ) for row in vehicles
        )
    return isinstance(value, dict) and (
        any(value.get(key) is True for key in ("not_used", "sbis", "diadoc", "kontur"))
        or (value.get("other") is True and _present(value.get("other_name")))
    )


def _composite_is_present(field: str, value: Any) -> bool:
    if field in {"vehicle_purchase_purpose", "electronic_document_management_systems"}:
        return _selection_is_present(field, value)
    if field == "transaction_beneficiary":
        return _record_has(value, ("fio",))
    row_keys = {
        "main_counterparties": ("name", "inn"),
        "management_company_details": ("name", "inn"),
        "licenses_or_sro_membership": ("document_id", "user_title"),
    }
    if field == "management_company_details" and isinstance(value, dict):
        # Existing requirement applies to requisites; §3.30 does not require an
        # LC-requested document before assignment. TODO(TZ40): define separately.
        value = value.get("requisites")
    if field in row_keys:
        return isinstance(value, list) and bool(value) and all(
            _record_has(row, row_keys[field]) for row in value
        )
    if field == "open_bank_accounts":
        return isinstance(value, list) and bool(value) and all(
            _record_has(row, ("acc_number",)) and (
                _record_has(row.get("bank"), ("name", "bik"))
                if isinstance(row.get("bank"), dict)
                else isinstance(row.get("bank"), str) and _record_has(
                    row, ("bank", "bik", "correspondent_account")
                )
            ) for row in value
        )
    if field in {"founders", "beneficiaries", "other_representatives"}:
        return isinstance(value, list) and bool(value) and all(
            isinstance(row, dict) and (
                _present(row.get("name")) or _present(row.get("full_name"))
                or _record_has(row, ("surname", "first_name"))
            ) for row in value
        )
    return _present(value)


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(_present(item) for item in value)
    if isinstance(value, dict):
        business = {key: item for key, item in value.items() if key not in {"id", "signer_key"}}
        return bool(business) and any(_present(item) for item in business.values())
    return True
