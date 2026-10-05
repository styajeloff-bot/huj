"""Serialize new references without FK with administrative vehicle deletion.

Revision ID: 118
Revises: 117

Existing orphan references are deliberately preserved. The guards validate
only inserted or changed references; no backfill, deletion or silent cleanup.
"""
from alembic import op

revision = "118"
down_revision = "117"
branch_labels = None
depends_on = None

_SCALAR_TABLES = (
    "leasing_applications",
    "shopping_cart",
    "compensations",
    "application_applied_supports",
    "leasing_application_vehicle_calculations",
    "guest_cart_transfers",
)


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION guard_vehicle_scalar_reference() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.vehicle_id IS NULL THEN
                RETURN NEW;
            END IF;
            IF TG_OP = 'UPDATE' THEN
                IF NEW.vehicle_id IS NOT DISTINCT FROM OLD.vehicle_id THEN
                    RETURN NEW;
                END IF;
            END IF;
            PERFORM id FROM vehicles WHERE id = NEW.vehicle_id FOR KEY SHARE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Vehicle % does not exist', NEW.vehicle_id
                    USING ERRCODE = '23503', TABLE = TG_TABLE_NAME,
                          CONSTRAINT = 'guard_vehicle_reference';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    for table in _SCALAR_TABLES:
        op.execute(f"""
            CREATE TRIGGER guard_vehicle_reference
            BEFORE INSERT OR UPDATE OF vehicle_id ON {table}
            FOR EACH ROW EXECUTE FUNCTION guard_vehicle_scalar_reference()
        """)
    op.execute("""
        CREATE FUNCTION guard_vehicle_array_references() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            previous_ids uuid[] := ARRAY[]::uuid[];
            referenced_id uuid;
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                previous_ids := COALESCE(OLD.vehicle_ids, ARRAY[]::uuid[]);
            END IF;
            FOR referenced_id IN
                SELECT DISTINCT item
                FROM unnest(NEW.vehicle_ids) AS refs(item)
                WHERE item IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM unnest(previous_ids) AS old_refs(old_id)
                                  WHERE old_id = item)
                ORDER BY item
            LOOP
                PERFORM id FROM vehicles WHERE id = referenced_id FOR KEY SHARE;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'Vehicle % does not exist', referenced_id
                        USING ERRCODE = '23503', TABLE = TG_TABLE_NAME,
                              CONSTRAINT = 'guard_vehicle_array_references';
                END IF;
            END LOOP;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER guard_vehicle_array_references
        BEFORE INSERT OR UPDATE OF vehicle_ids ON calculation_history
        FOR EACH ROW EXECUTE FUNCTION guard_vehicle_array_references()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER guard_vehicle_array_references ON calculation_history")
    op.execute("DROP FUNCTION guard_vehicle_array_references()")
    for table in _SCALAR_TABLES:
        op.execute(f"DROP TRIGGER guard_vehicle_reference ON {table}")
    op.execute("DROP FUNCTION guard_vehicle_scalar_reference()")
