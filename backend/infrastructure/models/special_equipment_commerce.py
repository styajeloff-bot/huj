"""Persistence models for special-equipment commerce.

The tables in this module deliberately do not reuse vehicle commerce foreign
keys.  A special-equipment product is a concrete sellable unit and therefore
has a quantity of one and at most one active commercial claim.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class SpecialEquipmentFavorite(Base):
    __tablename__ = "special_equipment_favorites"
    __table_args__ = (
        sa.Index(
            "idx_special_equipment_favorites_product_user",
            "product_id",
            "user_id",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_products.id", ondelete="CASCADE"),
        primary_key=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )


class SpecialEquipmentGuestCartTransfer(Base):
    """Durable idempotency receipt for one authenticated guest-cart transfer."""

    __tablename__ = "special_equipment_guest_cart_transfers"
    __table_args__ = (
        sa.PrimaryKeyConstraint(
            "user_id",
            "transfer_id",
            name="pk_special_equipment_guest_cart_transfers",
        ),
        sa.CheckConstraint(
            "char_length(request_hash) = 64",
            name="ck_se_guest_cart_transfers_request_hash",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            name="fk_se_guest_cart_transfers_user",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    transfer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    request_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )


class SpecialEquipmentCartItem(Base):
    __tablename__ = "special_equipment_cart_items"
    __table_args__ = (
        sa.Index(
            "uq_special_equipment_cart_user_product",
            "user_id",
            "product_id",
            unique=True,
            postgresql_where=sa.text("parent_item_id IS NULL"),
        ),
        sa.Index(
            "uq_se_cart_items_child_product",
            "parent_item_id",
            "product_id",
            unique=True,
            postgresql_where=sa.text("parent_item_id IS NOT NULL"),
        ),
        sa.Index(
            "idx_special_equipment_cart_user_added",
            "user_id",
            sa.desc("added_at"),
            sa.desc("id"),
        ),
        sa.Index("idx_special_equipment_cart_product", "product_id"),
        sa.Index("idx_se_cart_items_parent", "parent_item_id"),
        sa.CheckConstraint(
            "custom_price IS NULL OR custom_price > 0",
            name="ck_special_equipment_cart_custom_price_positive",
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_se_cart_items_quantity_positive",
        ),
        sa.CheckConstraint(
            "quantity <= 1000",
            name="ck_se_cart_items_quantity_max",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=1,
        server_default=sa.text("1"),
    )
    allow_overstock: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        server_default=sa.false(),
    )
    parent_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_cart_items.id",
            name="fk_se_cart_items_parent",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    is_selected: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.true(), nullable=False
    )
    custom_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2))
    comment: Mapped[str | None] = mapped_column(sa.Text)
    equipments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False
    )
    services: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False
    )
    added_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        onupdate=sa.func.current_timestamp(),
        nullable=False,
    )


class SpecialEquipmentApplicationItem(Base):
    __tablename__ = "special_equipment_application_items"
    __table_args__ = (
        sa.UniqueConstraint(
            "application_id",
            "product_id",
            name="uq_special_equipment_application_product",
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
        sa.CheckConstraint(
            "item_role IN ('offer', 'attachment', 'component')",
            name="ck_se_application_items_role",
        ),
        sa.CheckConstraint(
            "price_status IN ('none', 'pending', 'set')",
            name="ck_se_application_items_price_status",
        ),
        sa.CheckConstraint(
            "(price_status IN ('none', 'pending') "
            "AND price_set_by IS NULL AND price_set_at IS NULL) OR "
            "(price_status = 'set' "
            "AND price_set_by IS NOT NULL AND price_set_at IS NOT NULL)",
            name="ck_se_application_items_price_status_consistency",
        ),
        sa.CheckConstraint(
            "price_status = 'none' OR "
            "(item_role <> 'component' AND ("
            "(price_status = 'pending' AND ("
            "(unit_price IS NULL AND total_price IS NULL) OR "
            "(unit_price > 0 AND total_price > 0))) OR "
            "(price_status = 'set' AND unit_price > 0 AND total_price > 0)))",
            name="ck_se_application_items_price_status_amounts",
        ),
        sa.CheckConstraint(
            "overstock_requested_quantity >= 0",
            name="ck_se_application_items_overstock_qty",
        ),
        sa.Index(
            "idx_special_equipment_application_items_application",
            "application_id",
            "id",
        ),
        sa.Index(
            "idx_special_equipment_application_items_product_status",
            "product_id",
            "item_status",
            "application_id",
        ),
        sa.Index(
            "idx_se_application_items_live_seller",
            "seller_company_id",
            "product_id",
            postgresql_where=sa.text(
                "seller_company_id IS NOT NULL "
                "AND item_status IN ('active', 'reserved')"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_cart_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    parent_group_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    item_role: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default="offer",
        server_default=sa.text("'offer'"),
    )
    seller_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
    )
    unit_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2))
    total_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2))
    currency_code: Mapped[str] = mapped_column(
        sa.String(3), server_default="RUB", nullable=False
    )
    item_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    comment: Mapped[str | None] = mapped_column(sa.Text)
    equipments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False
    )
    services: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False
    )
    leasing_purpose: Mapped[str | None] = mapped_column(sa.String(100))
    leasing_purposes: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    regions: Mapped[list[str]] = mapped_column(
        JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False
    )
    item_status: Mapped[str] = mapped_column(
        sa.String(20), server_default="active", nullable=False
    )
    overstock_requested_quantity: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default=sa.text("0"),
    )
    price_status: Mapped[str] = mapped_column(
        sa.String(20),
        default="none",
        server_default=sa.text("'none'"),
        nullable=False,
    )
    price_set_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            name="fk_se_application_items_price_set_by",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    price_set_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    reserve_expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        onupdate=sa.func.current_timestamp(),
        nullable=False,
    )


class SpecialEquipmentPriceChangeLog(Base):
    """Append-only audit of dealer-agreed application item prices."""

    __tablename__ = "special_equipment_price_change_log"
    __table_args__ = (
        sa.CheckConstraint(
            "new_price > 0",
            name="ck_se_price_change_log_new_price_positive",
        ),
        sa.CheckConstraint(
            "source IN ('dealer_ui', 'api')",
            name="ck_se_price_change_log_source",
        ),
        sa.Index(
            "idx_se_price_change_log_item_changed",
            "item_id",
            sa.desc("changed_at"),
            "id",
        ),
        sa.Index(
            "idx_se_price_change_log_changed_by",
            "changed_by",
            sa.desc("changed_at"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_application_items.id",
            name="fk_se_price_change_log_item",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    old_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2))
    new_price: Mapped[Decimal] = mapped_column(sa.Numeric(15, 2), nullable=False)
    changed_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            name="fk_se_price_change_log_changed_by",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    changed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(sa.String(32), nullable=False)


class SpecialEquipmentPurchaseOrder(Base):
    __tablename__ = "special_equipment_purchase_orders"
    __table_args__ = (
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_special_equipment_orders_user_idempotency",
        ),
        sa.UniqueConstraint(
            "refund_external_reference",
            name="uq_special_equipment_orders_refund_external_reference",
        ),
        sa.CheckConstraint(
            "purchase_type IN ('reservation', 'preorder', 'full_purchase', 'leasing')",
            name="ck_special_equipment_order_purchase_type",
        ),
        sa.CheckConstraint(
            "status IN ('payment_pending', 'reserved', 'preordered', 'purchased', "
            "'leasing_pending', 'leasing_active', 'cancellation_requested', "
            "'cancelled', 'expired', 'failed')",
            name="ck_special_equipment_order_status",
        ),
        sa.CheckConstraint(
            "(purchase_type = 'preorder' AND status IN ("
            "'preordered', 'cancellation_requested', 'cancelled', 'expired', 'failed')) "
            "OR (purchase_type <> 'preorder' AND status <> 'preordered')",
            name="ck_special_equipment_order_preorder_state",
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
        sa.Index(
            "idx_special_equipment_orders_user_created",
            "user_id",
            sa.desc("created_at"),
            sa.desc("id"),
        ),
        sa.Index(
            "idx_special_equipment_orders_status_hold",
            "status",
            "hold_expires_at",
        ),
        sa.Index(
            "idx_special_equipment_orders_product_status", "product_id", "status"
        ),
        sa.Index(
            "idx_se_orders_live_seller",
            "seller_company_id",
            "product_id",
            postgresql_where=sa.text(
                "seller_company_id IS NOT NULL AND status IN ("
                "'payment_pending', 'reserved', 'preordered', 'purchased', "
                "'leasing_pending', 'leasing_active', 'cancellation_requested')"
            ),
        ),
        sa.Index(
            "uq_special_equipment_orders_active_product",
            "product_id",
            unique=True,
            postgresql_where=sa.text(
                "purchase_type <> 'preorder' AND status IN ("
                "'payment_pending', 'reserved', 'purchased', "
                "'leasing_pending', 'leasing_active', 'cancellation_requested')"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    seller_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
    )
    leasing_application_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="SET NULL"),
    )
    purchase_type: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(sa.Numeric(15, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(sa.Numeric(15, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False
    )
    remaining_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False
    )
    currency_code: Mapped[str] = mapped_column(
        sa.String(3), server_default="RUB", nullable=False
    )
    down_payment_percent: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 2))
    item_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    hold_expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )
    cancellation_reason: Mapped[str | None] = mapped_column(sa.Text)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    refund_external_reference: Mapped[str | None] = mapped_column(sa.String(255))
    refunded_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2))
    refund_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
    )
    refund_confirmed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        onupdate=sa.func.current_timestamp(),
        nullable=False,
    )


class SpecialEquipmentOrderItem(Base):
    """Immutable concrete equipment allocation within a purchase order."""

    __tablename__ = "special_equipment_order_items"
    __table_args__ = (
        sa.UniqueConstraint(
            "purchase_order_id",
            "product_id",
            name="uq_se_order_items_order_product",
        ),
        sa.CheckConstraint(
            "item_role IN ('offer', 'attachment', 'component')",
            name="ck_se_order_items_role",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_se_order_items_position_nonnegative",
        ),
        sa.CheckConstraint(
            "unit_price >= 0",
            name="ck_se_order_items_unit_price_nonnegative",
        ),
        sa.Index(
            "idx_se_order_items_order_position",
            "purchase_order_id",
            "position",
            "id",
        ),
        sa.Index("idx_se_order_items_product", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_purchase_orders.id",
            name="fk_se_order_items_purchase_order",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_products.id",
            name="fk_se_order_items_product",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    source_cart_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    parent_group_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    item_role: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default="offer",
        server_default=sa.text("'offer'"),
    )
    position: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default=sa.text("0"),
    )
    unit_price: Mapped[Decimal] = mapped_column(sa.Numeric(15, 2), nullable=False)
    item_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )


class SpecialEquipmentPayment(Base):
    __tablename__ = "special_equipment_payments"
    __table_args__ = (
        sa.UniqueConstraint(
            "purchase_order_id",
            "idempotency_key",
            name="uq_special_equipment_payments_order_idempotency",
        ),
        sa.UniqueConstraint(
            "gateway_transaction_id",
            name="uq_special_equipment_payments_gateway_transaction",
        ),
        sa.CheckConstraint(
            "payment_type IN ('reservation', 'preorder', 'full_purchase', "
            "'remaining_balance', 'leasing', 'leasing_monthly')",
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
            "amount > 0",
            name="ck_special_equipment_payment_amount_positive",
        ),
        sa.Index(
            "idx_special_equipment_payments_order_created",
            "purchase_order_id",
            "created_at",
            "id",
        ),
        sa.Index(
            "idx_special_equipment_payments_status_expires",
            "status",
            "expires_at",
        ),
        sa.Index(
            "idx_special_equipment_payments_fiscal_updated",
            "fiscal_status",
            "updated_at",
        ),
        sa.Index(
            "idx_special_equipment_payments_receipt_retry",
            "receipt_ingestion_next_retry_at",
            "updated_at",
            postgresql_where=sa.text(
                "receipt_storage_key IS NULL "
                "AND fiscal_status = 'completed' "
                "AND receipt_ingestion_status IN ('pending', 'failed', 'processing')"
            ),
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
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payment_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(15, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(24), server_default="pending", nullable=False
    )
    payment_method: Mapped[str | None] = mapped_column(sa.String(24))
    gateway_transaction_id: Mapped[str | None] = mapped_column(sa.String(255))
    gateway_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    receipt_storage_key: Mapped[str | None] = mapped_column(sa.String(500))
    receipt_ingestion_status: Mapped[str | None] = mapped_column(sa.String(20))
    receipt_ingestion_retry_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("0"), nullable=False
    )
    receipt_ingestion_error_code: Mapped[str | None] = mapped_column(sa.String(100))
    receipt_ingestion_next_retry_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    fiscal_status: Mapped[str | None] = mapped_column(sa.String(30))
    fiscal_receipt_id: Mapped[str | None] = mapped_column(sa.String(255))
    fiscal_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    fiscal_retry_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("0"), nullable=False
    )
    fiscal_error_message: Mapped[str | None] = mapped_column(sa.Text)
    idempotency_key: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        onupdate=sa.func.current_timestamp(),
        nullable=False,
    )


class SpecialEquipmentPaymentCallbackInbox(Base):
    """Durable, redacted inbox for verified ModulBank callbacks."""

    __tablename__ = "special_equipment_payment_callback_inbox"
    __table_args__ = (
        sa.UniqueConstraint(
            "event_key",
            name="uq_special_equipment_callback_inbox_event_key",
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
        sa.Index(
            "idx_special_equipment_callback_inbox_retry",
            "next_retry_at",
            "received_at",
            "id",
            postgresql_where=sa.text("status IN ('pending', 'retry')"),
        ),
        sa.Index(
            "idx_special_equipment_callback_inbox_manual_review",
            sa.desc("received_at"),
            sa.desc("id"),
            postgresql_where=sa.text("status = 'manual_review'"),
        ),
        sa.Index(
            "idx_special_equipment_callback_inbox_transaction",
            "gateway_transaction_id",
            "received_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    event_key: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    gateway_transaction_id: Mapped[str] = mapped_column(
        sa.String(255), nullable=False
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_payments.id", ondelete="SET NULL"),
    )
    signature_digest: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20), server_default="pending", nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("0"), nullable=False
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )
    lease_token: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    lease_until: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )
    last_error_code: Mapped[str | None] = mapped_column(sa.String(100))
    manual_review_reason: Mapped[str | None] = mapped_column(sa.String(100))
    received_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        onupdate=sa.func.current_timestamp(),
        nullable=False,
    )


class SpecialEquipmentLeasingPaymentSchedule(Base):
    __tablename__ = "special_equipment_leasing_payment_schedule"
    __table_args__ = (
        sa.UniqueConstraint(
            "purchase_order_id",
            "payment_number",
            name="uq_special_equipment_schedule_order_number",
        ),
        sa.Index(
            "idx_special_equipment_schedule_order_due",
            "purchase_order_id",
            "due_date",
            "id",
        ),
        sa.Index(
            "idx_special_equipment_schedule_unpaid_due",
            "due_date",
            postgresql_where=sa.text("is_paid = false"),
        ),
        sa.CheckConstraint(
            "payment_number > 0",
            name="ck_special_equipment_schedule_payment_number_positive",
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_special_equipment_schedule_amount_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    payment_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(15, 2), nullable=False)
    principal: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2))
    interest: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_payments.id", ondelete="SET NULL"),
    )
    is_paid: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        onupdate=sa.func.current_timestamp(),
        nullable=False,
    )
