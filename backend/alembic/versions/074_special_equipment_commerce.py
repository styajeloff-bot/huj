"""Create isolated commerce tables for special equipment.

Revision ID: 074
Revises: 073
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "074"
down_revision: str | None = "073"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "special_equipment_favorites",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["special_equipment_products.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "product_id"),
    )
    op.create_index(
        "idx_special_equipment_favorites_product_user",
        "special_equipment_favorites",
        ["product_id", "user_id"],
    )

    op.create_table(
        "special_equipment_cart_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "is_selected", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column("custom_price", sa.Numeric(15, 2), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "equipments",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "services",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "custom_price IS NULL OR custom_price > 0",
            name="ck_special_equipment_cart_custom_price_positive",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["special_equipment_products.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "product_id",
            name="uq_special_equipment_cart_user_product",
        ),
    )
    op.create_index(
        "idx_special_equipment_cart_product",
        "special_equipment_cart_items",
        ["product_id"],
    )
    op.create_index(
        "idx_special_equipment_cart_user_added",
        "special_equipment_cart_items",
        ["user_id", sa.text("added_at DESC"), sa.text("id DESC")],
    )

    op.create_table(
        "special_equipment_application_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("unit_price", sa.Numeric(15, 2), nullable=True),
        sa.Column("total_price", sa.Numeric(15, 2), nullable=True),
        sa.Column(
            "currency_code", sa.String(3), server_default="RUB", nullable=False
        ),
        sa.Column("item_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "equipments",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "services",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("leasing_purpose", sa.String(100), nullable=True),
        sa.Column(
            "regions",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "item_status", sa.String(20), server_default="active", nullable=False
        ),
        sa.Column("reserve_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "item_status IN ('active', 'reserved', 'replaced', 'removed', 'rejected')",
            name="ck_special_equipment_application_item_status",
        ),
        sa.CheckConstraint(
            "unit_price IS NULL OR unit_price >= 0",
            name="ck_special_equipment_application_unit_price",
        ),
        sa.CheckConstraint(
            "total_price IS NULL OR total_price >= 0",
            name="ck_special_equipment_application_total_price",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["leasing_applications.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["special_equipment_products.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["seller_company_id"], ["companies.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "application_id",
            "product_id",
            name="uq_special_equipment_application_product",
        ),
    )
    op.create_index(
        "idx_special_equipment_application_items_application",
        "special_equipment_application_items",
        ["application_id", "id"],
    )
    op.create_index(
        "idx_special_equipment_application_items_product_status",
        "special_equipment_application_items",
        ["product_id", "item_status", "application_id"],
    )

    op.create_table(
        "special_equipment_purchase_orders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "analytics_session_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "leasing_application_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("purchase_type", sa.String(24), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("unit_price", sa.Numeric(15, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(15, 2), nullable=False),
        sa.Column(
            "paid_amount", sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "remaining_amount",
            sa.Numeric(15, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "currency_code", sa.String(3), server_default="RUB", nullable=False
        ),
        sa.Column("down_payment_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("item_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column(
            "cancellation_requested_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refund_external_reference", sa.String(255), nullable=True),
        sa.Column("refunded_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column(
            "refund_confirmed_by", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("refund_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "purchase_type IN ('reservation', 'full_purchase', 'leasing')",
            name="ck_special_equipment_order_purchase_type",
        ),
        sa.CheckConstraint(
            "status IN ('payment_pending', 'reserved', 'purchased', "
            "'leasing_pending', 'leasing_active', 'cancellation_requested', "
            "'cancelled', 'expired', 'failed')",
            name="ck_special_equipment_order_status",
        ),
        sa.CheckConstraint(
            "total_price > 0 AND paid_amount >= 0 AND remaining_amount >= 0",
            name="ck_special_equipment_order_amounts",
        ),
        sa.CheckConstraint(
            "paid_amount + remaining_amount = total_price",
            name="ck_special_equipment_order_amount_balance",
        ),
        sa.CheckConstraint(
            "(refund_external_reference IS NULL AND refunded_amount IS NULL "
            "AND refund_confirmed_by IS NULL AND refund_confirmed_at IS NULL) OR "
            "(status = 'cancelled' AND refund_external_reference IS NOT NULL "
            "AND refunded_amount > 0 AND refund_confirmed_by IS NOT NULL "
            "AND refund_confirmed_at IS NOT NULL AND paid_amount = 0 "
            "AND remaining_amount = total_price)",
            name="ck_special_equipment_order_refund_audit",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["special_equipment_products.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["seller_company_id"], ["companies.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["leasing_application_id"],
            ["leasing_applications.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["refund_confirmed_by"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_special_equipment_orders_user_idempotency",
        ),
        sa.UniqueConstraint(
            "refund_external_reference",
            name="uq_special_equipment_orders_refund_external_reference",
        ),
    )
    op.create_index(
        "idx_special_equipment_orders_user_created",
        "special_equipment_purchase_orders",
        ["user_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "idx_special_equipment_orders_status_hold",
        "special_equipment_purchase_orders",
        ["status", "hold_expires_at"],
    )
    op.create_index(
        "idx_special_equipment_orders_product_status",
        "special_equipment_purchase_orders",
        ["product_id", "status"],
    )
    op.create_index(
        "uq_special_equipment_orders_active_product",
        "special_equipment_purchase_orders",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('payment_pending', 'reserved', 'purchased', "
            "'leasing_pending', 'leasing_active', 'cancellation_requested')"
        ),
    )

    op.create_table(
        "special_equipment_payments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "analytics_session_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("payment_type", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("status", sa.String(24), server_default="pending", nullable=False),
        sa.Column("payment_method", sa.String(24), nullable=True),
        sa.Column("gateway_transaction_id", sa.String(255), nullable=True),
        sa.Column("gateway_response", postgresql.JSONB(), nullable=True),
        sa.Column("receipt_storage_key", sa.String(500), nullable=True),
        sa.Column("receipt_ingestion_status", sa.String(20), nullable=True),
        sa.Column(
            "receipt_ingestion_retry_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("receipt_ingestion_error_code", sa.String(100), nullable=True),
        sa.Column(
            "receipt_ingestion_next_retry_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("fiscal_status", sa.String(30), nullable=True),
        sa.Column("fiscal_receipt_id", sa.String(255), nullable=True),
        sa.Column("fiscal_response", postgresql.JSONB(), nullable=True),
        sa.Column(
            "fiscal_retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("fiscal_error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "payment_type IN ('reservation', 'full_purchase', 'remaining_balance', "
            "'leasing', 'leasing_monthly')",
            name="ck_special_equipment_payment_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', "
            "'expired', 'refunded')",
            name="ck_special_equipment_payment_status",
        ),
        sa.CheckConstraint(
            "payment_method IS NULL OR payment_method IN ('card', 'sbp', 'bank_transfer')",
            name="ck_special_equipment_payment_method",
        ),
        sa.CheckConstraint(
            "amount > 0", name="ck_special_equipment_payment_amount_positive"
        ),
        sa.CheckConstraint(
            "receipt_ingestion_status IS NULL OR receipt_ingestion_status IN "
            "('pending', 'processing', 'completed', 'failed')",
            name="ck_special_equipment_receipt_ingestion_status",
        ),
        sa.CheckConstraint(
            "(status = 'refunded' AND refunded_at IS NOT NULL) OR "
            "(status <> 'refunded' AND refunded_at IS NULL)",
            name="ck_special_equipment_payment_refunded_at",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"],
            ["special_equipment_purchase_orders.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "purchase_order_id",
            "idempotency_key",
            name="uq_special_equipment_payments_order_idempotency",
        ),
        sa.UniqueConstraint(
            "gateway_transaction_id",
            name="uq_special_equipment_payments_gateway_transaction",
        ),
    )
    op.create_index(
        "idx_special_equipment_payments_order_created",
        "special_equipment_payments",
        ["purchase_order_id", "created_at", "id"],
    )
    op.create_index(
        "idx_special_equipment_payments_status_expires",
        "special_equipment_payments",
        ["status", "expires_at"],
    )
    op.create_index(
        "idx_special_equipment_payments_fiscal_updated",
        "special_equipment_payments",
        ["fiscal_status", "updated_at"],
    )
    op.create_index(
        "idx_special_equipment_payments_receipt_retry",
        "special_equipment_payments",
        ["receipt_ingestion_next_retry_at", "updated_at"],
        postgresql_where=sa.text(
            "receipt_storage_key IS NULL "
            "AND fiscal_status = 'completed' "
            "AND receipt_ingestion_status IN ('pending', 'failed', 'processing')"
        ),
    )

    op.create_table(
        "special_equipment_payment_callback_inbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("event_key", sa.String(64), nullable=False),
        sa.Column("gateway_transaction_id", sa.String(255), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("signature_digest", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "status", sa.String(20), server_default="pending", nullable=False
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("manual_review_reason", sa.String(100), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processed', 'manual_review', 'retry')",
            name="ck_special_equipment_callback_inbox_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_special_equipment_callback_inbox_attempt_count",
        ),
        sa.CheckConstraint(
            "char_length(event_key) = 64 AND char_length(signature_digest) = 64",
            name="ck_special_equipment_callback_inbox_digest_lengths",
        ),
        sa.CheckConstraint(
            "(status = 'manual_review' AND manual_review_reason IS NOT NULL) "
            "OR status <> 'manual_review'",
            name="ck_special_equipment_callback_inbox_manual_review_reason",
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["special_equipment_payments.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_key",
            name="uq_special_equipment_callback_inbox_event_key",
        ),
    )
    op.create_index(
        "idx_special_equipment_callback_inbox_retry",
        "special_equipment_payment_callback_inbox",
        ["next_retry_at", "received_at", "id"],
        postgresql_where=sa.text("status IN ('pending', 'retry')"),
    )
    op.create_index(
        "idx_special_equipment_callback_inbox_manual_review",
        "special_equipment_payment_callback_inbox",
        [sa.text("received_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("status = 'manual_review'"),
    )
    op.create_index(
        "idx_special_equipment_callback_inbox_transaction",
        "special_equipment_payment_callback_inbox",
        ["gateway_transaction_id", "received_at"],
    )

    op.create_table(
        "special_equipment_leasing_payment_schedule",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("payment_number", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("principal", sa.Numeric(15, 2), nullable=True),
        sa.Column("interest", sa.Numeric(15, 2), nullable=True),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_paid", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "payment_number > 0",
            name="ck_special_equipment_schedule_payment_number_positive",
        ),
        sa.CheckConstraint(
            "amount > 0", name="ck_special_equipment_schedule_amount_positive"
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"],
            ["special_equipment_purchase_orders.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["special_equipment_payments.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "purchase_order_id",
            "payment_number",
            name="uq_special_equipment_schedule_order_number",
        ),
    )
    op.create_index(
        "idx_special_equipment_schedule_order_due",
        "special_equipment_leasing_payment_schedule",
        ["purchase_order_id", "due_date", "id"],
    )
    op.create_index(
        "idx_special_equipment_schedule_unpaid_due",
        "special_equipment_leasing_payment_schedule",
        ["due_date"],
        postgresql_where=sa.text("is_paid = false"),
    )

    op.create_table(
        "special_equipment_commerce_outbox",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column(
            "schema_version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("last_error", sa.String(1000), nullable=True),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_special_equipment_outbox_attempt_count"
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "idx_special_equipment_outbox_pending",
        "special_equipment_commerce_outbox",
        ["available_at", "occurred_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_special_equipment_outbox_pending",
        table_name="special_equipment_commerce_outbox",
    )
    op.drop_table("special_equipment_commerce_outbox")

    op.drop_index(
        "idx_special_equipment_schedule_unpaid_due",
        table_name="special_equipment_leasing_payment_schedule",
    )
    op.drop_index(
        "idx_special_equipment_schedule_order_due",
        table_name="special_equipment_leasing_payment_schedule",
    )
    op.drop_table("special_equipment_leasing_payment_schedule")

    op.drop_index(
        "idx_special_equipment_callback_inbox_transaction",
        table_name="special_equipment_payment_callback_inbox",
    )
    op.drop_index(
        "idx_special_equipment_callback_inbox_manual_review",
        table_name="special_equipment_payment_callback_inbox",
    )
    op.drop_index(
        "idx_special_equipment_callback_inbox_retry",
        table_name="special_equipment_payment_callback_inbox",
    )
    op.drop_table("special_equipment_payment_callback_inbox")

    op.drop_index(
        "idx_special_equipment_payments_receipt_retry",
        table_name="special_equipment_payments",
    )
    op.drop_index(
        "idx_special_equipment_payments_fiscal_updated",
        table_name="special_equipment_payments",
    )
    op.drop_index(
        "idx_special_equipment_payments_status_expires",
        table_name="special_equipment_payments",
    )
    op.drop_index(
        "idx_special_equipment_payments_order_created",
        table_name="special_equipment_payments",
    )
    op.drop_table("special_equipment_payments")

    op.drop_index(
        "uq_special_equipment_orders_active_product",
        table_name="special_equipment_purchase_orders",
    )
    op.drop_index(
        "idx_special_equipment_orders_product_status",
        table_name="special_equipment_purchase_orders",
    )
    op.drop_index(
        "idx_special_equipment_orders_status_hold",
        table_name="special_equipment_purchase_orders",
    )
    op.drop_index(
        "idx_special_equipment_orders_user_created",
        table_name="special_equipment_purchase_orders",
    )
    op.drop_table("special_equipment_purchase_orders")

    op.drop_index(
        "idx_special_equipment_application_items_product_status",
        table_name="special_equipment_application_items",
    )
    op.drop_index(
        "idx_special_equipment_application_items_application",
        table_name="special_equipment_application_items",
    )
    op.drop_table("special_equipment_application_items")

    op.drop_index(
        "idx_special_equipment_cart_user_added",
        table_name="special_equipment_cart_items",
    )
    op.drop_index(
        "idx_special_equipment_cart_product",
        table_name="special_equipment_cart_items",
    )
    op.drop_table("special_equipment_cart_items")

    op.drop_index(
        "idx_special_equipment_favorites_product_user",
        table_name="special_equipment_favorites",
    )
    op.drop_table("special_equipment_favorites")
