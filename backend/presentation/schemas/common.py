"""Shared Pydantic schemas used across routers."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field


def _reject_blank_address(value: str) -> str:
    if not value.strip():
        raise ValueError("Адрес не может быть пустым")
    return value


NonBlankAddress = Annotated[str, AfterValidator(_reject_blank_address)]


class Pagination(BaseModel):
    """Response-side pagination metadata."""

    page: int = Field(..., ge=1, description="Current page, 1-based")
    limit: int = Field(..., ge=1, le=100, description="Page size")
    total: int = Field(..., ge=0, description="Total items across all pages")
    pages: int = Field(..., ge=0, description="Total number of pages")


class PaginatedResponse[T](BaseModel):
    """Generic wrapper: ``{items: [...], pagination: {...}}``."""

    items: list[T]
    pagination: Pagination
