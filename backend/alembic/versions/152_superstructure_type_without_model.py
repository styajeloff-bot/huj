"""Superstructure type without model, mark or modification.

Revision ID: 152
Revises: 151
Create Date: 2026-10-01 00:00:00
"""

from __future__ import annotations

import logging
import re

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

logger = logging.getLogger("alembic.runtime.migration")

revision = "152"
down_revision = "151"
branch_labels = None
depends_on = None

_CYRILLIC_LOWER_TRANSLIT: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}


def _to_slug(name: str) -> str:
    res: list[str] = []
    for ch in name.strip().casefold():
        if ch in _CYRILLIC_LOWER_TRANSLIT:
            res.append(_CYRILLIC_LOWER_TRANSLIT[ch])
        elif ch.isalnum():
            res.append(ch)
        else:
            res.append("-")
    slug = "".join(res)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "superstructure"


def upgrade() -> None:
    # 1. special_equipment_products: add superstructure_model_id column & index
    op.add_column(
        "special_equipment_products",
        sa.Column(
            "superstructure_model_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("special_equipment_models.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_se_products_superstructure_model",
        "special_equipment_products",
        ["superstructure_model_id", sa.text("updated_at DESC"), sa.text("id DESC")],
    )

    # 2. Backup table for superstructures model_id / modification_id
    op.execute(
        """
        CREATE TABLE special_equipment_superstructures_model_backup_152 (
            id UUID PRIMARY KEY,
            model_id UUID NOT NULL,
            modification_id UUID NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO special_equipment_superstructures_model_backup_152 (id, model_id, modification_id)
        SELECT id, model_id, modification_id FROM special_equipment_superstructures
        """
    )

    # 3. Fill superstructure_model_id on existing kit products from superstructures
    op.execute(
        """
        UPDATE special_equipment_products p
        SET superstructure_model_id = b.model_id
        FROM special_equipment_superstructures_model_backup_152 b
        WHERE p.superstructure_id = b.id
          AND p.superstructure_id IS NOT NULL;
        """
    )

    # 4. Composite FK (superstructure_modification_id, superstructure_model_id)
    op.create_foreign_key(
        "fk_se_products_superstructure_modification_model",
        "special_equipment_products",
        "special_equipment_modifications",
        ["superstructure_modification_id", "superstructure_model_id"],
        ["id", "model_id"],
        ondelete="RESTRICT",
    )

    # 5. Update ck_se_products_kind check constraint
    op.drop_constraint("ck_se_products_kind", "special_equipment_products", type_="check")
    op.create_check_constraint(
        "ck_se_products_kind",
        "special_equipment_products",
        """
        (superstructure_id IS NULL AND modification_id IS NOT NULL AND model_id IS NULL
           AND superstructure_modification_id IS NULL
           AND superstructure_name IS NULL AND superstructure_manufacturer IS NULL
           AND superstructure_model_id IS NULL)
        OR
        (superstructure_id IS NOT NULL AND model_id IS NOT NULL AND trim_id IS NULL
           AND superstructure_name IS NOT NULL AND btrim(superstructure_name) <> ''
           AND superstructure_manufacturer IS NOT NULL AND btrim(superstructure_manufacturer) <> ''
           AND superstructure_model_id IS NOT NULL)
        """,
    )

    # 6. Deduplicate superstructure names by lower(btrim(name))
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT
                s.id,
                s.name,
                s.slug,
                s.created_at,
                m.name AS model_name,
                mk.name AS mark_name
            FROM special_equipment_superstructures s
            JOIN special_equipment_models m ON m.id = s.model_id
            JOIN special_equipment_marks mk ON mk.id = m.mark_id
            ORDER BY s.created_at ASC, s.id ASC
            """
        )
    ).fetchall()

    seen_names: set[str] = set()
    used_slugs: set[str] = {r.slug.strip().casefold() for r in rows}

    for r in rows:
        raw_name = r.name
        norm_name = raw_name.strip().casefold()

        if norm_name not in seen_names:
            seen_names.add(norm_name)
            continue

        # Duplicate name detected
        mark_name = (r.mark_name or "").strip()
        model_name = (r.model_name or "").strip()
        base_new_name = f"{raw_name.strip()} ({mark_name} {model_name})".strip()
        cand_name = base_new_name
        idx = 2
        while cand_name.strip().casefold() in seen_names:
            cand_name = f"{base_new_name} {idx}"
            idx += 1

        seen_names.add(cand_name.strip().casefold())

        cand_slug = _to_slug(cand_name)
        base_slug = cand_slug
        s_idx = 2
        while cand_slug in used_slugs:
            cand_slug = f"{base_slug}-{s_idx}"
            s_idx += 1

        used_slugs.add(cand_slug)

        logger.info(
            "Renamed duplicate superstructure %s: '%s' -> '%s', slug -> '%s'",
            r.id,
            raw_name,
            cand_name,
            cand_slug,
        )
        conn.execute(
            sa.text(
                """
                UPDATE special_equipment_superstructures
                SET name = :name, slug = :slug
                WHERE id = :id
                """
            ),
            {"id": r.id, "name": cand_name, "slug": cand_slug},
        )

    # 7. Drop old constraints and columns from special_equipment_superstructures
    op.drop_index(
        "uq_se_superstructures_model_mod_name",
        table_name="special_equipment_superstructures",
    )
    op.drop_index(
        "uq_se_superstructures_model_mod_slug",
        table_name="special_equipment_superstructures",
    )
    op.drop_index(
        "idx_se_superstructures_model_mod_active_name",
        table_name="special_equipment_superstructures",
    )
    op.drop_constraint(
        "fk_se_superstructures_modification_model",
        "special_equipment_superstructures",
        type_="foreignkey",
    )
    op.execute(
        """
        DO $$
        DECLARE
            c_name text;
        BEGIN
            SELECT tc.constraint_name INTO c_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_name = 'special_equipment_superstructures'
              AND kcu.column_name = 'model_id'
              AND tc.constraint_name <> 'fk_se_superstructures_modification_model';
            IF c_name IS NOT NULL THEN
                EXECUTE 'ALTER TABLE special_equipment_superstructures DROP CONSTRAINT ' || quote_ident(c_name);
            END IF;
        END $$;
        """
    )
    op.drop_column("special_equipment_superstructures", "modification_id")
    op.drop_column("special_equipment_superstructures", "model_id")

    # 8. Create new unique indexes and active_name index
    op.create_index(
        "uq_se_superstructures_name",
        "special_equipment_superstructures",
        [sa.text("lower(btrim(name))")],
        unique=True,
    )
    op.create_index(
        "uq_se_superstructures_slug",
        "special_equipment_superstructures",
        [sa.text("lower(btrim(slug))")],
        unique=True,
    )
    op.create_index(
        "idx_se_superstructures_active_name",
        "special_equipment_superstructures",
        ["is_active", "name", "id"],
    )


def downgrade() -> None:
    # 1. Drop new indexes on superstructures
    op.drop_index(
        "idx_se_superstructures_active_name",
        table_name="special_equipment_superstructures",
    )
    op.drop_index(
        "uq_se_superstructures_slug",
        table_name="special_equipment_superstructures",
    )
    op.drop_index(
        "uq_se_superstructures_name",
        table_name="special_equipment_superstructures",
    )

    # 2. Add back model_id and modification_id to superstructures
    op.add_column(
        "special_equipment_superstructures",
        sa.Column(
            "model_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("special_equipment_models.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "special_equipment_superstructures",
        sa.Column(
            "modification_id",
            PGUUID(as_uuid=True),
            nullable=True,
        ),
    )

    # 3. Restore from backup
    op.execute(
        """
        UPDATE special_equipment_superstructures s
        SET model_id = b.model_id,
            modification_id = b.modification_id
        FROM special_equipment_superstructures_model_backup_152 b
        WHERE s.id = b.id;
        """
    )
    op.execute(
        """
        UPDATE special_equipment_superstructures s
        SET model_id = (
            SELECT p.superstructure_model_id
            FROM special_equipment_products p
            WHERE p.superstructure_id = s.id
            LIMIT 1
        )
        WHERE s.model_id IS NULL;
        """
    )

    conn = op.get_bind()
    null_codes = conn.execute(
        sa.text("SELECT code FROM special_equipment_superstructures WHERE model_id IS NULL")
    ).scalars().all()
    if null_codes:
        raise RuntimeError(
            f"Cannot downgrade migration 152: superstructures without model_id: {list(null_codes)}"
        )

    op.alter_column(
        "special_equipment_superstructures",
        "model_id",
        nullable=False,
    )
    op.create_foreign_key(
        "fk_se_superstructures_modification_model",
        "special_equipment_superstructures",
        "special_equipment_modifications",
        ["modification_id", "model_id"],
        ["id", "model_id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_se_superstructures_model_mod_name",
        "special_equipment_superstructures",
        [
            "model_id",
            sa.text(
                "coalesce(modification_id, '00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            sa.text("lower(btrim(name))"),
        ],
        unique=True,
    )
    op.create_index(
        "uq_se_superstructures_model_mod_slug",
        "special_equipment_superstructures",
        [
            "model_id",
            sa.text(
                "coalesce(modification_id, '00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            sa.text("lower(btrim(slug))"),
        ],
        unique=True,
    )
    op.create_index(
        "idx_se_superstructures_model_mod_active_name",
        "special_equipment_superstructures",
        ["model_id", "modification_id", "is_active", "name", "id"],
    )

    # 4. Products revert
    op.drop_constraint("ck_se_products_kind", "special_equipment_products", type_="check")
    op.create_check_constraint(
        "ck_se_products_kind",
        "special_equipment_products",
        """
        (superstructure_id IS NULL AND modification_id IS NOT NULL AND model_id IS NULL
           AND superstructure_modification_id IS NULL
           AND superstructure_name IS NULL AND superstructure_manufacturer IS NULL)
        OR
        (superstructure_id IS NOT NULL AND model_id IS NOT NULL AND trim_id IS NULL
           AND superstructure_name IS NOT NULL AND btrim(superstructure_name) <> ''
           AND superstructure_manufacturer IS NOT NULL AND btrim(superstructure_manufacturer) <> '')
        """,
    )
    op.drop_constraint(
        "fk_se_products_superstructure_modification_model",
        "special_equipment_products",
        type_="foreignkey",
    )
    op.drop_index(
        "idx_se_products_superstructure_model",
        table_name="special_equipment_products",
    )
    op.drop_column("special_equipment_products", "superstructure_model_id")

    op.execute("DROP TABLE IF EXISTS special_equipment_superstructures_model_backup_152;")
