"""HTTP contract of ``/api/v1/fast-deals``.

Requests are strict (``extra="forbid"``): an unsupported field is an error, never
silently ignored or stored. Identifiers are UUIDs. Money in requests is a decimal
number or a decimal string; money in responses is always an exact decimal STRING with
kopeck precision (``"1250000.00"``), never a JSON float. Responses are documented
here; the routers return the JSON that the use cases build.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Phone = Annotated[str, StringConstraints(pattern=r"^\+7\d{10}$")]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Money = Annotated[Decimal, Field(max_digits=20, allow_inf_nan=False)]
Percent = Annotated[Decimal, Field(max_digits=7, allow_inf_nan=False)]
MoneyStr = str  # exact decimal string, e.g. "1250000.00"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- requests

class CompanyObject(BaseModel):
    """The company object received from ``CompanyAutocomplete`` ``@select``, unchanged.

    ``{ name, inn, kpp, ogrn, legal_address, manager_name, ... }``. Creating the
    company does not create a user, an account or any notification.
    """

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=500)
    inn: str = Field(min_length=10, max_length=12)
    full_name: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    legal_address: str | None = None
    actual_address: str | None = None
    phone: str | None = None
    email: str | None = None
    manager_name: str | None = None
    entity_type: str | None = None
    foundation_date: str | None = None
    employee_count: int | None = None
    business_activity: str | None = None
    website: str | None = None


class CreateFastDealBody(_Strict):
    """Create a draft. The direction follows the caller's role (dealer → DD, leasing → DL)."""

    company_id: UUID | None = Field(default=None, description="Существующая компания клиента")
    company: CompanyObject | None = Field(default=None, description="Выбранная компания целиком")
    client_phone: Phone = Field(description="Телефон клиента: +7XXXXXXXXXX")

    @model_validator(mode="after")
    def _exactly_one_company(self) -> CreateFastDealBody:
        if (self.company_id is None) == (self.company is None):
            raise ValueError("Передайте либо company_id, либо company")
        return self


class AddVehicleBody(_Strict):
    """A position: a catalog unit (``product``) or a manual one (``manual``).

    Product: ``product_id`` (+ ``vin`` for a listing without VIN or «под заказ»,
    + ``price`` for «цена по запросу»). Dealer manual (DD): directory chain
    ``category_id → mark_id → model_id → modification_id → trim_id`` or the text
    fallbacks ``mark_name`` / ``model_name``. Leasing manual (DL): text ``mark_name``,
    ``model_name``, ``modification_name``, ``vin``, ``body_color_name``, directory
    ``category_id`` and an explicit ``dealer_company_id``.
    """

    vehicle_source_type: Literal["product", "manual"]
    product_id: UUID | None = None
    vin: str | None = Field(default=None, max_length=32)
    price: Money | None = None
    category_id: UUID | None = None
    mark_id: UUID | None = None
    model_id: UUID | None = None
    modification_id: UUID | None = None
    trim_id: UUID | None = None
    mark_name: str | None = Field(default=None, max_length=255)
    model_name: str | None = Field(default=None, max_length=255)
    modification_name: str | None = Field(default=None, max_length=255)
    trim_name: str | None = Field(default=None, max_length=255)
    body_color_id: UUID | None = None
    body_color_name: str | None = Field(default=None, max_length=255)
    dealer_company_id: UUID | None = None


class PatchVehicleBody(_Strict):
    """Edit allowed fields of a position, or replace it (mutually exclusive).

    Catalog-derived values cannot be sent as trusted data; only the fields below.
    """

    vin: str | None = Field(default=None, max_length=32)
    price: Money | None = None
    category_id: UUID | None = None
    mark_id: UUID | None = None
    model_id: UUID | None = None
    modification_id: UUID | None = None
    trim_id: UUID | None = None
    mark_name: str | None = Field(default=None, max_length=255)
    model_name: str | None = Field(default=None, max_length=255)
    modification_name: str | None = Field(default=None, max_length=255)
    body_color_id: UUID | None = None
    body_color_name: str | None = Field(default=None, max_length=255)
    dealer_company_id: UUID | None = None
    replace_with: AddVehicleBody | None = None

    @model_validator(mode="after")
    def _replace_is_exclusive(self) -> PatchVehicleBody:
        others = self.model_dump(exclude={"replace_with"}, exclude_none=True)
        if self.replace_with is not None and others:
            raise ValueError("replace_with нельзя сочетать с другими полями")
        if self.replace_with is None and not others:
            raise ValueError("Не указано, что изменить")
        return self


class PriceAdjustmentBody(_Strict):
    """Discount (DD, DL) or markup (DL). ``type`` and ``amount`` both null clear it."""

    type: Literal["discount", "markup"] | None = None
    amount: Money | None = None

    @model_validator(mode="after")
    def _both_or_none(self) -> PriceAdjustmentBody:
        if (self.type is None) != (self.amount is None):
            raise ValueError("Укажите тип и размер корректировки либо очистите оба поля")
        return self


class OptionItem(_Strict):
    code: str = Field(min_length=1, max_length=64)
    price: Money = Field(default=Decimal(0))
    comment: str | None = Field(default=None, max_length=500)


class OptionsBody(_Strict):
    """The complete option set of a position; it replaces the previous one atomically."""

    equipments: list[OptionItem] = Field(default_factory=list, max_length=100)
    services: list[OptionItem] = Field(default_factory=list, max_length=100)
    purposes: list[str] = Field(default_factory=list, max_length=64, description="purpose_name")
    regions: list[str] = Field(default_factory=list, max_length=100, description="region_name")


class LeasingTermsBody(_Strict):
    """Leasing terms. The advance is given in rubles OR in percent, never both."""

    down_payment: Money | None = None
    down_payment_percent: Percent | None = None
    lease_term_months: int = Field(ge=12, le=84)
    monthly_payment: Money | None = Field(
        default=None, description="Ручной платёж; без него считается калькулятором"
    )
    buyout_amount: Money | None = None

    @model_validator(mode="after")
    def _one_advance_mode(self) -> LeasingTermsBody:
        if (self.down_payment is None) == (self.down_payment_percent is None):
            raise ValueError("Укажите аванс либо в рублях, либо в процентах")
        return self


class SendToLeasingCompaniesBody(_Strict):
    leasing_company_ids: list[UUID] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _unique(self) -> SendToLeasingCompaniesBody:
        if len(set(self.leasing_company_ids)) != len(self.leasing_company_ids):
            raise ValueError("Список лизинговых компаний не должен содержать повторов")
        return self


class OfferBody(_Strict):
    """Commercial proposal. Required: financing amount, advance, term, payment, cost."""

    financing_amount: Money
    down_payment: Money
    down_payment_percent: Percent | None = None
    lease_term_months: int = Field(ge=12, le=84)
    monthly_payment: Money
    total_cost: Money = Field(description="Стоимость договора")
    buyout_amount: Money | None = None
    rate: Percent | None = None
    markup: Money | None = Field(default=None, description="Удорожание")
    total_interest: Money | None = None
    vat_refund: Money | None = None
    profit_tax_savings: Money | None = None
    total_savings: Money | None = None
    optional_financial_terms: dict[str, str | int | None] = Field(default_factory=dict)
    pdf_file_id: UUID | None = Field(default=None, description="Ранее загруженный lc_offer_pdf")


class ReasonBody(_Strict):
    reason: Reason


class CancelBody(_Strict):
    reason: Comment | None = None


class ConfirmBody(_Strict):
    file_ids: list[UUID] = Field(default_factory=list, max_length=20)


class SendChangesBody(_Strict):
    comment: Comment | None = None


class ApplySupportProgramBody(_Strict):
    support_program_id: UUID


class SupportRequestBody(_Strict):
    amount: Money
    comment: Comment | None = None


class SupportDecisionBody(_Strict):
    """Distributor's decision: reject (``cancelled``), pre-approve or approve."""

    status: Literal["cancelled", "pre_approved", "approved"]
    decided_amount: Money | None = Field(
        default=None, description="Обязательна при approved; может отличаться от запрошенной"
    )
    comment: Comment | None = None

    @model_validator(mode="after")
    def _amount_for_approval(self) -> SupportDecisionBody:
        if self.status == "approved" and self.decided_amount is None:
            raise ValueError("Укажите согласованную сумму")
        return self


class AssigneesBody(_Strict):
    """Responsible employees of the caller's own party."""

    primary_user_id: UUID
    additional_user_id: UUID | None = None


# -------------------------------------------------------------------------- responses

class CompanyBrief(BaseModel):
    id: UUID
    name: str
    inn: str | None = None


class AssigneeOut(BaseModel):
    company_id: UUID
    user_id: UUID
    user_name: str | None = None
    role: Literal["primary", "additional"]


class VehicleOut(BaseModel):
    """A position. A leasing company receives an allow-listed subset (no support data)."""

    id: UUID
    position: int
    vehicle_source_type: Literal["product", "manual"]
    vin: str
    vin_entered_manually: bool
    mark_name: str
    model_name: str
    modification_name: str | None = None
    trim_name: str | None = None
    category_name: str | None = None
    body_color_name: str | None = None
    dealer_company_id: UUID | None = None
    final_price: MoneyStr
    equipments: list[dict[str, Any]] = Field(default_factory=list)
    services: list[dict[str, Any]] = Field(default_factory=list)
    purposes: list[Any] = Field(default_factory=list)
    regions: list[Any] = Field(default_factory=list)
    item_status: Literal["active", "removed", "replaced"]
    # Dealer / platform projection only:
    is_reservable: bool | None = None
    reserved: bool | None = None
    base_price: MoneyStr | None = None
    adjustment_type: Literal["discount", "markup"] | None = None
    adjustment_amount: MoneyStr | None = None
    options_amount: MoneyStr | None = None
    support_amount: MoneyStr | None = None
    unaccounted_support: MoneyStr | None = None
    applied_supports: list[dict[str, Any]] | None = None
    support_request: dict[str, Any] | None = None
    can_request_support: bool | None = None
    support_hint: str | None = None
    price_on_request: bool | None = None


class OfferOut(BaseModel):
    id: UUID
    financing_amount: MoneyStr
    down_payment: MoneyStr
    down_payment_percent: MoneyStr | None = None
    lease_term_months: int
    monthly_payment: MoneyStr
    total_cost: MoneyStr
    buyout_amount: MoneyStr
    rate: MoneyStr | None = None
    markup: MoneyStr | None = None
    total_interest: MoneyStr | None = None
    vat_refund: MoneyStr | None = None
    profit_tax_savings: MoneyStr | None = None
    total_savings: MoneyStr | None = None
    optional_financial_terms: dict[str, Any] = Field(default_factory=dict)
    pdf_file_id: UUID | None = None
    created_at: datetime


class LcApplicationOut(BaseModel):
    id: UUID
    leasing_company: CompanyBrief
    status: str
    offer: OfferOut | None = None
    rejection_reason: str | None = None
    selected: bool = False


class TermsOut(BaseModel):
    down_payment_mode: Literal["amount", "percent"] | None = None
    down_payment: MoneyStr | None = None
    down_payment_percent: MoneyStr | None = None
    lease_term_months: int | None = None
    monthly_payment: MoneyStr | None = None
    monthly_payment_is_manual: bool = False
    calculated_monthly_payment: MoneyStr | None = None
    buyout_amount: MoneyStr | None = None
    total_cost: MoneyStr | None = None


class FileOut(BaseModel):
    id: UUID
    kind: Literal["deal_main", "deal_additional", "lc_offer_pdf", "vehicle_offer"]
    filename: str
    content_type: str
    size_bytes: int
    fast_deal_vehicle_id: UUID | None = None
    addressee_company_id: UUID | None = None
    uploaded_by_company_id: UUID
    created_at: datetime


class HistoryOut(BaseModel):
    id: UUID
    event_type: str
    from_status: str | None = None
    to_status: str | None = None
    actor_name: str | None = None
    actor_company_name: str | None = None
    reason: str | None = None
    changes: dict[str, Any] | None = None
    created_at: datetime


class PendingChangeOut(BaseModel):
    """DL: a field changed by the dealer, before and after."""

    vehicle_id: UUID
    vin: str | None = None
    field: str
    before: Any = None
    after: Any = None


class FastDealCard(BaseModel):
    """Card of one deal as the caller may see it. ``etag`` also arrives as ``ETag``."""

    id: UUID
    display_number: str
    source_type: Literal["dealer_to_leasing", "leasing_to_dealer"]
    status: str
    version: int
    etag: str
    review_cycle: int
    group_id: UUID | None = None
    client: CompanyBrief
    client_phone: str
    initiator_company: CompanyBrief
    dealer_company: CompanyBrief | None = None
    leasing_company: CompanyBrief | None = None
    requested_terms: TermsOut
    final_terms: TermsOut | None = None
    vehicles_total: MoneyStr
    confirmed_amount: MoneyStr | None = None
    has_pending_changes: bool = False
    pending_changes: list[PendingChangeOut] = Field(default_factory=list)
    status_reason: str | None = None
    vehicles: list[VehicleOut]
    lc_applications: list[LcApplicationOut] = Field(default_factory=list)
    group_deals: list[dict[str, Any]] = Field(default_factory=list)
    files: list[FileOut] = Field(default_factory=list)
    assignees: list[AssigneeOut] = Field(default_factory=list)
    history: list[HistoryOut] = Field(default_factory=list)
    allowed_actions: list[str]
    party: Literal["initiator", "leasing", "dealer", "distributor", "platform"]
    sent_at: datetime | None = None
    confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class FastDealCardResponse(BaseModel):
    deal: FastDealCard


class FastDealListItem(BaseModel):
    id: UUID
    display_number: str
    source_type: Literal["dealer_to_leasing", "leasing_to_dealer"]
    status: str
    client: CompanyBrief
    initiator_company: CompanyBrief
    dealer_company: CompanyBrief | None = None
    leasing_company: CompanyBrief | None = None
    invited_lc_count: int = 0
    vehicle_count: int = 0
    vehicles_total: MoneyStr
    assignees: list[AssigneeOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    kind: Literal["fast_deal"] = "fast_deal"


class FastDealListResponse(BaseModel):
    items: list[FastDealListItem]
    total: int
    page: int
    page_size: int


class FilterOptionsResponse(BaseModel):
    clients: list[CompanyBrief]
    leasing_companies: list[CompanyBrief]
    dealers: list[CompanyBrief]


class VinLookupResponse(BaseModel):
    """Result of the VIN search in the actor's scope (own stock / all published)."""

    found: bool
    product: dict[str, Any] | None = None
    reserved: bool = False
    reason: str | None = None


class UploadFilesResponse(BaseModel):
    files: list[FileOut]
    deal: FastDealCard


class SendToDealersResponse(BaseModel):
    group_id: UUID
    deals: list[FastDealCard]


class SupportProgramOut(BaseModel):
    id: UUID
    name: str
    support_type: str
    support_amount: MoneyStr
    is_compatible: bool = True
    applied: bool = False
    starts_at: date | None = None
    ends_at: date | None = None


class SupportProgramsResponse(BaseModel):
    items: list[SupportProgramOut]
    support_hint: str | None = None


class AssignableEmployeesResponse(BaseModel):
    items: list[dict[str, Any]]


# ------------------------------------------------------------------------ wire encoding

_CENT = Decimal("0.01")


def _scalar_to_wire(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value.quantize(_CENT, rounding=ROUND_HALF_UP), "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def to_wire(value: Any) -> Any:
    """JSON-ready copy of a use-case result with EXACT money.

    ``jsonable_encoder`` would turn ``Decimal`` into a float; here every ``Decimal`` becomes
    a kopeck-precision string, ids become strings and timestamps ISO 8601.
    """
    if isinstance(value, Mapping):
        return {str(key): to_wire(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [to_wire(item) for item in value]
    return _scalar_to_wire(value)
