"""PostgreSQL ENUM type definitions for use in SQLAlchemy mapped_column declarations.

All enums use create_type=False so the types are managed exclusively by Alembic
migrations rather than being auto-created by SQLAlchemy.
"""

import sqlalchemy as sa

user_role_enum = sa.Enum(
    "carcraft_employee",
    "dealer",
    "client",
    "leasing_company",
    "distributor",
    "external_api",
    name="user_role",
    create_type=False,
)

company_type_enum = sa.Enum(
    "dealer",
    "leasing_company",
    "distributor",
    "other",
    name="company_type",
    create_type=False,
)

application_status_enum = sa.Enum(
    "active",
    "rejected",
    "issued",
    name="application_status",
    create_type=False,
)

leasing_company_application_status_enum = sa.Enum(
    "draft",
    "submitted",
    "under_review",
    "approved_scoring",
    "approved_scoring_another_cond",
    "rejected_prescoring",
    "documents_required",
    "approved_final",
    "approved_final_another_cond",
    "rejected_approved",
    "selected_lc",
    "deal",
    "closed",
    # Historical DB values remain readable; domain transitions are separate.
    "prescoring",
    "issued",
    "under_review_with_docs",
    name="leasing_company_application_status",
    create_type=False,
)

document_status_enum = sa.Enum(
    "not_uploaded",
    "uploaded",
    "under_review",
    "verified",
    "requested",
    name="document_status",
    create_type=False,
)

notification_type_enum = sa.Enum(
    "application_status",
    "document_request",
    "approval",
    "general",
    "document_status",
    "leasing_approval",
    "system",
    "exchange_new_request",
    "exchange_new_bid",
    "exchange_bid_updated",
    "exchange_bid_accepted",
    "exchange_request_changed",
    "exchange_bid_withdrawn",
    "exchange_deadline",
    "exchange_request_finalized",
    "exchange_bid_not_selected",
    name="notification_type",
    create_type=False,
)

support_type_enum = sa.Enum(
    "down_payment_compensation",
    "vehicle_discount_dealer_compensation",
    "vehicle_discount_dealer_invoice",
    "leasing_interest_compensation",
    name="support_type",
    create_type=False,
)

purchase_type_enum = sa.Enum(
    "reservation",
    "full_purchase",
    name="purchase_type",
    create_type=False,
)

purchase_status_enum = sa.Enum(
    "reserved",
    "purchased",
    "leasing_pending",
    "leasing_active",
    "cancelled",
    "cancellation_requested",
    name="purchase_status",
    create_type=False,
)

payment_status_enum = sa.Enum(
    "processing",
    "completed",
    "error",
    "pending_payment",
    "failed",
    name="payment_status",
    create_type=False,
)

payment_type_enum = sa.Enum(
    "reservation",
    "remaining_balance",
    "full_purchase",
    "leasing_monthly",
    name="payment_type",
    create_type=False,
)

compensation_status_enum = sa.Enum(
    "under_review",
    "accepted",
    "rejected",
    "paid",
    "overdue",
    "cancelled",
    name="compensation_status",
    create_type=False,
)

payer_type_enum = sa.Enum(
    "distributor",
    "dealer",
    "carcraft",
    "minpromtorg",
    "client",
    name="payer_type",
    create_type=False,
)

recipient_type_enum = sa.Enum(
    "leasing_company",
    "dealer",
    "carcraft",
    "client",
    "distributor",
    name="recipient_type",
    create_type=False,
)

calculation_base_enum = sa.Enum(
    "base_price",
    "special_price",
    "dealer_cost",
    "application_price",
    "down_payment",
    "support_amount",
    name="calculation_base",
    create_type=False,
)

compensation_value_type_enum = sa.Enum(
    "percent",
    "sum",
    name="compensation_value_type",
    create_type=False,
)

payment_schedule_type_enum = sa.Enum(
    "fixed_date",
    "days_count",
    "weekly",
    "quarterly",
    "reporting_period",
    name="payment_schedule_type",
    create_type=False,
)
