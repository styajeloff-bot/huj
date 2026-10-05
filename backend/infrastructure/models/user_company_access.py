"""SQLAlchemy ORM models for user-company personal access rules and permissions."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class UserCompanyAccessRule(Base):
    """Personal object-level access rule for a user within a specific company."""

    __tablename__ = "user_company_access_rules"
    __table_args__ = (
        sa.Index(
            "uq_uc_access_rules_obj",
            "user_company_id",
            "access_object",
            "access_type",
            "object_id",
            unique=True,
            postgresql_where=sa.text("object_id IS NOT NULL"),
        ),
        sa.Index(
            "uq_uc_access_rules_null",
            "user_company_id",
            "access_object",
            unique=True,
            postgresql_where=sa.text("object_id IS NULL"),
        ),
        sa.Index("idx_uc_access_rules_user_company_id", "user_company_id"),
        sa.Index("idx_uc_access_rules_object", "access_object", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=sa.text("gen_random_uuid()")
    )
    user_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("user_companies.id", ondelete="CASCADE", name="fk_user_company_access_rules_uc_id"),
        nullable=False,
    )
    access_object: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    access_type: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    object_id: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    object_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, default=True, server_default=sa.true(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )


class UserCompanySectionAccess(Base):
    """Personal workspace section visibility for a user within a specific company."""

    __tablename__ = "user_company_section_access"
    __table_args__ = (
        sa.UniqueConstraint(
            "user_company_id",
            "section_code",
            name="uq_user_company_section_access",
        ),
        sa.Index("idx_uc_section_access_user_company_id", "user_company_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=sa.text("gen_random_uuid()")
    )
    user_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("user_companies.id", ondelete="CASCADE", name="fk_user_company_section_access_uc_id"),
        nullable=False,
    )
    section_code: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    can_view: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )


class UserCompanyEmployeePermission(Base):
    """Permission to create, update and manage company employees with audit history."""

    __tablename__ = "user_company_employee_permissions"
    __table_args__ = (
        sa.Index("idx_uc_employee_permissions_user_company_id", "user_company_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=sa.text("gen_random_uuid()")
    )
    user_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("user_companies.id", ondelete="CASCADE", name="fk_uc_employee_permissions_uc_id"),
        unique=True,
        nullable=False,
    )
    can_create_employees: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.false(), nullable=False
    )
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_uc_employee_permissions_granted_by"),
        nullable=True,
    )
    granted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_uc_employee_permissions_revoked_by"),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )
