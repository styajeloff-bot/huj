"""Versioned facts for the notification workflow (no transport or persistence)."""

from datetime import date, datetime, timedelta
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

EventType = Literal[
    "document_registry.expiring",
    "monetization.deal_created",
    "monetization.party_confirmed",
    "monetization.deal_paid",
    "monetization.deal_terms_changed",
    "monetization.capture_failed",
    "monetization.condition_requested",
    "monetization.condition_responded",
    "monetization.condition_decided",
    "leasing.application_created",
    "leasing.vehicle_reserved",
    "leasing.vehicle_reservation_expired",
    "leasing.vehicle_cancelled",
    "leasing.additional_price_changed",
    "leasing.company_assigned",
    "leasing.application_status_changed",
    "leasing.company_selected",
    "leasing.company_not_selected",
    "leasing.preliminary_offer_accepted",
    "leasing.final_offer_accepted",
    "leasing.application_cancelled",
    "leasing.company_decision_received",
    "leasing.documents_requested",
    "leasing.documents_uploaded",
    "leasing.documents_uploads_summary",
    "leasing.application_finalized",
    "exchange.request_published",
    "exchange.bid_created",
    "exchange.bid_updated",
    "exchange.bid_withdrawn",
    "exchange.request_changed",
    "exchange.deadline_24h",
    "exchange.deadline_1h",
    "exchange.request_finalized",
    "exchange.bid_selected",
    "exchange.bid_not_selected",
]

REQUIRED_PAYLOAD_FIELDS: dict[str, tuple[str, ...]] = {
    "document_registry.expiring": ("version_id", "valid_to", "document_type", "document_name"),
    "monetization.deal_created": ("revision",),
    "monetization.party_confirmed": ("revision", "confirmed_party"),
    "monetization.deal_paid": ("revision",),
    "monetization.deal_terms_changed": ("revision",),
    "monetization.capture_failed": ("reason",),
    **dict.fromkeys(
        (
            "monetization.condition_requested",
            "monetization.condition_responded",
            "monetization.condition_decided",
        ),
        ("application_id",),
    ),
    **dict.fromkeys(
        (
            "leasing.vehicle_reserved",
            "leasing.vehicle_cancelled",
            "leasing.vehicle_reservation_expired",
        ),
        ("application_vehicle_id",),
    ),
    **dict.fromkeys(
        (
            "leasing.company_assigned",
            "leasing.company_selected",
            "leasing.preliminary_offer_accepted",
            "leasing.final_offer_accepted",
            "leasing.documents_requested",
            "leasing.documents_uploaded",
        ),
        ("leasing_company_id",),
    ),
    "leasing.company_not_selected": ("selected_leasing_company_id",),
    "leasing.documents_uploads_summary": (
        "leasing_company_id", "request_batch_id", "group_id", "document_count",
        "first_upload_at", "last_upload_at", "closes_at",
    ),
    "exchange.bid_selected": ("selected_dealer_company_id",),
    "exchange.bid_not_selected": ("selected_dealer_company_id",),
    "exchange.deadline_24h": ("expiration_at",),
    "exchange.deadline_1h": ("expiration_at",),
}


def _validate_wire_values(value: Any, key: str = "") -> None:
    """IDs remain UUIDs and money never crosses the wire as binary floats."""
    if isinstance(value, float):
        raise ValueError(  # noqa: TRY004 - ValueError is converted to Pydantic ValidationError
            "Notification numeric values must use integers or decimal strings"
        )
    if key.endswith("_id") and value is not None and UUID(str(value)).int == 0:
        raise ValueError("Zero UUID is not an entity identifier")
    if key.endswith("_ids") and value is not None:
        if not isinstance(value, list):
            raise ValueError("Entity identifier collections must be arrays")
        for item in value:
            _validate_wire_values(item, "entity_id")
    if key.endswith("_at") and value is not None:
        if not isinstance(value, str):
            raise ValueError("Timestamps must be ISO-8601 strings")
        timestamp = datetime.fromisoformat(value)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Timestamps must include a timezone")
    if isinstance(value, dict):
        for name, child in value.items():
            _validate_wire_values(child, name)
    elif isinstance(value, list):
        for child in value:
            _validate_wire_values(child)


class NotificationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    event_id: UUID
    event_type: EventType
    entity_type: Literal[
        "reference_document",
        "leasing_application",
        "exchange_request",
        "exchange_bid",
        "monetization_deal",
        "monetization_capture",
        "monetization_condition_request",
    ]
    entity_id: UUID
    aggregate_id: UUID
    application_id: UUID | None = None
    actor_user_id: UUID | None = None
    request_number: str = Field(min_length=1, max_length=100)
    occurred_at: AwareDatetime
    changed_fields: list[str] = Field(default_factory=list, max_length=100)
    previous_values: dict[str, Any] = Field(default_factory=dict)
    new_values: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurrence_key: str | None = Field(default=None, max_length=500)
    correlation_id: str | None = Field(default=None, max_length=128)

    @field_validator("occurred_at", mode="before")
    @classmethod
    def timestamp_not_epoch(cls, value: Any) -> Any:
        if not isinstance(value, str | datetime):
            raise ValueError("occurred_at must be an aware datetime or ISO-8601 string")  # noqa: TRY004 - Pydantic validation
        return value

    @field_validator(
        "event_id", "entity_id", "aggregate_id", "application_id", "actor_user_id"
    )
    @classmethod
    def nonzero_ids(cls, value: UUID | None) -> UUID | None:
        if value is not None and value.int == 0:
            raise ValueError("Zero UUID is not an entity identifier")
        return value

    @model_validator(mode="after")
    def coherent_fact(self) -> Self:
        self._validate_fact_identity()
        _validate_wire_values(self.payload)
        _validate_wire_values(self.previous_values)
        _validate_wire_values(self.new_values)
        for key in REQUIRED_PAYLOAD_FIELDS.get(self.event_type, ()):
            if self.payload.get(key) is None:
                raise ValueError(f"Required event payload field is missing: {key}")
        if self.event_type == "leasing.documents_uploads_summary":
            count = self.payload["document_count"]
            start = datetime.fromisoformat(self.payload["first_upload_at"])
            end = datetime.fromisoformat(self.payload["closes_at"])
            last = datetime.fromisoformat(self.payload["last_upload_at"])
            if type(count) is not int or count < 1:
                raise ValueError("Document summary requires a positive integer count")
            if end != start + timedelta(minutes=10) or not start <= last < end:
                raise ValueError("Document summary must describe its ten-minute upload window")
            if (
                UUID(str(self.payload["group_id"])) != self.event_id
                or self.occurred_at != end
                or self.occurrence_key != f"leasing.documents_uploads_summary:{self.event_id}"
            ):
                raise ValueError("Document summary identity must match its closed group")
        changed = {
            key
            for key in self.previous_values.keys() | self.new_values.keys()
            if self.previous_values.get(key) != self.new_values.get(key)
        }
        if set(self.changed_fields) != changed or len(self.changed_fields) != len(
            changed
        ):
            raise ValueError("changed_fields must describe exactly the changed values")
        return self

    @model_validator(mode="after")
    def optional_proposal_kind_matches_decision(self) -> Self:
        if (
            self.event_type != "leasing.company_decision_received"
            or "proposal_kind" not in self.payload
        ):
            return self
        decision_statuses = {
            "preliminary": {
                "approved_scoring", "approved_scoring_another_cond", "rejected_prescoring",
            },
            "final": {
                "approved_final", "approved_final_another_cond", "rejected_approved",
            },
        }
        kind = self.payload["proposal_kind"]
        decision_status = self.new_values.get("lca_status")
        if (
            not isinstance(kind, str)
            or not isinstance(decision_status, str)
            or decision_status not in decision_statuses.get(kind, set())
        ):
            raise ValueError("proposal_kind must match the leasing company decision status")
        return self

    def _validate_fact_identity(self) -> None:
        leasing = self.event_type.startswith("leasing.")
        if self.event_type == "document_registry.expiring":
            self._validate_document_registry_fact()
        elif self.event_type.startswith("monetization."):
            self._validate_monetization_fact()
        elif leasing:
            if self.entity_type != "leasing_application" or not (
                self.application_id == self.entity_id == self.aggregate_id
            ):
                raise ValueError(
                    "Leasing notification must identify its root application"
                )
        elif self.application_id is not None or self.entity_type not in {
            "exchange_request", "exchange_bid",
        }:
            raise ValueError(
                "Exchange notification cannot reference a leasing application"
            )
        elif (
            self.entity_type == "exchange_request"
            and self.entity_id != self.aggregate_id
        ):
            raise ValueError("Exchange request is its own aggregate")

    def _validate_document_registry_fact(self) -> None:
        if (
            self.entity_type != "reference_document"
            or self.entity_id != self.aggregate_id
            or self.application_id is not None
        ):
            raise ValueError("A document expiry must identify its reference document")
        version_id = UUID(str(self.payload.get("version_id")))
        expiry = self.payload.get("valid_to")
        if not isinstance(expiry, str) or date.fromisoformat(expiry).isoformat() != expiry:
            raise ValueError("Document expiry must be an ISO calendar date")
        expected_key = f"document_registry.expiring:{self.entity_id}:{version_id}:{expiry}"
        if self.occurrence_key != expected_key:
            raise ValueError("Document expiry occurrence must identify its version and end date")
        for field, limit in (("document_type", 100), ("document_name", 255)):
            value = self.payload.get(field)
            if not isinstance(value, str) or not 1 <= len(value) <= limit:
                raise ValueError(f"Document expiry requires a valid {field}")

    def _validate_monetization_fact(self) -> None:
        if self.entity_id != self.aggregate_id:
            raise ValueError("A monetization fact must identify its own aggregate")
        if self.event_type.startswith("monetization.condition_"):
            if (
                self.entity_type != "monetization_condition_request"
                or self.application_id is None
            ):
                raise ValueError(
                    "A commission request must identify its source application"
                )
            if str(self.application_id) != str(self.payload.get("application_id")):
                raise ValueError(
                    "Commission request application identifiers must match"
                )
        elif self.event_type == "monetization.capture_failed":
            if self.entity_type != "monetization_capture":
                raise ValueError("A capture failure must identify its source capture")
        elif self.entity_type != "monetization_deal":
            raise ValueError(
                "A financial notification must identify its monetization deal"
            )
        if self.entity_type == "monetization_deal":
            revision = self.payload.get("revision")
            if type(revision) is not int or revision < 1:
                raise ValueError(
                    "A monetization deal fact requires its positive revision"
                )
        if self.event_type == "monetization.party_confirmed" and self.payload.get(
            "confirmed_party"
        ) not in {"leasing", "dealer", "distributor"}:
            raise ValueError("Only a participating side can confirm monetization")
