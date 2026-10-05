"""Supplier quantities, physical stock allocations and explicit overstock consent.

Revision ID: 119
Revises: 118
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "119"
down_revision = "118"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("shopping_cart", "guest_cart_transfers"):
        op.add_column(table, sa.Column("allow_overstock", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("application_vehicles", sa.Column("requested_quantity", sa.Integer(), nullable=True))
    op.add_column("application_vehicles", sa.Column("confirmed_quantity", sa.Integer(), nullable=True))
    op.add_column("application_vehicles", sa.Column("fulfillment_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_application_requested_quantity", "application_vehicles", "requested_quantity IS NULL OR requested_quantity > 0")
    op.create_check_constraint("ck_application_confirmed_quantity", "application_vehicles", "confirmed_quantity IS NULL OR confirmed_quantity > 0")
    op.create_table("application_vehicle_allocations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("application_vehicle_id", UUID(as_uuid=True), sa.ForeignKey("application_vehicles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("vehicle_id", UUID(as_uuid=True), sa.ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("vin", sa.String(50)),
        sa.Column("unit_price", sa.Numeric(15, 2), nullable=False),
        sa.Column("reserved_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("release_reason", sa.Text()))
    op.create_index("uq_vehicle_active_allocation", "application_vehicle_allocations", ["vehicle_id"], unique=True, postgresql_where=sa.text("released_at IS NULL"))
    op.create_index("idx_allocation_line", "application_vehicle_allocations", ["application_vehicle_id"])
    op.create_table("application_vehicle_fulfillment_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("application_vehicle_id", UUID(as_uuid=True), sa.ForeignKey("application_vehicles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("previous_values", JSONB(), nullable=False),
        sa.Column("new_values", JSONB(), nullable=False),
        sa.Column("comment", sa.Text()))
    op.create_index("idx_fulfillment_history_line", "application_vehicle_fulfillment_history", ["application_vehicle_id"])
    # Last-line defence for legacy imports, callbacks and administrative updates.
    # Owning fulfillment releases its claim before moving stock to available.
    op.execute("""
      CREATE FUNCTION protect_allocated_vehicle() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF EXISTS (SELECT 1 FROM application_vehicle_allocations a
                   WHERE a.vehicle_id = OLD.id AND a.released_at IS NULL) THEN
          IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
             NEW.status = 'sold' AND EXISTS (
               SELECT 1 FROM application_vehicle_allocations a
               WHERE a.vehicle_id = OLD.id AND a.released_at IS NULL
                 AND a.completed_at IS NOT NULL)) THEN
            NEW.status := OLD.status;
          END IF;
          NEW.is_available := OLD.is_available;
          NEW.vin := OLD.vin;
          NEW.dealer_id := OLD.dealer_id;
          NEW.complectation_id := OLD.complectation_id;
        END IF;
        RETURN NEW;
      END $$;
    """)
    op.execute("""
      CREATE TRIGGER protect_allocated_vehicle BEFORE UPDATE ON vehicles
      FOR EACH ROW EXECUTE FUNCTION protect_allocated_vehicle()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER protect_allocated_vehicle ON vehicles")
    op.execute("DROP FUNCTION protect_allocated_vehicle()")
    op.drop_table("application_vehicle_fulfillment_history")
    op.drop_table("application_vehicle_allocations")
    op.drop_constraint("ck_application_confirmed_quantity", "application_vehicles")
    op.drop_constraint("ck_application_requested_quantity", "application_vehicles")
    for name in ("requested_quantity", "confirmed_quantity", "fulfillment_version"):
        op.drop_column("application_vehicles", name)
    for table in ("shopping_cart", "guest_cart_transfers"):
        op.drop_column(table, "allow_overstock")
