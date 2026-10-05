"""Add created_by to leasing_applications

Revision ID: 006
Revises: 005
Create Date: 2026-05-21 07:05:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leasing_applications",
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_leasing_applications_created_by",
        "leasing_applications",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_leasing_applications_created_by",
        "leasing_applications",
        type_="foreignkey",
    )
    op.drop_column("leasing_applications", "created_by")
