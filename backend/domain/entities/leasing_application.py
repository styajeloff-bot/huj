"""LeasingApplication aggregate root — simplified 3-status lifecycle.

Encapsulates the application status machine, ownership/role checks and
totals computation. Hydrated from a repository dict via ``from_dict``.

The set of allowed status transitions is the single source of truth — both
client-facing handlers and admin handlers go through
``ensure_can_change_status`` to mutate ``status``.

Status machine
--------------

The underlying PostgreSQL ``application_status`` enum (see
``infrastructure/models/enums.py``) defines: ``active``, ``rejected``,
``issued``.

::

    active ───► rejected
    active ───► issued
    rejected ──► active
    issued ────► rejected
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from decimal import Decimal
from typing import Any
from uuid import UUID

from domain.errors import (
    ApplicationNotEditableError,
    ApplicationNotOwnedError,
    DealerAssignmentNotAllowedError,
    EmployeeAssignmentNotAllowedError,
    InvalidStatusTransitionError,
)

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

STATUS_ACTIVE = "active"
STATUS_REJECTED = "rejected"
STATUS_ISSUED = "issued"

ALL_STATUSES: frozenset[str] = frozenset(
    {
        STATUS_ACTIVE,
        STATUS_REJECTED,
        STATUS_ISSUED,
    }
)

# Allowed transitions: current → set of legitimate next statuses.
_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_ACTIVE: frozenset({STATUS_REJECTED, STATUS_ISSUED}),
    STATUS_REJECTED: frozenset({STATUS_ACTIVE}),
    STATUS_ISSUED: frozenset({STATUS_REJECTED}),
}


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError, TypeError):
        return Decimal("0")


def _coerce_uuid(raw: Any) -> uuid.UUID:
    if raw is None:
        return uuid.uuid4()
    if isinstance(raw, uuid.UUID):
        return raw
    return uuid.UUID(str(raw))


def _coerce_created_by(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, uuid.UUID):
        return raw
    return uuid.UUID(str(raw))


def _coerce_field(key: str, raw: Any) -> Any:
    if key in {"total_amount", "down_payment", "monthly_payment"}:
        result: Any = _to_decimal(raw)
    elif key == "down_payment_percent":
        result = float(raw) if raw is not None else 0.0
    elif key in {"lease_term_months", "questionnaire_progress"}:
        result = int(raw) if raw is not None else 0
    elif key in {"selected_leasing_companies", "deal_documents"}:
        result = list(raw) if raw is not None else []
    elif key == "id":
        result = _coerce_uuid(raw)
    elif key == "display_number":
        result = str(raw) if raw is not None else None
    elif key in {"name", "email", "status", "current_stage"}:
        result = str(raw) if raw is not None else ""
    elif key in {
        "created_by",
        "dealer_company_id",
        "assigned_dealer_group_id",
        "dealer_assigned_by",
        "primary_employee_id",
        "additional_employee_id",
        "employees_assigned_by",
    }:
        result = _coerce_created_by(raw)
    else:
        result = raw
    return result


@dataclass
class LeasingApplication:
    """Aggregate root for a single leasing application."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    display_number: str | None = None
    company_id: UUID = field(default_factory=uuid.uuid4)
    dealer_company_id: UUID | None = None
    assigned_dealer_group_id: UUID | None = None
    dealer_assigned_by: UUID | None = None
    dealer_assigned_at: Any | None = None
    primary_employee_id: UUID | None = None
    additional_employee_id: UUID | None = None
    employees_assigned_by: UUID | None = None
    employees_assigned_at: Any | None = None
    name: str = ""
    email: str = ""
    status: str = STATUS_ACTIVE
    total_amount: Decimal = field(default_factory=lambda: Decimal("0"))
    down_payment: Decimal = field(default_factory=lambda: Decimal("0"))
    down_payment_percent: float = 0.0
    lease_term_months: int = 0
    monthly_payment: Decimal = field(default_factory=lambda: Decimal("0"))
    selected_leasing_companies: list[UUID] = field(default_factory=list)
    questionnaire_progress: int = 0
    current_stage: str = "leasing_companies"
    created_by: UUID | None = None
    deal_date: Any | None = None
    deal_documents: list[dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Hydration
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LeasingApplication:
        """Create an entity from a repo-shape dict (extra keys ignored)."""
        names = {f.name for f in fields(cls)}
        cleaned = {k: _coerce_field(k, v) for k, v in data.items() if k in names}
        return cls(**cleaned)

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    def _owned_by_dealer(self, user_id: UUID, company_id: UUID | None) -> bool:
        if self.dealer_company_id is not None and self.dealer_company_id == company_id:
            return True
        if company_id is not None and self.company_id == company_id:
            return True
        return self.created_by is not None and self.created_by == user_id

    def _owned_by_client(self, user_id: UUID, company_id: UUID | None) -> bool:
        if company_id is not None and self.company_id == company_id:
            return True
        return self.created_by is not None and self.created_by == user_id

    def ensure_owned_by(
        self,
        *,
        user_id: UUID,
        role: str,
        company_id: UUID | None = None,
        leasing_company_id: UUID | None = None,
    ) -> None:
        """Domain ownership / role check.

        - ``carcraft_employee`` sees everything.
        - ``leasing_company`` sees the application iff its company is in
          ``selected_leasing_companies``.
        - ``dealer`` sees the application iff they are the creator (or the
          application's company is theirs).
        - ``client`` sees the application iff they are the creator **or**
          its ``company_id`` matches their company.
        - ``distributor`` sees everything (read-only via scope).
        """
        if role in {"carcraft_employee", "distributor"}:
            return
        if role == "leasing_company":
            lc_id = leasing_company_id if leasing_company_id is not None else company_id
            if lc_id is not None and lc_id in self.selected_leasing_companies:
                return
            raise ApplicationNotOwnedError()
        if role == "dealer" and self._owned_by_dealer(user_id, company_id):
            return
        if role == "client" and self._owned_by_client(user_id, company_id):
            return
        raise ApplicationNotOwnedError()

    def ensure_can_assign_dealer(
        self,
        *,
        actor_role: str,
        actor_company_id: UUID | None,
        has_vehicle_on_actor_warehouse: bool,
    ) -> None:
        """Allow a distributor to assign or reassign a dealer.

        The current assignment is deliberately not a precondition: repeating
        the operation replaces it and is a successful domain action.
        """
        if actor_role != "distributor" or actor_company_id is None:
            raise ApplicationNotOwnedError(
                "Назначать дилера может только дистрибьютор своей компании"
            )
        if not has_vehicle_on_actor_warehouse:
            raise DealerAssignmentNotAllowedError(
                "В заявке нет автомобиля со склада текущего дистрибьютора"
            )

    def ensure_dealer_assignment_candidate(
        self,
        *,
        group_is_active: bool,
        dealer_is_active: bool,
        dealer_is_member: bool,
        dealer_company_type: str | None,
    ) -> None:
        """Validate the chosen group/member without performing I/O."""
        if not group_is_active:
            raise DealerAssignmentNotAllowedError(
                "Выбранная группа дилеров неактивна"
            )
        if dealer_company_type != "dealer":
            raise DealerAssignmentNotAllowedError(
                "Выбранная компания не является дилером"
            )
        if not dealer_is_active:
            raise DealerAssignmentNotAllowedError("Выбранный дилер неактивен")
        if not dealer_is_member:
            raise DealerAssignmentNotAllowedError(
                "Выбранный дилер не входит в группу"
            )

    def ensure_can_manage_employees(
        self,
        *,
        actor_role: str,
        actor_company_id: UUID | None,
        has_vehicle_on_actor_warehouse: bool = False,
    ) -> None:
        """Check role-specific access to application employee assignment."""
        if actor_role == "carcraft_employee":
            return
        if (
            actor_role == "dealer"
            and actor_company_id is not None
            and self.dealer_company_id == actor_company_id
        ):
            return
        if (
            actor_role == "distributor"
            and actor_company_id is not None
            and has_vehicle_on_actor_warehouse
        ):
            return
        raise ApplicationNotOwnedError(
            "Нет доступа к назначению сотрудников этой заявки"
        )

    def ensure_employee_is_assignable(
        self,
        *,
        employee_is_active_company_member: bool,
    ) -> None:
        """Validate a selected employee after repository membership lookup."""
        if not employee_is_active_company_member:
            raise EmployeeAssignmentNotAllowedError(
                "Сотрудник неактивен или не состоит в компании"
            )

    def ensure_employee_assignments_are_distinct(
        self,
        *,
        primary_employee_id: UUID | None,
        additional_employee_id: UUID | None,
    ) -> None:
        """Prevent one employee from occupying both application roles."""
        if (
            primary_employee_id is not None
            and primary_employee_id == additional_employee_id
        ):
            raise EmployeeAssignmentNotAllowedError(
                "Основной и дополнительный сотрудник должны быть разными"
            )

    # ------------------------------------------------------------------
    # Status guards
    # ------------------------------------------------------------------

    def ensure_can_change_status(self, new_status: str) -> None:
        """Validate a status transition.

        Raises:
            InvalidStatusTransitionError: If the transition is not allowed
                from ``self.status`` to ``new_status``.
        """
        if new_status not in ALL_STATUSES:
            raise InvalidStatusTransitionError(self.status, new_status)
        if new_status == self.status:
            # No-op: not a real transition; reject so callers handle it
            # explicitly rather than silently returning.
            raise InvalidStatusTransitionError(self.status, new_status)
        allowed = _TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            raise InvalidStatusTransitionError(self.status, new_status)

    def ensure_can_assign_vin(self) -> None:
        """VIN can only be assigned while the application is active.

        Used by the client-side VIN assignment flow. Admin assignment is a
        separate code path and bypasses this check.
        """
        if self.status != STATUS_ACTIVE:
            raise InvalidStatusTransitionError(
                self.status, "vin_assignment(требуется active)"
            )

    def ensure_editable(self, *, has_lc_children: bool) -> None:
        """Partial-update guard for checkout flow.

        Editing is allowed only while no admin has dispatched the application
        to LCs yet (no rows in ``leasing_company_applications`` for this
        parent). The parent status itself is no longer the gate — the presence
        of LC children is.
        """
        if has_lc_children:
            raise ApplicationNotEditableError(
                "Заявка уже отправлена в лизинговые компании"
            )

    # ------------------------------------------------------------------
    # Domain calculations
    # ------------------------------------------------------------------

    def compute_totals(
        self, vehicles: list[dict[str, Any]]
    ) -> dict[str, Decimal | int]:
        """Aggregate vehicle line totals (unit_price * quantity).

        Returns a dict with ``total_amount``, ``vehicles_count`` and
        ``positions_count``. Quantities default to 1 when missing or
        non-positive; prices to 0 when missing/invalid.
        """
        total = Decimal("0")
        vehicle_count = 0
        positions = 0
        for v in vehicles:
            qty_raw = v.get("quantity")
            try:
                qty = int(qty_raw) if qty_raw is not None else 1
            except (TypeError, ValueError):
                qty = 1
            qty = max(qty, 1)
            unit = _to_decimal(v.get("unit_price"))
            total += unit * Decimal(qty)
            vehicle_count += qty
            positions += 1
        return {
            "total_amount": total,
            "vehicles_count": vehicle_count,
            "positions_count": positions,
        }
