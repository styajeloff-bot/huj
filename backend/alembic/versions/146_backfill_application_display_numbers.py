"""Backfill application display numbers.

Revision ID: 146
Revises: 145
Create Date: 2026-09-30
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision: str = "146"
down_revision: str | None = "145"
branch_labels: str | None = None
depends_on: str | None = None

_LOGGER = logging.getLogger("carcraft-backend")

_BACKFILL_SQL = sa.text(
    """
    WITH apps_to_update AS (
        SELECT
            a.id,
            btrim(c.inn) AS inn,
            timezone('UTC', a.created_at)::date AS app_date,
            to_char(timezone('UTC', a.created_at), 'DDMMYY') AS date_str,
            ROW_NUMBER() OVER (
                PARTITION BY btrim(c.inn), timezone('UTC', a.created_at)::date
                ORDER BY a.created_at, a.id
            ) AS rn
        FROM leasing_applications a
        JOIN companies c ON c.id = a.company_id
        WHERE a.display_number IS NULL
          AND c.inn IS NOT NULL
          AND btrim(c.inn) <> ''
    ),
    existing_max AS (
        SELECT
            btrim(c.inn) AS inn,
            timezone('UTC', a.created_at)::date AS app_date,
            MAX(CAST(substring(a.display_number from '-(\\d{3})$') AS int)) AS max_seq
        FROM leasing_applications a
        JOIN companies c ON c.id = a.company_id
        WHERE a.display_number IS NOT NULL
        GROUP BY btrim(c.inn), timezone('UTC', a.created_at)::date
    ),
    computed AS (
        SELECT
            u.id,
            u.inn || '-' || u.date_str || '-' || lpad((COALESCE(m.max_seq, 0) + u.rn)::text, 3, '0') AS new_display_number
        FROM apps_to_update u
        LEFT JOIN existing_max m ON m.inn = u.inn AND m.app_date = u.app_date
    )
    UPDATE leasing_applications la
    SET display_number = computed.new_display_number
    FROM computed
    WHERE la.id = computed.id
    """
)


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(_BACKFILL_SQL)
    rowcount = int(getattr(result, "rowcount", 0) or 0)
    _LOGGER.info("backfill_application_display_numbers: updated %d rows", rowcount)


def downgrade() -> None:
    # No-op: already issued display numbers may have been communicated
    # externally in emails, documents, or partner systems, so reverting them
    # back to NULL would cause data loss and inconsistency.
    pass
