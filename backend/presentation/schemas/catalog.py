"""Pydantic schemas for the catalog upload endpoints."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CatalogPreviewSampleRow(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    vin: str
    mark: str
    model: str
    generation: str
    price: Any
    has_vin: bool = Field(alias="hasVin", serialization_alias="hasVin")


class CatalogGdriveStats(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    total: int
    unique: int


class CatalogPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    total_rows: int = Field(alias="totalRows", serialization_alias="totalRows")
    unique_marks: int = Field(alias="uniqueMarks", serialization_alias="uniqueMarks")
    unique_models: int = Field(alias="uniqueModels", serialization_alias="uniqueModels")
    unique_generations: int = Field(alias="uniqueGenerations", serialization_alias="uniqueGenerations")
    vehicles_count: int = Field(alias="vehiclesCount", serialization_alias="vehiclesCount")
    rows_without_vin: int = Field(alias="rowsWithoutVin", serialization_alias="rowsWithoutVin")
    has_errors: bool = Field(alias="hasErrors", serialization_alias="hasErrors")
    errors: list[str]
    warnings: list[str]
    sample_data: list[CatalogPreviewSampleRow] = Field(alias="sampleData", serialization_alias="sampleData")
    gdrive_images: CatalogGdriveStats = Field(alias="gdriveImages", serialization_alias="gdriveImages")


class CatalogUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    job_id: str = Field(alias="jobId", serialization_alias="jobId")
    status: Literal["queued"]


class CatalogJobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    job_id: str = Field(alias="jobId", serialization_alias="jobId")
    status: str
    rows_total: int = Field(..., ge=0, alias="rowsTotal", serialization_alias="rowsTotal")
    rows_done: int = Field(..., ge=0, alias="rowsDone", serialization_alias="rowsDone")
    images_total: int = Field(..., ge=0, alias="imagesTotal", serialization_alias="imagesTotal")
    images_done: int = Field(..., ge=0, alias="imagesDone", serialization_alias="imagesDone")
    images_failed: int = Field(..., ge=0, alias="imagesFailed", serialization_alias="imagesFailed")
    error: str | None = None
    filename: str | None = None
    created_at: str = Field(alias="createdAt", serialization_alias="createdAt")
    updated_at: str = Field(alias="updatedAt", serialization_alias="updatedAt")
