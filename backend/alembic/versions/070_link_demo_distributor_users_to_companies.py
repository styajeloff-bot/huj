"""Link demo distributor users to demo distributor companies.

Revision ID: 070
Revises: 069
Create Date: 2026-07-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "070"
down_revision: str | None = "069"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            WITH mapping(phone, inn) AS (
                VALUES
                    ('+76661234573', '7701234570'),
                    ('+76661234574', '7701234571')
            ),
            pairs AS (
                SELECT u.id AS user_id, c.id AS company_id
                FROM mapping m
                JOIN users u ON u.phone = m.phone
                JOIN companies c ON c.inn = m.inn
                WHERE u.role = 'distributor'
                  AND c.company_type = 'distributor'
            )
            UPDATE users u
            SET company_id = pairs.company_id,
                updated_at = CURRENT_TIMESTAMP
            FROM pairs
            WHERE u.id = pairs.user_id;
            """
        )
    )

    op.execute(
        sa.text(
            """
            WITH mapping(phone, inn) AS (
                VALUES
                    ('+76661234573', '7701234570'),
                    ('+76661234574', '7701234571')
            ),
            pairs AS (
                SELECT u.id AS user_id, c.id AS company_id
                FROM mapping m
                JOIN users u ON u.phone = m.phone
                JOIN companies c ON c.inn = m.inn
                WHERE u.role = 'distributor'
                  AND c.company_type = 'distributor'
            )
            INSERT INTO user_companies (
                user_id,
                company_id,
                created_at,
                sub_role,
                can_view_applications,
                can_create_applications
            )
            SELECT
                pairs.user_id,
                pairs.company_id,
                CURRENT_TIMESTAMP,
                'administrator',
                TRUE,
                TRUE
            FROM pairs
            ON CONFLICT (user_id, company_id) DO UPDATE
            SET sub_role = EXCLUDED.sub_role,
                can_view_applications = EXCLUDED.can_view_applications,
                can_create_applications = EXCLUDED.can_create_applications;
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            WITH mapping(phone, inn) AS (
                VALUES
                    ('+76661234573', '7701234570'),
                    ('+76661234574', '7701234571')
            ),
            pairs AS (
                SELECT u.id AS user_id, c.id AS company_id
                FROM mapping m
                JOIN users u ON u.phone = m.phone
                JOIN companies c ON c.inn = m.inn
            )
            DELETE FROM user_companies uc
            USING pairs
            WHERE uc.user_id = pairs.user_id
              AND uc.company_id = pairs.company_id;
            """
        )
    )

    op.execute(
        sa.text(
            """
            WITH mapping(phone, inn) AS (
                VALUES
                    ('+76661234573', '7701234570'),
                    ('+76661234574', '7701234571')
            ),
            pairs AS (
                SELECT u.id AS user_id, c.id AS company_id
                FROM mapping m
                JOIN users u ON u.phone = m.phone
                JOIN companies c ON c.inn = m.inn
            )
            UPDATE users u
            SET company_id = NULL,
                updated_at = CURRENT_TIMESTAMP
            FROM pairs
            WHERE u.id = pairs.user_id
              AND u.company_id = pairs.company_id;
            """
        )
    )
