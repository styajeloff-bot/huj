"""Add role-level workspace section visibility overrides.

Revision ID: 084
Revises: 083
Create Date: 2026-08-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "084"
down_revision: str | None = "083"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_role_section_visibility",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("section_key", sa.String(length=64), nullable=False),
        sa.Column(
            "is_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
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
            "role IN ('leasing_company', 'dealer', 'distributor')",
            name="ck_workspace_role_section_visibility_role",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name="fk_workspace_role_section_visibility_updated_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_workspace_role_section_visibility",
        ),
        sa.UniqueConstraint(
            "role",
            "section_key",
            name="uq_workspace_role_section_visibility_role_section_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("workspace_role_section_visibility")
