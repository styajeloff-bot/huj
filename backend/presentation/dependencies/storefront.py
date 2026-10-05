"""Shared request dependency for resolving the public catalog scope."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.storefronts import (
    ResolveStorefrontQuery,
    handle_resolve_storefront,
)
from domain.storefronts import CatalogScope
from infrastructure.database import get_db


async def resolve_catalog_scope(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CatalogScope:
    raw_slug = request.path_params.get("storefront_slug")
    slug = str(raw_slug) if raw_slug is not None else None
    return await handle_resolve_storefront(ResolveStorefrontQuery(slug), session)
