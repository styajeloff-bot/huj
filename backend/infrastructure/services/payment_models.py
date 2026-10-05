"""Typed payment gateway payloads and internal DTOs."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _format_amount(value: Decimal | float | int | str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    amount = f"{float(value):.2f}"
    return amount.rstrip("0").rstrip(".")


class ModulbankPaymentRequest(BaseModel):
    """Validated payload for the hosted ModulBank payment form."""

    merchant: str = Field(min_length=1, max_length=128)
    amount: str
    order_id: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=250)
    unix_timestamp: str
    callback_url: str = Field(min_length=1, max_length=128)
    callback_on_failure: Literal["1"] = "1"
    success_url: str = Field(min_length=1, max_length=128)
    lifetime: str
    show_payment_methods: str
    client_phone: str | None = Field(default=None, max_length=15)
    client_email: str | None = Field(default=None, max_length=64)
    client_name: str | None = Field(default=None, max_length=255)
    signature: str = Field(min_length=40, max_length=40)

    @field_validator("amount", mode="before")
    @classmethod
    def _validate_amount(cls, value: Decimal | float | int | str) -> str:
        return _format_amount(value)

    @field_validator("unix_timestamp", "lifetime", mode="before")
    @classmethod
    def _validate_numeric_str(cls, value: int | str) -> str:
        return str(value)


class ModulbankSbpRequest(BaseModel):
    """Validated payload for the direct SBP API call."""

    merchant: str = Field(min_length=1, max_length=128)
    amount: str
    order_id: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=250)
    unix_timestamp: str
    callback_url: str = Field(min_length=1, max_length=128)
    callback_on_failure: Literal["1"] = "1"
    qr_lifetime: str
    client_phone: str | None = Field(default=None, max_length=15)
    client_email: str | None = Field(default=None, max_length=64)
    client_name: str | None = Field(default=None, max_length=255)
    signature: str = Field(min_length=40, max_length=40)

    @field_validator("amount", mode="before")
    @classmethod
    def _validate_amount(cls, value: Decimal | float | int | str) -> str:
        return _format_amount(value)

    @field_validator("unix_timestamp", "qr_lifetime", mode="before")
    @classmethod
    def _validate_numeric_str(cls, value: int | str) -> str:
        return str(value)


class ModulbankPaymentResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    form_url: str = Field(alias="formUrl")
    # Dict of strings is intentional: this is the exact signed payload that
    # will be POSTed verbatim to ModulBank. Wrapping it in a Pydantic model
    # again causes ``None`` fields to leak into the response as ``null`` and
    # diverge from the signed body.
    form_params: dict[str, str] = Field(alias="formParams")
    order_id: str = Field(alias="orderId")
    amount: Decimal
    expires_at: str = Field(alias="expiresAt")


class ModulbankSbpResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sbp_link: str = Field(alias="sbpLink")
    order_id: str = Field(alias="orderId")
    amount: Decimal
    description: str
    expires_at: str = Field(alias="expiresAt")


class PaymentStatusDetails(BaseModel):
    id: UUID
    status: str
    fiscal_status: str | None = None
    receipt_url: str | None = None
    error_message: str | None = None
    paid_at: datetime | None = None


class ModulbankWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    order_id: str | None = None
    status: str | None = None
    state: str | None = None
    result: str | None = None
    signature: str | None = None
    error_message: str | None = None
    error: str | None = None


class ModulkassaWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    status: str | None = None
    ofd_receipt_url: str | None = Field(default=None, alias="ofdReceiptUrl")
    receipt_url: str | None = None
    error: str | None = None
