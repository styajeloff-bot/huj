"""Rebuild dealer groups as distributor company groups.

Revision ID: 066
Revises: 065
Create Date: 2026-07-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "066"
down_revision: str | None = "065"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "distributors",
        sa.Column(
            "can_manage_dealer_groups",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )

    # The old implementation stored user ids in dealer_group_members and had no
    # distributor ownership. The new contract is company-based, so old links are
    # intentionally not migrated as active targeting data.
    op.execute("DELETE FROM support_program_dealer_groups")
    op.execute("UPDATE support_programs SET dealer_group_id = NULL")
    op.drop_table("dealer_group_members")
    op.drop_constraint("uq_dealer_groups_name", "dealer_groups", type_="unique")
    op.execute("DELETE FROM dealer_groups")

    op.add_column(
        "dealer_groups",
        sa.Column("distributor_company_id", sa.UUID(), nullable=False),
    )
    op.add_column(
        "dealer_groups",
        sa.Column("created_by", sa.UUID(), nullable=False),
    )
    op.add_column(
        "dealer_groups",
        sa.Column("updated_by", sa.UUID(), nullable=True),
    )
    op.alter_column(
        "dealer_groups",
        "is_active",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.true(),
    )
    op.create_foreign_key(
        "dealer_groups_distributor_company_id_fkey",
        "dealer_groups",
        "companies",
        ["distributor_company_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "dealer_groups_created_by_fkey",
        "dealer_groups",
        "users",
        ["created_by"],
        ["id"],
    )
    op.create_foreign_key(
        "dealer_groups_updated_by_fkey",
        "dealer_groups",
        "users",
        ["updated_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_dealer_groups_distributor",
        "dealer_groups",
        ["distributor_company_id"],
    )
    op.create_index("idx_dealer_groups_active", "dealer_groups", ["is_active"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_dealer_groups_distributor_name_active
        ON dealer_groups (distributor_company_id, lower(name))
        WHERE is_active = true
        """
    )

    op.create_table(
        "dealer_group_members",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "dealer_group_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "dealer_company_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="dealer_group_members_created_by_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["dealer_company_id"],
            ["companies.id"],
            name="dealer_group_members_dealer_company_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dealer_group_id"],
            ["dealer_groups.id"],
            name="dealer_group_members_dealer_group_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dealer_group_id",
            "dealer_company_id",
            name="uq_dealer_group_members_group_dealer_company",
        ),
    )
    op.create_index(
        "idx_dealer_group_members_group",
        "dealer_group_members",
        ["dealer_group_id"],
    )
    op.create_index(
        "idx_dealer_group_members_dealer_company",
        "dealer_group_members",
        ["dealer_company_id"],
    )


def downgrade() -> None:
    op.execute("DELETE FROM support_program_dealer_groups")
    op.execute("UPDATE support_programs SET dealer_group_id = NULL")
    op.execute("DELETE FROM dealer_groups")

    op.drop_index(
        "idx_dealer_group_members_dealer_company",
        table_name="dealer_group_members",
    )
    op.drop_index("idx_dealer_group_members_group", table_name="dealer_group_members")
    op.drop_table("dealer_group_members")

    op.drop_index("uq_dealer_groups_distributor_name_active", table_name="dealer_groups")
    op.drop_index("idx_dealer_groups_active", table_name="dealer_groups")
    op.drop_index("idx_dealer_groups_distributor", table_name="dealer_groups")
    op.drop_constraint(
        "dealer_groups_updated_by_fkey",
        "dealer_groups",
        type_="foreignkey",
    )
    op.drop_constraint(
        "dealer_groups_created_by_fkey",
        "dealer_groups",
        type_="foreignkey",
    )
    op.drop_constraint(
        "dealer_groups_distributor_company_id_fkey",
        "dealer_groups",
        type_="foreignkey",
    )
    op.drop_column("dealer_groups", "updated_by")
    op.drop_column("dealer_groups", "created_by")
    op.drop_column("dealer_groups", "distributor_company_id")
    op.alter_column(
        "dealer_groups",
        "is_active",
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=sa.true(),
    )
    op.create_unique_constraint("uq_dealer_groups_name", "dealer_groups", ["name"])

    op.create_table(
        "dealer_group_members",
        sa.Column(
            "dealer_group_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("dealer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["dealer_group_id"],
            ["dealer_groups.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["dealer_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("dealer_group_id", "dealer_id"),
    )
    op.drop_column("distributors", "can_manage_dealer_groups")
