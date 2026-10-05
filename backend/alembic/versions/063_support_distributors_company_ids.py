"""Point support-program distributor links to companies.

Revision ID: 063
Revises: 062
Create Date: 2026-06-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "063"
down_revision: str | None = "062"
branch_labels: str | None = None
depends_on: str | None = None


def _drop_distributor_fks() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        DO $$
        DECLARE
            fk record;
        BEGIN
            FOR fk IN
                SELECT
                    constraint_table.relname AS table_name,
                    constraint_info.conname AS constraint_name
                FROM pg_constraint AS constraint_info
                JOIN pg_class AS constraint_table
                    ON constraint_table.oid = constraint_info.conrelid
                JOIN pg_attribute AS column_info
                    ON column_info.attrelid = constraint_info.conrelid
                   AND column_info.attnum = ANY(constraint_info.conkey)
                WHERE constraint_info.contype = 'f'
                  AND constraint_table.relname IN (
                      'support_programs',
                      'support_program_distributors'
                  )
                  AND column_info.attname = 'distributor_id'
            LOOP
                EXECUTE format(
                    'ALTER TABLE %I DROP CONSTRAINT %I',
                    fk.table_name,
                    fk.constraint_name
                );
            END LOOP;
        END $$;
    """))


def _create_company_fks() -> None:
    op.create_foreign_key(
        "support_programs_distributor_id_fkey",
        "support_programs",
        "companies",
        ["distributor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "support_program_distributors_distributor_id_fkey",
        "support_program_distributors",
        "companies",
        ["distributor_id"],
        ["id"],
        ondelete="CASCADE",
    )


def _create_legacy_distributor_fks() -> None:
    op.create_foreign_key(
        "support_programs_distributor_id_fkey",
        "support_programs",
        "distributors",
        ["distributor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "support_program_distributors_distributor_id_fkey",
        "support_program_distributors",
        "distributors",
        ["distributor_id"],
        ["id"],
        ondelete="CASCADE",
    )


def upgrade() -> None:
    bind = op.get_bind()

    _drop_distributor_fks()

    bind.execute(sa.text("""
        UPDATE support_programs AS program
        SET distributor_id = distributor.company_id
        FROM distributors AS distributor
        WHERE program.distributor_id = distributor.id
          AND distributor.company_id IS NOT NULL
    """))
    bind.execute(sa.text("""
        UPDATE support_programs AS program
        SET distributor_id = NULL
        WHERE program.distributor_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM companies WHERE companies.id = program.distributor_id
          )
    """))

    bind.execute(sa.text("""
        CREATE TEMP TABLE _support_program_distributor_companies AS
        SELECT
            mapped.support_program_id,
            mapped.distributor_id,
            MIN(mapped.created_at) AS created_at
        FROM (
            SELECT
                spd.support_program_id,
                COALESCE(distributor.company_id, company.id) AS distributor_id,
                spd.created_at
            FROM support_program_distributors AS spd
            LEFT JOIN distributors AS distributor
                ON distributor.id = spd.distributor_id
            LEFT JOIN companies AS company
                ON company.id = spd.distributor_id
            WHERE COALESCE(distributor.company_id, company.id) IS NOT NULL
        ) AS mapped
        GROUP BY mapped.support_program_id, mapped.distributor_id
    """))
    bind.execute(sa.text("DELETE FROM support_program_distributors"))
    bind.execute(sa.text("""
        INSERT INTO support_program_distributors (
            support_program_id,
            distributor_id,
            created_at
        )
        SELECT support_program_id, distributor_id, created_at
        FROM _support_program_distributor_companies
    """))
    bind.execute(sa.text("DROP TABLE _support_program_distributor_companies"))

    _create_company_fks()


def downgrade() -> None:
    bind = op.get_bind()

    _drop_distributor_fks()

    bind.execute(sa.text("""
        UPDATE support_programs AS program
        SET distributor_id = legacy_distributor.id
        FROM (
            SELECT DISTINCT ON (company_id) id, company_id
            FROM distributors
            WHERE company_id IS NOT NULL
            ORDER BY company_id, id
        ) AS legacy_distributor
        WHERE program.distributor_id = legacy_distributor.company_id
    """))
    bind.execute(sa.text("""
        UPDATE support_programs AS program
        SET distributor_id = NULL
        WHERE program.distributor_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM distributors WHERE distributors.id = program.distributor_id
          )
    """))

    bind.execute(sa.text("""
        CREATE TEMP TABLE _support_program_distributor_legacy AS
        SELECT
            mapped.support_program_id,
            mapped.distributor_id,
            MIN(mapped.created_at) AS created_at
        FROM (
            SELECT
                spd.support_program_id,
                legacy_distributor.id AS distributor_id,
                spd.created_at
            FROM support_program_distributors AS spd
            JOIN (
                SELECT DISTINCT ON (company_id) id, company_id
                FROM distributors
                WHERE company_id IS NOT NULL
                ORDER BY company_id, id
            ) AS legacy_distributor
                ON legacy_distributor.company_id = spd.distributor_id
        ) AS mapped
        GROUP BY mapped.support_program_id, mapped.distributor_id
    """))
    bind.execute(sa.text("DELETE FROM support_program_distributors"))
    bind.execute(sa.text("""
        INSERT INTO support_program_distributors (
            support_program_id,
            distributor_id,
            created_at
        )
        SELECT support_program_id, distributor_id, created_at
        FROM _support_program_distributor_legacy
    """))
    bind.execute(sa.text("DROP TABLE _support_program_distributor_legacy"))

    _create_legacy_distributor_fks()
