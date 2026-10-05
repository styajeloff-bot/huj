"""SQLAlchemy ORM models for the Vehicle Exchange (Биржа ТС) domain.

Covers dealer options reference, leasing company carts & requests, dealer bids
with KP (commercial proposal) flow, and their associated options/warehouses/files.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, synonym

from infrastructure.models import Base


class DealerOption(Base):
    """Global reference of extra dealer services (winter tires, delivery, etc)."""

    __tablename__ = "dealer_options"
    __table_args__ = (
        UniqueConstraint("name", name="dealer_options_name_unique"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, server_default=sa.func.current_timestamp()
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, server_default=sa.func.current_timestamp()
    )


class ExchangeCartItem(Base):
    """A vehicle added to an LC user's exchange cart before batch submission."""

    __tablename__ = "exchange_cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="exchange_cart_items_user_vehicle_unique"),
        sa.Index("idx_exchange_cart_items_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    expiration_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    discount_type: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    discount_value: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    file_url: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    file_name: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    selected_support_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)),
        nullable=False,
        server_default=sa.text("'{}'::uuid[]"),
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, server_default=sa.func.current_timestamp()
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, server_default=sa.func.current_timestamp()
    )


class ExchangeCartItemWarehouse(Base):
    """Warehouses targeted for a specific cart item (many-to-many)."""

    __tablename__ = "exchange_cart_item_warehouses"
    __table_args__ = (
        UniqueConstraint(
            "cart_item_id", "warehouse_id",
            name="exchange_cart_item_warehouses_unique",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cart_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("exchange_cart_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
    )


class ExchangeCartItemOption(Base):
    """Dealer options selected for a specific cart item (many-to-many)."""

    __tablename__ = "exchange_cart_item_options"
    __table_args__ = (
        UniqueConstraint(
            "cart_item_id", "dealer_option_id",
            name="exchange_cart_item_options_unique",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cart_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("exchange_cart_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    dealer_option_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("dealer_options.id", ondelete="CASCADE"),
        nullable=False,
    )


class ExchangeCartItemDealerComment(Base):
    """Per-dealer comment attached to a cart item."""

    __tablename__ = "exchange_cart_item_dealer_comments"
    __table_args__ = (
        UniqueConstraint(
            "cart_item_id", "dealer_id",
            name="exchange_cart_item_dealer_comments_unique",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cart_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("exchange_cart_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    dealer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class ExchangeRequest(Base):
    """A request to dealers for a specific vehicle (one per cart item after submission)."""

    __tablename__ = "exchange_requests"
    __table_args__ = (
        sa.Index("idx_exchange_requests_lc_user", "lc_user_id"),
        sa.Index("idx_exchange_requests_lc_company", "lc_company_id"),
        sa.Index("idx_exchange_requests_expiration", "expiration_at"),
        sa.Index("idx_exchange_requests_status", "status"),
        sa.Index("idx_exchange_requests_product", "product_id"),
        sa.Index("idx_exchange_requests_batch", "batch_number", "batch_index"),
        sa.Index("idx_exchange_requests_distributor_id", "distributor_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lc_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    lc_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_products.id"),
        nullable=False,
    )
    vehicle_id = synonym("product_id")
    distributor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    quantity: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    expiration_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    discount_type: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    discount_value: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    file_url: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    file_name: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False, server_default=sa.text("'open'"))
    accepted_bid_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "exchange_bids.id",
            ondelete="SET NULL",
            name="fk_exchange_requests_accepted_bid",
            use_alter=True,
        ),
        nullable=True,
    )
    selected_support_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)),
        nullable=False,
        server_default=sa.text("'{}'::uuid[]"),
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, server_default=sa.func.current_timestamp()
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, server_default=sa.func.current_timestamp()
    )
    batch_number: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    batch_index: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)


class ExchangeRequestOption(Base):
    """Dealer options requested for a given exchange request (many-to-many)."""

    __tablename__ = "exchange_request_options"
    __table_args__ = (
        UniqueConstraint(
            "request_id", "dealer_option_id",
            name="exchange_request_options_unique",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("exchange_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    dealer_option_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("dealer_options.id", ondelete="CASCADE"),
        nullable=False,
    )


class ExchangeRequestWarehouse(Base):
    """Mapping of an exchange request to a target warehouse + responsible dealer."""

    __tablename__ = "exchange_request_warehouses"
    __table_args__ = (
        UniqueConstraint(
            "request_id", "warehouse_id",
            name="exchange_request_warehouses_unique",
        ),
        sa.Index("idx_exchange_request_warehouses_dealer", "dealer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("exchange_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
    )
    dealer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id"),
        nullable=False,
    )


class ExchangeRequestDealerComment(Base):
    """Per-dealer comment attached to an exchange request."""

    __tablename__ = "exchange_request_dealer_comments"
    __table_args__ = (
        UniqueConstraint(
            "request_id", "dealer_id",
            name="exchange_request_dealer_comments_unique",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("exchange_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    dealer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class ExchangeRequestFile(Base):
    """Files attached to an exchange request (KP uploads, etc)."""

    __tablename__ = "exchange_request_files"
    __table_args__ = (
        sa.Index("idx_exchange_request_files_request", "request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("exchange_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    dealer_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    file_url: Mapped[str] = mapped_column(sa.String(1000), nullable=False)
    file_name: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(sa.String(50), nullable=False, server_default=sa.text("'kp'"))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id"),
        nullable=False,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, server_default=sa.func.current_timestamp()
    )


class ExchangeBid(Base):
    """A dealer's bid on an exchange request, with KP flow state."""

    dealer_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )

    __tablename__ = "exchange_bids"
    __table_args__ = (
        UniqueConstraint("request_id", "dealer_id", name="exchange_bids_request_dealer_unique"),
        sa.Index("idx_exchange_bids_request", "request_id"),
        sa.Index("idx_exchange_bids_dealer", "dealer_id"),
        sa.Index("idx_exchange_bids_kp_status", "kp_status"),
        sa.Index("idx_exchange_bids_distributor_id", "distributor_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("exchange_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    dealer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    distributor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    price: Mapped[sa.Numeric] = mapped_column(sa.Numeric(15, 2), nullable=False)
    comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_accepted: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, server_default=sa.func.current_timestamp()
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, server_default=sa.func.current_timestamp()
    )
    kp_file_url: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    kp_file_name: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    kp_status: Mapped[str] = mapped_column(sa.String(20), nullable=False, server_default=sa.text("'none'"))
    kp_dealer_comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    kp_sent_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    kp_responded_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    quantity: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    bid_file_url: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    bid_file_name: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)


class ExchangeBidOption(Base):
    """Dealer options offered within a specific bid (many-to-many)."""

    __tablename__ = "exchange_bid_options"
    __table_args__ = (
        UniqueConstraint(
            "bid_id", "dealer_option_id",
            name="exchange_bid_options_unique",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bid_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("exchange_bids.id", ondelete="CASCADE"),
        nullable=False,
    )
    dealer_option_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("dealer_options.id", ondelete="CASCADE"),
        nullable=False,
    )


class ExchangeBidComment(Base):
    """Comment thread on an exchange bid."""

    __tablename__ = "exchange_bid_comments"
    __table_args__ = (
        sa.Index("idx_exchange_bid_comments_bid", "bid_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bid_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("exchange_bids.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    comment: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, server_default=sa.func.current_timestamp()
    )
