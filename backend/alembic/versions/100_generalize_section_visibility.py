"""Generalize workspace role visibility to application scopes.

Revision ID: 100
Revises: 099
Create Date: 2026-08-26
"""

from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast

import sqlalchemy as sa
from alembic import op

revision: str = "100"
down_revision: str | None = "099"
branch_labels: str | None = None
depends_on: str | None = None

_OLD_TABLE = "workspace_role_section_visibility"
_TABLE = "section_visibility"
_PRICE_MARKER_COLUMN = "price_on_request"


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _ensure_price_on_request_schema() -> None:
    """Repair databases that applied the other migration stamped as 099.

    Two different revisions with ID 099 briefly existed.  A database stamped
    with 099 may therefore contain only the visibility schema.  In that state
    Alembic considers the canonical price revision applied, so revision 100
    must install its schema before continuing.
    """
    if _PRICE_MARKER_COLUMN in _column_names("special_equipment_products"):
        return

    migration_path = Path(__file__).with_name(
        "099_special_equipment_price_on_request.py"
    )
    namespace = runpy.run_path(str(migration_path))
    upgrade_price_schema = cast(Callable[[], None], namespace["upgrade"])
    upgrade_price_schema()


def upgrade() -> None:
    """Converge every possible former 099 state on the canonical schema."""
    _ensure_price_on_request_schema()

    tables = _table_names()
    if _TABLE in tables:
        if "scope" not in _column_names(_TABLE):
            raise RuntimeError(
                "section_visibility exists without the expected scope column"
            )
        return
    if _OLD_TABLE not in tables:
        raise RuntimeError(
            "neither workspace_role_section_visibility nor section_visibility exists"
        )

    _upgrade_visibility_schema()


def _upgrade_visibility_schema() -> None:
    """Rename the existing table while retaining every stored override."""
    op.rename_table(_OLD_TABLE, _TABLE)
    op.alter_column(
        _TABLE,
        "role",
        new_column_name="scope",
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )

    op.drop_constraint(
        "uq_workspace_role_section_visibility_role_section_key",
        _TABLE,
        type_="unique",
    )
    op.drop_constraint(
        "ck_workspace_role_section_visibility_role",
        _TABLE,
        type_="check",
    )
    op.drop_constraint(
        "fk_workspace_role_section_visibility_updated_by",
        _TABLE,
        type_="foreignkey",
    )
    op.execute(
        sa.text(
            "ALTER TABLE section_visibility "
            "RENAME CONSTRAINT pk_workspace_role_section_visibility "
            "TO pk_section_visibility"
        )
    )

    op.create_unique_constraint(
        "uq_section_visibility_scope_section_key",
        _TABLE,
        ["scope", "section_key"],
    )
    op.create_check_constraint(
        "ck_section_visibility_scope",
        _TABLE,
        "scope IN ('public', 'carcraft_employee', 'leasing_company', "
        "'dealer', 'distributor')",
    )
    op.create_foreign_key(
        "fk_section_visibility_updated_by",
        _TABLE,
        "users",
        ["updated_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Return to the canonical price-only revision 099 state."""
    tables = _table_names()
    if _OLD_TABLE in tables:
        return
    if _TABLE not in tables:
        raise RuntimeError(
            "neither section_visibility nor workspace_role_section_visibility exists"
        )

    _downgrade_visibility_schema()


def _downgrade_visibility_schema() -> None:
    """Restore the role-only schema, discarding unsupported new scopes."""
    op.execute(
        sa.text(
            "DELETE FROM section_visibility "
            "WHERE scope IN ('public', 'carcraft_employee')"
        )
    )
    op.drop_constraint(
        "uq_section_visibility_scope_section_key",
        _TABLE,
        type_="unique",
    )
    op.drop_constraint(
        "ck_section_visibility_scope",
        _TABLE,
        type_="check",
    )
    op.drop_constraint(
        "fk_section_visibility_updated_by",
        _TABLE,
        type_="foreignkey",
    )
    op.execute(
        sa.text(
            "ALTER TABLE section_visibility "
            "RENAME CONSTRAINT pk_section_visibility "
            "TO pk_workspace_role_section_visibility"
        )
    )

    op.create_unique_constraint(
        "uq_workspace_role_section_visibility_role_section_key",
        _TABLE,
        ["scope", "section_key"],
    )
    op.create_check_constraint(
        "ck_workspace_role_section_visibility_role",
        _TABLE,
        "scope IN ('leasing_company', 'dealer', 'distributor')",
    )
    op.create_foreign_key(
        "fk_workspace_role_section_visibility_updated_by",
        _TABLE,
        "users",
        ["updated_by"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column(
        _TABLE,
        "scope",
        new_column_name="role",
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )
    op.rename_table(_TABLE, _OLD_TABLE)
