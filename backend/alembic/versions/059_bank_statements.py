"""bank statements

Revision ID: 059
Revises: 058
Create Date: 2026-06-22 10:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None

OPERATION_KINDS = [
    {"id": 1, "name": "Оплата покупателя", "direction": "income"},
    {"id": 2, "name": "Поступление по платежным картам/СБП", "direction": "income"},
    {"id": 3, "name": "Возврат от поставщика", "direction": "income"},
    {"id": 4, "name": "Получение займа", "direction": "income"},
    {"id": 5, "name": "Возврат займа контрагентом", "direction": "income"},
    {"id": 6, "name": "Получение кредита", "direction": "income"},
    {"id": 7, "name": "Взнос в уставный капитал", "direction": "income"},
    {"id": 8, "name": "Перевод с другого счета", "direction": "income"},
    {"id": 9, "name": "Взнос наличными", "direction": "income"},
    {"id": 10, "name": "Возврат налога", "direction": "income"},
    {"id": 11, "name": "Прочие доходы", "direction": "income"},
    {"id": 12, "name": "Оплата поставщику", "direction": "expense"},
    {"id": 13, "name": "Перечисление налога", "direction": "expense"},
    {"id": 14, "name": "Комиссия банка", "direction": "expense"},
    {"id": 15, "name": "Перечисление зарплаты", "direction": "expense"},
    {"id": 16, "name": "Возврат покупателю", "direction": "expense"},
    {"id": 17, "name": "Выдача займа", "direction": "expense"},
    {"id": 18, "name": "Возврат займа", "direction": "expense"},
    {"id": 19, "name": "Возврат кредита", "direction": "expense"},
    {"id": 20, "name": "Перевод на другой счет", "direction": "expense"},
    {"id": 21, "name": "Снятие наличных", "direction": "expense"},
    {"id": 22, "name": "Не определено", "direction": None},
]


def upgrade() -> None:
    op.create_table(
        "operation_kinds",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=True),
        sa.CheckConstraint(
            "direction IN ('income', 'expense') OR direction IS NULL",
            name="ck_operation_kinds_direction",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.bulk_insert(
        sa.table(
            "operation_kinds",
            sa.column("id", sa.SmallInteger),
            sa.column("name", sa.String),
            sa.column("direction", sa.String),
        ),
        OPERATION_KINDS,
    )

    op.create_table(
        "bank_statement_imports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("encoding", sa.String(length=32), nullable=False),
        sa.Column("format_version", sa.String(length=20), nullable=True),
        sa.Column("sender", sa.String(length=255), nullable=True),
        sa.Column("recipient", sa.String(length=255), nullable=True),
        sa.Column("created_on", sa.Date(), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("statement_account", sa.String(length=20), nullable=True),
        sa.Column("opening_balance", sa.Numeric(20, 2), nullable=True),
        sa.Column("total_income", sa.Numeric(20, 2), nullable=True),
        sa.Column("total_expense", sa.Numeric(20, 2), nullable=True),
        sa.Column("closing_balance", sa.Numeric(20, 2), nullable=True),
        sa.Column("transactions_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'uploaded'"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("raw_header", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("raw_account_section", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "file_sha256", name="uq_bank_statement_imports_company_checksum"),
    )
    op.create_index("idx_bank_statement_imports_company_id", "bank_statement_imports", ["company_id"])
    op.create_index("idx_bank_statement_imports_document_id", "bank_statement_imports", ["document_id"])

    op.create_table(
        "bank_accounts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_number", sa.String(length=20), nullable=False),
        sa.Column("owner_name", sa.String(length=255), nullable=False),
        sa.Column("owner_inn", sa.String(length=12), nullable=False),
        sa.Column("owner_kpp", sa.String(length=9), nullable=True),
        sa.Column("bank_name", sa.String(length=255), nullable=False),
        sa.Column("bik", sa.String(length=9), nullable=False),
        sa.Column("correspondent_account", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "account_number", name="uq_bank_accounts_company_account"),
    )
    op.create_index("idx_bank_accounts_owner_inn", "bank_accounts", ["owner_inn"])

    op.create_table(
        "bank_transactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_kind_id", sa.SmallInteger(), nullable=True),
        sa.Column("operation_kind", sa.String(length=100), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("document_section", sa.String(length=100), nullable=True),
        sa.Column("document_number", sa.String(length=50), nullable=True),
        sa.Column("document_date", sa.Date(), nullable=True),
        sa.Column("execution_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("payer_account", sa.String(length=20), nullable=True),
        sa.Column("payer_correspondent", sa.String(length=20), nullable=True),
        sa.Column("payer_write_off_date", sa.Date(), nullable=True),
        sa.Column("payer_inn", sa.String(length=12), nullable=True),
        sa.Column("payer_name", sa.String(length=255), nullable=True),
        sa.Column("payer_bank_name", sa.String(length=255), nullable=True),
        sa.Column("payer_bik", sa.String(length=9), nullable=True),
        sa.Column("payer_kpp", sa.String(length=9), nullable=True),
        sa.Column("recipient_account", sa.String(length=20), nullable=True),
        sa.Column("recipient_receipt_date", sa.Date(), nullable=True),
        sa.Column("recipient_inn", sa.String(length=12), nullable=True),
        sa.Column("recipient_name", sa.String(length=255), nullable=True),
        sa.Column("recipient_bank_name", sa.String(length=255), nullable=True),
        sa.Column("recipient_bik", sa.String(length=9), nullable=True),
        sa.Column("recipient_kpp", sa.String(length=9), nullable=True),
        sa.Column("recipient_correspondent", sa.String(length=20), nullable=True),
        sa.Column("kbk", sa.String(length=32), nullable=True),
        sa.Column("okato", sa.String(length=32), nullable=True),
        sa.Column("tax_reason", sa.String(length=32), nullable=True),
        sa.Column("tax_period", sa.String(length=32), nullable=True),
        sa.Column("tax_document_number", sa.String(length=50), nullable=True),
        sa.Column("tax_document_date", sa.String(length=32), nullable=True),
        sa.Column("tax_payer_status", sa.String(length=32), nullable=True),
        sa.Column("payment_type", sa.String(length=50), nullable=True),
        sa.Column("payment_code", sa.String(length=3), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("payment_purpose", sa.Text(), nullable=True),
        sa.Column("is_self_transfer", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("counterparty_name", sa.String(length=255), nullable=True),
        sa.Column("counterparty_inn", sa.String(length=12), nullable=True),
        sa.Column("counterparty_kpp", sa.String(length=9), nullable=True),
        sa.Column("counterparty_account", sa.String(length=20), nullable=True),
        sa.Column("raw_operation", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["import_id"], ["bank_statement_imports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operation_kind_id"], ["operation_kinds.id"]),
        sa.PrimaryKeyConstraint("id"),
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
    )
    op.create_index("idx_bank_transactions_company_document_date", "bank_transactions", ["company_id", "document_date"])
    op.create_index("idx_bank_transactions_company_operation_kind", "bank_transactions", ["company_id", "operation_kind"])
    op.create_index("idx_bank_transactions_company_direction", "bank_transactions", ["company_id", "direction"])
    op.create_index("idx_bank_transactions_company_counterparty_inn", "bank_transactions", ["company_id", "counterparty_inn"])


def downgrade() -> None:
    op.drop_index("idx_bank_transactions_company_counterparty_inn", table_name="bank_transactions")
    op.drop_index("idx_bank_transactions_company_direction", table_name="bank_transactions")
    op.drop_index("idx_bank_transactions_company_operation_kind", table_name="bank_transactions")
    op.drop_index("idx_bank_transactions_company_document_date", table_name="bank_transactions")
    op.drop_table("bank_transactions")
    op.drop_index("idx_bank_accounts_owner_inn", table_name="bank_accounts")
    op.drop_table("bank_accounts")
    op.drop_index("idx_bank_statement_imports_document_id", table_name="bank_statement_imports")
    op.drop_index("idx_bank_statement_imports_company_id", table_name="bank_statement_imports")
    op.drop_table("bank_statement_imports")
    op.drop_table("operation_kinds")
