"""Complete task 21940 category management and used-owner contracts.

Revision ID: 085
Revises: 084
Create Date: 2026-08-05
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "085"
down_revision: str | None = "084"
branch_labels: str | None = None
depends_on: str | None = None

_NONNEGATIVE_OWNER_CHECK = "owners_count IS NULL OR owners_count >= 0"
_NONNEGATIVE_CONDITION_CHECK = (
    "(condition = 'new' AND owners_count IS NULL) OR "
    "(condition = 'used' AND owners_count IS NOT NULL AND owners_count >= 0)"
)
_POSITIVE_OWNER_CHECK = "owners_count IS NULL OR owners_count >= 1"
_POSITIVE_CONDITION_CHECK = (
    "(condition = 'new' AND owners_count IS NULL) OR "
    "(condition = 'used' AND owners_count IS NOT NULL AND owners_count >= 1)"
)
_POSITIVE_OWNER_CONSTRAINT = (
    "ck_special_equipment_products_owners_count_positive"
)
_NONNEGATIVE_OWNER_CONSTRAINT = (
    "ck_special_equipment_products_owners_count_nonnegative"
)


def _replace_owner_checks(
    *,
    drop_owner_constraint_name: str,
    create_owner_constraint_name: str,
    owner_check: str,
    condition_check: str,
) -> None:
    op.drop_constraint(
        "ck_special_equipment_products_condition_owners",
        "special_equipment_products",
        type_="check",
    )
    op.drop_constraint(
        drop_owner_constraint_name,
        "special_equipment_products",
        type_="check",
    )
    op.create_check_constraint(
        create_owner_constraint_name,
        "special_equipment_products",
        owner_check,
        postgresql_not_valid=True,
    )
    op.create_check_constraint(
        "ck_special_equipment_products_condition_owners",
        "special_equipment_products",
        condition_check,
        postgresql_not_valid=True,
    )


def upgrade() -> None:
    op.create_index(
        "idx_se_categories_updated_desc",
        "special_equipment_categories",
        [
            sa.text("GREATEST(created_at, updated_at) DESC"),
            sa.text("id DESC"),
        ],
    )
    _replace_owner_checks(
        drop_owner_constraint_name=_POSITIVE_OWNER_CONSTRAINT,
        create_owner_constraint_name=_NONNEGATIVE_OWNER_CONSTRAINT,
        owner_check=_NONNEGATIVE_OWNER_CHECK,
        condition_check=_NONNEGATIVE_CONDITION_CHECK,
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM special_equipment_products
                    WHERE condition = 'used' AND owners_count = 0
                ) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade 085 while used products have zero owners';
                END IF;
            END $$
            """
        )
    )
    _replace_owner_checks(
        drop_owner_constraint_name=_NONNEGATIVE_OWNER_CONSTRAINT,
        create_owner_constraint_name=_POSITIVE_OWNER_CONSTRAINT,
        owner_check=_POSITIVE_OWNER_CHECK,
        condition_check=_POSITIVE_CONDITION_CHECK,
    )
    op.drop_index(
        "idx_se_categories_updated_desc",
        table_name="special_equipment_categories",
    )
