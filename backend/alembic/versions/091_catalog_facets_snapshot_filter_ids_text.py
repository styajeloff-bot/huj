"""Store catalog facet snapshot filter IDs as text.

Revision ID: 091
Revises: 090
Create Date: 2026-08-20
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "091"
down_revision: str | None = "090"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    for column_name in ("mark_id", "model_id", "generation_id"):
        op.alter_column(
            "catalog_facets_snapshot",
            column_name,
            existing_type=sa.String(length=50),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    # Snapshot rows are disposable cache data. Clear long CSV anchors before
    # narrowing the columns so rollback cannot fail on values over 50 chars.
    op.execute(sa.text("DELETE FROM catalog_facets_snapshot"))
    for column_name in ("mark_id", "model_id", "generation_id"):
        op.alter_column(
            "catalog_facets_snapshot",
            column_name,
            existing_type=sa.Text(),
            type_=sa.String(length=50),
            existing_nullable=True,
        )
