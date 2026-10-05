"""Immutable document metadata snapshots and reusable file objects.

Revision ID: 134
Revises: 133
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "134"
down_revision = "133"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reference_document_versions", sa.Column("name", sa.String(255), nullable=True))
    op.add_column("reference_document_versions", sa.Column("platform_ml_related", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("reference_document_versions", sa.Column("metadata_backfilled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(sa.text("""
        UPDATE reference_document_versions v
        SET name = d.name, platform_ml_related = d.platform_ml_related, metadata_backfilled = true
        FROM reference_documents d WHERE d.id = v.document_id
    """))
    op.alter_column("reference_document_versions", "name", nullable=False)
    op.create_check_constraint("ck_reference_document_version_name", "reference_document_versions", "length(trim(name)) > 0")
    op.create_table("reference_document_version_related_companies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("version_id", UUID(as_uuid=True), sa.ForeignKey("reference_document_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("version_id", "role", "company_id", name="uq_reference_document_version_related_company"),
        sa.CheckConstraint("role IN ('leasing_company','dealer','distributor')", name="ck_reference_document_version_related_role"))
    op.create_index("idx_reference_document_version_related_company", "reference_document_version_related_companies", ["company_id"])
    op.execute(sa.text("""
        INSERT INTO reference_document_version_related_companies (version_id, role, company_id)
        SELECT v.id, r.role, r.company_id
        FROM reference_document_versions v
        JOIN reference_document_related_companies r ON r.document_id = v.document_id
    """))
    op.drop_constraint("reference_document_files_s3_key_key", "reference_document_files", type_="unique")
    op.create_index("idx_reference_document_file_s3_key", "reference_document_files", ["s3_key"])


def downgrade() -> None:
    # Guard before any DDL: restoring UNIQUE must never discard shared file history.
    shared = op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM reference_document_files GROUP BY s3_key HAVING count(*) > 1)"))
    if shared:
        raise RuntimeError("Cannot downgrade document snapshots: file objects are shared by versions")
    op.drop_index("idx_reference_document_file_s3_key", table_name="reference_document_files")
    op.create_unique_constraint("reference_document_files_s3_key_key", "reference_document_files", ["s3_key"])
    op.drop_table("reference_document_version_related_companies")
    op.drop_constraint("ck_reference_document_version_name", "reference_document_versions", type_="check")
    op.drop_column("reference_document_versions", "metadata_backfilled")
    op.drop_column("reference_document_versions", "platform_ml_related")
    op.drop_column("reference_document_versions", "name")
