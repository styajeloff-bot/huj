"""Add sub_roles and permissions to user_companies

Revision ID: 007
Revises: 006
Create Date: 2026-05-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add sub_role column
    op.add_column(
        "user_companies",
        sa.Column("sub_role", sa.String(50), nullable=True),
    )
    # Add permission columns
    op.add_column(
        "user_companies",
        sa.Column(
            "can_view_applications",
            sa.Boolean,
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "user_companies",
        sa.Column(
            "can_create_applications",
            sa.Boolean,
            server_default=sa.false(),
            nullable=False,
        ),
    )

    # Backfill existing user_companies rows: all current members are treated as administrators
    op.execute(
        "UPDATE user_companies "
        "SET sub_role = 'administrator', "
        "    can_view_applications = true, "
        "    can_create_applications = true"
    )

    # Backfill legacy users (users.company_id set but no user_companies row)
    op.execute(
        "INSERT INTO user_companies (user_id, company_id, sub_role, can_view_applications, can_create_applications) "
        "SELECT u.id, u.company_id, 'administrator', true, true "
        "FROM users u "
        "WHERE u.company_id IS NOT NULL "
        "  AND NOT EXISTS (SELECT 1 FROM user_companies uc WHERE uc.user_id = u.id AND uc.company_id = u.company_id) "
        "ON CONFLICT (user_id, company_id) DO NOTHING"
    )

    # Index for sub_role lookups
    op.create_index(
        "idx_user_companies_sub_role",
        "user_companies",
        ["sub_role"],
    )


def downgrade() -> None:
    op.drop_index("idx_user_companies_sub_role", table_name="user_companies")
    op.drop_column("user_companies", "can_create_applications")
    op.drop_column("user_companies", "can_view_applications")
    op.drop_column("user_companies", "sub_role")
