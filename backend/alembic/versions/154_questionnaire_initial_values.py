"""Backfill missing questionnaire defaults without replacing explicit values.

Revision ID: 154_questionnaire_defaults
Revises: 153
Create Date: 2026-10-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "154_questionnaire_defaults"
down_revision = "153"
branch_labels = None
depends_on = None

# Frozen revision data: do not import defaults from the changing application code.
_FILE_DEFAULTS = {
    "loans_credits_leasing": "Данные о кредитах, займах и лизинге отсутствуют",
    "third_party_guarantees": "Данные о поручительствах за третьих лиц отсутствуют",
    "additional_collateral_available": "Данные о возможности предоставления дополнительного обеспечения отсутствуют",
    "state_defense_order": "Документ о гособоронзаказе не предоставлен",
    "director_appointment_document": "Документ о назначении руководителя не предоставлен",
}
_BOOLEAN_DEFAULTS = (
    "postal_address_matches_legal",
    "website_in_blocked_domains_registry",
    "director_is_pdl",
    "director_name_changed",
)


def upgrade() -> None:
    for field in (*_FILE_DEFAULTS, *_BOOLEAN_DEFAULTS):
        is_json = field in _FILE_DEFAULTS
        value = (
            {"status": "missing", "text": _FILE_DEFAULTS[field], "documents": []}
            if is_json else False
        )
        sources = (
            {f"{field}.{part}": "system" for part in ("status", "text", "documents")}
            if is_json else {field: "system"}
        )
        missing = f"({field} IS NULL OR {field} = 'null'::jsonb)" if is_json else f"{field} IS NULL"
        # Protect the whole absent value when its root or any nested member was
        # explicitly cleared. Existing non-null JSON is deliberately unchanged.
        statement = sa.text(f"""
            UPDATE application_questionnaires
            SET {field} = :value,
                field_sources = COALESCE(field_sources, '{{}}'::jsonb) || :sources
            WHERE {missing}
              AND NOT EXISTS (
                SELECT 1
                FROM jsonb_each_text(COALESCE(field_sources, '{{}}'::jsonb)) AS origin(path, source)
                WHERE (origin.path = :field OR left(origin.path, length(:field) + 1) = :field || '.')
                  AND origin.source IN ('manual', 'document_request')
              )
        """).bindparams(
            sa.bindparam("value", value, type_=JSONB() if is_json else sa.Boolean()),
            sa.bindparam("sources", sources, type_=JSONB()),
            sa.bindparam("field", field, type_=sa.String()),
        )
        op.get_bind().execute(statement)


def downgrade() -> None:
    # A populated default cannot be distinguished from a later accepted value;
    # retaining data is safer than clearing it during a schema rollback.
    pass
