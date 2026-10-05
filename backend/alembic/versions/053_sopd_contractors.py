"""sopd contractors

Revision ID: 053
Revises: 052
Create Date: 2026-06-17 18:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "053"
down_revision: str | None = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contractors",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("inn", sa.String(length=12), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inn", name="uq_contractors_inn"),
    )
    op.create_index("idx_contractors_inn", "contractors", ["inn"])
    op.create_index("idx_contractors_name", "contractors", ["name"])

    op.create_table(
        "leasing_company_contractors",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "leasing_company_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "contractor_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["contractor_id"], ["contractors.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["leasing_company_id"],
            ["leasing_companies.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "leasing_company_id",
            "contractor_id",
            name="uq_leasing_company_contractors_pair",
        ),
    )
    op.create_index(
        "idx_leasing_company_contractors_lc_id",
        "leasing_company_contractors",
        ["leasing_company_id"],
    )
    op.create_index(
        "idx_leasing_company_contractors_contractor_id",
        "leasing_company_contractors",
        ["contractor_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_leasing_company_contractors_contractor_id",
        table_name="leasing_company_contractors",
    )
    op.drop_index(
        "idx_leasing_company_contractors_lc_id",
        table_name="leasing_company_contractors",
    )
    op.drop_table("leasing_company_contractors")
    op.drop_index("idx_contractors_name", table_name="contractors")
    op.drop_index("idx_contractors_inn", table_name="contractors")
    op.drop_table("contractors")
