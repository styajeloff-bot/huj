"""Preserve every selected purpose on each application transport line."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "151"
down_revision = "150"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("application_vehicles", "special_equipment_application_items"):
        op.add_column(table, sa.Column("leasing_purposes", postgresql.JSONB(), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET leasing_purposes = CASE WHEN nullif(btrim(leasing_purpose), '') IS NULL THEN '[]'::jsonb ELSE jsonb_build_array(btrim(leasing_purpose)) END"))
    op.execute("""
        INSERT INTO application_questionnaires (id, application_id, vehicle_purchase_purpose)
        SELECT gen_random_uuid(), a.id, jsonb_build_object('vehicles', coalesce((
            SELECT jsonb_agg(jsonb_build_object('vehicle_id', v.id::text, 'purposes', v.leasing_purposes) ORDER BY v.id)
            FROM application_vehicles v WHERE v.application_id = a.id
            AND v.car_status NOT IN ('removed', 'replaced', 'rejected')
        ), '[]'::jsonb)) FROM leasing_applications a
        ON CONFLICT (application_id) DO UPDATE SET vehicle_purchase_purpose = excluded.vehicle_purchase_purpose
    """)


def downgrade() -> None:
    op.drop_column("special_equipment_application_items", "leasing_purposes")
    op.drop_column("application_vehicles", "leasing_purposes")
