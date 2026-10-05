"""Add symmetric support-program compatibility.

Revision ID: 105
Revises: 104
Create Date: 2026-08-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "105"
down_revision: str | None = "104"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "support_programs",
        sa.Column(
            "is_compatible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "support_program_compatibilities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "support_program_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "compatible_support_program_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "support_program_id < compatible_support_program_id",
            name="ck_support_program_compatibilities_canonical_order",
        ),
        sa.ForeignKeyConstraint(
            ["support_program_id"],
            ["support_programs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["compatible_support_program_id"],
            ["support_programs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "support_program_id",
            "compatible_support_program_id",
            name="uq_support_program_compatibilities_pair",
        ),
    )
    op.create_index(
        "idx_support_program_compatibilities_compatible_program",
        "support_program_compatibilities",
        ["compatible_support_program_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_support_program_compatibilities_compatible_program",
        table_name="support_program_compatibilities",
    )
    op.drop_table("support_program_compatibilities")
    op.drop_column("support_programs", "is_compatible")
