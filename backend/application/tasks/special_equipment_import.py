"""Taskiq pipeline for special-equipment XLSX preview and atomic apply."""

# ruff: noqa: TRY301

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import tempfile
import uuid
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import TaskiqEvents
from taskiq.state import TaskiqState

from application.special_equipment_import import (
    build_normalized_plan,
    compute_preview_hash,
    issues_to_rows,
    rebuild_summary_for_plan,
)
from domain.special_equipment_import import (
    DATA_SHEET_HEADERS,
    MAX_UI_ISSUES,
    ImportAggregateSemanticConflictError,
    ImportContractError,
    ImportErrorPolicy,
    ImportIssue,
    ImportMode,
    ImportStatus,
    IssueSeverity,
    apply_trim_value_import_policy,
    trim_value_plan_scope,
)
from domain.special_equipment_management import (
    TrimModificationValueConflict,
    trim_modification_value_conflicts,
)
from infrastructure.database import AsyncSessionLocal
from infrastructure.repositories import special_equipment_import_repository as repo
from infrastructure.services.special_equipment_import_images import (
    ImageTransferError,
    TransferredImage,
    transfer_temporary_image,
)
from infrastructure.services.special_equipment_import_storage import (
    ImportObjectStorage,
    get_special_equipment_import_storage,
)
from infrastructure.services.special_equipment_xlsx import (
    JsonlRows,
    parse_xlsx,
    read_rows_archive,
    write_rows_archive,
)
from infrastructure.settings import settings
from infrastructure.taskiq_broker import broker

logger = logging.getLogger("carcraft-backend")
_LEASE_DURATION = timedelta(minutes=10)
_ARTIFACT_CLEANUP_LEASE_DURATION = timedelta(minutes=30)
_ARTIFACT_CLEANUP_PAGE_SIZE = 50
_ARTIFACT_CLEANUP_MAX_PAGES = 4
_VALIDATION_RUNTIME_ERROR_DETAIL = (
    "Import validation failed because of an internal error; retry is scheduled."
)
_APPLY_RUNTIME_ERROR_DETAIL = "Import apply failed because of an internal error."
_ARTIFACT_KEY_FIELDS = (
    "source_object_key",
    "normalized_artifact_key",
    "diff_artifact_key",
    "validation_report_key",
)
_NORMALIZED_ARTIFACT_SCHEMA_VERSION = 5
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_LOCK_VERSION = 9_223_372_036_854_775_807
_PREVIEW_STALE_DETAIL = (
    "Каталог или состояние затрагиваемых товаров изменились после предпросмотра"
)
_ARTIFACT_SCHEMA_STALE_DETAIL = (
    "Предпросмотр создан предыдущей версией формата; выполните предпросмотр заново"
)


class _NormalizedArtifactPreviewStaleError(ImportContractError):
    """A valid older preview that must be regenerated, not marked corrupt."""


async def _begin_validation_snapshot(session: AsyncSession) -> None:
    """Start one PostgreSQL snapshot for revision and all validation reads."""
    await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})


def _artifact_contract_error() -> ImportContractError:
    return ImportContractError("NORMALIZED_ARTIFACT_MISMATCH")


async def _plan_trim_value_conflicts(
    session: AsyncSession,
    *,
    plan: Mapping[str, Iterable[dict[str, Any]]],
    expected_modification_value_markers: set[tuple[uuid.UUID, uuid.UUID]],
    expected_trim_value_markers: set[tuple[uuid.UUID, uuid.UUID, uuid.UUID]],
) -> tuple[TrimModificationValueConflict, ...]:
    """Recheck a normalized plan against locked persisted value markers."""

    modification_markers, trim_markers, modification_by_trim_hint = (
        trim_value_plan_scope(plan)
    )
    trim_ids = {trim_id for trim_id, _attribute_id in trim_markers}
    state = await repo.lock_and_read_trim_modification_value_state(
        session,
        modification_ids={marker[0] for marker in modification_markers},
        trim_ids=trim_ids,
        modification_by_trim_hint=modification_by_trim_hint,
    )
    return trim_modification_value_conflicts(
        incoming_modification_values=modification_markers,
        incoming_trim_values={
            (state["modification_by_trim"][trim_id], attribute_id)
            for trim_id, attribute_id in trim_markers
            if trim_id in state["modification_by_trim"]
        },
        persisted_modification_values=(
            state["modification_values"] - expected_modification_value_markers
        ),
        persisted_trim_values={
            (modification_id, attribute_id)
            for trim_id, modification_id, attribute_id in (
                state["trim_values"] - expected_trim_value_markers
            )
        },
    )


async def _trim_conflict_overrides_revision_stale(
    session: AsyncSession,
    *,
    revision: int,
    locked_job: Mapping[str, Any],
    plan: Mapping[str, Iterable[dict[str, Any]]],
    expected_modification_value_markers: set[tuple[uuid.UUID, uuid.UUID]],
    expected_trim_value_markers: set[tuple[uuid.UUID, uuid.UUID, uuid.UUID]],
    product_versions_match: bool,
    active_sellers_match: bool,
    archive_targets_are_available: bool,
) -> bool:
    """Classify the single trim race without weakening other stale guards."""

    if (
        revision != int(locked_job["catalog_revision"]) + 1
        or not product_versions_match
        or not active_sellers_match
        or not archive_targets_are_available
    ):
        return False
    conflicts = await _plan_trim_value_conflicts(
        session,
        plan=plan,
        expected_modification_value_markers=expected_modification_value_markers,
        expected_trim_value_markers=expected_trim_value_markers,
    )
    if not conflicts:
        return False
    apply_trim_value_import_policy(
        conflicts,
        error_policy=ImportErrorPolicy(str(locked_job["error_policy"])),
    )
    return True


async def _finish_if_preview_stale(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    revision: int,
    locked_job: Mapping[str, Any],
    plan: Mapping[str, Iterable[dict[str, Any]]],
    expected_modification_value_markers: set[tuple[uuid.UUID, uuid.UUID]],
    expected_trim_value_markers: set[tuple[uuid.UUID, uuid.UUID, uuid.UUID]],
    product_versions_match: bool,
    active_sellers_match: bool,
    archive_targets_are_available: bool,
) -> bool:
    trim_override = await _trim_conflict_overrides_revision_stale(
        session,
        revision=revision,
        locked_job=locked_job,
        plan=plan,
        expected_modification_value_markers=expected_modification_value_markers,
        expected_trim_value_markers=expected_trim_value_markers,
        product_versions_match=product_versions_match,
        active_sellers_match=active_sellers_match,
        archive_targets_are_available=archive_targets_are_available,
    )
    stale = (
        (revision != int(locked_job["catalog_revision"]) and not trim_override)
        or not product_versions_match
        or not active_sellers_match
        or not archive_targets_are_available
    )
    if not stale:
        return False
    await repo.update_job(
        session,
        job_id,
        status=ImportStatus.PREVIEW_STALE.value,
        phase="preview_stale",
        error_code="PREVIEW_STALE",
        error_detail=_PREVIEW_STALE_DETAIL,
    )
    await session.commit()
    return True


def _parse_expected_product_versions(value: Any) -> dict[uuid.UUID, int]:
    """Parse the artifact concurrency map without permissive coercions."""
    if not isinstance(value, dict):
        raise _artifact_contract_error()

    parsed: dict[uuid.UUID, int] = {}
    for raw_product_id, raw_version in value.items():
        if type(raw_product_id) is not str or type(raw_version) is not int:
            raise _artifact_contract_error()
        try:
            product_id = uuid.UUID(raw_product_id)
        except ValueError as exc:
            raise _artifact_contract_error() from exc
        if (
            str(product_id) != raw_product_id
            or product_id in parsed
            or not 1 <= raw_version <= _MAX_LOCK_VERSION
        ):
            raise _artifact_contract_error()
        parsed[product_id] = raw_version
    return parsed


def _parse_expected_active_seller_ids(value: Any) -> set[uuid.UUID]:
    """Parse one canonical, duplicate-free UUID list from artifact metadata."""
    if not isinstance(value, list):
        raise _artifact_contract_error()
    parsed: list[uuid.UUID] = []
    for raw_company_id in value:
        if type(raw_company_id) is not str:
            raise _artifact_contract_error()
        try:
            company_id = uuid.UUID(raw_company_id)
        except ValueError as exc:
            raise _artifact_contract_error() from exc
        if str(company_id) != raw_company_id:
            raise _artifact_contract_error()
        parsed.append(company_id)
    if parsed != sorted(set(parsed), key=str):
        raise _artifact_contract_error()
    return set(parsed)


def _parse_expected_modification_value_markers(
    value: Any,
) -> set[tuple[uuid.UUID, uuid.UUID]]:
    if not isinstance(value, list):
        raise _artifact_contract_error()
    parsed: list[tuple[uuid.UUID, uuid.UUID]] = []
    for raw_marker in value:
        if (
            not isinstance(raw_marker, list)
            or len(raw_marker) != 2
            or any(type(item) is not str for item in raw_marker)
        ):
            raise _artifact_contract_error()
        try:
            marker = (uuid.UUID(raw_marker[0]), uuid.UUID(raw_marker[1]))
        except ValueError as exc:
            raise _artifact_contract_error() from exc
        if [str(item) for item in marker] != raw_marker:
            raise _artifact_contract_error()
        parsed.append(marker)
    if parsed != sorted(set(parsed), key=lambda item: (str(item[0]), str(item[1]))):
        raise _artifact_contract_error()
    return set(parsed)


def _parse_expected_trim_value_markers(
    value: Any,
) -> set[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    if not isinstance(value, list):
        raise _artifact_contract_error()
    parsed: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]] = []
    for raw_marker in value:
        if (
            not isinstance(raw_marker, list)
            or len(raw_marker) != 3
            or any(type(item) is not str for item in raw_marker)
        ):
            raise _artifact_contract_error()
        try:
            marker = (
                uuid.UUID(raw_marker[0]),
                uuid.UUID(raw_marker[1]),
                uuid.UUID(raw_marker[2]),
            )
        except ValueError as exc:
            raise _artifact_contract_error() from exc
        if [str(item) for item in marker] != raw_marker:
            raise _artifact_contract_error()
        parsed.append(marker)
    if parsed != sorted(
        set(parsed), key=lambda item: (str(item[0]), str(item[1]), str(item[2]))
    ):
        raise _artifact_contract_error()
    return set(parsed)


def _validate_normalized_artifact(
    *,
    metadata: Any,
    plan: dict[str, JsonlRows],
    job_id: uuid.UUID,
    job: Mapping[str, Any],
) -> tuple[
    dict[uuid.UUID, int],
    set[uuid.UUID],
    set[tuple[uuid.UUID, uuid.UUID]],
    set[tuple[uuid.UUID, uuid.UUID, uuid.UUID]],
]:
    """Authenticate every apply input against the immutable preview record."""
    if not isinstance(metadata, dict):
        raise _artifact_contract_error()
    schema_version = metadata.get("schema_version")
    if type(schema_version) is int and schema_version in {3, 4}:
        raise _NormalizedArtifactPreviewStaleError(_ARTIFACT_SCHEMA_STALE_DETAIL)
    if set(plan) != set(DATA_SHEET_HEADERS):
        raise _artifact_contract_error()

    source_sha256 = metadata.get("source_sha256")
    preview_hash = metadata.get("preview_hash")
    catalog_revision = metadata.get("catalog_revision")
    if (
        type(schema_version) is not int
        or schema_version != _NORMALIZED_ARTIFACT_SCHEMA_VERSION
        or metadata.get("job_id") != str(job_id)
        or type(source_sha256) is not str
        or _SHA256_RE.fullmatch(source_sha256) is None
        or type(preview_hash) is not str
        or _SHA256_RE.fullmatch(preview_hash) is None
        or type(catalog_revision) is not int
        or catalog_revision < 0
        or source_sha256 != job.get("source_sha256")
        or preview_hash != job.get("preview_hash")
        or catalog_revision != job.get("catalog_revision")
    ):
        raise _artifact_contract_error()

    expected_product_versions = _parse_expected_product_versions(
        metadata.get("expected_product_versions")
    )
    expected_active_seller_ids = _parse_expected_active_seller_ids(
        metadata.get("expected_active_seller_ids")
    )
    expected_modification_value_markers = (
        _parse_expected_modification_value_markers(
            metadata.get("expected_modification_value_markers")
        )
    )
    expected_trim_value_markers = _parse_expected_trim_value_markers(
        metadata.get("expected_trim_value_markers")
    )
    recomputed_hash = compute_preview_hash(
        source_sha256=source_sha256,
        catalog_revision=catalog_revision,
        plan=plan,
        expected_product_versions=expected_product_versions,
        expected_active_seller_ids=expected_active_seller_ids,
        expected_modification_value_markers=(
            expected_modification_value_markers
        ),
        expected_trim_value_markers=expected_trim_value_markers,
    )
    if recomputed_hash != preview_hash:
        raise _artifact_contract_error()
    return (
        expected_product_versions,
        expected_active_seller_ids,
        expected_modification_value_markers,
        expected_trim_value_markers,
    )


def _artifact_matches_locked_job(
    metadata: Mapping[str, Any], locked: Mapping[str, Any]
) -> bool:
    """Re-check DB state after acquiring the job row lock, before catalog writes."""
    return (
        metadata.get("source_sha256") == locked.get("source_sha256")
        and metadata.get("preview_hash") == locked.get("preview_hash")
        and metadata.get("catalog_revision") == locked.get("catalog_revision")
        and metadata.get("job_id") == str(locked.get("id"))
    )


def _vin_rows_requiring_target_warehouse(
    plan: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    """Return new in-stock VIN rows without a row-level warehouse.

    A later XLSX contract can assign a warehouse per row and allows ``on_order``
    offers without stock. The job target is therefore a fallback only for
    rows whose warehouse cell was not explicitly supplied.
    """

    return [
        row
        for row in plan.get("products", ())
        if row.get("operation") == "ADD"
        and not bool(row.get("values", {}).get("no_vin"))
        and row.get("values", {}).get("sale_status") != "on_order"
        and row.get("values", {}).get("warehouse_id") is None
    ]


def _effective_warehouse_id(
    row: Mapping[str, Any], target_warehouse_id: uuid.UUID | None
) -> Any:
    values = row.get("values", {})
    return target_warehouse_id or values.get("warehouse_id")


def _row_requires_warehouse(
    row: Mapping[str, Any], target_warehouse_id: uuid.UUID | None
) -> bool:
    values = row.get("values", {})
    return (
        row.get("operation") != "DELETE"
        and not bool(values.get("no_vin"))
        and values.get("sale_status") != "on_order"
        and _effective_warehouse_id(row, target_warehouse_id) is None
    )


def _exclude_products_missing_target_warehouse(
    plan: Mapping[str, Any],
    *,
    target_warehouse_id: uuid.UUID | None = None,
    on_rejected: Callable[[Mapping[str, Any]], None] | None = None,
) -> int:
    """Stream-prune rejected product aggregates using a disk-backed code index.

    Both the normalized rows and the rejected-code index remain bounded in
    process memory, even for a multi-gigabyte import.
    """
    products = plan.get("products", ())
    database_path = (
        products.path.with_suffix(".warehouse-rejections.sqlite3")
        if isinstance(products, JsonlRows)
        else None
    )
    connection = sqlite3.connect(database_path or ":memory:")
    rejected = 0
    try:
        connection.execute("CREATE TABLE rejected (code TEXT PRIMARY KEY)")
        for row in products:
            if _row_requires_warehouse(row, target_warehouse_id):
                code = str(row.get("code"))
                connection.execute("INSERT OR IGNORE INTO rejected VALUES (?)", (code,))
                rejected += 1
                if on_rejected is not None:
                    on_rejected(row)
        connection.commit()

        def retained(family: str, rows: Any) -> Any:
            for row in rows:
                code = str(row.get("code")) if family == "products" else str(row.get("_aggregate_code"))
                is_rejected = (
                    (family == "products" or row.get("_aggregate_kind") == "product")
                    and connection.execute("SELECT 1 FROM rejected WHERE code = ?", (code,)).fetchone() is not None
                )
                if not is_rejected:
                    yield row

        for family, rows in plan.items():
            if isinstance(rows, JsonlRows):
                rows.replace(retained(family, rows))
            elif isinstance(plan, dict):
                plan[family] = list(retained(family, rows))
    finally:
        connection.close()
        if database_path is not None:
            database_path.unlink(missing_ok=True)
    return rejected


def _drop_plan_aggregate(
    plan: dict[str, JsonlRows], *, aggregate_kind: str, aggregate_code: str
) -> None:
    for rows in plan.values():
        rows.replace(
            row
            for row in rows
            if (
                str(row.get("_aggregate_kind")) != aggregate_kind
                or str(row.get("_aggregate_code")) != aggregate_code
            )
        )


async def _transfer_plan_images(  # noqa: PLR0912, PLR0915
    *,
    job_id: uuid.UUID,
    mode: ImportMode,
    plan: dict[str, JsonlRows],
    issues: Any,
    storage: ImportObjectStorage,
) -> dict[str, int]:
    """Replace private source URLs with staged keys before preview persistence."""

    requested = 0
    transferred = 0
    reused = 0
    optional_failures = 0
    blocking_failures = 0
    failed_aggregates: set[tuple[str, str]] = set()

    # 1. Categories
    normalized_category_rows: list[dict[str, Any]] = []
    for row in plan.get("categories", ()):
        values = dict(row.get("values") or {})
        action = values.pop("_image_action", None)
        source_url = values.pop("_image_source_url", None)
        if action == "clear":
            values["image_key"] = None
        elif action == "replace" and source_url:
            requested += 1
            owner_id = uuid.UUID(str(row["id"]))

            async def reserve_cat(
                transferred_image: TransferredImage,
                *,
                reserve_owner_kind: str = "category",
                reserve_owner_id: uuid.UUID = owner_id,
            ) -> None:
                async with AsyncSessionLocal() as reserve_session:
                    await repo.record_staged_media(
                        reserve_session,
                        job_id=job_id,
                        storage_key=transferred_image.storage_key,
                        owner_kind=reserve_owner_kind,
                        owner_id=reserve_owner_id,
                    )
                    await reserve_session.commit()

            try:
                image = await transfer_temporary_image(
                    source_url=str(source_url),
                    owner_kind="category",
                    owner_id=owner_id,
                    staging_job_id=job_id,
                    storage=storage,
                    reserve_storage_key=reserve_cat,
                )
            except (ImportContractError, ImageTransferError) as exc:
                blocking_failures += 1
                code = getattr(exc, "code", None) or str(exc)
                issues.append(
                    ImportIssue(
                        sheet_code=str(row.get("_sheet_code") or "Категории"),
                        row_number=row.get("_row_number"),
                        column_name="Картинка",
                        code=str(code)[:100],
                        message="Изображение категории не удалось безопасно перенести",
                        entity_type=str(row.get("_aggregate_kind") or "category"),
                        external_key=str(row.get("_aggregate_code") or "") or None,
                    )
                )
                failed_aggregates.add(
                    (
                        str(row.get("_aggregate_kind") or "category"),
                        str(row.get("_aggregate_code") or ""),
                    )
                )
            else:
                transferred += 1
                values["image_key"] = image.storage_key
        normalized_category_rows.append({**row, "values": values})
    plan["categories"].replace(normalized_category_rows)

    # 2. Products
    has_new_product_images = any(
        "_images_action" in (row.get("values") or {})
        for row in plan.get("products", ())
    )

    if not has_new_product_images:
        normalized_legacy_rows: list[dict[str, Any]] = []
        for row in plan.get("products", ()):
            values = dict(row.get("values") or {})
            action = values.pop("_image_action", None)
            source_url = values.pop("_image_source_url", None)
            if action == "clear":
                values["_primary_image_action"] = "clear"
            elif action == "replace" and source_url:
                requested += 1
                owner_id = uuid.UUID(str(row["id"]))

                async def reserve_legacy(
                    transferred_image: TransferredImage,
                    *,
                    reserve_owner_kind: str = "product",
                    reserve_owner_id: uuid.UUID = owner_id,
                ) -> None:
                    async with AsyncSessionLocal() as reserve_session:
                        await repo.record_staged_media(
                            reserve_session,
                            job_id=job_id,
                            storage_key=transferred_image.storage_key,
                            owner_kind=reserve_owner_kind,
                            owner_id=reserve_owner_id,
                        )
                        await reserve_session.commit()

                try:
                    image = await transfer_temporary_image(
                        source_url=str(source_url),
                        owner_kind="product",
                        owner_id=owner_id,
                        staging_job_id=job_id,
                        storage=storage,
                        reserve_storage_key=reserve_legacy,
                    )
                except (ImportContractError, ImageTransferError) as exc:
                    blocking_failures += 1
                    code = getattr(exc, "code", None) or str(exc)
                    issues.append(
                        ImportIssue(
                            sheet_code=str(row.get("_sheet_code") or "Объявления"),
                            row_number=row.get("_row_number"),
                            column_name="Ссылка на изображение",
                            code=str(code)[:100],
                            message="Основное изображение не удалось безопасно перенести",
                            entity_type=str(row.get("_aggregate_kind") or "product"),
                            external_key=str(row.get("_aggregate_code") or "") or None,
                        )
                    )
                    failed_aggregates.add(
                        (
                            str(row.get("_aggregate_kind") or "product"),
                            str(row.get("_aggregate_code") or ""),
                        )
                    )
                else:
                    transferred += 1
                    values["_primary_image_action"] = "replace"
                    values["_primary_image_storage_key"] = image.storage_key
            normalized_legacy_rows.append({**row, "values": values})
        plan["products"].replace(normalized_legacy_rows)
    else:
        unique_product_sources: dict[str, str] = {}
        known_storage_by_ref: dict[str, str] = {}

        for row in plan.get("products", ()):
            values = row.get("values") or {}
            for img in values.get("_current_images") or ():
                s_ref = img.get("source_ref")
                s_key = img.get("storage_key")
                if s_ref and s_key:
                    known_storage_by_ref[s_ref] = s_key

            if values.get("_images_action") == "replace":
                for src in values.get("_image_sources") or ():
                    ref = src["source_ref"]
                    url = src["raw_url"]
                    if ref not in unique_product_sources:
                        unique_product_sources[ref] = url

        requested += len(unique_product_sources)
        sources_to_download = {
            ref: url
            for ref, url in unique_product_sources.items()
            if ref not in known_storage_by_ref
        }

        download_results: dict[str, str] = dict(known_storage_by_ref)
        download_errors: dict[str, Exception] = {}

        concurrency = getattr(
            settings, "special_equipment_import_image_concurrency", 4
        )
        budget_seconds = getattr(
            settings, "special_equipment_import_image_budget_seconds", 600
        )

        semaphore = asyncio.Semaphore(concurrency)
        start_time = asyncio.get_running_loop().time()
        deadline = start_time + budget_seconds

        async def reserve_product_staged_media(
            transferred_image: TransferredImage,
        ) -> None:
            async with AsyncSessionLocal() as reserve_session:
                await repo.record_staged_media(
                    reserve_session,
                    job_id=job_id,
                    storage_key=transferred_image.storage_key,
                    owner_kind="product",
                    owner_id=job_id,
                )
                await reserve_session.commit()

        async def fetch_product_image(
            ref: str, url: str
        ) -> tuple[str, str | None, Exception | None]:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return (
                    ref,
                    None,
                    ImportContractError(
                        "Превышен общий бюджет времени на загрузку изображений",
                        code="IMAGE_FETCH_BUDGET_EXCEEDED",
                    ),
                )
            try:
                async with semaphore:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        return (
                            ref,
                            None,
                            ImportContractError(
                                "Превышен общий бюджет времени на загрузку изображений",
                                code="IMAGE_FETCH_BUDGET_EXCEEDED",
                            ),
                        )
                    image = await asyncio.wait_for(
                        transfer_temporary_image(
                            source_url=url,
                            owner_kind="product",
                            owner_id=job_id,
                            staging_job_id=job_id,
                            storage=storage,
                            reserve_storage_key=reserve_product_staged_media,
                        ),
                        timeout=remaining,
                    )
                    return ref, image.storage_key, None
            except TimeoutError:
                return (
                    ref,
                    None,
                    ImportContractError(
                        "Превышен общий бюджет времени на загрузку изображений",
                        code="IMAGE_FETCH_BUDGET_EXCEEDED",
                    ),
                )
            except Exception as exc:
                return ref, None, exc

        if sources_to_download:
            fetch_results = await asyncio.gather(
                *(
                    fetch_product_image(ref, url)
                    for ref, url in sources_to_download.items()
                )
            )
            for ref, storage_key, fetch_err in fetch_results:
                if storage_key is not None:
                    download_results[ref] = storage_key
                    transferred += 1
                else:
                    download_errors[ref] = fetch_err or Exception("Image fetch failed")

        normalized_product_rows: list[dict[str, Any]] = []
        for row in plan.get("products", ()):
            values = dict(row.get("values") or {})
            images_action = values.get("_images_action")
            if images_action == "clear":
                values["_images"] = []
            elif images_action == "keep":
                pass
            elif images_action == "replace":
                image_sources = values.get("_image_sources") or ()
                current_images = values.get("_current_images") or ()
                current_by_ref = {
                    img["source_ref"]: img
                    for img in current_images
                    if img.get("source_ref")
                }
                target_images: list[dict[str, Any]] = []
                for src in image_sources:
                    ref = src["source_ref"]
                    url = src["raw_url"]
                    pos = src.get("position", 1)

                    if ref in current_by_ref:
                        reused_img = current_by_ref[ref]
                        target_images.append(
                            {
                                "storage_key": reused_img["storage_key"],
                                "source_ref": ref,
                                "reuse_image_id": reused_img["id"],
                            }
                        )
                        reused += 1
                        continue

                    if ref in download_results:
                        storage_key = download_results[ref]
                        target_images.append(
                            {
                                "storage_key": storage_key,
                                "source_ref": ref,
                                "reuse_image_id": None,
                            }
                        )
                    else:
                        source_err = download_errors.get(ref)
                        code = getattr(source_err, "code", None) or type(source_err).__name__
                        issues.append(
                            ImportIssue(
                                sheet_code=str(
                                    row.get("_sheet_code") or "Объявления"
                                ),
                                row_number=row.get("_row_number"),
                                column_name="Ссылка на изображение",
                                code=str(code)[:100],
                                message=f"Фото #{pos} ({url[:300]}): не удалось загрузить изображение",
                                severity=IssueSeverity.WARNING,
                                entity_type=str(
                                    row.get("_aggregate_kind") or "product"
                                ),
                                external_key=str(
                                    row.get("_aggregate_code") or ""
                                ),
                                raw_value_preview=url[:300],
                            )
                        )
                        optional_failures += 1

                if (image_sources or values.get("_image_source_url")) and not target_images:
                    blocking_failures += 1
                    issues.append(
                        ImportIssue(
                            sheet_code=str(
                                row.get("_sheet_code") or "Объявления"
                            ),
                            row_number=row.get("_row_number"),
                            column_name="Ссылка на изображение",
                            code="PRODUCT_IMAGES_ALL_FAILED",
                            message="Ни одно изображение объявления не удалось загрузить",
                            severity=IssueSeverity.ERROR,
                            entity_type=str(
                                row.get("_aggregate_kind") or "product"
                            ),
                            external_key=str(
                                row.get("_aggregate_code") or ""
                            ),
                        )
                    )
                    failed_aggregates.add(
                        (
                            str(row.get("_aggregate_kind") or "product"),
                            str(row.get("_aggregate_code") or ""),
                        )
                    )
                else:
                    values["_images"] = target_images
            normalized_product_rows.append({**row, "values": values})
        plan["products"].replace(normalized_product_rows)

    if mode is not ImportMode.FULL_SNAPSHOT:
        for aggregate_kind, aggregate_code in failed_aggregates:
            _drop_plan_aggregate(
                plan,
                aggregate_kind=aggregate_kind,
                aggregate_code=aggregate_code,
            )
    return {
        "requested": requested,
        "transferred": transferred,
        "reused": reused,
        "optionalFailures": optional_failures,
        "blockingFailures": blocking_failures,
    }


@broker.task(task_name="special_equipment_import.validate")
async def validate_special_equipment_import(  # noqa: PLR0911, PLR0912, PLR0915
    job_id: str,
) -> None:
    job_uuid = uuid.UUID(job_id)
    storage = get_special_equipment_import_storage()
    async with AsyncSessionLocal() as session:
        job = await repo.get_job(session, job_uuid, for_update=True)
        if job is None or job["status"] in {
            ImportStatus.CANCELLED.value,
            ImportStatus.PREVIEW_READY.value,
            ImportStatus.VALIDATION_FAILED.value,
            ImportStatus.COMPLETED.value,
            ImportStatus.COMPLETED_WITH_WARNINGS.value,
        }:
            return
        now = datetime.now(UTC)
        if (
            job["lease_owner"]
            and job["lease_until"] is not None
            and job["lease_until"] > now
        ):
            # Duplicate Taskiq delivery: the active owner keeps the job.
            return
        if job["status"] not in {
            ImportStatus.UPLOADED.value,
            ImportStatus.FAILED_RETRYABLE.value,
            ImportStatus.VALIDATING_FILE.value,
            ImportStatus.VALIDATING_DATA.value,
            ImportStatus.TRANSFERRING_IMAGES.value,
        }:
            return
        lease_owner = f"taskiq:{uuid.uuid4()}"
        await repo.update_job(
            session,
            job_uuid,
            status=ImportStatus.VALIDATING_FILE.value,
            phase="validating_file",
            lease_owner=lease_owner,
            lease_until=now + _LEASE_DURATION,
            heartbeat_at=now,
            error_code=None,
            error_detail=None,
        )
        await session.commit()

    heartbeat_task = asyncio.create_task(
        _heartbeat_validation_lease(job_uuid, lease_owner)
    )
    try:
        with tempfile.TemporaryDirectory(prefix=f"se-import-{job_uuid}-") as temp:
            root = Path(temp)
            source_path = root / "source.xlsx"
            source_sha256 = await storage.download_to_path(
                str(job["source_object_key"]), source_path
            )
            workbook = await asyncio.to_thread(
                parse_xlsx,
                source_path,
                expected_mode=ImportMode(str(job["mode"])),
                expected_template_version=int(job["template_version"]),
                spool_dir=root / "parsed",
            )
            async with AsyncSessionLocal() as session:
                current = await repo.get_job(session, job_uuid)
                if current is None or _is_cancelled(current):
                    return
                await repo.update_job(
                    session,
                    job_uuid,
                    status=ImportStatus.VALIDATING_DATA.value,
                    phase="validating_data",
                    source_sha256=source_sha256,
                    rows_total=workbook.row_count,
                    rows_done=workbook.row_count,
                    heartbeat_at=datetime.now(UTC),
                    lease_until=datetime.now(UTC) + _LEASE_DURATION,
                )
                await session.commit()

            async with AsyncSessionLocal() as session:
                await _begin_validation_snapshot(session)
                current = await repo.get_job(session, job_uuid)
                if current is None or _is_cancelled(current):
                    return
                catalog_revision = await repo.get_catalog_revision(session)
                (
                    plan,
                    issues,
                    summary,
                    expected_product_versions,
                    expected_active_seller_ids,
                ) = await build_normalized_plan(
                    session,
                    job=current,
                    workbook=workbook,
                    plan_spool_dir=root / "plan",
                )
                (
                    modification_value_markers,
                    trim_value_markers,
                    modification_by_trim_hint,
                ) = trim_value_plan_scope(plan)
                preview_value_state = (
                    await repo.read_trim_modification_value_state(
                        session,
                        modification_ids={
                            marker[0] for marker in modification_value_markers
                        },
                        trim_ids={marker[0] for marker in trim_value_markers},
                        modification_by_trim_hint=modification_by_trim_hint,
                    )
                )
                expected_modification_value_markers = set(
                    preview_value_state["modification_values"]
                )
                expected_trim_value_markers = set(
                    preview_value_state["trim_values"]
                )

                def record_missing_warehouse(row: Mapping[str, Any]) -> None:
                    issues.append(
                        ImportIssue(
                            sheet_code=str(
                                row.get("_sheet_code") or "Объявления"
                            ),
                            row_number=row.get("_row_number"),
                            code="WAREHOUSE_REQUIRED",
                            message=(
                                "Для VIN-объявления в наличии требуется склад "
                                "в строке или target warehouse"
                            ),
                            entity_type="product",
                            external_key=str(row.get("code") or "") or None,
                        )
                    )

                import_mode = ImportMode(str(current["mode"]))
                if import_mode in {ImportMode.APPEND, ImportMode.PATCH}:
                    missing_warehouse_count = _exclude_products_missing_target_warehouse(
                        plan,
                        target_warehouse_id=current.get("target_warehouse_id"),
                        on_rejected=record_missing_warehouse,
                    )
                    if missing_warehouse_count:
                        summary["errors"] = int(summary.get("errors") or 0) + missing_warehouse_count
                        summary["rejectedRows"] = int(summary.get("rejectedRows") or 0) + missing_warehouse_count
                        summary["issuesTotal"] = issues.total_count
                        summary["issuesStored"] = len(issues)
                        summary["issuesTruncated"] = issues.is_truncated
                        summary = rebuild_summary_for_plan(
                            summary, plan, ImportMode(str(current["mode"]))
                        )
                else:
                    for product_row in plan.get("products", ()):
                        if _row_requires_warehouse(
                            product_row,
                            current.get("target_warehouse_id"),
                        ):
                            record_missing_warehouse(product_row)
                await session.commit()

            planned_category_transfers = sum(
                1
                for row in plan.get("categories", ())
                if (row.get("values") or {}).get("_image_action") == "replace"
            )
            planned_product_transfers = sum(
                len((row.get("values") or {}).get("_image_sources") or ())
                if (row.get("values") or {}).get("_images_action") == "replace"
                else (
                    1
                    if (row.get("values") or {}).get("_image_action") == "replace"
                    else 0
                )
                for row in plan.get("products", ())
            )
            planned_image_transfers = (
                planned_category_transfers + planned_product_transfers
            )
            if planned_image_transfers:
                async with AsyncSessionLocal() as session:
                    await repo.update_job(
                        session,
                        job_uuid,
                        status=ImportStatus.TRANSFERRING_IMAGES.value,
                        phase="transferring_images",
                        images_total=planned_image_transfers,
                        images_done=0,
                        heartbeat_at=datetime.now(UTC),
                        lease_until=datetime.now(UTC) + _LEASE_DURATION,
                    )
                    await session.commit()
            image_summary = await _transfer_plan_images(
                job_id=job_uuid,
                mode=ImportMode(str(job["mode"])),
                plan=plan,
                issues=issues,
                storage=storage,
            )
            if (
                ImportMode(str(job["mode"])) is not ImportMode.FULL_SNAPSHOT
                and image_summary.get("blockingFailures", 0) > 0
            ):
                summary = rebuild_summary_for_plan(
                    summary, plan, ImportMode(str(job["mode"]))
                )
            summary["imageSummary"] = image_summary
            summary["errors"] = issues.error_count
            summary["warnings"] = issues.warning_count
            summary["issuesTotal"] = issues.total_count
            summary["issuesStored"] = len(issues)
            summary["issuesTruncated"] = issues.is_truncated

            async with AsyncSessionLocal() as session:
                current = await repo.get_job(session, job_uuid, for_update=True)
                if current is None or _is_cancelled(current):
                    return
                entity_count = sum(len(rows) for rows in plan.values())
                await repo.update_job(
                    session,
                    job_uuid,
                    entities_total=entity_count,
                    entities_done=entity_count,
                    images_total=image_summary["requested"],
                    images_done=image_summary["transferred"],
                    heartbeat_at=datetime.now(UTC),
                    lease_until=datetime.now(UTC) + _LEASE_DURATION,
                )
                await session.commit()

            preview_hash = compute_preview_hash(
                source_sha256=source_sha256,
                catalog_revision=catalog_revision,
                plan=plan,
                expected_product_versions=expected_product_versions,
                expected_active_seller_ids=expected_active_seller_ids,
                expected_modification_value_markers=(
                    expected_modification_value_markers
                ),
                expected_trim_value_markers=expected_trim_value_markers,
            )
            artifact_path = root / "normalized.zip"
            await asyncio.to_thread(
                write_rows_archive,
                artifact_path,
                metadata={
                    "schema_version": _NORMALIZED_ARTIFACT_SCHEMA_VERSION,
                    "job_id": str(job_uuid),
                    "source_sha256": source_sha256,
                    "catalog_revision": catalog_revision,
                    "preview_hash": preview_hash,
                    "expected_product_versions": {
                        str(product_id): version
                        for product_id, version in sorted(
                            expected_product_versions.items(),
                            key=lambda item: str(item[0]),
                        )
                    },
                    "expected_active_seller_ids": [
                        str(seller_id)
                        for seller_id in sorted(expected_active_seller_ids, key=str)
                    ],
                    "expected_modification_value_markers": [
                        [str(modification_id), str(attribute_id)]
                        for modification_id, attribute_id in sorted(
                            expected_modification_value_markers,
                            key=lambda marker: (str(marker[0]), str(marker[1])),
                        )
                    ],
                    "expected_trim_value_markers": [
                        [str(trim_id), str(modification_id), str(attribute_id)]
                        for trim_id, modification_id, attribute_id in sorted(
                            expected_trim_value_markers,
                            key=lambda marker: (
                                str(marker[0]),
                                str(marker[1]),
                                str(marker[2]),
                            ),
                        )
                    ],
                },
                rows=plan,
            )
            artifact_key = (
                f"special-equipment/imports/{job_uuid}/normalized/{preview_hash}.zip"
            )
            await storage.put_path(artifact_key, artifact_path, "application/zip")
            report_path = root / "validation-report.json"
            await asyncio.to_thread(
                _write_validation_report,
                report_path,
                summary,
                issues,
            )
            report_key = (
                f"special-equipment/imports/{job_uuid}/reports/{preview_hash}.json"
            )
            await storage.put_path(report_key, report_path, "application/json")

            validation_blocked = (
                ImportErrorPolicy(str(job["error_policy"])) is ImportErrorPolicy.ATOMIC
                and int(summary["errors"]) > 0
            )
            terminal_status = (
                ImportStatus.VALIDATION_FAILED.value
                if validation_blocked
                else ImportStatus.PREVIEW_READY.value
            )
            async with AsyncSessionLocal() as session:
                current = await repo.get_job(session, job_uuid, for_update=True)
                if current is None or _is_cancelled(current):
                    return
                await repo.replace_issues(
                    session,
                    job_id=job_uuid,
                    issues=issues_to_rows(job_id=job_uuid, issues=issues),
                )
                await repo.update_job(
                    session,
                    job_uuid,
                    status=terminal_status,
                    phase=terminal_status,
                    source_sha256=source_sha256,
                    normalized_artifact_key=artifact_key,
                    validation_report_key=report_key,
                    catalog_revision=catalog_revision,
                    preview_hash=preview_hash,
                    summary=summary,
                    issues_total=issues.total_count,
                    images_done=image_summary["transferred"],
                    previewed_at=datetime.now(UTC),
                    lease_owner=None,
                    lease_until=None,
                    heartbeat_at=datetime.now(UTC),
                )
                await session.commit()
    except ImportContractError as exc:
        await _mark_validation_failed(job_uuid, str(exc))
    except Exception as exc:
        logger.error(
            "special_equipment_import_validation_failed job=%s error_type=%s",
            job_uuid,
            type(exc).__name__,
        )
        await _mark_retryable(
            job_uuid,
            "VALIDATION_RUNTIME_ERROR",
            _VALIDATION_RUNTIME_ERROR_DETAIL,
        )
    finally:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task


@broker.task(task_name="special_equipment_import.apply")
async def apply_special_equipment_import(  # noqa: PLR0912, PLR0915
    job_id: str,
) -> None:
    job_uuid = uuid.UUID(job_id)
    storage = get_special_equipment_import_storage()
    async with AsyncSessionLocal() as session:
        job = await repo.get_job(session, job_uuid)
    if job is None or job["status"] in {
        ImportStatus.COMPLETED.value,
        ImportStatus.COMPLETED_WITH_WARNINGS.value,
        ImportStatus.CANCELLED.value,
    }:
        return
    if (
        job["status"] != ImportStatus.APPLYING.value
        or not job["normalized_artifact_key"]
    ):
        return

    try:
        with tempfile.TemporaryDirectory(prefix=f"se-apply-{job_uuid}-") as temp:
            root = Path(temp)
            artifact_path = root / "normalized.zip"
            await storage.download_to_path(
                str(job["normalized_artifact_key"]), artifact_path
            )
            metadata, plan = await asyncio.to_thread(
                read_rows_archive,
                artifact_path,
                output_dir=root / "rows",
            )
            (
                expected_product_versions,
                expected_active_seller_ids,
                expected_modification_value_markers,
                expected_trim_value_markers,
            ) = await asyncio.to_thread(
                _validate_normalized_artifact,
                metadata=metadata,
                plan=plan,
                job_id=job_uuid,
                job=job,
            )

            async with AsyncSessionLocal() as session:
                locked = await repo.get_job(session, job_uuid, for_update=True)
                if locked is None or locked["status"] != ImportStatus.APPLYING.value:
                    return
                if not _artifact_matches_locked_job(metadata, locked):
                    raise _artifact_contract_error()
                revision = await repo.get_catalog_revision(session, for_update=True)
                product_versions_match = await repo.lock_expected_product_versions(
                    session, expected_product_versions
                )
                active_sellers_match = await repo.lock_active_seller_companies(
                    session, expected_active_seller_ids
                )
                archive_targets_are_available = await repo.lock_import_archive_targets(
                    session,
                    source_code=str(locked["source_code"]),
                    mode=str(locked["mode"]),
                    plan=plan,
                    target_warehouse_id=locked.get("target_warehouse_id"),
                )
                if await _finish_if_preview_stale(
                    session,
                    job_id=job_uuid,
                    revision=revision,
                    locked_job=locked,
                    plan=plan,
                    expected_modification_value_markers=(
                        expected_modification_value_markers
                    ),
                    expected_trim_value_markers=expected_trim_value_markers,
                    product_versions_match=product_versions_match,
                    active_sellers_match=active_sellers_match,
                    archive_targets_are_available=archive_targets_are_available,
                ):
                    return
                if locked.get("target_warehouse_id") is not None and not await repo.warehouse_is_active(
                    session, locked["target_warehouse_id"]
                ):
                    await repo.update_job(
                        session,
                        job_uuid,
                        status=ImportStatus.FAILED.value,
                        phase=ImportStatus.FAILED.value,
                        error_code="TARGET_WAREHOUSE_INVALID",
                        error_detail="TARGET_WAREHOUSE_INVALID",
                        lease_owner=None,
                        lease_until=None,
                    )
                    await session.commit()
                    return
                if (
                    str(locked["mode"]) == "FULL_SNAPSHOT"
                    and locked.get("target_warehouse_id") is not None
                ):
                    await repo.cascade_purge_warehouse_products(
                        session, locked["target_warehouse_id"]
                    )
                result = await repo.apply_normalized_plan(
                    session,
                    job_id=job_uuid,
                    source_code=str(locked["source_code"]),
                    mode=str(locked["mode"]),
                    plan=plan,
                    template_version=int(locked["template_version"]),
                    target_warehouse_id=locked.get("target_warehouse_id"),
                )
                await repo.assign_target_warehouse(
                    session,
                    warehouse_id=locked.get("target_warehouse_id"),
                    mode=str(locked["mode"]),
                    plan=plan,
                )
                rejected_aggregates = list(result.get("rejected_aggregates") or ())
                if rejected_aggregates:
                    existing_issues = await repo.list_issues(
                        session,
                        job_id=job_uuid,
                        severity=None,
                        sheet_code=None,
                        after_sequence=0,
                        limit=MAX_UI_ISSUES,
                    )
                    start_sequence = len(existing_issues) + 1
                    for offset, issue in enumerate(rejected_aggregates):
                        issue["job_id"] = job_uuid
                        issue["sequence"] = start_sequence + offset
                    await repo.append_issues(
                        session,
                        issues=rejected_aggregates,
                    )
                await repo.mark_job_staged_media_referenced(session, job_id=job_uuid)
                new_revision = await repo.increment_catalog_revision(
                    session, updated_by=locked["requested_by"]
                )
                warnings = int((locked.get("summary") or {}).get("warnings") or 0)
                warnings += len(rejected_aggregates)
                status = (
                    ImportStatus.COMPLETED_WITH_WARNINGS.value
                    if warnings
                    else ImportStatus.COMPLETED.value
                )
                summary = {
                    **(locked.get("summary") or {}),
                    "applied": result["counts"],
                    "rejectedAggregates": len(rejected_aggregates),
                }
                await repo.update_job(
                    session,
                    job_uuid,
                    status=status,
                    phase=status,
                    applied_revision=new_revision,
                    applied_at=datetime.now(UTC),
                    summary=summary,
                    issues_total=int(locked.get("issues_total") or 0)
                    + len(rejected_aggregates),
                    lease_owner=None,
                    lease_until=None,
                )
                await session.commit()
    except ImportAggregateSemanticConflictError as exc:
        await _mark_failed(job_uuid, exc.code, str(exc))
    except _NormalizedArtifactPreviewStaleError:
        await _mark_preview_stale(job_uuid, _ARTIFACT_SCHEMA_STALE_DETAIL)
    except ImportContractError as exc:
        await _mark_failed(job_uuid, "NORMALIZED_ARTIFACT_INVALID", str(exc))
    except Exception as exc:
        diag = repo.extract_dbapi_diagnostic(exc)
        if any(diag.values()):
            logger.exception(
                "special_equipment_import_apply_failed job=%s error_type=%s sqlstate=%s constraint=%s column=%s table=%s",
                job_uuid,
                type(exc).__name__,
                diag.get("sqlstate"),
                diag.get("constraint_name"),
                diag.get("column_name"),
                diag.get("table_name"),
            )
        else:
            logger.exception(
                "special_equipment_import_apply_failed job=%s error_type=%s",
                job_uuid,
                type(exc).__name__,
            )
        await _mark_failed(job_uuid, "APPLY_FAILED", _APPLY_RUNTIME_ERROR_DETAIL)


@broker.task(
    task_name="special_equipment_import.recover",
    schedule=[{"cron": "* * * * *"}],
)
async def recover_special_equipment_imports() -> None:
    async with AsyncSessionLocal() as session:
        jobs = await repo.list_recoverable_jobs(session)
        await session.commit()
    for job in jobs:
        if job["status"] == ImportStatus.APPLYING.value:
            await apply_special_equipment_import.kiq(str(job["id"]))
        else:
            await validate_special_equipment_import.kiq(str(job["id"]))


@broker.task(
    task_name="special_equipment_import.cleanup_staged_media",
    schedule=[{"cron": "0 * * * *"}],
)
async def cleanup_special_equipment_staged_media() -> None:
    """Delete expired, unreferenced job-scoped media in bounded pages."""
    storage = get_special_equipment_import_storage()
    while await _cleanup_staged_media_page(storage):
        pass


async def _cleanup_staged_media_page(storage: ImportObjectStorage) -> bool:
    async with AsyncSessionLocal() as session:
        candidates = await repo.list_staged_media_cleanup_candidates(session, limit=200)
        await session.commit()
    if not candidates:
        return False

    for candidate in candidates:
        job_id = uuid.UUID(str(candidate["job_id"]))
        storage_key = str(candidate["storage_key"])
        async with AsyncSessionLocal() as session:
            referenced = await repo.is_staged_media_referenced(
                session, storage_key=storage_key
            )
            protected = await repo.has_protected_staged_media(
                session, storage_key=storage_key
            )
            if referenced:
                await repo.mark_staged_media_status(
                    session,
                    job_id=job_id,
                    storage_key=storage_key,
                    status="referenced",
                )
                await session.commit()
                continue
            if protected:
                await session.commit()
                continue

        try:
            await storage.delete(storage_key)
        except Exception as exc:
            logger.warning(
                "special_equipment_staged_media_cleanup_failed job=%s err=%s",
                job_id,
                type(exc).__name__,
            )
            continue
        async with AsyncSessionLocal() as session:
            # Re-check after I/O. Job-scoped keys avoid cross-job reuse, and a
            # concurrent apply that referenced the key wins over deletion state.
            if await repo.is_staged_media_referenced(session, storage_key=storage_key):
                await repo.mark_staged_media_status(
                    session,
                    job_id=job_id,
                    storage_key=storage_key,
                    status="referenced",
                )
            else:
                await repo.mark_staged_media_status(
                    session,
                    job_id=job_id,
                    storage_key=storage_key,
                    status="deleted",
                )
            await session.commit()
    return len(candidates) == 200


@broker.task(
    task_name="special_equipment_import.cleanup_expired_artifacts",
    schedule=[{"cron": "20 * * * *"}],
)
async def cleanup_expired_special_equipment_import_artifacts() -> None:
    """Delete retained technical artifacts in an hourly bounded sweep."""
    storage = get_special_equipment_import_storage()
    for _page in range(_ARTIFACT_CLEANUP_MAX_PAGES):
        claimed = await _cleanup_expired_artifact_page(storage)
        if claimed < _ARTIFACT_CLEANUP_PAGE_SIZE:
            break


async def _cleanup_expired_artifact_page(storage: ImportObjectStorage) -> int:
    now = datetime.now(UTC)
    lease_owner = f"taskiq-artifact-gc:{uuid.uuid4()}"
    async with AsyncSessionLocal() as session:
        jobs = await repo.claim_expired_artifact_cleanup_jobs(
            session,
            now=now,
            lease_owner=lease_owner,
            lease_until=now + _ARTIFACT_CLEANUP_LEASE_DURATION,
            limit=_ARTIFACT_CLEANUP_PAGE_SIZE,
        )
        await session.commit()

    for job in jobs:
        job_id = uuid.UUID(str(job["id"]))
        # Deliberately excludes special_equipment_import_staged_media. Those
        # objects have a separate reference-aware lifecycle and may be live
        # category/product media after apply.
        artifact_keys = tuple(
            dict.fromkeys(
                str(job[field]) for field in _ARTIFACT_KEY_FIELDS if job.get(field)
            )
        )
        failures: list[str] = []
        for storage_key in artifact_keys:
            try:
                # S3 DeleteObject is idempotent, so a retry after a partial
                # sweep is safe even when an earlier key is already absent.
                await storage.delete(storage_key)
            except Exception as exc:  # pragma: no cover - provider dependent
                failures.append(type(exc).__name__)

        async with AsyncSessionLocal() as session:
            if failures:
                await repo.fail_artifact_cleanup(
                    session,
                    job_id=job_id,
                    lease_owner=lease_owner,
                    error="object storage delete failed: " + ",".join(failures),
                    failed_at=datetime.now(UTC),
                )
                logger.warning(
                    "special_equipment_import_artifact_cleanup_failed "
                    "job=%s failures=%s",
                    job_id,
                    len(failures),
                )
            else:
                await repo.complete_artifact_cleanup(
                    session,
                    job_id=job_id,
                    lease_owner=lease_owner,
                    cleaned_at=datetime.now(UTC),
                )
            await session.commit()
    return len(jobs)


async def _recover_on_startup(_state: TaskiqState) -> None:
    try:
        await recover_special_equipment_imports()
    except Exception as exc:  # pragma: no cover - infrastructure dependent
        logger.warning(
            "special_equipment_import_recovery_failed error_type=%s",
            type(exc).__name__,
        )


broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, _recover_on_startup)


def _is_cancelled(job: dict) -> bool:
    return (
        bool(job["cancellation_requested"])
        or job["status"] == ImportStatus.CANCELLED.value
    )


async def _heartbeat_validation_lease(job_id: uuid.UUID, lease_owner: str) -> None:
    active_statuses = {
        ImportStatus.VALIDATING_FILE.value,
        ImportStatus.VALIDATING_DATA.value,
        ImportStatus.TRANSFERRING_IMAGES.value,
    }
    while True:
        await asyncio.sleep(60)
        async with AsyncSessionLocal() as session:
            job = await repo.get_job(session, job_id, for_update=True)
            if (
                job is None
                or job["status"] not in active_statuses
                or job["lease_owner"] != lease_owner
            ):
                return
            now = datetime.now(UTC)
            await repo.update_job(
                session,
                job_id,
                heartbeat_at=now,
                lease_until=now + _LEASE_DURATION,
            )
            await session.commit()


def _write_validation_report(
    path: Path, summary: dict, issues: list[ImportIssue]
) -> None:
    with path.open("w", encoding="utf-8") as stream:
        stream.write('{"summary":')
        json.dump(summary, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write(',"issues":[')
        for index, issue in enumerate(issues):
            if index:
                stream.write(",")
            json.dump(
                issue.as_dict(), stream, ensure_ascii=False, separators=(",", ":")
            )
        stream.write("]}")


_CONTRACT_ERROR_MESSAGES: dict[str, str] = {
    "PARAMETERS_VERSION_MISMATCH": (
        "Версия шаблона книги не совпадает с актуальной версией v6. "
        "Скачайте актуальный шаблон."
    ),
    "PARAMETERS_SHEET_MISSING": (
        "В книге отсутствует обязательный служебный лист «Параметры»."
    ),
    "PARAMETERS_MODE_MISMATCH": (
        "Режим импорта на листе «Параметры» не совпадает с выбранным режимом задания."
    ),
    "PARAMETERS_KEY_INVALID": (
        "На листе «Параметры» указан некорректный или дублирующийся параметр."
    ),
    "PARAMETERS_CLEAR_TOKEN_INVALID": (
        "Неверный маркер очистки на листе «Параметры» (ожидается «__CLEAR__»)."
    ),
    "PARAMETERS_GENERATED_AT_INVALID": (
        "Некорректный формат даты формирования на листе «Параметры»."
    ),
    "MANIFEST_SHEET_MISSING": (
        "Книга имеет устаревший формат v1 или повреждён заголовок параметров."
    ),
    "MANIFEST_HEADER_INVALID": (
        "Книга имеет устаревший формат v1 или повреждён заголовок параметров."
    ),
    "XLSX_ZIP_INVALID": "Файл повреждён или не является корректной книгой Excel.",
    "XLSX_OPEN_FAILED": "Файл повреждён или не является корректной книгой Excel.",
    "XLSX_ACTIVE_CONTENT_FORBIDDEN": (
        "В файле обнаружены макросы (VBA) или элементы ActiveX. "
        "Разрешён только обычный файл XLSX."
    ),
    "XLSX_FORMULA_FORBIDDEN": (
        "В ячейках обнаружены формулы. Разрешены только статические значения."
    ),
    "CELL_TEXT_TOO_LONG": (
        "Текст в ячейке превышает максимально допустимую длину в 100 000 символов."
    ),
    "XLSX_TOO_MANY_ZIP_ENTRIES": (
        "Превышены допустимые лимиты размера или структуры архива Excel."
    ),
    "XLSX_UNCOMPRESSED_SIZE_EXCEEDED": (
        "Превышены допустимые лимиты размера или структуры архива Excel."
    ),
    "XLSX_COMPRESSION_RATIO_EXCEEDED": (
        "Превышены допустимые лимиты размера или структуры архива Excel."
    ),
}

_PARAMETERIZED_ERROR_TEMPLATES: dict[str, tuple[str, str]] = {
    "PARAMETERS_KEYS_MISSING": (
        "На листе «Параметры» отсутствуют обязательные параметры: {arg}.",
        "На листе «Параметры» отсутствуют обязательные параметры.",
    ),
    "PARAMETERS_KEY_UNKNOWN": (
        "На листе «Параметры» указан неизвестный параметр: {arg}.",
        "На листе «Параметры» указан неизвестный параметр.",
    ),
    "UNKNOWN_SHEET": (
        "В книге обнаружен неизвестный лист: «{arg}».",
        "В книге обнаружен неизвестный лист.",
    ),
    "SHEET_HEADER_INVALID": (
        "На листе «{arg}» изменены, отсутствуют или нарушен порядок колонок.",
        "На листе изменены, отсутствуют или нарушен порядок колонок.",
    ),
    "FULL_SNAPSHOT_SHEETS_MISSING": (
        "Для режима полной замены отсутствуют обязательные листы: {arg}.",
        "Для режима полной замены отсутствуют обязательные листы.",
    ),
}


def _humanize_contract_error(detail: str) -> tuple[str, str]:
    if not detail:
        return "", ""
    parts = detail.split(":", 1)
    code = parts[0][:100]
    arg = parts[1].strip() if len(parts) > 1 else ""

    if code in _CONTRACT_ERROR_MESSAGES:
        return code, _CONTRACT_ERROR_MESSAGES[code]

    if code in _PARAMETERIZED_ERROR_TEMPLATES:
        template_with_arg, template_default = _PARAMETERIZED_ERROR_TEMPLATES[code]
        message = template_with_arg.format(arg=arg) if arg else template_default
        return code, message[:1000]

    return code, detail[:1000]


async def _mark_validation_failed(job_id: uuid.UUID, detail: str) -> None:
    code, human_message = _humanize_contract_error(detail)
    issue = ImportIssue(
        sheet_code="workbook",
        code=code,
        message=human_message,
    )
    async with AsyncSessionLocal() as session:
        await repo.replace_issues(
            session,
            job_id=job_id,
            issues=issues_to_rows(job_id=job_id, issues=[issue]),
        )
        await repo.update_job(
            session,
            job_id,
            status=ImportStatus.VALIDATION_FAILED.value,
            phase="validation_failed",
            issues_total=1,
            error_code=issue.code,
            error_detail=human_message,
            lease_owner=None,
            lease_until=None,
        )
        await session.commit()


async def _mark_retryable(job_id: uuid.UUID, code: str, detail: str) -> None:
    async with AsyncSessionLocal() as session:
        job = await repo.get_job(session, job_id, for_update=True)
        if job is None:
            return
        retry_count = int(job["retry_count"]) + 1
        exhausted = retry_count >= 5
        retry_delay = min(2**retry_count, 300)
        await repo.update_job(
            session,
            job_id,
            status=(
                ImportStatus.FAILED.value
                if exhausted
                else ImportStatus.FAILED_RETRYABLE.value
            ),
            phase="failed" if exhausted else "failed_retryable",
            retry_count=retry_count,
            error_code="RETRIES_EXHAUSTED" if exhausted else code,
            error_detail=detail[:1000],
            lease_owner=None,
            lease_until=(
                None
                if exhausted
                else datetime.now(UTC) + timedelta(seconds=retry_delay)
            ),
        )
        await session.commit()


async def _mark_preview_stale(job_id: uuid.UUID, detail: str) -> None:
    async with AsyncSessionLocal() as session:
        job = await repo.get_job(session, job_id, for_update=True)
        if job is None or _is_cancelled(job):
            return
        await repo.update_job(
            session,
            job_id,
            status=ImportStatus.PREVIEW_STALE.value,
            phase=ImportStatus.PREVIEW_STALE.value,
            error_code="PREVIEW_STALE",
            error_detail=detail,
            lease_owner=None,
            lease_until=None,
        )
        await session.commit()


async def _mark_failed(job_id: uuid.UUID, code: str, detail: str) -> None:
    async with AsyncSessionLocal() as session:
        await repo.update_job(
            session,
            job_id,
            status=ImportStatus.FAILED.value,
            phase="failed",
            error_code=code,
            error_detail=detail[:1000],
            lease_owner=None,
            lease_until=None,
        )
        await session.commit()


__all__ = [
    "apply_special_equipment_import",
    "cleanup_expired_special_equipment_import_artifacts",
    "recover_special_equipment_imports",
    "validate_special_equipment_import",
]
