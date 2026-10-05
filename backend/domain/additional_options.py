"""Domain policy for application-vehicle additional option catalogs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from domain.errors import DomainError


class InvalidAdditionalOptionsError(DomainError):
    """Additional option selections violate the active catalog contract."""


@dataclass(frozen=True)
class AdditionalOptionsCatalogPolicy:
    """Validate option codes against one loaded equipment/service catalog."""

    equipment_codes: frozenset[str]
    service_codes: frozenset[str]

    def validate(
        self,
        *,
        equipment_codes: Sequence[object],
        service_codes: Sequence[object],
    ) -> None:
        selected_equipment_codes = _validated_codes(equipment_codes, "оборудования")
        selected_service_codes = _validated_codes(service_codes, "услуги")
        _ensure_catalog_membership(
            selected_equipment_codes,
            catalog_codes=self.equipment_codes,
            other_catalog_codes=self.service_codes,
            item_label="оборудования",
            other_label="услугам",
        )
        _ensure_catalog_membership(
            selected_service_codes,
            catalog_codes=self.service_codes,
            other_catalog_codes=self.equipment_codes,
            item_label="услуги",
            other_label="оборудованию",
        )


def _validated_codes(codes: Sequence[object], item_label: str) -> tuple[str, ...]:
    validated: list[str] = []
    for code in codes:
        if not isinstance(code, str) or not code:
            raise InvalidAdditionalOptionsError(f"Код {item_label} не указан")
        if code in validated:
            raise InvalidAdditionalOptionsError(
                f"Код {item_label} {code!r} повторяется"
            )
        validated.append(code)
    return tuple(validated)


def _ensure_catalog_membership(
    codes: Sequence[str],
    *,
    catalog_codes: frozenset[str],
    other_catalog_codes: frozenset[str],
    item_label: str,
    other_label: str,
) -> None:
    for code in codes:
        if code in catalog_codes:
            continue
        if code in other_catalog_codes:
            raise InvalidAdditionalOptionsError(
                f"Код {code!r} относится к {other_label}"
            )
        raise InvalidAdditionalOptionsError(f"Код {item_label} {code!r} не найден")
