"""Add test users by role

Revision ID: 005
Revises: 004
Create Date: 2026-05-21 06:28:54
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    test_users = [
        ("+76661234568", "dealer"),
        ("+76661234571", "leasing_company"),
        ("+76661234572", "leasing_company"),
        ("+76661234573", "distributor"),
        ("+76661234574", "distributor"),
    ]

    values_clause = ",\n        ".join(
        f"(gen_random_uuid(), '{phone}', '{role}', true, false, false, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        for phone, role in test_users
    )

    op.execute(sa.text(f"""
        INSERT INTO users
            (id, phone, role, is_active, email_verified, phone_verified, mfa_enabled, created_at, updated_at)
        VALUES
        {values_clause}
        ON CONFLICT (phone) DO NOTHING
    """))


def downgrade() -> None:
    phones = [
        "+76661234568",
        "+76661234571",
        "+76661234572",
        "+76661234573",
        "+76661234574",
    ]
    phones_literal = ", ".join(f"'{p}'" for p in phones)

    op.execute(sa.text(f"""
        DELETE FROM users WHERE phone IN ({phones_literal})
    """))
