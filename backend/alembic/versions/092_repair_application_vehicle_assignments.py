"""Repair vehicle assignments backfilled from the application parent.

Revision ID: 092
Revises: 091
Create Date: 2026-08-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "092"
down_revision: str | None = "091"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Restore the actual warehouse dealer for concrete vehicle rows.

    Revision 090 was applied locally before its backfill was corrected. Only
    rows that still exactly mirror the legacy parent assignment are repaired;
    explicit vehicle-level assignments made afterwards are preserved.
    """

    op.execute(
        sa.text(
            """
        UPDATE application_vehicles AS av
        SET dealer_company_id = COALESCE(
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
            ),
            dealer_assigned_by = NULL,
            dealer_assigned_at = NULL,
            primary_employee_id = NULL,
            additional_employee_id = NULL,
            employees_assigned_by = NULL,
            employees_assigned_at = NULL
        FROM leasing_applications AS la
        WHERE la.id = av.application_id
          AND av.vehicle_id IS NOT NULL
          AND av.dealer_company_id IS NOT DISTINCT FROM la.dealer_company_id
          AND av.dealer_assigned_by IS NOT DISTINCT FROM la.dealer_assigned_by
          AND av.dealer_assigned_at IS NOT DISTINCT FROM la.dealer_assigned_at
          AND av.primary_employee_id IS NOT DISTINCT FROM la.primary_employee_id
          AND av.additional_employee_id IS NOT DISTINCT FROM la.additional_employee_id
          AND av.employees_assigned_by IS NOT DISTINCT FROM la.employees_assigned_by
          AND av.employees_assigned_at IS NOT DISTINCT FROM la.employees_assigned_at
        """
        )
    )


def downgrade() -> None:
    """The repair intentionally has no destructive downgrade."""
