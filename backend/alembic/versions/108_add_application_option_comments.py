"""Add nullable comments to persisted application options.

Revision ID: 108
Revises: 107
Create Date: 2026-09-01
"""

from __future__ import annotations

from alembic import op

revision: str = "108"
down_revision: str | None = "107"
branch_labels: str | None = None
depends_on: str | None = None

_OPTION_COLUMNS = ("equipments", "services")


def _add_missing_nullable_comments(column_name: str) -> None:
    op.execute(
        f"""
        UPDATE application_vehicles
        SET {column_name} = (
            SELECT jsonb_agg(
                CASE
                    WHEN jsonb_typeof(option_item) = 'object'
                         AND NOT option_item ? 'comment'
                    THEN option_item || '{{"comment": null}}'::jsonb
                    ELSE option_item
                END
                ORDER BY ordinal
            )
            FROM jsonb_array_elements({column_name})
                WITH ORDINALITY AS options(option_item, ordinal)
        )
        WHERE jsonb_typeof({column_name}) = 'array'
          AND EXISTS (
              SELECT 1
              FROM jsonb_array_elements({column_name}) AS options(option_item)
              WHERE jsonb_typeof(option_item) = 'object'
                AND NOT option_item ? 'comment'
          )
        """
    )


def _remove_nullable_comments(column_name: str) -> None:
    op.execute(
        f"""
        UPDATE application_vehicles
        SET {column_name} = (
            SELECT jsonb_agg(
                CASE
                    WHEN jsonb_typeof(option_item) = 'object'
                         AND option_item -> 'comment' = 'null'::jsonb
                    THEN option_item - 'comment'
                    ELSE option_item
                END
                ORDER BY ordinal
            )
            FROM jsonb_array_elements({column_name})
                WITH ORDINALITY AS options(option_item, ordinal)
        )
        WHERE jsonb_typeof({column_name}) = 'array'
          AND EXISTS (
              SELECT 1
              FROM jsonb_array_elements({column_name}) AS options(option_item)
              WHERE jsonb_typeof(option_item) = 'object'
                AND option_item -> 'comment' = 'null'::jsonb
          )
        """
    )


def upgrade() -> None:
    for column_name in _OPTION_COLUMNS:
        _add_missing_nullable_comments(column_name)


def downgrade() -> None:
    for column_name in reversed(_OPTION_COLUMNS):
        _remove_nullable_comments(column_name)
