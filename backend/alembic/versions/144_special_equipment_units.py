"""Special equipment units directory.

Revision ID: 144
Revises: 143
Create Date: 2026-09-29 15:20:00
"""

from __future__ import annotations

import logging
import re
import uuid
from collections import Counter
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

logger = logging.getLogger("alembic.runtime.migration")

revision = "144"
down_revision = "143"
branch_labels = None
depends_on = None

_ENTITY_NAMESPACE = uuid.UUID("d79863e8-5724-52dd-bfd3-b466af53de09")

_CYRILLIC_UPPER_TRANSLIT: dict[str, str] = {
    "а": "A",
    "б": "B",
    "в": "V",
    "г": "G",
    "д": "D",
    "е": "E",
    "ё": "E",
    "ж": "ZH",
    "з": "Z",
    "и": "I",
    "й": "Y",
    "к": "K",
    "л": "L",
    "м": "M",
    "н": "N",
    "о": "O",
    "п": "P",
    "р": "R",
    "с": "S",
    "т": "T",
    "у": "U",
    "ф": "F",
    "х": "KH",
    "ц": "TS",
    "ч": "CH",
    "ш": "SH",
    "щ": "SCH",
    "ъ": "",
    "ы": "Y",
    "ь": "",
    "э": "E",
    "ю": "YU",
    "я": "YA",
}

_CYRILLIC_LOWER_TRANSLIT: dict[str, str] = {
    k: v.lower() for k, v in _CYRILLIC_UPPER_TRANSLIT.items()
}


def _unit_to_code(name: str) -> str:
    res: list[str] = []
    for ch in name:
        if ch == "°":
            res.append("DEG")
        elif ch == "³":
            res.append("3")
        elif ch == "²":
            res.append("2")
        elif ch == "%":
            res.append("PCT")
        elif ch.lower() in _CYRILLIC_UPPER_TRANSLIT:
            res.append(_CYRILLIC_UPPER_TRANSLIT[ch.lower()])
        elif ch.isalnum():
            res.append(ch.upper())
        else:
            res.append("_")
    code = "".join(res)
    code = re.sub(r"_+", "_", code).strip("_")
    return code or "UNIT"


def _unit_to_slug(name: str) -> str:
    res: list[str] = []
    for ch in name.strip().casefold():
        if ch == "°":
            res.append("deg")
        elif ch == "³":
            res.append("3")
        elif ch == "²":
            res.append("2")
        elif ch == "%":
            res.append("pct")
        elif ch in _CYRILLIC_LOWER_TRANSLIT:
            res.append(_CYRILLIC_LOWER_TRANSLIT[ch])
        elif ch.isalnum():
            res.append(ch)
        else:
            res.append("-")
    slug = "".join(res)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "unit"


def upgrade() -> None:
    # 1. Create special_equipment_units table
    op.create_table(
        "special_equipment_units",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "lock_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_units_lock_version",
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 50",
            name="ck_special_equipment_units_name_len",
        ),
    )
    op.create_unique_constraint(
        "uq_special_equipment_units_code",
        "special_equipment_units",
        ["code"],
    )
    op.create_index(
        "uq_se_units_lower_code",
        "special_equipment_units",
        [sa.text("lower(btrim(code))")],
        unique=True,
    )
    op.create_index(
        "uq_se_units_lower_name",
        "special_equipment_units",
        [sa.text("lower(btrim(name))")],
        unique=True,
    )

    # 2. Add unit_id column to special_equipment_attributes
    op.add_column(
        "special_equipment_attributes",
        sa.Column(
            "unit_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("special_equipment_units.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_se_attributes_unit",
        "special_equipment_attributes",
        ["unit_id"],
    )

    # 3. Populate units from existing special_equipment_attributes.unit
    bind = op.get_bind()
    attr_rows = bind.execute(
        sa.text(
            "SELECT id, btrim(unit) as u FROM special_equipment_attributes "
            "WHERE unit IS NOT NULL AND btrim(unit) <> ''"
        )
    ).fetchall()

    if attr_rows:
        groups: dict[str, list[str]] = {}
        for row in attr_rows:
            raw = str(row.u)
            key = raw.lower()
            groups.setdefault(key, []).append(raw)

        used_codes: set[str] = set()
        code_to_unit_id: dict[str, uuid.UUID] = {}
        key_to_unit_id: dict[str, uuid.UUID] = {}
        created_info: list[tuple[str, str]] = []

        for key in sorted(groups.keys()):
            names = groups[key]
            counts = Counter(names)
            best_name = sorted(counts.keys(), key=lambda n: (-counts[n], n))[0]
            base_code = _unit_to_code(best_name)
            candidate_code = base_code
            suffix = 2
            while candidate_code in used_codes:
                candidate_code = f"{base_code}_{suffix}"
                suffix += 1
            used_codes.add(candidate_code)

            unit_id = uuid.uuid5(_ENTITY_NAMESPACE, f"unit:{candidate_code}")
            slug = _unit_to_slug(best_name)

            bind.execute(
                sa.text(
                    "INSERT INTO special_equipment_units (id, code, name, slug, is_active, lock_version) "
                    "VALUES (:id, :code, :name, :slug, true, 1)"
                ),
                {
                    "id": unit_id,
                    "code": candidate_code,
                    "name": best_name,
                    "slug": slug,
                },
            )
            key_to_unit_id[key] = unit_id
            created_info.append((best_name, candidate_code))

        for row in attr_rows:
            key = str(row.u).lower()
            u_id = key_to_unit_id[key]
            bind.execute(
                sa.text(
                    "UPDATE special_equipment_attributes SET unit_id = :uid WHERE id = :aid"
                ),
                {"uid": u_id, "aid": row.id},
            )

        logger.info(
            "Migration 142: Created %d units: %s",
            len(created_info),
            created_info,
        )

    # 4. Check that all non-empty units were populated
    total_non_empty = bind.execute(
        sa.text(
            "SELECT count(*) FROM special_equipment_attributes "
            "WHERE unit IS NOT NULL AND btrim(unit) <> ''"
        )
    ).scalar()
    total_with_unit_id = bind.execute(
        sa.text(
            "SELECT count(*) FROM special_equipment_attributes "
            "WHERE unit_id IS NOT NULL"
        )
    ).scalar()
    if total_non_empty != total_with_unit_id:
        raise RuntimeError(
            f"Migration 142 unit migration mismatch: {total_non_empty} non-empty units vs {total_with_unit_id} unit_id populated"
        )

    # 5. Drop unit column from special_equipment_attributes
    op.drop_column("special_equipment_attributes", "unit")

    # 6. Update mutation receipts resource_type constraint
    _RECEIPT_CHECK = "ck_se_catalog_mutation_receipts_resource_type"
    op.drop_constraint(_RECEIPT_CHECK, "special_equipment_catalog_mutation_receipts", type_="check")
    op.create_check_constraint(
        _RECEIPT_CHECK,
        "special_equipment_catalog_mutation_receipts",
        "resource_type IN ('category', 'mark', 'model', 'modification', 'trim', 'attribute_group', 'attribute', 'attribute_option', 'product', 'color', 'unit', 'superstructure')",
    )


def downgrade() -> None:
    _RECEIPT_CHECK = "ck_se_catalog_mutation_receipts_resource_type"
    op.drop_constraint(_RECEIPT_CHECK, "special_equipment_catalog_mutation_receipts", type_="check")
    op.create_check_constraint(
        _RECEIPT_CHECK,
        "special_equipment_catalog_mutation_receipts",
        "resource_type IN ('category', 'mark', 'model', 'modification', 'trim', 'attribute_group', 'attribute', 'attribute_option', 'product', 'color')",
    )

    # 1. Re-add unit column to special_equipment_attributes
    op.add_column(
        "special_equipment_attributes",
        sa.Column("unit", sa.String(50), nullable=True),
    )

    # 2. Populate unit from special_equipment_units.name
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE special_equipment_attributes sa "
            "SET unit = su.name "
            "FROM special_equipment_units su "
            "WHERE sa.unit_id = su.id"
        )
    )

    # 3. Drop unit_id column and index
    op.drop_index("idx_se_attributes_unit", table_name="special_equipment_attributes")
    op.drop_column("special_equipment_attributes", "unit_id")

    # 4. Drop special_equipment_units table
    op.drop_table("special_equipment_units")
