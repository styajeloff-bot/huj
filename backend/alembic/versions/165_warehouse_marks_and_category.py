"""Support multiple warehouse marks and an optional vehicle category.

Revision ID: 165
Revises: 164
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "165"
down_revision = "164"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warehouse_marks",
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mark_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"],
            name="fk_warehouse_marks_warehouse_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mark_id"], ["special_equipment_marks.id"],
            name="fk_warehouse_marks_mark_id", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("warehouse_id", "mark_id"),
    )
    op.create_index("idx_warehouse_marks_mark_id", "warehouse_marks", ["mark_id"])
    op.execute("INSERT INTO warehouse_marks (warehouse_id, mark_id) SELECT id, brand_id FROM warehouses WHERE brand_id IS NOT NULL")
    op.add_column("warehouses", sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_warehouses_category_id_special_equipment_categories", "warehouses", "special_equipment_categories",
        ["category_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_index("idx_warehouses_category_id", "warehouses", ["category_id"])
    op.drop_index("idx_warehouses_brand_id", table_name="warehouses")
    op.drop_constraint("fk_warehouses_brand_id_special_equipment_marks", "warehouses", type_="foreignkey")
    op.drop_column("warehouses", "brand_id")


def downgrade() -> None:
    # The legacy schema cannot retain multiple selections. Refuse a lossy rollback.
    multiple_selections = op.get_bind().execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM warehouse_marks GROUP BY warehouse_id HAVING count(*) > 1)"
    )).scalar()
    if multiple_selections:
        raise RuntimeError("Cannot downgrade warehouses with multiple selected marks")
    op.add_column("warehouses", sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_warehouses_brand_id_special_equipment_marks", "warehouses", "special_equipment_marks",
        ["brand_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("idx_warehouses_brand_id", "warehouses", ["brand_id"])
    op.execute("UPDATE warehouses SET brand_id = warehouse_marks.mark_id FROM warehouse_marks WHERE warehouses.id = warehouse_marks.warehouse_id")
    op.drop_index("idx_warehouses_category_id", table_name="warehouses")
    op.drop_constraint("fk_warehouses_category_id_special_equipment_categories", "warehouses", type_="foreignkey")
    op.drop_column("warehouses", "category_id")
    op.drop_index("idx_warehouse_marks_mark_id", table_name="warehouse_marks")
    op.drop_table("warehouse_marks")
