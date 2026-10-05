"""Align the existing special-equipment trim schema with v5.16.

Revision ID: 097
Revises: 096
Create Date: 2026-08-24
"""

from __future__ import annotations

from alembic import op

revision: str = "097"
down_revision: str | None = "096"
branch_labels: str | None = None
depends_on: str | None = None

_RECEIPT_CHECK = "ck_se_catalog_mutation_receipts_resource_type"
_RECEIPT_TYPES_WITH_TRIM = (
    "resource_type IN ('category', 'mark', 'model', 'modification', 'trim', "
    "'attribute_group', 'attribute', 'attribute_option', 'product', 'color')"
)
_RECEIPT_TYPES_WITHOUT_TRIM = (
    "resource_type IN ('category', 'mark', 'model', 'modification', "
    "'attribute_group', 'attribute', 'attribute_option', 'product', 'color')"
)


def upgrade() -> None:
    # Migration 089 already created all trim tables.  The v5.16 migration only
    # adjusts ownership/deletion semantics and preserves every existing row.
    op.drop_constraint(
        "fk_se_trim_attributes_group",
        "special_equipment_trim_attributes",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_se_trim_attributes_group",
        "special_equipment_trim_attributes",
        "special_equipment_attribute_groups",
        ["group_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="SET NULL",
    )
    # The composite FK is the single ownership constraint.  A second FK on
    # trim_id alone is redundant and can disagree with that invariant.
    op.drop_constraint(
        "fk_se_products_trim",
        "special_equipment_products",
        type_="foreignkey",
    )
    op.drop_constraint(
        _RECEIPT_CHECK,
        "special_equipment_catalog_mutation_receipts",
        type_="check",
    )
    op.create_check_constraint(
        _RECEIPT_CHECK,
        "special_equipment_catalog_mutation_receipts",
        _RECEIPT_TYPES_WITH_TRIM,
    )


def downgrade() -> None:
    # Trim mutation receipts are an idempotency replay cache, not catalog
    # source data.  Revision 095 cannot represent their resource_type, so a
    # rollback deliberately invalidates only those receipts before restoring
    # the narrower check.  Replays after rollback execute as fresh requests.
    op.execute(
        "DELETE FROM special_equipment_catalog_mutation_receipts "
        "WHERE resource_type = 'trim'"
    )
    op.drop_constraint(
        _RECEIPT_CHECK,
        "special_equipment_catalog_mutation_receipts",
        type_="check",
    )
    op.create_check_constraint(
        _RECEIPT_CHECK,
        "special_equipment_catalog_mutation_receipts",
        _RECEIPT_TYPES_WITHOUT_TRIM,
    )
    op.create_foreign_key(
        "fk_se_products_trim",
        "special_equipment_products",
        "special_equipment_trims",
        ["trim_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "fk_se_trim_attributes_group",
        "special_equipment_trim_attributes",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_se_trim_attributes_group",
        "special_equipment_trim_attributes",
        "special_equipment_attribute_groups",
        ["group_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="RESTRICT",
    )
