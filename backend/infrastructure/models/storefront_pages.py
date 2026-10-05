"""ORM models for storefront constructor pages, revisions, and templates."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class StorefrontPage(Base):
    """Storefront page constructed via page builder."""

    __tablename__ = "catalog_storefront_pages"
    __table_args__ = (
        sa.CheckConstraint(
            "version > 0",
            name="ck_catalog_storefront_pages_version",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published')",
            name="ck_catalog_storefront_pages_status",
        ),
        sa.UniqueConstraint(
            "storefront_id",
            "page_key",
            name="uq_catalog_storefront_pages_storefront_page_key",
        ),
        sa.Index(
            "idx_catalog_storefront_pages_storefront_slug",
            "storefront_id",
            "slug",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    storefront_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "catalog_storefronts.id",
            ondelete="CASCADE",
            name="fk_catalog_storefront_pages_storefront_id",
        ),
        nullable=False,
    )
    page_key: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    slug: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    is_system: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false(), default=False
    )
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default="draft", default="draft"
    )
    version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="1", default=1
    )
    draft_layout: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    published_layout: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_catalog_storefront_pages_updated_by",
        ),
        nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
        onupdate=sa.func.current_timestamp(),
    )


class StorefrontPageRevision(Base):
    """Historical snapshot revision of a storefront page layout."""

    __tablename__ = "catalog_storefront_page_revisions"
    __table_args__ = (
        sa.Index(
            "idx_catalog_storefront_page_revisions_page_version",
            "page_id",
            "version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "catalog_storefront_pages.id",
            ondelete="CASCADE",
            name="fk_catalog_storefront_page_revisions_page_id",
        ),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    summary: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    layout_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_catalog_storefront_page_revisions_created_by",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    )


class StorefrontTemplate(Base):
    """Ready-to-use template for storefront page constructor."""

    __tablename__ = "catalog_storefront_templates"
    __table_args__ = (
        sa.UniqueConstraint(
            "code",
            name="uq_catalog_storefront_templates_code",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    category: Mapped[str] = mapped_column(
        sa.String(64), nullable=False, server_default="general", default="general"
    )
    preview_image_url: Mapped[str | None] = mapped_column(
        sa.String(512), nullable=True
    )
    layout: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true(), default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
        onupdate=sa.func.current_timestamp(),
    )
