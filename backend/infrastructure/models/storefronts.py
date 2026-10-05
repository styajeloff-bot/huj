"""ORM models for catalog storefront configuration."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from domain.storefronts import (
    DEFAULT_STOREFRONT_BACKGROUND_COLOR,
    DEFAULT_STOREFRONT_BORDER_RADIUS,
    DEFAULT_STOREFRONT_PRIMARY_COLOR,
    DEFAULT_STOREFRONT_SURFACE_COLOR,
    DEFAULT_STOREFRONT_TEXT_COLOR,
)
from infrastructure.models import Base


class StorefrontFont(Base):
    __tablename__ = "catalog_storefront_fonts"
    __table_args__ = (
        sa.CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 120",
            name="ck_catalog_storefront_fonts_name",
        ),
        sa.CheckConstraint(
            "size_bytes > 0", name="ck_catalog_storefront_fonts_size_bytes"
        ),
        sa.CheckConstraint(
            "content_type = 'font/woff2'",
            name="ck_catalog_storefront_fonts_content_type",
        ),
        sa.CheckConstraint(
            "checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_catalog_storefront_fonts_checksum_sha256",
        ),
        sa.UniqueConstraint(
            "storage_key", name="uq_catalog_storefront_fonts_storage_key"
        ),
        sa.UniqueConstraint(
            "checksum_sha256", name="uq_catalog_storefront_fonts_checksum_sha256"
        ),
        sa.Index(
            "uq_catalog_storefront_fonts_name_lower",
            sa.func.lower(sa.column("name")),
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    original_filename: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(
        sa.String(64), nullable=False, server_default="font/woff2"
    )
    size_bytes: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_catalog_storefront_fonts_created_by",
        ),
        nullable=True,
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


class Storefront(Base):
    __tablename__ = "catalog_storefronts"
    __table_args__ = (
        sa.CheckConstraint(
            "(is_default AND slug IS NULL) OR (NOT is_default AND slug IS NOT NULL)",
            name="ck_catalog_storefronts_default_slug",
        ),
        sa.CheckConstraint(
            "slug IS NULL OR slug ~ '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$'",
            name="ck_catalog_storefronts_slug_format",
        ),
        sa.CheckConstraint("version > 0", name="ck_catalog_storefronts_version"),
        sa.CheckConstraint(
            "home_page_key IN ('home', 'about', 'special_equipment_catalog')",
            name="ck_catalog_storefronts_home_page_key",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(public_page_titles) = 'object' "
            "AND public_page_titles ?& ARRAY['home', 'about', "
            "'special_equipment_catalog'] "
            "AND (public_page_titles - ARRAY['home', 'about', "
            "'special_equipment_catalog']) = '{}'::jsonb "
            "AND jsonb_typeof(public_page_titles -> 'home') = 'string' "
            "AND jsonb_typeof(public_page_titles -> 'about') = 'string' "
            "AND jsonb_typeof(public_page_titles -> "
            "'special_equipment_catalog') = 'string'",
            name="ck_catalog_storefronts_public_page_titles",
        ),
        sa.CheckConstraint(
            "appearance_primary_color ~ '^#[0-9A-F]{6}$'",
            name="ck_catalog_storefronts_appearance_primary_color",
        ),
        sa.CheckConstraint(
            "appearance_background_color ~ '^#[0-9A-F]{6}$'",
            name="ck_catalog_storefronts_appearance_background_color",
        ),
        sa.CheckConstraint(
            "appearance_surface_color ~ '^#[0-9A-F]{6}$'",
            name="ck_catalog_storefronts_appearance_surface_color",
        ),
        sa.CheckConstraint(
            "appearance_text_color ~ '^#[0-9A-F]{6}$'",
            name="ck_catalog_storefronts_appearance_text_color",
        ),
        sa.CheckConstraint(
            "appearance_border_radius IN ('none', 'small', 'medium', 'large')",
            name="ck_catalog_storefronts_appearance_border_radius",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(appearance_color_overrides) = 'object'",
            name="ck_catalog_storefronts_appearance_color_overrides",
        ),
        sa.Index(
            "uq_catalog_storefronts_slug_lower",
            sa.func.lower(sa.column("slug")),
            unique=True,
            postgresql_where=sa.text("slug IS NOT NULL"),
        ),
        sa.Index(
            "uq_catalog_storefronts_default",
            "is_default",
            unique=True,
            postgresql_where=sa.text("is_default = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    slug: Mapped[str | None] = mapped_column(sa.String(63), nullable=True)
    is_default: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    logo_storage_key: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    logo_content_type: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    home_page_key: Mapped[str] = mapped_column(
        sa.String(64), nullable=False, server_default="home"
    )
    public_page_titles: Mapped[dict[str, str]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "home": "Главная",
            "about": "О нас",
            "special_equipment_catalog": "Спецтехника",
        },
        server_default=sa.text(
            "'{\"home\": \"Главная\", \"about\": \"О нас\", "
            "\"special_equipment_catalog\": \"Спецтехника\"}'::jsonb"
        ),
    )
    public_ui_updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_catalog_storefronts_public_ui_updated_by",
        ),
        nullable=True,
    )
    public_ui_updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    )
    appearance_primary_color: Mapped[str] = mapped_column(
        sa.String(7),
        nullable=False,
        server_default=DEFAULT_STOREFRONT_PRIMARY_COLOR,
    )
    appearance_background_color: Mapped[str] = mapped_column(
        sa.String(7),
        nullable=False,
        server_default=DEFAULT_STOREFRONT_BACKGROUND_COLOR,
    )
    appearance_surface_color: Mapped[str] = mapped_column(
        sa.String(7),
        nullable=False,
        server_default=DEFAULT_STOREFRONT_SURFACE_COLOR,
    )
    appearance_text_color: Mapped[str] = mapped_column(
        sa.String(7),
        nullable=False,
        server_default=DEFAULT_STOREFRONT_TEXT_COLOR,
    )
    appearance_border_radius: Mapped[str] = mapped_column(
        sa.String(16),
        nullable=False,
        server_default=DEFAULT_STOREFRONT_BORDER_RADIUS,
    )
    appearance_color_overrides: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    font_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "catalog_storefront_fonts.id",
            ondelete="SET NULL",
            name="fk_catalog_storefronts_font_id",
        ),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
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


class StorefrontWarehouse(Base):
    __tablename__ = "catalog_storefront_warehouses"
    __table_args__ = (
        sa.PrimaryKeyConstraint(
            "storefront_id",
            "warehouse_id",
            name="pk_catalog_storefront_warehouses",
        ),
        sa.Index("idx_catalog_storefront_warehouses_warehouse_id", "warehouse_id"),
    )

    storefront_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("catalog_storefronts.id", ondelete="CASCADE"),
        nullable=False,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
