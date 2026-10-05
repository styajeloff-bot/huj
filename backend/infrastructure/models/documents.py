"""SQLAlchemy ORM models for document-related tables."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base
from infrastructure.models.enums import document_status_enum


class DocumentType(Base):
    """ORM model for the document_types table."""

    __tablename__ = "document_types"
    __table_args__ = (
        sa.Index("idx_document_types_type_code", "type_code", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    type_code: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    display_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_required_for_all: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=True
    )
    file_types: Mapped[list[str] | None] = mapped_column(ARRAY(sa.Text), nullable=True)
    max_file_size_mb: Mapped[int | None] = mapped_column(
        sa.Integer, server_default=sa.text("10"), nullable=True
    )
    validation_rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    auto_approve: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=True
    )
    has_form: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=False
    )
    form_schema: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class Document(Base):
    """ORM model for the documents table."""

    __tablename__ = "documents"
    __table_args__ = (
        sa.Index("idx_documents_company_id", "company_id"),
        sa.Index("idx_documents_dbrain_task_id", "dbrain_task_id"),
        sa.Index("idx_documents_is_current_version", "is_current_version"),
        sa.Index("idx_documents_leasing_company_status", "leasing_company_status"),
        sa.Index("idx_documents_parent_document_id", "parent_document_id"),
        sa.Index("idx_documents_recognition_status", "recognition_status"),
        sa.Index("idx_documents_related_application_id", "related_application_id"),
        sa.Index("idx_documents_s3_key", "s3_key"),
        sa.Index("idx_documents_version", "version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id"),
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    file_path: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    file_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    s3_key: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    period_label: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    comments: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_required: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=True
    )
    status: Mapped[str | None] = mapped_column(
        document_status_enum,
        server_default="not_uploaded",
        nullable=True,
    )
    version: Mapped[int | None] = mapped_column(
        sa.Integer, server_default=sa.text("1"), nullable=True
    )
    parent_document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_current_version: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.true(), nullable=True
    )
    related_application_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_by_leasing_company: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    leasing_company_status: Mapped[str | None] = mapped_column(
        sa.String(50), server_default=sa.text("'pending'"), nullable=True
    )
    leasing_company_comments: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    leasing_company_reviewed_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    extracted_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    recognition_status: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    recognition_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    dbrain_task_id: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    recognized_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    uploaded_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    verified_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )

class DocumentLeasingCompanyApproval(Base):
    """ORM model for the document_leasing_company_approvals table."""

    __tablename__ = "document_leasing_company_approvals"
    __table_args__ = (
        sa.UniqueConstraint("document_id", "leasing_company_id"),
        sa.Index("idx_document_leasing_company_approvals_document_id", "document_id"),
        sa.Index("idx_document_leasing_company_approvals_leasing_company_id", "leasing_company_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    leasing_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str | None] = mapped_column(
        sa.String(50), server_default=sa.text("'pending'"), nullable=True
    )
    comments: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id"),
        nullable=True,
    )
    reviewed_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
    )


class ApplicationDocumentRequest(Base):
    """ORM model for the application_document_requests table."""

    __tablename__ = "application_document_requests"
    __table_args__ = (
        sa.UniqueConstraint(
            "request_batch_id",
            "document_type",
            name="uq_application_document_requests_batch_type",
        ),
        sa.Index(
            "idx_application_document_requests_app_lc_requested_at",
            "application_id",
            "leasing_company_id",
            "requested_at",
        ),
        sa.Index(
            "idx_application_document_requests_batch_id",
            "request_batch_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    leasing_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    request_batch_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    document_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    has_form: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=False
    )
    form_schema: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    form_data: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(
        sa.String(50), server_default=sa.text("'requested'"), nullable=True
    )
    is_required: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.true(), nullable=True
    )
    request_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    requested_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
    )
    provided_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id"),
        nullable=True,
    )
    deadline: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    reminder_sent_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class ApplicationDocument(Base):
    """ORM model for the application_documents table."""

    __tablename__ = "application_documents"
    __table_args__ = (
        sa.UniqueConstraint("application_id", "document_id", "leasing_company_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_request_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("application_document_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    leasing_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str | None] = mapped_column(
        sa.String(50), server_default=sa.text("'submitted'"), nullable=True
    )
    user_title: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    reviewer_comments: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id"),
        nullable=True,
    )
    submitted_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
    )
    reviewed_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    revision_requested_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    auto_approved: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=True
    )


class DocumentApplication(Base):
    """ORM model for the document_applications table."""

    __tablename__ = "document_applications"
    __table_args__ = (
        sa.UniqueConstraint("document_id", "application_id"),
        sa.Index("idx_document_applications_application_id", "application_id"),
        sa.Index("idx_document_applications_document_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class DirectorDocSigningInvitation(Base):
    """One row per (application × document_type × period_label) slot.

    Tracks the post-upload SMS dispatched to the company's general
    director when a signed document slot is filled. The unique
    constraint on (application_id, document_type, COALESCE(period_label, ''))
    is created in migration 019 — re-uploading the same slot reuses the
    existing row, so no second SMS goes out.
    """

    __tablename__ = "director_doc_signing_invitations"
    __table_args__ = (
        sa.Index("idx_dirinv_application_id", "application_id"),
        sa.Index(
            "uq_dirinv_app_type_period",
            "application_id",
            "document_type",
            sa.text("COALESCE(period_label, '')"),
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    period_label: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    signature_request_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("signature_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    director_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    director_phone: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    sms_sent_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    sms_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )


class PassportRecognitionData(Base):
    """ORM model for the passport_recognition_data table."""

    __tablename__ = "passport_recognition_data"
    __table_args__ = (
        sa.UniqueConstraint("user_id", "file_hash", "passport_type"),
        sa.Index("idx_passport_recognition_document_id", "document_id"),
        sa.Index("idx_passport_recognition_file_hash", "file_hash"),
        sa.Index("idx_passport_recognition_passport_type", "passport_type"),
        sa.Index("idx_passport_recognition_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
    )
    file_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    passport_type: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    mapped_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    dbrain_task_id: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
