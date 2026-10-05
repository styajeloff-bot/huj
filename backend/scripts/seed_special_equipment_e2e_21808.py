"""Idempotent, explicit E2E catalog fixture for Bitrix task 21808.

This module is a developer tool, not an application startup seed. Every owned
entity has a stable UUID and an ``E2E_21808`` code/name prefix. Re-running the
fixture updates those exact rows and relationships without touching unrelated
catalog data.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from infrastructure.database import AsyncSessionLocal  # noqa: E402
from infrastructure.models.companies import Company  # noqa: E402
from infrastructure.models.special_equipment import (  # noqa: E402
    SpecialEquipmentAttribute,
    SpecialEquipmentAttributeGroup,
    SpecialEquipmentAttributeOption,
    SpecialEquipmentCategory,
    SpecialEquipmentCategoryAttribute,
    SpecialEquipmentCategoryRelation,
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentModificationAttributeValue,
    SpecialEquipmentModificationCategory,
    SpecialEquipmentProduct,
    SpecialEquipmentProductCategory,
)

E2E_PREFIX = "E2E_21808"
_UUID_NAMESPACE = uuid5(NAMESPACE_URL, "carcraft:bitrix:21808:e2e-fixture")
_PUBLISHED_AT = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
_LOGGER = logging.getLogger("carcraft-backend")


@dataclass(frozen=True)
class E2E21808FixtureSummary:
    """Stable identifiers and row counts exposed to E2E callers."""

    category_ids: dict[str, UUID]
    mark_ids: dict[str, UUID]
    model_ids: dict[str, UUID]
    modification_ids: dict[str, UUID]
    attribute_group_ids: dict[str, UUID]
    attribute_ids: dict[str, UUID]
    option_ids: dict[str, UUID]
    product_ids: dict[str, UUID]
    counts: dict[str, int]


def _id(key: str) -> UUID:
    return uuid5(_UUID_NAMESPACE, key)


async def _merge[OrmRow](session: AsyncSession, row: OrmRow) -> OrmRow:
    """Upsert one fixture-owned row by its deterministic primary key."""

    return await session.merge(row)


async def seed_special_equipment_e2e_21808(
    session: AsyncSession,
) -> E2E21808FixtureSummary:
    """Upsert the connected E2E_21808 catalog into the caller's transaction."""

    seller = await _merge(
        session,
        Company(
            id=_id("company:test-dealer"),
            name=f"{E2E_PREFIX} ООО «Тестовый дилер спецтехники»",
            inn="2180800000",
            company_type="dealer",
            legal_address="г. Москва, тестовый проезд, д. 21808",
            is_active=True,
        ),
    )

    categories = {
        "lifting": await _merge(
            session,
            SpecialEquipmentCategory(
                id=_id("category:lifting"),
                code=f"{E2E_PREFIX}_CATEGORY_LIFTING",
                name=f"{E2E_PREFIX} Подъёмная техника",
                slug="e2e-21808-lifting",
                usage_metric="engine_hours",
                sort_order=21801,
                is_active=True,
            ),
        ),
        "construction": await _merge(
            session,
            SpecialEquipmentCategory(
                id=_id("category:construction"),
                code=f"{E2E_PREFIX}_CATEGORY_CONSTRUCTION",
                name=f"{E2E_PREFIX} Строительная техника",
                slug="e2e-21808-construction",
                usage_metric="engine_hours",
                sort_order=21802,
                is_active=True,
            ),
        ),
        "shared_cranes": await _merge(
            session,
            SpecialEquipmentCategory(
                id=_id("category:shared-cranes"),
                code=f"{E2E_PREFIX}_CATEGORY_CRANES",
                name=f"{E2E_PREFIX} Автокраны",
                slug="e2e-21808-cranes",
                usage_metric="engine_hours",
                sort_order=21803,
                is_active=True,
            ),
        ),
        "trucks": await _merge(
            session,
            SpecialEquipmentCategory(
                id=_id("category:trucks"),
                code=f"{E2E_PREFIX}_CATEGORY_TRUCKS",
                name=f"{E2E_PREFIX} Грузовая техника",
                slug="e2e-21808-trucks",
                usage_metric="mileage_km",
                sort_order=21804,
                is_active=True,
            ),
        ),
    }
    category_relations = (
        await _merge(
            session,
            SpecialEquipmentCategoryRelation(
                parent_id=categories["lifting"].id,
                child_id=categories["shared_cranes"].id,
                sort_order=1,
            ),
        ),
        await _merge(
            session,
            SpecialEquipmentCategoryRelation(
                parent_id=categories["construction"].id,
                child_id=categories["shared_cranes"].id,
                sort_order=2,
            ),
        ),
    )

    marks = {
        "faw": await _merge(
            session,
            SpecialEquipmentMark(
                id=_id("mark:faw"),
                code=f"{E2E_PREFIX}_MARK_FAW",
                name=f"{E2E_PREFIX} FAW",
                slug="e2e-21808-faw",
                is_active=True,
            ),
        ),
        "ivanovets": await _merge(
            session,
            SpecialEquipmentMark(
                id=_id("mark:ivanovets"),
                code=f"{E2E_PREFIX}_MARK_IVANOVETS",
                name=f"{E2E_PREFIX} Ивановец",
                slug="e2e-21808-ivanovets",
                is_active=True,
            ),
        ),
    }
    models = {
        "j6p": await _merge(
            session,
            SpecialEquipmentModel(
                id=_id("model:faw-j6p"),
                mark_id=marks["faw"].id,
                code=f"{E2E_PREFIX}_MODEL_J6P",
                name=f"{E2E_PREFIX} J6P",
                slug="e2e-21808-j6p",
                is_active=True,
            ),
        ),
        "ks": await _merge(
            session,
            SpecialEquipmentModel(
                id=_id("model:ivanovets-ks"),
                mark_id=marks["ivanovets"].id,
                code=f"{E2E_PREFIX}_MODEL_KS",
                name=f"{E2E_PREFIX} КС",
                slug="e2e-21808-ks",
                is_active=True,
            ),
        ),
    }
    modifications = {
        "j6p_6x4": await _merge(
            session,
            SpecialEquipmentModification(
                id=_id("modification:faw-j6p-6x4"),
                model_id=models["j6p"].id,
                code=f"{E2E_PREFIX}_MODIFICATION_J6P_6X4",
                name=f"{E2E_PREFIX} J6P 6×4",
                slug="e2e-21808-j6p-6x4",
                year_from=2020,
                year_to=2026,
                is_active=True,
            ),
        ),
        "ks_45717": await _merge(
            session,
            SpecialEquipmentModification(
                id=_id("modification:ivanovets-ks-45717"),
                model_id=models["ks"].id,
                code=f"{E2E_PREFIX}_MODIFICATION_KS_45717",
                name=f"{E2E_PREFIX} КС-45717",
                slug="e2e-21808-ks-45717",
                year_from=2019,
                year_to=2026,
                is_active=True,
            ),
        ),
    }
    modification_categories = (
        await _merge(
            session,
            SpecialEquipmentModificationCategory(
                modification_id=modifications["j6p_6x4"].id,
                category_id=categories["trucks"].id,
            ),
        ),
        await _merge(
            session,
            SpecialEquipmentModificationCategory(
                modification_id=modifications["ks_45717"].id,
                category_id=categories["shared_cranes"].id,
            ),
        ),
    )

    attribute_groups = {
        "engine": await _merge(
            session,
            SpecialEquipmentAttributeGroup(
                id=_id("attribute-group:engine"),
                code=f"{E2E_PREFIX}_GROUP_ENGINE",
                name=f"{E2E_PREFIX} Двигатель",
                slug="e2e-21808-engine",
                sort_order=1,
                is_active=True,
            ),
        ),
        "chassis": await _merge(
            session,
            SpecialEquipmentAttributeGroup(
                id=_id("attribute-group:chassis"),
                code=f"{E2E_PREFIX}_GROUP_CHASSIS",
                name=f"{E2E_PREFIX} Шасси и рабочее оборудование",
                slug="e2e-21808-chassis",
                sort_order=2,
                is_active=True,
            ),
        ),
    }
    attributes = {
        "engine_power": await _merge(
            session,
            SpecialEquipmentAttribute(
                id=_id("attribute:engine-power"),
                code=f"{E2E_PREFIX}_ATTRIBUTE_ENGINE_POWER",
                name=f"{E2E_PREFIX} Мощность двигателя",
                data_type="number",
                unit="л.с.",
                filter_kind="range",
                is_active=True,
            ),
        ),
        "drive": await _merge(
            session,
            SpecialEquipmentAttribute(
                id=_id("attribute:drive"),
                code=f"{E2E_PREFIX}_ATTRIBUTE_DRIVE",
                name=f"{E2E_PREFIX} Колёсная формула",
                data_type="select",
                filter_kind="exact",
                is_active=True,
            ),
        ),
        "boom_length": await _merge(
            session,
            SpecialEquipmentAttribute(
                id=_id("attribute:boom-length"),
                code=f"{E2E_PREFIX}_ATTRIBUTE_BOOM_LENGTH",
                name=f"{E2E_PREFIX} Длина стрелы",
                data_type="number",
                unit="м",
                filter_kind="range",
                is_active=True,
            ),
        ),
    }
    options = {
        "drive_6x4": await _merge(
            session,
            SpecialEquipmentAttributeOption(
                id=_id("attribute-option:drive-6x4"),
                attribute_id=attributes["drive"].id,
                code=f"{E2E_PREFIX}_OPTION_DRIVE_6X4",
                name=f"{E2E_PREFIX} 6×4",
                sort_order=1,
                is_active=True,
            ),
        ),
        "drive_6x6": await _merge(
            session,
            SpecialEquipmentAttributeOption(
                id=_id("attribute-option:drive-6x6"),
                attribute_id=attributes["drive"].id,
                code=f"{E2E_PREFIX}_OPTION_DRIVE_6X6",
                name=f"{E2E_PREFIX} 6×6",
                sort_order=2,
                is_active=True,
            ),
        ),
    }

    category_attributes = (
        await _merge(
            session,
            SpecialEquipmentCategoryAttribute(
                category_id=categories["shared_cranes"].id,
                attribute_id=attributes["engine_power"].id,
                group_id=attribute_groups["engine"].id,
                is_required=True,
                is_filterable=True,
                is_visible=True,
                sort_order=1,
            ),
        ),
        await _merge(
            session,
            SpecialEquipmentCategoryAttribute(
                category_id=categories["shared_cranes"].id,
                attribute_id=attributes["drive"].id,
                group_id=attribute_groups["chassis"].id,
                is_required=True,
                is_filterable=True,
                is_visible=True,
                sort_order=2,
            ),
        ),
        await _merge(
            session,
            SpecialEquipmentCategoryAttribute(
                category_id=categories["shared_cranes"].id,
                attribute_id=attributes["boom_length"].id,
                group_id=attribute_groups["chassis"].id,
                is_required=True,
                is_filterable=True,
                is_visible=True,
                sort_order=3,
            ),
        ),
        await _merge(
            session,
            SpecialEquipmentCategoryAttribute(
                category_id=categories["trucks"].id,
                attribute_id=attributes["engine_power"].id,
                group_id=attribute_groups["engine"].id,
                is_required=True,
                is_filterable=True,
                is_visible=True,
                sort_order=1,
            ),
        ),
        await _merge(
            session,
            SpecialEquipmentCategoryAttribute(
                category_id=categories["trucks"].id,
                attribute_id=attributes["drive"].id,
                group_id=attribute_groups["chassis"].id,
                is_required=True,
                is_filterable=True,
                is_visible=True,
                sort_order=2,
            ),
        ),
    )
    modification_values = (
        await _merge(
            session,
            SpecialEquipmentModificationAttributeValue(
                modification_id=modifications["j6p_6x4"].id,
                attribute_id=attributes["engine_power"].id,
                value_number=Decimal("420.0000"),
            ),
        ),
        await _merge(
            session,
            SpecialEquipmentModificationAttributeValue(
                modification_id=modifications["j6p_6x4"].id,
                attribute_id=attributes["drive"].id,
                option_id=options["drive_6x4"].id,
            ),
        ),
        await _merge(
            session,
            SpecialEquipmentModificationAttributeValue(
                modification_id=modifications["ks_45717"].id,
                attribute_id=attributes["engine_power"].id,
                value_number=Decimal("240.0000"),
            ),
        ),
        await _merge(
            session,
            SpecialEquipmentModificationAttributeValue(
                modification_id=modifications["ks_45717"].id,
                attribute_id=attributes["drive"].id,
                option_id=options["drive_6x6"].id,
            ),
        ),
        await _merge(
            session,
            SpecialEquipmentModificationAttributeValue(
                modification_id=modifications["ks_45717"].id,
                attribute_id=attributes["boom_length"].id,
                value_number=Decimal("31.0000"),
            ),
        ),
    )

    products = {
        "new_crane": await _merge(
            session,
            SpecialEquipmentProduct(
                id=_id("product:new-crane"),
                code=f"{E2E_PREFIX}_PRODUCT_01_NEW_CRANE",
                modification_id=modifications["ks_45717"].id,
                seller_company_id=seller.id,
                slug="e2e-21808-new-crane",
                description=(
                    f"{E2E_PREFIX} новый автокран для проверки публичного каталога"
                ),
                price=Decimal("18400000.00"),
                manufacture_year=2026,
                vin="E2E21808NEWCRANE0",
                no_vin=False,
                condition="new",
                owners_count=None,
                mileage_km=None,
                engine_hours=None,
                publication_status="published",
                sale_status="available",
                published_at=_PUBLISHED_AT,
            ),
        ),
        "used_crane": await _merge(
            session,
            SpecialEquipmentProduct(
                id=_id("product:used-crane"),
                code=f"{E2E_PREFIX}_PRODUCT_02_USED_CRANE",
                modification_id=modifications["ks_45717"].id,
                seller_company_id=seller.id,
                slug="e2e-21808-used-crane",
                description=f"{E2E_PREFIX} автокран с моточасами",
                price=Decimal("12900000.00"),
                manufacture_year=2022,
                vin="E2E21808USEDCRANE",
                no_vin=False,
                condition="used",
                owners_count=1,
                mileage_km=None,
                engine_hours=1840,
                publication_status="published",
                sale_status="available",
                published_at=_PUBLISHED_AT,
            ),
        ),
        "used_truck": await _merge(
            session,
            SpecialEquipmentProduct(
                id=_id("product:used-truck"),
                code=f"{E2E_PREFIX}_PRODUCT_03_USED_TRUCK",
                modification_id=modifications["j6p_6x4"].id,
                seller_company_id=seller.id,
                slug="e2e-21808-used-truck",
                description=f"{E2E_PREFIX} грузовик с пробегом",
                price=Decimal("7800000.00"),
                manufacture_year=2021,
                vin="E2E21808USEDTRUCK",
                no_vin=False,
                condition="used",
                owners_count=2,
                mileage_km=126000,
                engine_hours=None,
                publication_status="published",
                sale_status="available",
                published_at=_PUBLISHED_AT,
            ),
        ),
    }
    product_categories = (
        await _merge(
            session,
            SpecialEquipmentProductCategory(
                product_id=products["new_crane"].id,
                category_id=categories["shared_cranes"].id,
            ),
        ),
        await _merge(
            session,
            SpecialEquipmentProductCategory(
                product_id=products["used_crane"].id,
                category_id=categories["shared_cranes"].id,
            ),
        ),
        await _merge(
            session,
            SpecialEquipmentProductCategory(
                product_id=products["used_truck"].id,
                category_id=categories["trucks"].id,
            ),
        ),
    )

    await session.flush()

    return E2E21808FixtureSummary(
        category_ids={key: row.id for key, row in categories.items()},
        mark_ids={key: row.id for key, row in marks.items()},
        model_ids={key: row.id for key, row in models.items()},
        modification_ids={key: row.id for key, row in modifications.items()},
        attribute_group_ids={key: row.id for key, row in attribute_groups.items()},
        attribute_ids={key: row.id for key, row in attributes.items()},
        option_ids={key: row.id for key, row in options.items()},
        product_ids={key: row.id for key, row in products.items()},
        counts={
            "companies": 1,
            "categories": len(categories),
            "category_relations": len(category_relations),
            "marks": len(marks),
            "models": len(models),
            "modifications": len(modifications),
            "modification_categories": len(modification_categories),
            "attribute_groups": len(attribute_groups),
            "attributes": len(attributes),
            "attribute_options": len(options),
            "category_attributes": len(category_attributes),
            "modification_attribute_values": len(modification_values),
            "products": len(products),
            "product_categories": len(product_categories),
        },
    )


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Upsert only the deterministic E2E_21808 special-equipment fixture "
            "into the configured database."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        required=True,
        help="Required confirmation that the configured database may be updated.",
    )
    return parser.parse_args(argv)


async def _apply_fixture() -> E2E21808FixtureSummary:
    async with AsyncSessionLocal() as session:
        summary = await seed_special_equipment_e2e_21808(session)
        await session.commit()
        return summary


def main(argv: Sequence[str] | None = None) -> int:
    _arguments(argv)
    logging.basicConfig(level=logging.INFO)
    summary = asyncio.run(_apply_fixture())
    _LOGGER.info(
        "E2E_21808 special-equipment fixture applied: %s",
        summary.counts,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
