"""Durable idempotency receipts for guest cart transfers."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from domain.storefronts import DEFAULT_STOREFRONT_ID
from infrastructure.models import Base


class GuestCartTransfer(Base):
    """Records an applied guest-cart operation for one authenticated user."""

    __tablename__ = "guest_cart_transfers"
    __table_args__ = (
        sa.PrimaryKeyConstraint(
            "user_id",
            "storefront_id",
            "transfer_id",
            name="pk_guest_cart_transfers",
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_guest_cart_transfers_quantity_positive",
        ),
        sa.Index("idx_guest_cart_transfers_storefront_id", "storefront_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    storefront_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "catalog_storefronts.id",
            name="fk_guest_cart_transfers_storefront_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        default=lambda: DEFAULT_STOREFRONT_ID,
        server_default=sa.text("'00000000-0000-0000-0000-000000000001'::uuid"),
    )
    transfer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    allow_overstock: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())
    quantity: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    equipments: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    )
    services: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    )
