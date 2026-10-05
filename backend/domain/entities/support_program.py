"""Support program domain entity — admin-side support programs."""

from __future__ import annotations

import datetime as _dt
from collections.abc import Mapping, Set
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from domain.errors import InvalidSupportProgramError

_ALLOWED_SUPPORT_TYPES: frozenset[str] = frozenset(
    {
        "down_payment_compensation",
        "vehicle_discount_dealer_compensation",
        "vehicle_discount_dealer_invoice",
        "leasing_interest_compensation",
    }
)


@dataclass
class SupportProgram:
    """Aggregate root for an admin-created support program."""

    program_id: UUID | None
    name: str
    mark_id: UUID | str | None
    support_type: str
    support_params: dict[str, Any] = field(default_factory=dict)
    mark_ids: list[Any] = field(default_factory=list)
    model_id: UUID | str | None = None
    model_ids: list[Any] | None = None
    complectation_ids: list[str] | None = None
    vin: str | None = None
    vins: list[str] | None = None
    dealer_group_id: UUID | None = None
    dealer_group_ids: list[UUID] = field(default_factory=list)
    distributor_id: UUID | None = None
    distributor_ids: list[UUID] = field(default_factory=list)
    leasing_company_ids: list[UUID] = field(default_factory=list)
    production_year_from: int | None = None
    production_year_to: int | None = None
    production_date_from: _dt.date | None = None
    production_date_to: _dt.date | None = None
    delivery_date_from: _dt.date | None = None
    delivery_date_to: _dt.date | None = None
    starts_at: _dt.date | None = None
    ends_at: _dt.date | None = None
    is_active: bool = False
    is_compatible: bool = False
    compatible_support_ids: list[UUID] = field(default_factory=list)
    show_to_leasing_company: bool = True
    show_to_client: bool = True
    comment: str | None = None
    created_by: UUID | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SupportProgram:
        return cls(
            program_id=data.get("id") or data.get("program_id"),
            name=data["name"],
            mark_id=data["mark_id"],
            mark_ids=list(
                data.get("mark_ids")
                or ([] if not data.get("mark_id") else [data["mark_id"]])
            ),
            support_type=data["support_type"],
            support_params=data.get("support_params") or {},
            model_id=data.get("model_id"),
            model_ids=data.get("model_ids"),
            complectation_ids=data.get("complectation_ids"),
            vin=data.get("vin"),
            vins=data.get("vins"),
            dealer_group_id=data.get("dealer_group_id"),
            dealer_group_ids=list(data.get("dealer_group_ids") or []),
            distributor_id=data.get("distributor_id"),
            distributor_ids=list(
                data.get("distributor_ids")
                or (
                    []
                    if data.get("distributor_id") is None
                    else [data["distributor_id"]]
                )
            ),
            leasing_company_ids=list(data.get("leasing_company_ids") or []),
            production_year_from=data.get("production_year_from"),
            production_year_to=data.get("production_year_to"),
            production_date_from=_to_date(data.get("production_date_from")),
            production_date_to=_to_date(data.get("production_date_to")),
            delivery_date_from=_to_date(data.get("delivery_date_from")),
            delivery_date_to=_to_date(data.get("delivery_date_to")),
            starts_at=_to_date(data.get("starts_at")),
            ends_at=_to_date(data.get("ends_at")),
            is_active=bool(data.get("is_active", False)),
            is_compatible=bool(data.get("is_compatible", False)),
            compatible_support_ids=list(data.get("compatible_support_ids") or []),
            show_to_leasing_company=bool(data.get("show_to_leasing_company", True)),
            show_to_client=bool(data.get("show_to_client", True)),
            comment=_normalize_comment(data.get("comment")),
            created_by=data.get("created_by"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    def ensure_valid(self) -> None:
        """Validate cross-field invariants. Raises InvalidSupportProgramError."""
        name = (self.name or "").strip()
        if not name:
            raise InvalidSupportProgramError("Название программы обязательно")
        self.name = name

        if not self.mark_ids and self.mark_id:
            self.mark_ids = [self.mark_id]
        self.mark_ids = [
            str(mark).strip() for mark in self.mark_ids if str(mark).strip()
        ]
        self.mark_id = self.mark_ids[0] if self.mark_ids else self.mark_id

        if not self.mark_ids and not str(self.mark_id or "").strip():
            raise InvalidSupportProgramError("Марка обязательна")

        if not self.distributor_ids and self.distributor_id is not None:
            self.distributor_ids = [self.distributor_id]
        if not self.distributor_ids:
            raise InvalidSupportProgramError("Дистрибьютор обязателен")
        if len(self.distributor_ids) > 1:
            raise InvalidSupportProgramError(
                "Можно выбрать только одного дистрибьютора"
            )
        self.distributor_id = self.distributor_ids[0]

        if self.support_type not in _ALLOWED_SUPPORT_TYPES:
            raise InvalidSupportProgramError(
                f"Недопустимый тип программы: {self.support_type}"
            )

        if not isinstance(self.support_params, dict):
            raise InvalidSupportProgramError("support_params должен быть объектом")
        self.support_params = _clean_support_params(self.support_params)

        self.compatible_support_ids = list(
            dict.fromkeys(self.compatible_support_ids)
        )
        if self.program_id is not None and self.program_id in self.compatible_support_ids:
            raise InvalidSupportProgramError(
                "Программа поддержки не может быть совместима сама с собой"
            )
        if not self.is_compatible and self.compatible_support_ids:
            raise InvalidSupportProgramError(
                "Чтобы выбрать совместимые программы, включите признак совместимости"
            )

        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.starts_at > self.ends_at
        ):
            raise InvalidSupportProgramError(
                "Дата начала не может быть позже даты окончания"
            )

        if (
            self.production_year_from is not None
            and self.production_year_to is not None
            and self.production_year_from > self.production_year_to
        ):
            raise InvalidSupportProgramError(
                "Год выпуска: from не может быть больше to"
            )

        _ensure_date_range(
            self.production_date_from,
            self.production_date_to,
            "Дата окончания производства не может быть раньше даты начала",
        )
        _ensure_date_range(
            self.delivery_date_from,
            self.delivery_date_to,
            "Дата окончания поставки не может быть раньше даты начала",
        )

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True

    def to_persistence_dict(self) -> dict[str, Any]:
        """Return data ready to be inserted/updated by the repository."""
        return {
            "name": self.name,
            "mark_id": self.mark_id,
            "mark_ids": self.mark_ids,
            "model_id": self.model_id,
            "model_ids": self.model_ids,
            "complectation_ids": self.complectation_ids,
            "vin": self.vin,
            "vins": self.vins,
            "dealer_group_id": self.dealer_group_id,
            "distributor_id": self.distributor_id,
            "distributor_ids": self.distributor_ids,
            "support_type": self.support_type,
            "support_params": _clean_support_params(self.support_params),
            "production_year_from": self.production_year_from,
            "production_year_to": self.production_year_to,
            "production_date_from": self.production_date_from,
            "production_date_to": self.production_date_to,
            "delivery_date_from": self.delivery_date_from,
            "delivery_date_to": self.delivery_date_to,
            "starts_at": self.starts_at,
            "ends_at": self.ends_at,
            "is_active": self.is_active,
            "is_compatible": self.is_compatible,
            "show_to_leasing_company": self.show_to_leasing_company,
            "show_to_client": self.show_to_client,
            "comment": self.comment,
            "created_by": self.created_by,
        }


def are_support_programs_pairwise_compatible(
    program_ids: list[UUID],
    compatibility_flags: Mapping[UUID, bool],
    compatibility_by_program_id: Mapping[UUID, Set[UUID]],
) -> bool:
    """Return whether every distinct pair in the selection is compatible."""
    unique_program_ids = list(dict.fromkeys(program_ids))
    if len(unique_program_ids) < 2:
        return True
    if any(
        not compatibility_flags.get(program_id, False)
        for program_id in unique_program_ids
    ):
        return False
    for index, program_id in enumerate(unique_program_ids):
        compatible_ids = compatibility_by_program_id.get(program_id, frozenset())
        if any(
            candidate_id not in compatible_ids
            for candidate_id in unique_program_ids[index + 1 :]
        ):
            return False
    return True


def _to_date(value: Any) -> _dt.date | None:
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, str) and value:
        try:
            return _dt.date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _normalize_comment(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _ensure_date_range(
    date_from: _dt.date | None,
    date_to: _dt.date | None,
    message: str,
) -> None:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise InvalidSupportProgramError(message)


def _clean_support_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}
