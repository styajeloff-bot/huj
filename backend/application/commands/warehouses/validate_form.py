"""Validation of warehouse directory selections before any write."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories import warehouse_repository as repo


class WarehouseFormValidationError(ServiceError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message, status_code=422)
        self.field = field


async def validate_warehouse_form_selection(
    session: AsyncSession,
    brand_ids: list[UUID],
    category_id: UUID | None,
) -> None:
    if len(brand_ids) != len(set(brand_ids)):
        raise WarehouseFormValidationError(
            "brand_ids", "Марки ТС не должны повторяться"
        )
    if await repo.active_mark_ids(session, brand_ids) != set(brand_ids):
        raise WarehouseFormValidationError(
            "brand_ids", "Одна или несколько марок ТС не найдены или недоступны"
        )
    if category_id is not None and not await repo.category_available_for_marks(
        session, category_id, brand_ids
    ):
        raise WarehouseFormValidationError(
            "category_id",
            "Категория ТС не найдена, недоступна или не принадлежит выбранным маркам",
        )
