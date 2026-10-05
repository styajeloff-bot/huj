"""Add extended specifications to the ordinary car catalog.

Revision ID: 107
Revises: 106
Create Date: 2026-09-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "107"
down_revision: str | None = "106"
branch_labels: str | None = None
depends_on: str | None = None

_SPECIFICATION_COLUMNS = (
    "wheel_formula",
    "permitted_axle_loads",
    "cabin",
    "permitted_gross_train_weight",
    "suspension",
    "fuel_tanks",
)


def upgrade() -> None:
    for column_name in _SPECIFICATION_COLUMNS:
        op.add_column(
            "specifications",
            sa.Column(column_name, sa.String(length=100), nullable=True),
        )


def downgrade() -> None:
    for column_name in reversed(_SPECIFICATION_COLUMNS):
        op.drop_column("specifications", column_name)
