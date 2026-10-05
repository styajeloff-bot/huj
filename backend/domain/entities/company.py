"""Company domain entity.

Invariants:
  * Profile is owned by the company itself; access is granted to:
      - users with the ``carcraft_employee`` role,
      - users linked to this company via ``users.company_id``,
      - users linked to this company via the ``user_companies`` join.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from typing import Any
from uuid import UUID

from domain.errors import CompanyAccessDeniedError

CARCRAFT_EMPLOYEE_ROLE = "carcraft_employee"


@dataclass
class Company:
    """Aggregate root for the company profile.

    Field set mirrors the ``companies`` table (post-010 schema, with the
    enrichment columns flattened in). JSONB columns (``legal_address_details``,
    ``founders``, ``additional_okved_list``) are passed through as-is — the
    presentation layer is responsible for their final shape.
    """

    id: UUID = field(default_factory=uuid.uuid4)
    name: str = ""
    inn: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    company_type: str = ""
    legal_address: str | None = None
    actual_address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    is_active: bool | None = None
    full_name: str | None = None
    short_name: str | None = None
    okpo: str | None = None
    okato: str | None = None
    legal_form: str | None = None
    region: str | None = None
    city: str | None = None
    legal_address_details: dict[str, Any] | None = None
    registration_date: date | None = None
    registration_department: str | None = None
    employees_count: int | None = None
    main_okved_code: str | None = None
    main_okved_description: str | None = None
    additional_okved_code: str | None = None
    additional_okved_description: str | None = None
    additional_okved_list: list[dict[str, Any]] | dict[str, Any] | None = None
    director_full_name: str | None = None
    director_position: str | None = None
    director_inn: str | None = None
    founders: list[dict[str, Any]] | dict[str, Any] | None = None
    bank_bik: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    authorized_capital: int | None = None
    net_profit: int | None = None
    reporting_year: int | None = None
    enrichment_status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Company:
        """Hydrate from a repository dict, ignoring unknown keys."""
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})

    def ensure_owned_by(
        self,
        *,
        user_id: UUID,
        user_role: str | None,
        user_company_id: UUID | None,
        user_company_ids: Iterable[UUID] | None = None,
    ) -> None:
        """Raise CompanyAccessDeniedError if the caller cannot view this company.

        Access is granted when:
          - the caller has role ``carcraft_employee``;
          - ``users.company_id`` matches this company's id;
          - this company's id appears in ``user_company_ids`` (join table).

        ``user_id`` is included for symmetry with other entities; it is not
        used in the check itself but documents that the rule is per-caller.
        """
        del user_id  # documented but unused — owner check is via company id
        if user_role == CARCRAFT_EMPLOYEE_ROLE:
            return
        if user_company_id is not None and user_company_id == self.id:
            return
        if user_company_ids is not None and self.id in set(user_company_ids):
            return
        raise CompanyAccessDeniedError()
