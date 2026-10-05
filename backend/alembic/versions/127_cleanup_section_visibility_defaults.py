"""Remove obsolete catalog/models section visibility keys, enable special equipment.

Revision ID: 127
Revises: 126
Create Date: 2026-09-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "127"
down_revision: str | None = "126"
branch_labels: str | None = None
depends_on: str | None = None

_OBSOLETE_KEYS = ("catalog", "models", "model_brand_selection", "cars_brand_filter")


def upgrade() -> None:
    conn = op.get_bind()
    # Delete obsolete section visibility overrides
    conn.execute(
        sa.text(
            "DELETE FROM section_visibility "
            "WHERE section_key = ANY(:keys)"
        ),
        {"keys": list(_OBSOLETE_KEYS)},
    )
    # Enable special_equipment_catalog for all scopes that have it
    conn.execute(
        sa.text(
            "UPDATE section_visibility "
            "SET is_visible = true, updated_at = CURRENT_TIMESTAMP "
            "WHERE section_key = 'special_equipment_catalog'"
        ),
    )
    # Enable special_equipment_import for carcraft_employee
    conn.execute(
        sa.text(
            "UPDATE section_visibility "
            "SET is_visible = true, updated_at = CURRENT_TIMESTAMP "
            "WHERE section_key = 'special_equipment_import' "
            "AND scope = 'carcraft_employee'"
        ),
    )


def downgrade() -> None:
    conn = op.get_bind()
    # Restore special_equipment defaults to hidden
    conn.execute(
        sa.text(
            "UPDATE section_visibility "
            "SET is_visible = false, updated_at = CURRENT_TIMESTAMP "
            "WHERE section_key IN ('special_equipment_catalog', 'special_equipment_import')"
        ),
    )
    # Note: deleted keys cannot be restored without knowing exact original data
