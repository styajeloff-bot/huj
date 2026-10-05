"""Compensation domain entity — business rules for support compensations."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from domain.errors import (
    CompensationDocumentsRequiredError,
    InvalidCompensationStatusError,
    InvalidCompensationValueError,
    TooManyCompensationsError,
    ZeroCalculationBaseError,
)
from domain.values import (
    CalculationBase,
    CompensationStatus,
    CompensationValueType,
    PayerType,
    PaymentSchedulePeriod,
    PaymentScheduleType,
    RecipientType,
)

MAX_COMPENSATIONS_PER_SUPPORT = 4


@dataclass
class Compensation:
    """Single compensation linked to an applied support."""

    compensation_id: UUID | None
    applied_support_id: UUID
    payer: PayerType
    recipient: RecipientType
    calculation_base: CalculationBase
    calculation_base_amount: Decimal
    value_type: CompensationValueType
    value: Decimal
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    min_percent: Decimal | None = None
    max_percent: Decimal | None = None
    amount: Decimal = Decimal(0)
    status: CompensationStatus = CompensationStatus.UNDER_REVIEW
    payment_schedule_type: PaymentScheduleType = PaymentScheduleType.DAYS_COUNT
    payment_schedule_period: PaymentSchedulePeriod | None = None
    payment_schedule_value: str | None = None
    due_date: _dt.date | None = None
    paid_at: _dt.datetime | None = None
    documents: list[dict] = field(default_factory=list)
    comment: str = ""
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None

    @classmethod
    def from_dict(cls, data: dict) -> Compensation:
        return cls(
            compensation_id=data.get("id") or data.get("compensation_id"),
            applied_support_id=data["applied_support_id"],
            payer=PayerType(data["payer"]),
            recipient=RecipientType(data["recipient"]),
            calculation_base=CalculationBase(data["calculation_base"]),
            calculation_base_amount=Decimal(str(data.get("calculation_base_amount", 0))),
            value_type=CompensationValueType(data["value_type"]),
            value=Decimal(str(data.get("value", 0))),
            min_amount=_to_decimal(data.get("min_amount")),
            max_amount=_to_decimal(data.get("max_amount")),
            min_percent=_to_decimal(data.get("min_percent")),
            max_percent=_to_decimal(data.get("max_percent")),
            amount=Decimal(str(data.get("amount", 0))),
            status=CompensationStatus(data.get("status", "under_review")),
            payment_schedule_type=PaymentScheduleType(
                data.get("payment_schedule_type", "days_count")
            ),
            payment_schedule_period=_to_schedule_period(
                data.get("payment_schedule_period")
            ),
            payment_schedule_value=data.get("payment_schedule_value"),
            due_date=_to_date(data.get("due_date")),
            paid_at=_to_datetime(data.get("paid_at")),
            documents=data.get("documents") or [],
            comment=data.get("comment", ""),
            created_at=_to_datetime(data.get("created_at")),
            updated_at=_to_datetime(data.get("updated_at")),
        )

    def compute_amount(self) -> None:
        """Calculate compensation amount based on value_type and constraints."""
        self.validate_amount_rules()

        base = self.calculation_base_amount
        if self.value_type == CompensationValueType.PERCENT:
            raw = base * self.value / Decimal(100)
            if self.min_amount is not None and raw < self.min_amount:
                raw = self.min_amount
            if self.max_amount is not None and raw > self.max_amount:
                raw = self.max_amount
        else:
            raw = self.value
            min_from_percent = (
                base * self.min_percent / Decimal(100)
                if self.min_percent is not None
                else None
            )
            max_from_percent = (
                base * self.max_percent / Decimal(100)
                if self.max_percent is not None
                else None
            )
            if min_from_percent is not None and raw < min_from_percent:
                raw = min_from_percent
            if max_from_percent is not None and raw > max_from_percent:
                raw = max_from_percent

        self.amount = raw.quantize(Decimal("1"))

    def compute_due_date(self, reference_date: _dt.date | None = None) -> None:
        """Calculate due_date from schedule type and value."""
        ref = reference_date or _dt.datetime.now(_dt.UTC).date()
        self._validate_schedule()

        if self.payment_schedule_type == PaymentScheduleType.FIXED_DATE:
            self.due_date = _dt.date.fromisoformat(str(self.payment_schedule_value))
        else:
            val = int(str(self.payment_schedule_value))

            if self.payment_schedule_type == PaymentScheduleType.DAYS_COUNT:
                self.due_date = ref + _dt.timedelta(days=val)
            elif self.payment_schedule_type == PaymentScheduleType.REPORTING_PERIOD:
                self.due_date = _period_due_date(
                    ref, val, self._resolved_schedule_period()
                )
            elif self.payment_schedule_type == PaymentScheduleType.WEEKLY:
                days_ahead = val - ref.isoweekday()
                if days_ahead <= 0:
                    days_ahead += 7
                self.due_date = ref + _dt.timedelta(days=days_ahead)
            else:
                next_quarter_start = _next_quarter_start(ref)
                next_next_quarter_start = _next_quarter_start(next_quarter_start)
                quarter_length = (next_next_quarter_start - next_quarter_start).days
                clamped_day = min(val, quarter_length)
                self.due_date = next_quarter_start + _dt.timedelta(days=clamped_day - 1)

    def mark_paid(
        self,
        *,
        documents: list[dict] | None = None,
        paid_at: _dt.datetime | None = None,
    ) -> None:
        if self.status not in (CompensationStatus.ACCEPTED, CompensationStatus.OVERDUE):
            raise InvalidCompensationStatusError(
                f"Невозможно отметить оплату: текущий статус '{self.status.value}'"
            )
        payload = documents if documents is not None else self.documents
        if not payload:
            raise CompensationDocumentsRequiredError()
        self.documents = payload
        self.status = CompensationStatus.PAID
        self.paid_at = paid_at or _dt.datetime.now(_dt.UTC)

    def accept(self, *, comment: str | None = None, documents: list[dict] | None = None) -> None:
        if self.status != CompensationStatus.UNDER_REVIEW:
            raise InvalidCompensationStatusError(
                f"Невозможно акцептовать: текущий статус '{self.status.value}'"
            )
        self.status = CompensationStatus.ACCEPTED
        if comment:
            self.comment = comment
        if documents is not None:
            self.documents = [*self.documents, *documents]

    def reject(self, *, comment: str | None = None, documents: list[dict] | None = None) -> None:
        if self.status != CompensationStatus.UNDER_REVIEW:
            raise InvalidCompensationStatusError(
                f"Невозможно отказать: текущий статус '{self.status.value}'"
            )
        self.status = CompensationStatus.REJECTED
        if comment:
            self.comment = comment
        if documents is not None:
            self.documents = [*self.documents, *documents]

    def mark_overdue(self) -> None:
        if self.status != CompensationStatus.ACCEPTED:
            raise InvalidCompensationStatusError(
                f"Невозможно перевести в просрочку: текущий статус '{self.status.value}'"
            )
        self.status = CompensationStatus.OVERDUE

    def cancel(self) -> None:
        if self.status not in (
            CompensationStatus.UNDER_REVIEW,
            CompensationStatus.ACCEPTED,
            CompensationStatus.OVERDUE,
        ):
            raise InvalidCompensationStatusError(
                f"Невозможно отменить: текущий статус '{self.status.value}'"
            )
        self.status = CompensationStatus.CANCELLED

    @property
    def is_overdue_eligible(self) -> bool:
        return (
            self.status == CompensationStatus.ACCEPTED
            and self.due_date is not None
            and self.due_date <= _dt.datetime.now(_dt.UTC).date()
        )

    @staticmethod
    def validate_count(existing_count: int) -> None:
        if existing_count >= MAX_COMPENSATIONS_PER_SUPPORT:
            raise TooManyCompensationsError()

    def validate_amount_rules(self) -> None:
        if self.calculation_base_amount <= 0:
            raise ZeroCalculationBaseError()
        if self.value <= 0:
            raise InvalidCompensationValueError(
                "Значение компенсации должно быть больше нуля"
            )

        if self.value_type == CompensationValueType.PERCENT:
            if self.min_percent is not None or self.max_percent is not None:
                raise InvalidCompensationValueError(
                    "Ограничения в процентах недоступны для value_type=percent"
                )
            _validate_bounds(
                self.min_amount,
                self.max_amount,
                "Минимальная сумма не может быть больше максимальной",
            )
            return

        if self.min_amount is not None or self.max_amount is not None:
            raise InvalidCompensationValueError(
                "Ограничения в рублях недоступны для value_type=sum"
            )
        _validate_bounds(
            self.min_percent,
            self.max_percent,
            "Минимальный процент не может быть больше максимального",
        )

    def _validate_schedule(self) -> None:
        if self.payment_schedule_type == PaymentScheduleType.FIXED_DATE:
            if not self.payment_schedule_value:
                raise InvalidCompensationValueError(
                    "Для fixed_date требуется дата оплаты"
                )
            try:
                _dt.date.fromisoformat(str(self.payment_schedule_value))
            except ValueError as exc:
                raise InvalidCompensationValueError(
                    "Некорректная дата для fixed_date"
                ) from exc
            return

        if self.payment_schedule_value is None:
            raise InvalidCompensationValueError(
                "Для выбранного графика оплаты требуется значение"
            )

        try:
            value = int(str(self.payment_schedule_value))
        except ValueError as exc:
            raise InvalidCompensationValueError(
                "Значение графика оплаты должно быть целым числом"
            ) from exc

        if value <= 0:
            raise InvalidCompensationValueError(
                "Значение графика оплаты должно быть больше нуля"
            )
        if self.payment_schedule_type == PaymentScheduleType.WEEKLY:
            _validate_schedule_day(value, 7, "Для weekly день недели")
        elif self.payment_schedule_type == PaymentScheduleType.REPORTING_PERIOD:
            self._validate_reporting_period_value(value)
        elif self.payment_schedule_type == PaymentScheduleType.QUARTERLY:
            _validate_schedule_day(value, 92, "Для quarterly день квартала")

    def _validate_reporting_period_value(self, value: int) -> None:
        period = self._resolved_schedule_period()
        max_day = _schedule_period_max_day(period)
        _validate_schedule_day(value, max_day, f"Для периода {period.value} день")

    def _resolved_schedule_period(self) -> PaymentSchedulePeriod:
        if self.payment_schedule_period is not None:
            return self.payment_schedule_period
        return PaymentSchedulePeriod.MONTH


def _next_quarter_start(reference: _dt.date) -> _dt.date:
    current_quarter_start_month = ((reference.month - 1) // 3) * 3 + 1
    next_quarter_month = current_quarter_start_month + 3
    year = reference.year
    if next_quarter_month > 12:
        next_quarter_month -= 12
        year += 1
    return _dt.date(year, next_quarter_month, 1)


def _period_due_date(
    reference: _dt.date, day: int, period: PaymentSchedulePeriod
) -> _dt.date:
    if period == PaymentSchedulePeriod.WEEK:
        days_ahead = day - reference.isoweekday()
        if days_ahead <= 0:
            days_ahead += 7
        return reference + _dt.timedelta(days=days_ahead)

    period_start = _next_period_start(reference, period)
    next_period_start = _add_period(period_start, period)
    period_length = (next_period_start - period_start).days
    return period_start + _dt.timedelta(days=min(day, period_length) - 1)


def _next_period_start(
    reference: _dt.date, period: PaymentSchedulePeriod
) -> _dt.date:
    if period == PaymentSchedulePeriod.MONTH:
        return _add_months(_dt.date(reference.year, reference.month, 1), 1)
    if period == PaymentSchedulePeriod.TWO_MONTHS:
        start_month = ((reference.month - 1) // 2) * 2 + 1
        return _add_months(_dt.date(reference.year, start_month, 1), 2)
    if period == PaymentSchedulePeriod.QUARTER:
        return _next_quarter_start(reference)
    if period == PaymentSchedulePeriod.HALF_YEAR:
        start_month = 1 if reference.month <= 6 else 7
        return _add_months(_dt.date(reference.year, start_month, 1), 6)
    if period == PaymentSchedulePeriod.YEAR:
        return _dt.date(reference.year + 1, 1, 1)
    raise InvalidCompensationValueError("Некорректный период графика оплаты")


def _add_period(start: _dt.date, period: PaymentSchedulePeriod) -> _dt.date:
    month_counts = {
        PaymentSchedulePeriod.MONTH: 1,
        PaymentSchedulePeriod.TWO_MONTHS: 2,
        PaymentSchedulePeriod.QUARTER: 3,
        PaymentSchedulePeriod.HALF_YEAR: 6,
        PaymentSchedulePeriod.YEAR: 12,
    }
    months = month_counts.get(period)
    if months is None:
        return start + _dt.timedelta(days=7)
    return _add_months(start, months)


def _add_months(reference: _dt.date, months: int) -> _dt.date:
    month = reference.month + months
    year = reference.year
    while month > 12:
        month -= 12
        year += 1
    return _dt.date(year, month, 1)


def _schedule_period_max_day(period: PaymentSchedulePeriod) -> int:
    return {
        PaymentSchedulePeriod.WEEK: 7,
        PaymentSchedulePeriod.MONTH: 31,
        PaymentSchedulePeriod.TWO_MONTHS: 62,
        PaymentSchedulePeriod.QUARTER: 92,
        PaymentSchedulePeriod.HALF_YEAR: 184,
        PaymentSchedulePeriod.YEAR: 366,
    }[period]


def _validate_bounds(
    minimum: Decimal | None,
    maximum: Decimal | None,
    message: str,
) -> None:
    if minimum is not None and minimum < 0:
        raise InvalidCompensationValueError(
            "Минимальное ограничение не может быть отрицательным"
        )
    if maximum is not None and maximum < 0:
        raise InvalidCompensationValueError(
            "Максимальное ограничение не может быть отрицательным"
        )
    if minimum is not None and maximum is not None and minimum > maximum:
        raise InvalidCompensationValueError(message)


def _validate_schedule_day(value: int, max_day: int, label: str) -> None:
    if not 1 <= value <= max_day:
        raise InvalidCompensationValueError(
            f"{label} должен быть в диапазоне 1-{max_day}"
        )


def _to_decimal(value: object | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _to_date(value: object | None) -> _dt.date | None:
    if value is None or isinstance(value, _dt.date):
        return value
    return _dt.date.fromisoformat(str(value))


def _to_schedule_period(value: object | None) -> PaymentSchedulePeriod | None:
    if value is None or value == "":
        return None
    return PaymentSchedulePeriod(str(value))


def _to_datetime(value: object | None) -> _dt.datetime | None:
    if value is None or isinstance(value, _dt.datetime):
        return value
    return _dt.datetime.fromisoformat(str(value))
