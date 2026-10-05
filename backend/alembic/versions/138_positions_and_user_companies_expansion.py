"""Positions catalog and user_companies multi-company expansion.

Revision ID: 138
Revises: 137
Create Date: 2026-09-28 05:15:00
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "138"
down_revision = "137"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create positions table
    positions_table = op.create_table(
        "positions",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(100), unique=True, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_positions_is_active", "positions", ["is_active"])

    # 2. Seed initial positions
    op.bulk_insert(
        positions_table,
        [
            {
                "id": uuid.uuid4(),
                "name": "Менеджер",
                "code": "manager",
                "is_active": True,
            },
            {
                "id": uuid.uuid4(),
                "name": "Супервайзер",
                "code": "supervisor",
                "is_active": True,
            },
        ],
    )

    # 3. Add columns to user_companies
    op.add_column(
        "user_companies",
        sa.Column(
            "role",
            sa.String(50),
            server_default="client",
            nullable=False,
        ),
    )
    op.add_column(
        "user_companies",
        sa.Column("position_id", PGUUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "user_companies",
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.add_column(
        "user_companies",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )

    # 4. Foreign key and indexes on user_companies
    op.create_foreign_key(
        "fk_user_companies_position_id_positions",
        "user_companies",
        "positions",
        ["position_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_user_companies_role", "user_companies", ["role"])
    op.create_index("idx_user_companies_is_active", "user_companies", ["is_active"])
    op.create_index("idx_user_companies_position_id", "user_companies", ["position_id"])

    # 5. Backfill user_companies.role from users.role
    op.execute(
        sa.text(
            """
            UPDATE user_companies
            SET role = users.role::text,
                is_active = true,
                updated_at = now()
            FROM users
            WHERE user_companies.user_id = users.id
              AND users.role::text IN ('dealer', 'distributor', 'leasing_company');
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE user_companies
            SET role = 'client',
                is_active = true,
                updated_at = now()
            WHERE role IS NULL OR role NOT IN ('dealer', 'distributor', 'leasing_company');
            """
        )
    )


def downgrade() -> None:
    op.drop_index("idx_user_companies_position_id", table_name="user_companies")
    op.drop_index("idx_user_companies_is_active", table_name="user_companies")
    op.drop_index("idx_user_companies_role", table_name="user_companies")
    op.drop_constraint(
        "fk_user_companies_position_id_positions",
        "user_companies",
        type_="foreignkey",
    )
    op.drop_column("user_companies", "updated_at")
    op.drop_column("user_companies", "is_active")
    op.drop_column("user_companies", "position_id")
    op.drop_column("user_companies", "role")

    op.drop_index("idx_positions_is_active", table_name="positions")
    op.drop_table("positions")
