"""Personal access rules for dealer and distributor employees (Task 21952).

Revision ID: 139
Revises: 138
Create Date: 2026-09-29 08:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "139"
down_revision = "138"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add additional_phone to users
    op.add_column("users", sa.Column("additional_phone", sa.String(20), nullable=True))

    # 2. Add id UUID to user_companies
    op.add_column(
        "user_companies",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint("uq_user_companies_id", "user_companies", ["id"])

    # 3. Create user_company_access_rules
    op.create_table(
        "user_company_access_rules",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_company_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("user_companies.id", ondelete="CASCADE", name="fk_user_company_access_rules_uc_id"),
            nullable=False,
        ),
        sa.Column("access_object", sa.String(50), nullable=False),
        sa.Column("access_type", sa.String(30), nullable=False),
        sa.Column("object_id", sa.String(100), nullable=True),
        sa.Column("object_name", sa.String(255), nullable=True),
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
    op.create_index(
        "idx_uc_access_rules_user_company_id",
        "user_company_access_rules",
        ["user_company_id"],
    )
    op.create_index(
        "idx_uc_access_rules_object",
        "user_company_access_rules",
        ["access_object", "is_active"],
    )
    op.create_index(
        "uq_uc_access_rules_obj",
        "user_company_access_rules",
        ["user_company_id", "access_object", "access_type", "object_id"],
        unique=True,
        postgresql_where=sa.text("object_id IS NOT NULL"),
    )
    op.create_index(
        "uq_uc_access_rules_null",
        "user_company_access_rules",
        ["user_company_id", "access_object"],
        unique=True,
        postgresql_where=sa.text("object_id IS NULL"),
    )

    # 4. Create user_company_section_access
    op.create_table(
        "user_company_section_access",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_company_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("user_companies.id", ondelete="CASCADE", name="fk_user_company_section_access_uc_id"),
            nullable=False,
        ),
        sa.Column("section_code", sa.String(50), nullable=False),
        sa.Column("can_view", sa.Boolean(), nullable=False),
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
        sa.UniqueConstraint("user_company_id", "section_code", name="uq_user_company_section_access"),
    )
    op.create_index(
        "idx_uc_section_access_user_company_id",
        "user_company_section_access",
        ["user_company_id"],
    )

    # 5. Create user_company_employee_permissions
    op.create_table(
        "user_company_employee_permissions",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_company_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("user_companies.id", ondelete="CASCADE", name="fk_uc_employee_permissions_uc_id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("can_create_employees", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "granted_by_user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_uc_employee_permissions_granted_by"),
            nullable=True,
        ),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revoked_by_user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_uc_employee_permissions_revoked_by"),
            nullable=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index(
        "idx_uc_employee_permissions_user_company_id",
        "user_company_employee_permissions",
        ["user_company_id"],
    )


def downgrade() -> None:
    op.drop_table("user_company_employee_permissions")
    op.drop_table("user_company_section_access")
    op.drop_table("user_company_access_rules")
    op.drop_constraint("uq_user_companies_id", "user_companies", type_="unique")
    op.drop_column("user_companies", "id")
    op.drop_column("users", "additional_phone")
