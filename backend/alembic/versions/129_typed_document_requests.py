"""Bitrix #20418 typed document requests.

Revision ID: 129
Revises: 128
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "129"
down_revision = "128"
branch_labels = None
depends_on = None

SCHEMAS = {
    "main_counterparties": {
        "schema_version": 1, "kind": "main_counterparties",
        "fields": [{"id": "counterparties", "kind": "list", "label": "Контрагенты", "required": True, "min_items": 1, "max_items": 10, "item_fields": [{"id": "name", "kind": "text", "label": "Название", "required": True}, {"id": "inn", "kind": "digits", "label": "ИНН", "required": True, "allowed_lengths": [10, 12]}]}],
    },
    "open_bank_accounts": {
        "schema_version": 1, "kind": "open_bank_accounts",
        "fields": [{"id": "accounts", "kind": "list", "label": "Расчётные счета", "required": True, "min_items": 1, "max_items": 10, "item_fields": [{"id": "bank", "kind": "object", "label": "Банк", "required": True, "fields": [{"id": "name", "kind": "text", "label": "Название банка", "required": True}, {"id": "bik", "kind": "digits", "label": "БИК", "required": True, "exact_digits": 9}]}, {"id": "acc_number", "kind": "digits", "label": "Расчётный счёт", "required": True, "exact_digits": 20}]}],
    },
    "beneficial_owner": {
        "schema_version": 1, "kind": "beneficial_owner",
        "fields": [{"id": "fio", "kind": "text", "label": "ФИО выгодоприобретателя", "required": True}],
    },
    "snils": {
        "schema_version": 1, "kind": "snils",
        "fields": [{"id": "number", "kind": "digits", "label": "СНИЛС", "required": True, "exact_digits": 11}],
    },
}
TYPES = {
    "ceo_passport_page23": "Паспорт ген. директора (2 и 3 страницы)",
    "appointment_docs": "Документация о назначении (решение/протокол: номер, дата, срок полномочий)",
    "licenses": "Наличие лицензий", "sro": "Членство в СРО",
    "main_counterparties": "Основные контрагенты (поставщики/покупатели)",
    "open_bank_accounts": "Перечень открытых расчётных счетов",
    "loans_docs": "Сведения о кредитах, займах, лизинге (таблица с суммой, остатком, обеспечением)",
    "third_member_guarantees": "Поручительства за третьих лиц",
    "additional_collateral": "Возможность предоставления дополнительного обеспечения",
    "management_company": "Сведения об управляющей компании (если применимо)",
    "beneficial_owner": "Выгодоприобретатель по сделке",
    "state_defense_order": "Вопрос о гособоронзаказе (сопровождаемая сделка)",
    "snils": "СНИЛС",
}


def upgrade() -> None:
    op.add_column("document_types", sa.Column("has_form", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("document_types", sa.Column("form_schema", postgresql.JSONB(none_as_null=True), nullable=True))
    op.add_column("application_document_requests", sa.Column("has_form", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("application_document_requests", sa.Column("form_schema", postgresql.JSONB(none_as_null=True), nullable=True))
    op.add_column("application_document_requests", sa.Column("form_data", postgresql.JSONB(none_as_null=True), nullable=True))
    op.add_column("application_document_requests", sa.Column("idempotency_key", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_document_request_idempotency_key", "application_document_requests", ["idempotency_key"])
    op.create_check_constraint("ck_document_types_form_schema", "document_types", "(has_form = false AND form_schema IS NULL) OR (has_form = true AND form_schema IS NOT NULL AND form_schema <> '{}'::jsonb)")
    op.create_check_constraint("ck_document_requests_form_schema", "application_document_requests", "(has_form = false AND form_schema IS NULL) OR (has_form = true AND form_schema IS NOT NULL AND form_schema <> '{}'::jsonb)")
    table = sa.table("document_types", sa.column("id", postgresql.UUID(as_uuid=True)), sa.column("name", sa.String), sa.column("type_code", sa.String), sa.column("display_name", sa.String), sa.column("has_form", sa.Boolean), sa.column("form_schema", postgresql.JSONB(none_as_null=True)), sa.column("auto_approve", sa.Boolean))
    for code, name in TYPES.items():
        schema = SCHEMAS.get(code)
        form_schema = schema if schema is not None else sa.null()
        stmt = postgresql.insert(table).values(id=uuid.uuid4(), name=name, type_code=code, display_name=name, has_form=schema is not None, form_schema=form_schema, auto_approve=False)
        op.execute(stmt.on_conflict_do_update(index_elements=["type_code"], set_={"has_form": schema is not None, "form_schema": form_schema, "auto_approve": False}))


def downgrade() -> None:
    op.drop_constraint("ck_document_requests_form_schema", "application_document_requests", type_="check")
    op.drop_constraint("ck_document_types_form_schema", "document_types", type_="check")
    op.drop_constraint("uq_document_request_idempotency_key", "application_document_requests", type_="unique")
    for column in ("idempotency_key", "form_data", "form_schema", "has_form"):
        op.drop_column("application_document_requests", column)
    op.drop_column("document_types", "form_schema")
    op.drop_column("document_types", "has_form")
