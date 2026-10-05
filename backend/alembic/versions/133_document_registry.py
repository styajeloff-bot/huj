"""Dedicated reference documents, versions, files and monetization links.

Revision ID: 133
Revises: 132
"""
from typing import Any
from uuid import uuid4
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

revision = "133"
down_revision = "132"
branch_labels = None
depends_on = None

def _id() -> sa.Column[Any]:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4, server_default=sa.text("gen_random_uuid()"))


def _fk(name: str, target: str, *, nullable: bool = False, primary_key: bool = False) -> sa.Column[Any]:
    return sa.Column(name, UUID(as_uuid=True), sa.ForeignKey(target, ondelete="RESTRICT"), nullable=nullable, primary_key=primary_key)


def _created() -> sa.Column[Any]:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def _role() -> sa.Column[Any]:
    return sa.Column("role", sa.String(30), nullable=False)


def build_tables(metadata: sa.MetaData) -> tuple[sa.Table, ...]:
    groups = sa.Table("document_groups", metadata,
        _id(), sa.Column("platform_ml_participates", sa.Boolean, nullable=False, server_default=sa.false()),
        _fk("mark_id", "special_equipment_marks.id", nullable=True),
        _fk("model_id", "special_equipment_models.id", nullable=True),
        _fk("created_by", "users.id"), _created(),
        sa.CheckConstraint("model_id IS NULL OR mark_id IS NOT NULL", name="ck_document_group_model_mark"),
        sa.Index("idx_document_groups_order", "created_at", "id"))
    participants = sa.Table("document_group_participants", metadata, _id(),
        _fk("group_id", "document_groups.id"), _role(), _fk("company_id", "companies.id"),
        sa.UniqueConstraint("group_id", "role", "company_id", name="uq_document_group_participant"),
        sa.CheckConstraint("role IN ('leasing_company','dealer','distributor')", name="ck_document_group_participant_role"),
        sa.Index("idx_document_group_participant_company", "company_id"))
    types = sa.Table("reference_document_types", metadata,
        sa.Column("type_code", sa.String(30), primary_key=True), sa.Column("display_name", sa.String(100), nullable=False))
    documents = sa.Table("reference_documents", metadata, _id(), _fk("group_id", "document_groups.id"),
        sa.Column("is_main", sa.Boolean, nullable=False),
        sa.Column("document_type", sa.String(30), sa.ForeignKey("reference_document_types.type_code", ondelete="RESTRICT"), nullable=False),
        sa.Column("contract_number", sa.String(100), nullable=False),
        sa.Column("contract_number_normalized", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("platform_ml_related", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("deactivated_at", sa.DateTime(timezone=True)), _fk("deactivated_by", "users.id", nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True)), _fk("deleted_by", "users.id", nullable=True),
        _fk("created_by", "users.id"), _created(),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(contract_number_normalized) > 0 AND length(trim(name)) > 0", name="ck_reference_document_identity"),
        sa.Index("uq_reference_document_number_live", "contract_number_normalized", unique=True, postgresql_where=sa.text("deleted_at IS NULL")),
        sa.Index("uq_reference_document_main_live", "group_id", unique=True, postgresql_where=sa.text("is_main AND deleted_at IS NULL")),
        sa.Index("idx_reference_documents_group", "group_id"))
    related = sa.Table("reference_document_related_companies", metadata, _id(),
        _fk("document_id", "reference_documents.id"), _role(), _fk("company_id", "companies.id"),
        sa.UniqueConstraint("document_id", "role", "company_id", name="uq_reference_document_related_company"),
        sa.CheckConstraint("role IN ('leasing_company','dealer','distributor')", name="ck_reference_document_related_role"),
        sa.Index("idx_reference_document_related_company", "company_id"))
    versions = sa.Table("reference_document_versions", metadata, _id(), _fk("document_id", "reference_documents.id"),
        sa.Column("version_number", sa.Integer, nullable=False), sa.Column("valid_from", sa.Date, nullable=False),
        sa.Column("valid_to", sa.Date), sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.true()),
        _fk("uploaded_by", "users.id"), _created(),
        sa.UniqueConstraint("document_id", "version_number", name="uq_reference_document_version_number"),
        sa.CheckConstraint("version_number > 0", name="ck_reference_document_version_positive"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="ck_reference_document_version_period"),
        sa.Index("uq_reference_document_current_version", "document_id", unique=True, postgresql_where=sa.text("is_current")))
    files = sa.Table("reference_document_files", metadata, _id(), _fk("version_id", "reference_document_versions.id"),
        sa.Column("file_name", sa.String(255), nullable=False), sa.Column("s3_key", sa.Text, nullable=False, unique=True),
        sa.Column("content_type", sa.String(255), nullable=False), sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("position", sa.Integer, nullable=False), _created(),
        sa.CheckConstraint("file_size > 0 AND position >= 0", name="ck_reference_document_file_size_position"),
        sa.UniqueConstraint("version_id", "position", name="uq_reference_document_file_position"))
    links = sa.Table("reference_document_monetization_programs", metadata,
        _fk("document_id", "reference_documents.id", primary_key=True),
        _fk("program_id", "monetization_programs.id", primary_key=True), _fk("created_by", "users.id"), _created(),
        sa.Index("idx_reference_document_monetization_program", "program_id"))
    return groups, participants, types, documents, related, versions, files, links


def upgrade() -> None:
    metadata = sa.MetaData()
    bind = op.get_bind()
    for name in ("users", "companies", "special_equipment_marks", "special_equipment_models", "monetization_programs"):
        sa.Table(name, metadata, autoload_with=bind)
    tables = build_tables(metadata)
    for table in tables:
        table.create(bind)
    op.bulk_insert(tables[2], [
        {"type_code": "contract", "display_name": "Договор"},
        {"type_code": "agreement", "display_name": "Соглашение"},
        {"type_code": "additional_agreement", "display_name": "Доп. соглашение"},
        {"type_code": "invoice", "display_name": "Счёт"},
        {"type_code": "act", "display_name": "Акт"},
        {"type_code": "power_of_attorney", "display_name": "Доверенность"},
        {"type_code": "other", "display_name": "Прочее"},
    ])


def downgrade() -> None:
    for name in ("reference_document_monetization_programs", "reference_document_files", "reference_document_versions", "reference_document_related_companies", "reference_documents", "reference_document_types", "document_group_participants", "document_groups"):
        op.drop_table(name)
