"""Persist authoritative monetization provenance; never infer historical sources."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "121"
down_revision = "120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leasing_applications", sa.Column("source_type", sa.String(32), nullable=True)
    )
    for name in ("dealer_company_id", "distributor_company_id"):
        op.add_column(
            "application_applied_supports",
            sa.Column(name, postgresql.UUID(as_uuid=True), nullable=True),
        )
    op.execute("""
        CREATE FUNCTION prevent_application_source_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.source_type IS DISTINCT FROM OLD.source_type THEN
                RAISE EXCEPTION 'Источник заявки нельзя изменять после создания';
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER leasing_application_source_immutable
        BEFORE UPDATE OF source_type ON leasing_applications
        FOR EACH ROW EXECUTE FUNCTION prevent_application_source_change()
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER leasing_application_source_immutable ON leasing_applications"
    )
    op.execute("DROP FUNCTION prevent_application_source_change()")
    op.drop_column("application_applied_supports", "distributor_company_id")
    op.drop_column("application_applied_supports", "dealer_company_id")
    op.drop_column("leasing_applications", "source_type")
