"""Domain value objects — enums, constants and immutable data shapes."""
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class CompanyInfo:
    """Normalized external-company data — provider-agnostic.

    Returned by `CompanyLookupProvider` implementations. The HTTP layer
    serializes this directly, so no provider-specific fields leak out.
    """

    name: str
    full_name: str | None
    inn: str | None
    kpp: str | None
    ogrn: str | None
    legal_address: str | None
    actual_address: str | None
    phone: str | None
    email: str | None
    foundation_date: str | None
    employee_count: int | None
    business_activity: str | None
    manager_name: str | None
    entity_type: str | None  # "LEGAL" | "INDIVIDUAL"


class OrderStatus(str, Enum):
    RESERVED = "reserved"
    PURCHASED = "purchased"
    CANCELLATION_REQUESTED = "cancellation_requested"
    CANCELLED = "cancelled"
    LEASING_ACTIVE = "leasing_active"
    LEASING_PENDING = "leasing_pending"


class PurchaseType(str, Enum):
    RESERVATION = "reservation"
    FULL_PURCHASE = "full_purchase"


class PaymentStatus(str, Enum):
    PENDING = "pending_payment"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PaymentType(str, Enum):
    RESERVATION = "reservation"
    FULL_PURCHASE = "full_purchase"
    REMAINING_BALANCE = "remaining_balance"
    LEASING_MONTHLY = "leasing_monthly"


class PaymentMethod(str, Enum):
    CARD = "card"
    SBP = "sbp"
    BANK_TRANSFER = "bank_transfer"


class VehicleStatus(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"


class ApplicationVehicleStatus(str, Enum):
    PENDING_CONFIRMATION = "active"
    NOT_CONFIRMED = "not_confirmed"
    CONFIRMED = "confirmed"
    REPLACEMENT = "replacement"


class WarehouseStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class WarehouseAccessType(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class WarehouseOwnerType(str, Enum):
    DEALER = "dealer"
    DISTRIBUTOR = "distributor"


class SpecialEquipmentPublicationStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class SpecialEquipmentSaleStatus(str, Enum):
    AVAILABLE = "available"
    ON_ORDER = "on_order"
    RESERVED = "reserved"
    SOLD = "sold"
    UNAVAILABLE = "unavailable"


class IdentityVerificationStatus(str, Enum):
    PENDING = "pending"
    SMS_REQUESTED = "sms_requested"
    SMS_VERIFIED = "sms_verified"
    VERIFIED = "verified"
    DATA_RECEIVED = "data_received"
    FAILED = "failed"
    EXPIRED = "expired"


class CompensationStatus(str, Enum):
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class PayerType(str, Enum):
    DISTRIBUTOR = "distributor"
    DEALER = "dealer"
    CARCRAFT = "carcraft"
    MINPROMTORG = "minpromtorg"
    CLIENT = "client"


class RecipientType(str, Enum):
    LEASING_COMPANY = "leasing_company"
    DEALER = "dealer"
    CARCRAFT = "carcraft"
    CLIENT = "client"


class CalculationBase(str, Enum):
    BASE_PRICE = "base_price"
    SPECIAL_PRICE = "special_price"
    DEALER_COST = "dealer_cost"
    APPLICATION_PRICE = "application_price"
    DOWN_PAYMENT = "down_payment"
    SUPPORT_AMOUNT = "support_amount"


class CompensationValueType(str, Enum):
    PERCENT = "percent"
    SUM = "sum"


class PaymentScheduleType(str, Enum):
    FIXED_DATE = "fixed_date"
    DAYS_COUNT = "days_count"
    WEEKLY = "weekly"
    QUARTERLY = "quarterly"
    REPORTING_PERIOD = "reporting_period"


class PaymentSchedulePeriod(str, Enum):
    WEEK = "week"
    MONTH = "month"
    TWO_MONTHS = "two_months"
    QUARTER = "quarter"
    HALF_YEAR = "half_year"
    YEAR = "year"
