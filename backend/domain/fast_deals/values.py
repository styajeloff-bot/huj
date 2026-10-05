"""Status dictionaries and constants of the fast deal process.

These dictionaries are the module's own; they are never merged with the ordinary
leasing application statuses.
"""
from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    """Direction of the deal; also its monetization source."""

    DEALER_TO_LEASING = "dealer_to_leasing"  # DD
    LEASING_TO_DEALER = "leasing_to_dealer"  # DL


class DealStatus(StrEnum):
    DRAFT = "draft"
    PENDING_LC_CONFIRMATION = "pending_lc_confirmation"
    PENDING_LC_FINAL_CONFIRMATION = "pending_lc_final_confirmation"
    PENDING_DEALER_CONFIRMATION = "pending_dealer_confirmation"
    PENDING_LC_CHANGES_CONFIRMATION = "pending_lc_changes_confirmation"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class LcStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    OFFER_SENT = "offer_sent"
    SELECTED_BY_DEALER = "selected_by_dealer"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CLOSED_NOT_SELECTED = "closed_not_selected"


class ItemStatus(StrEnum):
    ACTIVE = "active"
    REMOVED = "removed"
    REPLACED = "replaced"


class VehicleSource(StrEnum):
    PRODUCT = "product"
    MANUAL = "manual"


class AdjustmentType(StrEnum):
    DISCOUNT = "discount"
    MARKUP = "markup"


class SupportRequestStatus(StrEnum):
    REQUESTED = "requested"
    PRE_APPROVED = "pre_approved"
    APPROVED = "approved"
    CANCELLED = "cancelled"  # shown as "Отклонено"


class FileKind(StrEnum):
    DEAL_MAIN = "deal_main"
    DEAL_ADDITIONAL = "deal_additional"
    LC_OFFER_PDF = "lc_offer_pdf"
    VEHICLE_OFFER = "vehicle_offer"


class AssigneeRole(StrEnum):
    PRIMARY = "primary"
    ADDITIONAL = "additional"


class DownPaymentMode(StrEnum):
    AMOUNT = "amount"
    PERCENT = "percent"


class Party(StrEnum):
    """How an actor relates to a particular deal."""

    INITIATOR = "initiator"  # DD: dealer; DL: leasing company
    LEASING = "leasing"  # DD: invited / selected leasing company
    DEALER = "dealer"  # DL: dealer of this part
    DISTRIBUTOR = "distributor"
    PLATFORM = "platform"  # carcraft employee, read only
    NONE = "none"


class Role(StrEnum):
    DEALER = "dealer"
    LEASING_COMPANY = "leasing_company"
    DISTRIBUTOR = "distributor"
    PLATFORM = "carcraft_employee"
    CLIENT = "client"


# Roles for which the section exists; the client has no access at all.
VISIBLE_ROLES = frozenset(
    {Role.DEALER, Role.LEASING_COMPANY, Role.DISTRIBUTOR, Role.PLATFORM}
)
# Roles that may create a deal.
CREATOR_ROLES = frozenset({Role.DEALER, Role.LEASING_COMPANY})

NUMBER_PREFIX = {
    SourceType.DEALER_TO_LEASING: "DD",
    SourceType.LEASING_TO_DEALER: "DL",
}

# Confirmed and cancelled are final; rejected can be reopened by the initiator.
FINAL_STATUSES = frozenset({DealStatus.CONFIRMED, DealStatus.CANCELLED})
# Statuses in which a reserved unit must be held by the deal.
RESERVING_STATUSES = frozenset(
    {
        DealStatus.PENDING_LC_CONFIRMATION,
        DealStatus.PENDING_LC_FINAL_CONFIRMATION,
        DealStatus.PENDING_DEALER_CONFIRMATION,
        DealStatus.PENDING_LC_CHANGES_CONFIRMATION,
    }
)
# DD statuses after sending, before the final decision.
DD_IN_REVIEW = frozenset(
    {DealStatus.PENDING_LC_CONFIRMATION, DealStatus.PENDING_LC_FINAL_CONFIRMATION}
)

MIN_LEASE_TERM_MONTHS = 12
MAX_LEASE_TERM_MONTHS = 84
MAX_DOWN_PAYMENT_PERCENT = 49
MAX_BUYOUT_PERCENT = 5
MAX_UPLOAD_FILES = 20
MAX_FILE_BYTES = 50 * 1024 * 1024  # the same limit as exchange requests and bids


class HistoryEvent:
    """``event_type`` values of ``fast_deal_status_history``."""

    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    VEHICLE_ADDED = "vehicle_added"
    VEHICLE_CHANGED = "vehicle_changed"
    VEHICLE_REMOVED = "vehicle_removed"
    VEHICLE_REPLACED = "vehicle_replaced"
    TERMS_CHANGED = "terms_changed"
    SENT = "sent"
    INVITED = "lc_invited"
    OFFER_SENT = "offer_sent"
    OFFER_SELECTED = "offer_selected"
    SELECTION_WITHDRAWN = "selection_withdrawn"
    LC_REJECTED = "lc_rejected"
    RESET = "reset"
    REOPENED = "reopened"
    SPLIT = "split"
    CHANGES_SENT = "changes_sent"
    CHANGES_ACCEPTED = "changes_accepted"
    CHANGES_REJECTED = "changes_rejected"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    ASSIGNEES_CHANGED = "assignees_changed"
    SUPPORT_APPLIED = "support_applied"
    SUPPORT_REMOVED = "support_removed"
    SUPPORT_REQUESTED = "support_requested"
    SUPPORT_DECIDED = "support_decided"
    SUPPORT_ACCOUNTED = "support_accounted"
    FILE_UPLOADED = "file_uploaded"


class NotifyEvent:
    """Notification event types (``fast_deal.*``), one per business fact."""

    SENT = "fast_deal.sent"
    OFFER_SENT = "fast_deal.offer_sent"
    OFFER_SELECTED = "fast_deal.offer_selected"
    SELECTION_WITHDRAWN = "fast_deal.selection_withdrawn"
    LC_REJECTED = "fast_deal.lc_rejected"
    CONFIRMED = "fast_deal.confirmed"
    REJECTED = "fast_deal.rejected"
    RESET = "fast_deal.reset"
    CHANGES_SENT = "fast_deal.changes_sent"
    CHANGES_ACCEPTED = "fast_deal.changes_accepted"
    CHANGES_REJECTED = "fast_deal.changes_rejected"
    CANCELLED = "fast_deal.cancelled"
    ASSIGNEES_CHANGED = "fast_deal.assignees_changed"
    SUPPORT_REQUESTED = "fast_deal.support_requested"
    SUPPORT_DECIDED = "fast_deal.support_decided"

    ALL = (
        SENT, OFFER_SENT, OFFER_SELECTED, SELECTION_WITHDRAWN, LC_REJECTED, CONFIRMED,
        REJECTED, RESET, CHANGES_SENT, CHANGES_ACCEPTED, CHANGES_REJECTED, CANCELLED,
        ASSIGNEES_CHANGED, SUPPORT_REQUESTED, SUPPORT_DECIDED,
    )
