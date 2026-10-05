"""UUID validation for external identifiers and persisted JSON values."""

from typing import Any
from uuid import UUID

from domain.monetization.errors import MonetizationValidation


def entity_id(value: Any) -> UUID:
    """Validate UUID input without numeric coercion; typed repository values pass through."""
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        raise MonetizationValidation("Идентификатор должен быть UUID")
    try:
        return UUID(value)
    except ValueError as exc:
        raise MonetizationValidation("Некорректный UUID") from exc


def same_entity(left: Any, right: Any) -> bool:
    """Nullable participants match only when both refer to the same UUID."""
    return (
        left is not None and right is not None and entity_id(left) == entity_id(right)
    )
