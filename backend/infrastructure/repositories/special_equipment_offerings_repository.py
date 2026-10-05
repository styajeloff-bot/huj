"""Batch reads for public attachment, component, and grouping offerings."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.special_equipment import (
    SpecialEquipmentAttribute,
    SpecialEquipmentAttributeOption,
    SpecialEquipmentCategory,
    SpecialEquipmentCategoryAttribute,
    SpecialEquipmentCategoryRelation,
    SpecialEquipmentModificationAttributeValue,
    SpecialEquipmentProduct,
    SpecialEquipmentProductAttachment,
)


async def load_fingerprint_inputs(
    session: AsyncSession,
    rows: Sequence[dict],
) -> dict[str, list[dict]]:
    """Return every grouping input with a fixed number of batch queries."""

    product_ids = tuple({row["id"] for row in rows})
    modification_ids = tuple({row["modification_id"] for row in rows})
    if not product_ids:
        return {
            "categories": [],
            "relations": [],
            "rules": [],
            "attributes": [],
            "attachments": [],
            "components": [],
        }

    categories = (
        await session.execute(
            sa.select(
                SpecialEquipmentCategory.id,
                SpecialEquipmentCategory.is_attachment_category,
            ).where(
                SpecialEquipmentCategory.is_active.is_(True)
            )
        )
    ).mappings()
    relations = (
        await session.execute(
            sa.select(
                SpecialEquipmentCategoryRelation.parent_id,
                SpecialEquipmentCategoryRelation.child_id,
            )
        )
    ).mappings()
    rules = (
        await session.execute(
            sa.select(
                SpecialEquipmentCategoryAttribute.category_id,
                SpecialEquipmentCategoryAttribute.attribute_id,
                SpecialEquipmentCategoryAttribute.group_id,
                SpecialEquipmentCategoryAttribute.is_required,
                SpecialEquipmentCategoryAttribute.is_filterable,
                SpecialEquipmentCategoryAttribute.is_visible,
                SpecialEquipmentCategoryAttribute.sort_order,
            ).join(
                SpecialEquipmentAttribute,
                SpecialEquipmentAttribute.id
                == SpecialEquipmentCategoryAttribute.attribute_id,
            ).where(SpecialEquipmentAttribute.is_active.is_(True))
        )
    ).mappings()
    attributes = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationAttributeValue.modification_id,
                SpecialEquipmentModificationAttributeValue.attribute_id,
                SpecialEquipmentModificationAttributeValue.value_number,
                SpecialEquipmentModificationAttributeValue.value_text,
                SpecialEquipmentModificationAttributeValue.value_boolean,
                SpecialEquipmentAttributeOption.code.label("option_code"),
            )
            .join(
                SpecialEquipmentAttribute,
                SpecialEquipmentAttribute.id
                == SpecialEquipmentModificationAttributeValue.attribute_id,
            )
            .outerjoin(
                SpecialEquipmentAttributeOption,
                SpecialEquipmentAttributeOption.id
                == SpecialEquipmentModificationAttributeValue.option_id,
            )
            .where(
                SpecialEquipmentModificationAttributeValue.modification_id.in_(
                    modification_ids
                ),
                SpecialEquipmentAttribute.is_active.is_(True),
            )
        )
    ).mappings()
    attachments = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductAttachment.product_id,
                SpecialEquipmentProductAttachment.attachment_product_id,
                SpecialEquipmentProductAttachment.position,
            ).where(SpecialEquipmentProductAttachment.product_id.in_(product_ids))
        )
    ).mappings()
    return {
        "categories": [dict(row) for row in categories],
        "relations": [dict(row) for row in relations],
        "rules": [dict(row) for row in rules],
        "attributes": [dict(row) for row in attributes],
        "attachments": [dict(row) for row in attachments],
        "components": [],
    }


async def list_attachment_links(
    session: AsyncSession,
    product_id: UUID,
) -> list[dict]:
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductAttachment.attachment_product_id,
                SpecialEquipmentProductAttachment.position,
            )
            .join(
                SpecialEquipmentProduct,
                SpecialEquipmentProduct.id
                == SpecialEquipmentProductAttachment.attachment_product_id,
            )
            .where(
                SpecialEquipmentProductAttachment.product_id == product_id,
                SpecialEquipmentProduct.publication_status == "published",
                SpecialEquipmentProduct.sale_status.in_(("available", "on_order")),
            )
            .order_by(
                SpecialEquipmentProductAttachment.position,
                SpecialEquipmentProductAttachment.attachment_product_id,
            )
        )
    ).mappings()
    return [dict(row) for row in rows]
