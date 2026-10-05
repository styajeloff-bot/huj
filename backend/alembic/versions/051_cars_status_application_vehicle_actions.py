"""cars status and application vehicle dealer actions

Revision ID: 051
Revises: 050
Create Date: 2026-06-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cars_status",
        sa.Column("status_name", sa.String(length=50), primary_key=True),
        sa.Column("status_display_name", sa.String(length=255), nullable=False),
    )
    op.bulk_insert(
        sa.table(
            "cars_status",
            sa.column("status_name", sa.String),
            sa.column("status_display_name", sa.String),
        ),
        [
            {
                "status_name": "confirmed",
                "status_display_name": "Подтверждено",
            },
            {
                "status_name": "not_confirmed",
                "status_display_name": "Не подтверждено",
            },
            {
                "status_name": "active",
                "status_display_name": "Подтверждается",
            },
            {
                "status_name": "replacement",
                "status_display_name": "Замена ТС",
            },
        ],
    )
    op.add_column(
        "application_vehicles",
        sa.Column(
            "car_status",
            sa.String(length=50),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "application_vehicles",
        sa.Column("dealer_comment", sa.Text(), nullable=True),
    )
    op.add_column(
        "application_vehicles",
        sa.Column("reserve_expires_at", sa.Date(), nullable=True),
    )
    op.add_column(
        "application_vehicles",
        sa.Column("discount_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "application_vehicles",
        sa.Column("discount_value", sa.Numeric(15, 2), nullable=True),
    )
    op.add_column(
        "application_vehicles",
        sa.Column("final_price", sa.Numeric(15, 2), nullable=True),
    )
    op.create_foreign_key(
        "fk_application_vehicles_car_status",
        "application_vehicles",
        "cars_status",
        ["car_status"],
        ["status_name"],
    )
    op.create_index(
        "idx_application_vehicles_car_status",
        "application_vehicles",
        ["car_status"],
    )


def downgrade() -> None:
    op.drop_index("idx_application_vehicles_car_status", table_name="application_vehicles")
    op.drop_constraint(
        "fk_application_vehicles_car_status",
        "application_vehicles",
        type_="foreignkey",
    )
    op.drop_column("application_vehicles", "final_price")
    op.drop_column("application_vehicles", "discount_value")
    op.drop_column("application_vehicles", "discount_type")
    op.drop_column("application_vehicles", "reserve_expires_at")
    op.drop_column("application_vehicles", "dealer_comment")
    op.drop_column("application_vehicles", "car_status")
    op.drop_table("cars_status")
