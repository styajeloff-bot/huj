"""Version the bank-account request form without changing saved request snapshots.

Revision ID: 157
Revises: 156
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "157"
down_revision = "156"
branch_labels = None
depends_on = None


def _set_schema(version: int) -> None:
    bank_name = {"id": "name", "kind": "text", "label": "Название банка", "required": True}
    bik = {"id": "bik", "kind": "digits", "label": "БИК", "required": True, "exact_digits": 9}
    account = {"id": "acc_number", "kind": "digits", "label": "Расчётный счёт", "required": True, "exact_digits": 20}
    if version == 1:
        fields = [
            {"id": "bank", "kind": "object", "label": "Банк", "required": True, "fields": [bank_name, bik]},
            account,
        ]
    else:
        fields = [
            {"id": "bank", "kind": "text", "label": "Наименование банка", "required": True},
            account, bik,
            {"id": "correspondent_account", "kind": "digits", "label": "Корр. счёт", "required": True, "exact_digits": 20},
        ]
    schema = {
        "schema_version": version, "kind": "open_bank_accounts",
        "fields": [{
            "id": "accounts", "kind": "list", "label": "Расчётные счета", "required": True,
            "min_items": 1, "max_items": 10, "item_fields": fields,
        }],
    }
    types = sa.table("document_types", sa.column("type_code", sa.String), sa.column("form_schema", postgresql.JSONB))
    op.execute(types.update().where(types.c.type_code == "open_bank_accounts").values(form_schema=schema))


def upgrade() -> None:
    # Pending and answered requests own immutable form_schema/form_data snapshots.
    _set_schema(2)


def downgrade() -> None:
    # Existing v2 snapshots remain v2 even when the catalog returns to v1.
    _set_schema(1)
