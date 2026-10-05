"""LeasingProposal aggregate — a single commercial proposal (КП) issued
by a leasing company in response to a leasing application.

Two named slots per LCA: ``preliminary`` (editable until decision submit)
and ``final`` (final terms, locked together with the rest of the response
when ``submitted_at`` is stamped). The set of fields mirrors
LeasingApplication's parameters one-to-one — values come straight from
the cart's leasing calculator, but the LC may also override individual
fields manually.

A proposal is "complete" only when every required parameter is filled;
this gate is read by the application-layer submit guard to enforce the
"Approve requires a complete proposal" rule.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from domain.errors import (
    DomainError,
    LeasingProposalAlreadyDecidedError,
    LeasingProposalNotSubmittedError,
)

KIND_PRELIMINARY = "preliminary"
KIND_FINAL = "final"
ALL_KINDS: frozenset[str] = frozenset({KIND_PRELIMINARY, KIND_FINAL})

CLIENT_DECISION_ACCEPTED = "accepted"
CLIENT_DECISION_REJECTED = "rejected"
# "cancelled" is a client action, not a stored decision: it clears the
# previously recorded "accepted" decision instead of being persisted, so
# it is intentionally NOT part of ALL_CLIENT_DECISIONS.
CLIENT_DECISION_CANCELLED = "cancelled"
ALL_CLIENT_DECISIONS: frozenset[str] = frozenset(
    {CLIENT_DECISION_ACCEPTED, CLIENT_DECISION_REJECTED}
)


# Parameter fields mirror LeasingApplication. All numeric fields default
# to None on the entity so we can clearly distinguish "not yet entered"
# from "entered as zero".
_REQUIRED_FOR_COMPLETE: tuple[str, ...] = (
    "total_amount",
    "down_payment",
    "down_payment_percent",
    "lease_term_months",
    "monthly_payment",
)


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError, TypeError):
        return None


@dataclass
class LeasingProposal:
    """Aggregate for a single КП (commercial proposal) under an LCA."""

    id: UUID = field(default_factory=uuid.uuid4)
    leasing_company_application_id: UUID = field(default_factory=uuid.uuid4)
    kind: str = KIND_PRELIMINARY
    position: int = 1
    total_amount: Decimal | None = None
    down_payment: Decimal | None = None
    down_payment_percent: Decimal | None = None
    lease_term_months: int | None = None
    monthly_payment: Decimal | None = None
    total_cost: Decimal | None = None
    markup: Decimal | None = None
    rate: Decimal | None = None
    total_interest: Decimal | None = None
    buyout_amount: Decimal | None = field(default_factory=lambda: Decimal("0"))
    vat_refund: Decimal | None = None
    profit_tax_savings: Decimal | None = None
    total_savings: Decimal | None = None
    client_decision_action: str | None = None
    client_decision_at: datetime | None = None
    client_decision_comment: str | None = None
    submitted_at: datetime | None = None
    pdf_s3_key: str | None = None
    pdf_file_name: str | None = None
    pdf_size: int | None = None
    pdf_uploaded_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LeasingProposal:
        names = {f.name for f in fields(cls)}
        cleaned: dict[str, Any] = {}
        for key, raw in data.items():
            if key not in names:
                continue
            if key in {"id", "leasing_company_application_id"}:
                if isinstance(raw, uuid.UUID):
                    cleaned[key] = raw
                elif isinstance(raw, str):
                    cleaned[key] = uuid.UUID(raw)
                else:
                    raise TypeError(f"{key} must be a UUID")
            elif key == "position":
                cleaned[key] = int(raw) if raw is not None else 1
            elif key == "kind":
                cleaned[key] = str(raw) if raw else KIND_PRELIMINARY
            elif key in {"lease_term_months", "pdf_size"}:
                cleaned[key] = int(raw) if raw is not None else None
            elif key in {"client_decision_at", "submitted_at", "pdf_uploaded_at"}:
                cleaned[key] = raw if isinstance(raw, datetime) else None
            elif key in {"client_decision_action", "client_decision_comment", "pdf_s3_key", "pdf_file_name"}:
                cleaned[key] = (
                    str(raw) if raw is not None else None
                )
            else:
                cleaned[key] = _to_decimal(raw)
        return cls(**cleaned)

    @classmethod
    def from_application_defaults(
        cls,
        *,
        leasing_company_application_id: UUID,
        kind: str,
        application: dict[str, Any],
    ) -> LeasingProposal:
        """Pre-fill a proposal from the parent LeasingApplication.

        Used when the LC opens the response form — the calculator on the
        right side starts from the client's requested values, which the
        LC then adjusts.
        """
        return cls(
            leasing_company_application_id=leasing_company_application_id,
            kind=kind,
            total_amount=_to_decimal(application.get("total_amount")),
            down_payment=_to_decimal(application.get("down_payment")),
            down_payment_percent=_to_decimal(
                application.get("down_payment_percent")
            ),
            lease_term_months=int(application["lease_term_months"])
            if application.get("lease_term_months") is not None
            else None,
            monthly_payment=_to_decimal(application.get("monthly_payment")),
            total_cost=_to_decimal(application.get("total_cost")),
            markup=_to_decimal(application.get("markup")),
            rate=_to_decimal(application.get("rate")),
            total_interest=_to_decimal(application.get("total_interest")),
            buyout_amount=_to_decimal(application.get("buyout_amount"))
            or Decimal("0"),
            vat_refund=_to_decimal(application.get("vat_refund")),
            profit_tax_savings=_to_decimal(
                application.get("profit_tax_savings")
            ),
            total_savings=_to_decimal(application.get("total_savings")),
        )

    def is_complete(self) -> bool:
        """All parameters required to consider this КП ready to submit."""
        for name in _REQUIRED_FOR_COMPLETE:
            value = getattr(self, name)
            if value is None:
                return False
        return True

    def has_client_decision(self) -> bool:
        return self.client_decision_action is not None

    def ensure_client_can_decide(self) -> None:
        """Guard for client accept / reject calls.

        The proposal must have been submitted by the LC (so the client can
        actually see it) and must not already carry a client decision. The
        server still validates LC ownership / application access at the
        handler layer before invoking this method.
        """
        if not self.is_complete():
            # If the proposal isn't complete we shouldn't be exposing it to
            # the client in the first place — refuse defensively.
            raise LeasingProposalNotSubmittedError()
        if self.has_client_decision():
            raise LeasingProposalAlreadyDecidedError()

    @staticmethod
    def normalize_client_decision(action: str) -> str:
        normalized = (action or "").lower().strip()
        if normalized not in ALL_CLIENT_DECISIONS:
            raise DomainError(
                f"Неизвестное решение клиента: {action!r}"
            )
        return normalized

    def ensure_client_can_cancel(self) -> None:
        """Отменить можно только ранее принятое КП (accepted)."""
        if self.client_decision_action != CLIENT_DECISION_ACCEPTED:
            raise DomainError(
                "Отменить можно только принятое КП"
            )

    def to_storage_dict(self) -> dict[str, Any]:
        """Serialise to a repo-shape dict (Decimals stay as Decimals)."""
        return {
            "leasing_company_application_id": self.leasing_company_application_id,
            "kind": self.kind,
            "position": self.position,
            "total_amount": self.total_amount,
            "down_payment": self.down_payment,
            "down_payment_percent": self.down_payment_percent,
            "lease_term_months": self.lease_term_months,
            "monthly_payment": self.monthly_payment,
            "total_cost": self.total_cost,
            "markup": self.markup,
            "rate": self.rate,
            "total_interest": self.total_interest,
            "buyout_amount": self.buyout_amount,
            "vat_refund": self.vat_refund,
            "profit_tax_savings": self.profit_tax_savings,
            "total_savings": self.total_savings,
            "pdf_s3_key": self.pdf_s3_key,
            "pdf_file_name": self.pdf_file_name,
            "pdf_size": self.pdf_size,
            "pdf_uploaded_at": self.pdf_uploaded_at,
        }
