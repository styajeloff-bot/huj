"""Add source_ref and index to special_equipment_product_images, drop storage_key unique constraint.

Revision ID: 135
Revises: 134
Create Date: 2026-09-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "135"
down_revision = "134"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "special_equipment_product_images",
        sa.Column("source_ref", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_special_equipment_product_images_product_id_source_ref",
        "special_equipment_product_images",
        ["product_id", "source_ref"],
        unique=False,
    )
    op.drop_constraint(
        "uq_special_equipment_product_images_storage_key",
        "special_equipment_product_images",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_special_equipment_product_images_storage_key",
        "special_equipment_product_images",
        ["storage_key"],
    )
    op.drop_index(
        "ix_special_equipment_product_images_product_id_source_ref",
        table_name="special_equipment_product_images",
    )
    op.drop_column("special_equipment_product_images", "source_ref")
