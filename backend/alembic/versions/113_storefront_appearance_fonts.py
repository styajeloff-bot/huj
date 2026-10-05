"""Add storefront appearance and administrator font catalog.

Revision ID: 113
Revises: 112
Create Date: 2026-09-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "113"
down_revision: str | None = "112"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_storefront_fonts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column(
            "content_type",
            sa.String(length=64),
            nullable=False,
            server_default="font/woff2",
        ),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
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
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_catalog_storefront_fonts_created_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_catalog_storefront_fonts"),
        sa.UniqueConstraint(
            "storage_key", name="uq_catalog_storefront_fonts_storage_key"
        ),
        sa.UniqueConstraint(
            "checksum_sha256", name="uq_catalog_storefront_fonts_checksum_sha256"
        ),
    )
    op.create_index(
        "uq_catalog_storefront_fonts_name_lower",
        "catalog_storefront_fonts",
        [sa.text("lower(name)")],
        unique=True,
    )

    for name, default in (
        ("appearance_primary_color", "#3367BD"),
        ("appearance_background_color", "#F9FAFB"),
        ("appearance_surface_color", "#FFFFFF"),
        ("appearance_text_color", "#111827"),
    ):
        op.add_column(
            "catalog_storefronts",
            sa.Column(
                name,
                sa.String(length=7),
                nullable=False,
                server_default=default,
            ),
        )
    op.add_column(
        "catalog_storefronts",
        sa.Column(
            "appearance_border_radius",
            sa.String(length=16),
            nullable=False,
            server_default="medium",
        ),
    )
    op.add_column(
        "catalog_storefronts",
        sa.Column("font_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_catalog_storefronts_appearance_primary_color",
        "catalog_storefronts",
        "appearance_primary_color ~ '^#[0-9A-F]{6}$'",
    )
    op.create_check_constraint(
        "ck_catalog_storefronts_appearance_background_color",
        "catalog_storefronts",
        "appearance_background_color ~ '^#[0-9A-F]{6}$'",
    )
    op.create_check_constraint(
        "ck_catalog_storefronts_appearance_surface_color",
        "catalog_storefronts",
        "appearance_surface_color ~ '^#[0-9A-F]{6}$'",
    )
    op.create_check_constraint(
        "ck_catalog_storefronts_appearance_text_color",
        "catalog_storefronts",
        "appearance_text_color ~ '^#[0-9A-F]{6}$'",
    )
    op.create_check_constraint(
        "ck_catalog_storefronts_appearance_border_radius",
        "catalog_storefronts",
        "appearance_border_radius IN ('none', 'small', 'medium', 'large')",
    )
    op.create_foreign_key(
        "fk_catalog_storefronts_font_id",
        "catalog_storefronts",
        "catalog_storefront_fonts",
        ["font_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_catalog_storefronts_font_id",
        "catalog_storefronts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_catalog_storefronts_appearance_border_radius",
        "catalog_storefronts",
        type_="check",
    )
    for name in (
        "appearance_text_color",
        "appearance_surface_color",
        "appearance_background_color",
        "appearance_primary_color",
    ):
        op.drop_constraint(
            f"ck_catalog_storefronts_{name}",
            "catalog_storefronts",
            type_="check",
        )
    op.drop_column("catalog_storefronts", "font_id")
    op.drop_column("catalog_storefronts", "appearance_border_radius")
    op.drop_column("catalog_storefronts", "appearance_text_color")
    op.drop_column("catalog_storefronts", "appearance_surface_color")
    op.drop_column("catalog_storefronts", "appearance_background_color")
    op.drop_column("catalog_storefronts", "appearance_primary_color")
    op.drop_index(
        "uq_catalog_storefront_fonts_name_lower",
        table_name="catalog_storefront_fonts",
    )
    op.drop_table("catalog_storefront_fonts")
