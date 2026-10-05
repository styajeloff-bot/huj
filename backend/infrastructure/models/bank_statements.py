"""SQLAlchemy ORM models for bank statement imports and transactions."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class BankStatementImport(Base):
    """Uploaded 1CClientBankExchange file metadata."""

    __tablename__ = "bank_statement_imports"
    __table_args__ = (
        sa.UniqueConstraint(
            "company_id",
            "file_sha256",
            name="uq_bank_statement_imports_company_checksum",
        ),
        sa.Index("idx_bank_statement_imports_company_id", "company_id"),
        sa.Index("idx_bank_statement_imports_document_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    file_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    encoding: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    format_version: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    sender: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    recipient: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    created_on: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    period_start: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    period_end: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    statement_account: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    opening_balance: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(20, 2), nullable=True)
    total_income: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(20, 2), nullable=True)
    total_expense: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(20, 2), nullable=True)
    closing_balance: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(20, 2), nullable=True)
    transactions_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'uploaded'")
    )
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    raw_header: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    raw_account_section: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class BankAccount(Base):
    """Bank account owned by the uploading company."""

    __tablename__ = "bank_accounts"
    __table_args__ = (
        sa.UniqueConstraint(
            "company_id", "account_number", name="uq_bank_accounts_company_account"
        ),
        sa.Index("idx_bank_accounts_owner_inn", "owner_inn"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False
    )
    account_number: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    owner_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    owner_inn: Mapped[str] = mapped_column(sa.String(12), nullable=False)
    owner_kpp: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)
    bank_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    bik: Mapped[str] = mapped_column(sa.String(9), nullable=False)
    correspondent_account: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class OperationKind(Base):
    """Lookup table for recognized operation types."""

    __tablename__ = "operation_kinds"
    __table_args__ = (
        sa.CheckConstraint(
            "direction IN ('income', 'expense') OR direction IS NULL",
            name="ck_operation_kinds_direction",
        ),
    )

    id: Mapped[int] = mapped_column(sa.SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False, unique=True)
    direction: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)


class BankTransaction(Base):
    """Normalized transaction row parsed from a bank statement."""

    __tablename__ = "bank_transactions"
    __table_args__ = (
        sa.UniqueConstraint(
            "import_id",
            "document_section",
            "document_number",
            "document_date",
            "amount",
            "payer_account",
            "recipient_account",
            name="uq_bank_transactions_import_document",
        ),
        sa.Index("idx_bank_transactions_company_document_date", "company_id", "document_date"),
        sa.Index("idx_bank_transactions_company_operation_kind", "company_id", "operation_kind"),
        sa.Index("idx_bank_transactions_company_direction", "company_id", "direction"),
        sa.Index("idx_bank_transactions_company_counterparty_inn", "company_id", "counterparty_inn"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    import_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("bank_statement_imports.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False
    )
    operation_kind_id: Mapped[int | None] = mapped_column(
        sa.SmallInteger, sa.ForeignKey("operation_kinds.id"), nullable=True
    )
    operation_kind: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    direction: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    document_section: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    document_number: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    document_date: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    execution_date: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    amount: Mapped[sa.Numeric] = mapped_column(sa.Numeric(20, 2), nullable=False)

    payer_account: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    payer_correspondent: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    payer_write_off_date: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    payer_inn: Mapped[str | None] = mapped_column(sa.String(12), nullable=True)
    payer_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    payer_bank_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    payer_bik: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)
    payer_kpp: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)

    recipient_account: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    recipient_receipt_date: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    recipient_inn: Mapped[str | None] = mapped_column(sa.String(12), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    recipient_bank_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    recipient_bik: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)
    recipient_kpp: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)
    recipient_correspondent: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)

    kbk: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    okato: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    tax_reason: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    tax_period: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    tax_document_number: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    tax_document_date: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    tax_payer_status: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)

    payment_type: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    payment_code: Mapped[str | None] = mapped_column(sa.String(3), nullable=True)
    priority: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    payment_purpose: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_self_transfer: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    counterparty_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    counterparty_inn: Mapped[str | None] = mapped_column(sa.String(12), nullable=True)
    counterparty_kpp: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)
    counterparty_account: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    raw_operation: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
