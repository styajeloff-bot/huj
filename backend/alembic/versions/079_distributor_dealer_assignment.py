"""Add distributor dealer and employee assignments to leasing applications.

Revision ID: 079
Revises: 078
Create Date: 2026-07-20
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "079"
down_revision: str | None = "078"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "leasing_applications",
        sa.Column(
            "assigned_dealer_group_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "leasing_applications",
        sa.Column(
            "dealer_assigned_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "leasing_applications",
        sa.Column("dealer_assigned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "leasing_applications",
        sa.Column(
            "primary_employee_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "leasing_applications",
        sa.Column(
            "additional_employee_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "leasing_applications",
        sa.Column(
            "employees_assigned_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "leasing_applications",
        sa.Column(
            "employees_assigned_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_leasing_applications_assigned_dealer_group",
        "leasing_applications",
        "dealer_groups",
        ["assigned_dealer_group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_leasing_applications_dealer_assigned_by",
        "leasing_applications",
        "users",
        ["dealer_assigned_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_leasing_applications_primary_employee",
        "leasing_applications",
        "users",
        ["primary_employee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_leasing_applications_additional_employee",
        "leasing_applications",
        "users",
        ["additional_employee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_leasing_applications_employees_assigned_by",
        "leasing_applications",
        "users",
        ["employees_assigned_by"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "idx_leasing_applications_assigned_dealer_group_id",
        "leasing_applications",
        ["assigned_dealer_group_id"],
    )
    op.create_index(
        "idx_leasing_applications_dealer_assigned_by",
        "leasing_applications",
        ["dealer_assigned_by"],
    )
    op.create_index(
        "idx_leasing_applications_primary_employee_id",
        "leasing_applications",
        ["primary_employee_id"],
    )
    op.create_index(
        "idx_leasing_applications_additional_employee_id",
        "leasing_applications",
        ["additional_employee_id"],
    )
    op.create_index(
        "idx_leasing_applications_employees_assigned_by",
        "leasing_applications",
        ["employees_assigned_by"],
    )

    op.execute(
        sa.text(
            """
            UPDATE leasing_applications AS application
               SET dealer_company_id = NULL
              FROM companies AS dealer_company
             WHERE dealer_company.id = application.dealer_company_id
               AND dealer_company.company_type = 'distributor'
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "idx_leasing_applications_employees_assigned_by",
        table_name="leasing_applications",
    )
    op.drop_index(
        "idx_leasing_applications_additional_employee_id",
        table_name="leasing_applications",
    )
    op.drop_index(
        "idx_leasing_applications_primary_employee_id",
        table_name="leasing_applications",
    )
    op.drop_index(
        "idx_leasing_applications_dealer_assigned_by",
        table_name="leasing_applications",
    )
    op.drop_index(
        "idx_leasing_applications_assigned_dealer_group_id",
        table_name="leasing_applications",
    )

    op.drop_constraint(
        "fk_leasing_applications_employees_assigned_by",
        "leasing_applications",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_leasing_applications_additional_employee",
        "leasing_applications",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_leasing_applications_primary_employee",
        "leasing_applications",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_leasing_applications_dealer_assigned_by",
        "leasing_applications",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_leasing_applications_assigned_dealer_group",
        "leasing_applications",
        type_="foreignkey",
    )

    op.drop_column("leasing_applications", "employees_assigned_at")
    op.drop_column("leasing_applications", "employees_assigned_by")
    op.drop_column("leasing_applications", "additional_employee_id")
    op.drop_column("leasing_applications", "primary_employee_id")
    op.drop_column("leasing_applications", "dealer_assigned_at")
    op.drop_column("leasing_applications", "dealer_assigned_by")
    op.drop_column("leasing_applications", "assigned_dealer_group_id")
