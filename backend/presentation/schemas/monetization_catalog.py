"""Internal catalog lookup DTOs retain the registered external string IDs."""

from uuid import UUID

from pydantic import BaseModel


class CatalogMark(BaseModel):
    id: str
    ids: list[str]
    name: str


class CatalogModel(BaseModel):
    id: str
    name: str


class CatalogModification(BaseModel):
    id: UUID
    name: str


class CatalogTrim(BaseModel):
    id: UUID
    name: str | None
    trim_name: str


class CatalogMarksOut(BaseModel):
    marks: list[CatalogMark]


class CatalogModelsOut(BaseModel):
    models: list[CatalogModel]


class CatalogModificationsOut(BaseModel):
    modifications: list[CatalogModification]


class CatalogTrimsOut(BaseModel):
    trims: list[CatalogTrim]
