"""SQLAlchemy ORM models for user-related tables."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, synonym

from domain.storefronts import DEFAULT_STOREFRONT_ID
from infrastructure.models import Base
from infrastructure.models.enums import user_role_enum


class User(Base):
    """ORM model for the users table."""

    __tablename__ = "users"
    __table_args__ = (
        sa.Index("idx_users_company_id", "company_id"),
        sa.Index("idx_users_deleted_at", "deleted_at"),
        sa.Index("idx_users_email", "email"),
        sa.Index("idx_users_last_login_at", "last_login_at"),
        sa.Index("idx_users_phone", "phone"),
        sa.Index("idx_users_role", "role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(
        user_role_enum,
        default="client",
        server_default="client",
        nullable=True,
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    phone: Mapped[str] = mapped_column(sa.String(20), unique=True, nullable=False)
    additional_phone: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    is_active: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.true(), nullable=True
    )
    email_verified: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=True
    )
    email_verified_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    phone_verified: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=True
    )
    phone_verified_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_login: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, server_default=sa.false(), nullable=False
    )
    mfa_secret: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    mfa_pending_secret: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    mfa_backup_codes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class UserSession(Base):
    """ORM model for the user_sessions table."""

    __tablename__ = "user_sessions"
    __table_args__ = (
        sa.Index(
            "idx_user_sessions_user_id_last_used_at_desc",
            "user_id",
            sa.text("last_used_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    refresh_token_hash: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    country_code: Mapped[str | None] = mapped_column(sa.String(2), nullable=True)
    expires_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    last_used_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class ClientProfile(Base):
    """ORM model for the client_profiles table."""

    __tablename__ = "client_profiles"
    __table_args__ = (
        sa.Index("idx_client_profiles_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    client_type: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    passport_series: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    passport_issued_date: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    passport_issued_by: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    company_name: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    inn: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    kpp: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    ogrn: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    legal_address: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    address: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    birth_date: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    notification_settings: Mapped[dict | None] = mapped_column(
        JSONB, server_default=sa.text("'{}'"), nullable=True
    )
    two_factor_enabled: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=True
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class UserIdentityVerification(Base):
    """Audit trail for user identity verification provider attempts."""

    __tablename__ = "user_identity_verifications"
    __table_args__ = (
        sa.Index(
            "idx_user_identity_verifications_user_provider_status",
            "user_id",
            "provider",
            "status",
        ),
        sa.Index(
            "idx_user_identity_verifications_user_verified_at",
            "user_id",
            sa.text("verified_at DESC"),
            postgresql_where=sa.text("status = 'verified'"),
        ),
        sa.Index(
            "idx_user_identity_verifications_correlation_id",
            "correlation_id",
            unique=True,
        ),
        sa.Index("idx_user_identity_verifications_auth_req_id", "auth_req_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    auth_req_id: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4
    )
    mobile_id_sub: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    birthdate: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    birthdate_match: Mapped[str | None] = mapped_column(sa.String(8), nullable=True)
    given_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    middle_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    family_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    national_identifier_masked: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    started_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    sms_requested_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    verified_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
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


class VerificationCode(Base):
    """ORM model for the verification_codes table."""

    __tablename__ = "verification_codes"
    __table_args__ = (
        sa.Index("idx_verification_codes_email", "email"),
        sa.Index("idx_verification_codes_phone", "phone"),
        sa.Index("idx_verification_codes_purpose_entity", "purpose", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    code: Mapped[str] = mapped_column(sa.String(6), nullable=False)
    expires_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    purpose: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    used_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    failed_attempts: Mapped[int] = mapped_column(
        sa.Integer, server_default="0", nullable=False
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class UserCompany(Base):
    """ORM model for the user_companies join table (composite primary key)."""

    __tablename__ = "user_companies"
    __table_args__ = (
        sa.PrimaryKeyConstraint("user_id", "company_id"),
        sa.Index("idx_user_companies_company_id", "company_id"),
        sa.Index("idx_user_companies_user_id", "user_id"),
        sa.Index("idx_user_companies_sub_role", "sub_role"),
        sa.Index("idx_user_companies_role", "role"),
        sa.Index("idx_user_companies_is_active", "is_active"),
        sa.Index("idx_user_companies_position_id", "position_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
        unique=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        sa.String(50), server_default="client", default="client", nullable=False
    )
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("positions.id", ondelete="SET NULL"),
        nullable=True,
    )
    sub_role: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    can_view_applications: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=False
    )
    can_create_applications: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.true(), default=True, nullable=False
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True
    )


class CompanySelectHistory(Base):
    """ORM model for the company_select_history table."""

    __tablename__ = "company_select_history"
    __table_args__ = (
        sa.Index("idx_company_select_history_company_id", "company_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class MagicLink(Base):
    """One-shot activation/login link sent to invited users.

    Issued during a leasing application when the applicant invites their
    CEO / founders to sign СОПД. The token is embedded in an SMS as
    ``{public_url}/s/{token}``. A single successful use sets
    ``used_at`` — further attempts return 410 Gone.
    """

    __tablename__ = "magic_links"
    __table_args__ = (
        sa.Index("idx_magic_links_token", "token", unique=True),
        sa.Index("idx_magic_links_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(
        sa.String(32), server_default="activation", nullable=False
    )
    expires_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )


class UserFavorite(Base):
    """ORM model for the user_favorites table."""

    __tablename__ = "user_favorites"
    __table_args__ = (
        sa.UniqueConstraint(
            "user_id",
            "storefront_id",
            "product_id",
            name="user_favorites_user_id_vehicle_id_key",
        ),
        sa.Index("idx_user_favorites_user_id", "user_id"),
        sa.Index("idx_user_favorites_product_id", "product_id"),
        sa.Index("idx_user_favorites_storefront_id", "storefront_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    storefront_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "catalog_storefronts.id",
            name="fk_user_favorites_storefront_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        default=lambda: DEFAULT_STOREFRONT_ID,
        server_default=sa.text("'00000000-0000-0000-0000-000000000001'::uuid"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    vehicle_id = synonym("product_id")
    added_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
