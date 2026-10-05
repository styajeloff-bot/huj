"""Canonical public locations for special-equipment projections."""

from __future__ import annotations

from uuid import UUID

from domain.special_equipment_commerce import (
    has_special_equipment_public_detail,
)


def special_equipment_detail_url(
    product_id: UUID | None,
    slug: object,
) -> str | None:
    """Return a detail location only when both canonical path parts exist."""

    normalized_slug = slug.strip() if isinstance(slug, str) else ""
    if product_id is None or not normalized_slug:
        return None
    return f"/special-equipment/products/{product_id}/{normalized_slug}"


def public_special_equipment_detail_url(
    product_id: UUID | None,
    slug: object,
    *,
    publication_status: object,
    sale_status: object,
) -> str | None:
    """Return the canonical location only for a currently public product."""

    if not has_special_equipment_public_detail(
        publication_status,
        sale_status,
    ):
        return None
    return special_equipment_detail_url(product_id, slug)
