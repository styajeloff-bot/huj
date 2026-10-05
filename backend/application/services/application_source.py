"""Resolve application provenance before inserting its immutable source."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.application_sources import source_for_creation
from infrastructure.repositories import warehouse_repository


async def resolve_application_source(
    session: AsyncSession, *, requested: str, first_product_id: UUID | None
) -> str:
    owner_type = None
    if requested != "platform" and first_product_id is not None:
        owner_type = await warehouse_repository.get_product_warehouse_owner_type(
            session, first_product_id
        )
    return source_for_creation(requested, owner_type)
