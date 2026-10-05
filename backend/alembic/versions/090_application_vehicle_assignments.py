"""Store dealer and employee assignments per application vehicle.

Revision ID: 090
Revises: 089
Create Date: 2026-08-20
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "090"
down_revision: str | None = "089"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "application_vehicles",
        sa.Column("dealer_company_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "application_vehicles",
        sa.Column("dealer_assigned_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "application_vehicles",
        sa.Column("dealer_assigned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "application_vehicles",
        sa.Column("primary_employee_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "application_vehicles",
        sa.Column(
            "additional_employee_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.add_column(
        "application_vehicles",
        sa.Column(
            "employees_assigned_by", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.add_column(
        "application_vehicles",
        sa.Column("employees_assigned_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_foreign_key(
        "fk_application_vehicles_dealer_company_id",
        "application_vehicles",
        "companies",
        ["dealer_company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for column in (
        "dealer_assigned_by",
        "primary_employee_id",
        "additional_employee_id",
        "employees_assigned_by",
    ):
        op.create_foreign_key(
            f"fk_application_vehicles_{column}",
            "application_vehicles",
            "users",
            [column],
            ["id"],
            ondelete="SET NULL",
        )
    for column in (
        "dealer_company_id",
        "dealer_assigned_by",
        "primary_employee_id",
        "additional_employee_id",
        "employees_assigned_by",
    ):
        op.create_index(
            f"idx_application_vehicles_{column}", "application_vehicles", [column]
        )

    op.execute(
        sa.text(
            """
        UPDATE application_vehicles AS av
        SET dealer_company_id = CASE
                WHEN av.vehicle_id IS NULL THEN la.dealer_company_id
                ELSE COALESCE(
                    (
                        SELECT COALESCE(w.company_id, w.dealer_id)
                        FROM vehicle_warehouses AS vw
                        JOIN warehouses AS w ON w.id = vw.warehouse_id
                        WHERE vw.vehicle_id = av.vehicle_id
                        LIMIT 1
                    ),
                    (
                        SELECT v.dealer_id
                        FROM vehicles AS v
                        WHERE v.id = av.vehicle_id
                    )
                )
            END,
            dealer_assigned_by = CASE
                WHEN av.vehicle_id IS NULL THEN la.dealer_assigned_by
                ELSE NULL
            END,
            dealer_assigned_at = CASE
                WHEN av.vehicle_id IS NULL THEN la.dealer_assigned_at
                ELSE NULL
            END,
            primary_employee_id = CASE
                WHEN av.vehicle_id IS NULL THEN la.primary_employee_id
                ELSE NULL
            END,
            additional_employee_id = CASE
                WHEN av.vehicle_id IS NULL THEN la.additional_employee_id
                ELSE NULL
            END,
            employees_assigned_by = CASE
                WHEN av.vehicle_id IS NULL THEN la.employees_assigned_by
                ELSE NULL
            END,
            employees_assigned_at = CASE
                WHEN av.vehicle_id IS NULL THEN la.employees_assigned_at
                ELSE NULL
            END
        FROM leasing_applications AS la
        WHERE la.id = av.application_id
        """
        )
    )


def downgrade() -> None:
    indexed = (
        "employees_assigned_by",
        "additional_employee_id",
        "primary_employee_id",
        "dealer_assigned_by",
        "dealer_company_id",
    )
    for column in indexed:
        op.drop_index(
            f"idx_application_vehicles_{column}", table_name="application_vehicles"
        )
    for column in indexed:
        op.drop_constraint(
            f"fk_application_vehicles_{column}",
            "application_vehicles",
            type_="foreignkey",
        )
    for column in (
        "employees_assigned_at",
        "employees_assigned_by",
        "additional_employee_id",
        "primary_employee_id",
        "dealer_assigned_at",
        "dealer_assigned_by",
        "dealer_company_id",
    ):
        op.drop_column("application_vehicles", column)
