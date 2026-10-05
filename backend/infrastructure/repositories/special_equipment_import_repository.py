"""Persistence adapter for special-equipment import jobs and apply metadata."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, TypedDict, cast

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.special_equipment_import import (
    TERMINAL_STATUSES,
    ImportAggregateSemanticConflictError,
    ImportErrorPolicy,
    ImportMode,
    apply_trim_value_import_policy,
    special_equipment_column_title,
    trim_value_plan_scope,
)
from domain.special_equipment_management import (
    SpecialEquipmentManagementConflictError,
    ensure_deactivation_allowed,
    ensure_product_archive_allowed,
    ensure_sale_transition,
    trim_modification_value_conflicts,
)
from infrastructure.models.applications import (
    ApplicationVehicle,
    ApplicationVehicleAllocation,
)
from infrastructure.models.companies import Company
from infrastructure.models.exchange import (
    ExchangeCartItem,
    ExchangeRequest,
)
from infrastructure.models.payments import (
    LeasingPaymentSchedule,
    Payment,
    PurchaseOrder,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentAttribute,
    SpecialEquipmentAttributeGroup,
    SpecialEquipmentAttributeOption,
    SpecialEquipmentCategory,
    SpecialEquipmentCategoryAttribute,
    SpecialEquipmentCategoryRelation,
    SpecialEquipmentColor,
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentModificationAttributeValue,
    SpecialEquipmentModificationCategory,
    SpecialEquipmentProduct,
    SpecialEquipmentProductAttachment,
    SpecialEquipmentProductCategory,
    SpecialEquipmentProductChassisValue,
    SpecialEquipmentProductImage,
    SpecialEquipmentProductSuperstructureValue,
    SpecialEquipmentSuperstructure,
    SpecialEquipmentSuperstructureAttribute,
    SpecialEquipmentSuperstructureCategory,
    SpecialEquipmentTrim,
    SpecialEquipmentTrimAttribute,
    SpecialEquipmentTrimAttributeValue,
    SpecialEquipmentUnit,
)
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
    SpecialEquipmentCartItem,
    SpecialEquipmentFavorite,
    SpecialEquipmentLeasingPaymentSchedule,
    SpecialEquipmentOrderItem,
    SpecialEquipmentPayment,
    SpecialEquipmentPaymentCallbackInbox,
    SpecialEquipmentPriceChangeLog,
    SpecialEquipmentPurchaseOrder,
)
from infrastructure.models.special_equipment_import import (
    SpecialEquipmentCatalogState,
    SpecialEquipmentImportIssue,
    SpecialEquipmentImportJob,
    SpecialEquipmentImportStagedMedia,
    SpecialEquipmentImportUploadPart,
)
from infrastructure.models.users import UserFavorite
from infrastructure.models.vehicles import City, VehicleWarehouseTransfer, Warehouse
from infrastructure.repositories import (
    special_equipment_management_repository as management_repository,
)

_TERMINAL_IMPORT_STATUS_VALUES = tuple(status.value for status in TERMINAL_STATUSES)


class TrimModificationValueState(TypedDict):
    """Persisted markers read while modification and trim rows are locked."""

    modification_by_trim: dict[uuid.UUID, uuid.UUID]
    trim_values: set[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]
    modification_values: set[tuple[uuid.UUID, uuid.UUID]]


def _uuid_array(name: str, values: set[uuid.UUID]) -> Any:
    return sa.bindparam(
        name,
        value=sorted(values, key=str),
        type_=ARRAY(PGUUID(as_uuid=True)),
    )


def _job_dict(model: SpecialEquipmentImportJob) -> dict[str, Any]:
    return {
        column.name: getattr(model, column.name) for column in model.__table__.columns
    }


def _part_dict(model: SpecialEquipmentImportUploadPart) -> dict[str, Any]:
    return {
        column.name: getattr(model, column.name) for column in model.__table__.columns
    }


def _issue_dict(model: SpecialEquipmentImportIssue) -> dict[str, Any]:
    return {
        column.name: getattr(model, column.name) for column in model.__table__.columns
    }


async def get_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    requested_by: uuid.UUID | None = None,
    for_update: bool = False,
) -> dict[str, Any] | None:
    query = sa.select(SpecialEquipmentImportJob).where(
        SpecialEquipmentImportJob.id == job_id
    )
    if requested_by is not None:
        query = query.where(SpecialEquipmentImportJob.requested_by == requested_by)
    if for_update:
        query = query.with_for_update()
    model = (await session.execute(query)).scalar_one_or_none()
    return _job_dict(model) if model else None


async def get_job_by_idempotency(
    session: AsyncSession, *, requested_by: uuid.UUID, idempotency_key: str
) -> dict[str, Any] | None:
    model = (
        await session.execute(
            sa.select(SpecialEquipmentImportJob).where(
                SpecialEquipmentImportJob.requested_by == requested_by,
                SpecialEquipmentImportJob.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    return _job_dict(model) if model else None


async def acquire_create_idempotency_lock(
    session: AsyncSession,
    *,
    requested_by: uuid.UUID,
    idempotency_key: str,
) -> None:
    """Serialize the first read/insert for one user-scoped import key."""
    lock_key = f"special-equipment-import:{requested_by}:{idempotency_key}"
    await session.execute(
        sa.text(
            "SELECT pg_advisory_xact_lock(hashtextextended(CAST(:lock_key AS text), 0))"
        ),
        {"lock_key": lock_key},
    )


async def create_job(
    session: AsyncSession, *, values: dict[str, Any]
) -> dict[str, Any]:
    model = SpecialEquipmentImportJob(**values)
    session.add(model)
    try:
        await session.flush()
    except IntegrityError as exc:
        if _is_target_warehouse_integrity_error(exc):
            raise ImportTargetWarehouseUnavailableError from exc
        raise
    return _job_dict(model)


async def list_jobs(
    session: AsyncSession,
    *,
    requested_by: uuid.UUID,
    limit: int,
    before_created_at: datetime | None = None,
    before_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    query = sa.select(SpecialEquipmentImportJob).where(
        SpecialEquipmentImportJob.requested_by == requested_by
    )
    if before_created_at is not None and before_id is not None:
        query = query.where(
            sa.tuple_(
                SpecialEquipmentImportJob.created_at,
                SpecialEquipmentImportJob.id,
            )
            < sa.tuple_(sa.literal(before_created_at), sa.literal(before_id))
        )
    models = (
        (
            await session.execute(
                query.order_by(
                    SpecialEquipmentImportJob.created_at.desc(),
                    SpecialEquipmentImportJob.id.desc(),
                ).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [_job_dict(model) for model in models]


async def warehouse_is_active(session: AsyncSession, warehouse_id: uuid.UUID) -> bool:
    return bool(
        await session.scalar(
            sa.select(sa.literal(True)).where(
                Warehouse.id == warehouse_id, Warehouse.status == "active"
            )
        )
    )


async def get_warehouse_assignment(
    session: AsyncSession, warehouse_id: uuid.UUID | None
) -> dict[str, Any] | None:
    """Return the safe, human-readable warehouse DTO for an import response."""
    if warehouse_id is None:
        return None
    row = (
        await session.execute(
            sa.select(Warehouse.id, Warehouse.address, City.name.label("city_name"))
            .outerjoin(City, City.id == Warehouse.city_id)
            .where(Warehouse.id == warehouse_id)
        )
    ).mappings().one_or_none()
    if row is None:
        return None
    return {"id": row["id"], "address": row["address"], "city_name": row["city_name"]}


async def get_warehouse_assignments(
    session: AsyncSession, warehouse_ids: set[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    """Load response-safe warehouse DTOs for one import history page."""
    if not warehouse_ids:
        return {}
    rows = (
        await session.execute(
            sa.select(Warehouse.id, Warehouse.address, City.name.label("city_name"))
            .outerjoin(City, City.id == Warehouse.city_id)
            .where(Warehouse.id.in_(warehouse_ids))
        )
    ).mappings()
    return {
        row["id"]: {
            "id": row["id"],
            "address": row["address"],
            "city_name": row["city_name"],
        }
        for row in rows
    }


async def update_job(
    session: AsyncSession, job_id: uuid.UUID, **values: Any
) -> dict[str, Any]:
    values["updated_at"] = sa.func.now()
    await session.execute(
        sa.update(SpecialEquipmentImportJob)
        .where(SpecialEquipmentImportJob.id == job_id)
        .values(**values)
    )
    await session.flush()
    job = await get_job(session, job_id)
    if job is None:  # pragma: no cover - guarded by callers
        raise LookupError("Import job disappeared")
    return job


async def acquire_part_lock(
    session: AsyncSession, *, job_id: uuid.UUID, part_number: int
) -> None:
    # Two signed int32 keys avoid Python/hash randomisation and serialize only
    # retries of the same part, not independent parallel parts.
    first = int.from_bytes(job_id.bytes[:4], "big", signed=True)
    await session.execute(
        sa.text("SELECT pg_advisory_xact_lock(:first, :second)"),
        {"first": first, "second": part_number},
    )


async def get_part(
    session: AsyncSession, *, job_id: uuid.UUID, part_number: int
) -> dict[str, Any] | None:
    model = await session.get(SpecialEquipmentImportUploadPart, (job_id, part_number))
    return _part_dict(model) if model else None


async def add_part(session: AsyncSession, *, values: dict[str, Any]) -> dict[str, Any]:
    model = SpecialEquipmentImportUploadPart(**values)
    session.add(model)
    await session.flush()
    return _part_dict(model)


async def mark_part_retry(
    session: AsyncSession, *, job_id: uuid.UUID, part_number: int
) -> None:
    await session.execute(
        sa.update(SpecialEquipmentImportUploadPart)
        .where(
            SpecialEquipmentImportUploadPart.job_id == job_id,
            SpecialEquipmentImportUploadPart.part_number == part_number,
        )
        .values(
            attempt_count=SpecialEquipmentImportUploadPart.attempt_count + 1,
            updated_at=sa.func.now(),
        )
    )


async def list_parts(
    session: AsyncSession, *, job_id: uuid.UUID
) -> list[dict[str, Any]]:
    models = (
        (
            await session.execute(
                sa.select(SpecialEquipmentImportUploadPart)
                .where(SpecialEquipmentImportUploadPart.job_id == job_id)
                .order_by(SpecialEquipmentImportUploadPart.part_number)
            )
        )
        .scalars()
        .all()
    )
    return [_part_dict(model) for model in models]


async def replace_issues(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    issues: list[dict[str, Any]],
) -> None:
    await session.execute(
        sa.delete(SpecialEquipmentImportIssue).where(
            SpecialEquipmentImportIssue.job_id == job_id
        )
    )
    if issues:
        await session.execute(sa.insert(SpecialEquipmentImportIssue), issues)


async def append_issues(session: AsyncSession, *, issues: list[dict[str, Any]]) -> None:
    """Append apply-time aggregate conflicts after preview diagnostics."""

    if issues:
        await session.execute(sa.insert(SpecialEquipmentImportIssue), issues)


async def record_staged_media(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    storage_key: str,
    owner_kind: str,
    owner_id: uuid.UUID,
) -> None:
    """Persist uploaded media before it can be referenced by catalog rows."""
    statement = pg_insert(SpecialEquipmentImportStagedMedia).values(
        job_id=job_id,
        storage_key=storage_key,
        owner_kind=owner_kind,
        owner_id=owner_id,
        status="staged",
        cleanup_after=datetime.now(UTC) + timedelta(days=7),
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["job_id", "storage_key"],
            set_={
                "owner_kind": owner_kind,
                "owner_id": owner_id,
                "status": "staged",
                "cleanup_after": datetime.now(UTC) + timedelta(days=7),
                "deleted_at": None,
                "updated_at": sa.func.now(),
            },
        )
    )


async def mark_job_staged_media_referenced(
    session: AsyncSession, *, job_id: uuid.UUID
) -> None:
    category_reference = sa.exists(
        sa.select(SpecialEquipmentCategory.id).where(
            SpecialEquipmentCategory.image_key
            == SpecialEquipmentImportStagedMedia.storage_key
        )
    )
    product_reference = sa.exists(
        sa.select(SpecialEquipmentProductImage.id).where(
            SpecialEquipmentProductImage.storage_key
            == SpecialEquipmentImportStagedMedia.storage_key
        )
    )
    await session.execute(
        sa.update(SpecialEquipmentImportStagedMedia)
        .where(
            SpecialEquipmentImportStagedMedia.job_id == job_id,
            SpecialEquipmentImportStagedMedia.status == "staged",
            sa.or_(category_reference, product_reference),
        )
        .values(
            status="referenced",
            referenced_at=sa.func.now(),
            updated_at=sa.func.now(),
        )
    )


async def list_staged_media_cleanup_candidates(
    session: AsyncSession, *, limit: int = 200
) -> list[dict[str, Any]]:
    cleanup_job_statuses = (
        "validation_failed",
        "preview_stale",
        "completed",
        "completed_with_warnings",
        "failed",
        "cancelled",
    )
    rows = (
        (
            await session.execute(
                sa.select(SpecialEquipmentImportStagedMedia)
                .join(
                    SpecialEquipmentImportJob,
                    SpecialEquipmentImportJob.id
                    == SpecialEquipmentImportStagedMedia.job_id,
                )
                .where(
                    SpecialEquipmentImportStagedMedia.status == "staged",
                    SpecialEquipmentImportStagedMedia.cleanup_after <= sa.func.now(),
                    SpecialEquipmentImportJob.status.in_(cleanup_job_statuses),
                )
                .order_by(
                    SpecialEquipmentImportStagedMedia.cleanup_after,
                    SpecialEquipmentImportStagedMedia.job_id,
                    SpecialEquipmentImportStagedMedia.storage_key,
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "job_id": row.job_id,
            "storage_key": row.storage_key,
        }
        for row in rows
    ]


async def is_staged_media_referenced(
    session: AsyncSession, *, storage_key: str
) -> bool:
    category_reference = sa.exists(
        sa.select(SpecialEquipmentCategory.id).where(
            SpecialEquipmentCategory.image_key == storage_key
        )
    )
    product_reference = sa.exists(
        sa.select(SpecialEquipmentProductImage.id).where(
            SpecialEquipmentProductImage.storage_key == storage_key
        )
    )
    return bool(
        await session.scalar(sa.select(sa.or_(category_reference, product_reference)))
    )


async def has_protected_staged_media(
    session: AsyncSession, *, storage_key: str
) -> bool:
    active_job_statuses = (
        "awaiting_upload",
        "uploaded",
        "validating_file",
        "validating_data",
        "transferring_images",
        "preview_ready",
        "applying",
        "failed_retryable",
    )
    protected = sa.exists(
        sa.select(SpecialEquipmentImportStagedMedia.job_id)
        .join(
            SpecialEquipmentImportJob,
            SpecialEquipmentImportJob.id == SpecialEquipmentImportStagedMedia.job_id,
        )
        .where(
            SpecialEquipmentImportStagedMedia.storage_key == storage_key,
            SpecialEquipmentImportStagedMedia.status == "staged",
            sa.or_(
                SpecialEquipmentImportStagedMedia.cleanup_after > sa.func.now(),
                SpecialEquipmentImportJob.status.in_(active_job_statuses),
            ),
        )
    )
    return bool(await session.scalar(sa.select(protected)))


async def mark_staged_media_status(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    storage_key: str,
    status: str,
) -> None:
    values: dict[str, Any] = {
        "status": status,
        "updated_at": sa.func.now(),
    }
    if status == "referenced":
        values["referenced_at"] = sa.func.now()
    if status == "deleted":
        values["deleted_at"] = sa.func.now()
    await session.execute(
        sa.update(SpecialEquipmentImportStagedMedia)
        .where(
            SpecialEquipmentImportStagedMedia.job_id == job_id,
            SpecialEquipmentImportStagedMedia.storage_key == storage_key,
            SpecialEquipmentImportStagedMedia.status == "staged",
        )
        .values(**values)
    )


async def list_issues(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    severity: str | None,
    sheet_code: str | None,
    after_sequence: int,
    limit: int,
) -> list[dict[str, Any]]:
    query = sa.select(SpecialEquipmentImportIssue).where(
        SpecialEquipmentImportIssue.job_id == job_id,
        SpecialEquipmentImportIssue.sequence > after_sequence,
    )
    if severity:
        query = query.where(SpecialEquipmentImportIssue.severity == severity)
    if sheet_code:
        query = query.where(SpecialEquipmentImportIssue.sheet_code == sheet_code)
    models = (
        (
            await session.execute(
                query.order_by(SpecialEquipmentImportIssue.sequence).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [_issue_dict(model) for model in models]


async def get_catalog_revision(
    session: AsyncSession, *, for_update: bool = False
) -> int:
    query = sa.select(SpecialEquipmentCatalogState).where(
        SpecialEquipmentCatalogState.singleton.is_(True)
    )
    if for_update:
        query = query.with_for_update()
    state = (await session.execute(query)).scalar_one()
    return int(state.revision)


async def increment_catalog_revision(
    session: AsyncSession, *, updated_by: uuid.UUID
) -> int:
    revision = (
        await session.execute(
            sa.update(SpecialEquipmentCatalogState)
            .where(SpecialEquipmentCatalogState.singleton.is_(True))
            .values(
                revision=SpecialEquipmentCatalogState.revision + 1,
                updated_at=sa.func.now(),
                updated_by=updated_by,
            )
            .returning(SpecialEquipmentCatalogState.revision)
        )
    ).scalar_one()
    return int(revision)


async def lock_expected_product_versions(
    session: AsyncSession,
    expected: dict[uuid.UUID, int],
) -> bool:
    """Lock affected existing products in UUID order and compare preview tokens."""
    if not expected:
        return True
    ids = sa.bindparam(
        "expected_product_version_ids",
        value=sorted(expected, key=str),
        type_=ARRAY(PGUUID(as_uuid=True)),
    )
    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentProduct.id,
                SpecialEquipmentProduct.lock_version,
            )
            .where(SpecialEquipmentProduct.id == sa.any_(ids))
            .order_by(SpecialEquipmentProduct.id)
            .with_for_update()
        )
    ).all()
    actual = {row.id: int(row.lock_version) for row in rows}
    return actual == expected


async def lock_active_seller_companies(
    session: AsyncSession,
    company_ids: set[uuid.UUID],
) -> bool:
    """Lock and verify the artifact-bound active seller set in UUID order."""
    if not company_ids:
        return True
    ids = sa.bindparam(
        "expected_active_seller_ids",
        value=sorted(company_ids, key=str),
        type_=ARRAY(PGUUID(as_uuid=True)),
    )
    rows = (
        await session.execute(
            sa.select(Company.id)
            .where(
                Company.id == sa.any_(ids),
                Company.is_active.is_(True),
            )
            .order_by(Company.id)
            .with_for_update(read=True)
        )
    ).scalars()
    return set(rows) == company_ids


async def list_recoverable_jobs(
    session: AsyncSession, *, limit: int = 100
) -> list[dict[str, Any]]:
    models = (
        (
            await session.execute(
                sa.select(SpecialEquipmentImportJob)
                .where(
                    SpecialEquipmentImportJob.status.in_(
                        (
                            "uploaded",
                            "validating_file",
                            "validating_data",
                            "transferring_images",
                            "failed_retryable",
                            "applying",
                        )
                    ),
                    sa.or_(
                        SpecialEquipmentImportJob.lease_until.is_(None),
                        SpecialEquipmentImportJob.lease_until < sa.func.now(),
                    ),
                )
                .order_by(SpecialEquipmentImportJob.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    return [_job_dict(model) for model in models]


async def claim_expired_artifact_cleanup_jobs(
    session: AsyncSession,
    *,
    now: datetime,
    lease_owner: str,
    lease_until: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    """Claim one bounded page of expired terminal-job artifacts.

    ``FOR UPDATE SKIP LOCKED`` allows multiple schedulers to coexist, while the
    dedicated owner token prevents a stale worker from overwriting a newer
    claim after its lease expired.
    """
    candidates = (
        sa.select(SpecialEquipmentImportJob.id)
        .where(
            SpecialEquipmentImportJob.status.in_(_TERMINAL_IMPORT_STATUS_VALUES),
            SpecialEquipmentImportJob.retain_until.is_not(None),
            SpecialEquipmentImportJob.retain_until <= now,
            sa.or_(
                SpecialEquipmentImportJob.artifact_cleanup_status == "pending",
                sa.and_(
                    SpecialEquipmentImportJob.artifact_cleanup_status == "processing",
                    sa.or_(
                        SpecialEquipmentImportJob.artifact_cleanup_lease_until.is_(
                            None
                        ),
                        SpecialEquipmentImportJob.artifact_cleanup_lease_until < now,
                    ),
                ),
            ),
        )
        .order_by(
            SpecialEquipmentImportJob.retain_until,
            SpecialEquipmentImportJob.id,
        )
        .limit(max(1, limit))
        .with_for_update(skip_locked=True)
        .cte("special_equipment_artifact_cleanup_candidates")
    )
    result = await session.execute(
        sa.update(SpecialEquipmentImportJob)
        .where(SpecialEquipmentImportJob.id.in_(sa.select(candidates.c.id)))
        .values(
            artifact_cleanup_status="processing",
            artifact_cleanup_lease_owner=lease_owner,
            artifact_cleanup_lease_until=lease_until,
            artifact_cleanup_attempt_count=(
                SpecialEquipmentImportJob.artifact_cleanup_attempt_count + 1
            ),
            artifact_cleanup_last_error=None,
            updated_at=now,
        )
        .returning(*SpecialEquipmentImportJob.__table__.columns)
        .execution_options(synchronize_session=False)
    )
    rows = [dict(row) for row in result.mappings().all()]
    rows.sort(key=lambda row: (row["retain_until"], str(row["id"])))
    return rows


async def complete_artifact_cleanup(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    lease_owner: str,
    cleaned_at: datetime,
) -> None:
    await session.execute(
        sa.update(SpecialEquipmentImportJob)
        .where(
            SpecialEquipmentImportJob.id == job_id,
            SpecialEquipmentImportJob.artifact_cleanup_status == "processing",
            SpecialEquipmentImportJob.artifact_cleanup_lease_owner == lease_owner,
        )
        .values(
            artifact_cleanup_status="completed",
            artifact_cleanup_lease_owner=None,
            artifact_cleanup_lease_until=None,
            artifact_cleanup_last_error=None,
            artifacts_cleaned_at=cleaned_at,
            updated_at=cleaned_at,
        )
    )


async def fail_artifact_cleanup(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    lease_owner: str,
    error: str,
    failed_at: datetime,
) -> None:
    await session.execute(
        sa.update(SpecialEquipmentImportJob)
        .where(
            SpecialEquipmentImportJob.id == job_id,
            SpecialEquipmentImportJob.artifact_cleanup_status == "processing",
            SpecialEquipmentImportJob.artifact_cleanup_lease_owner == lease_owner,
        )
        .values(
            artifact_cleanup_status="pending",
            artifact_cleanup_lease_owner=None,
            artifact_cleanup_lease_until=None,
            artifact_cleanup_last_error=error[:1000],
            updated_at=failed_at,
        )
    )


_APPLY_BATCH_SIZE = 1_000
V2AggregateSemanticConflictError = ImportAggregateSemanticConflictError


def _batches(values: Any, size: int = _APPLY_BATCH_SIZE) -> Any:
    batch: list[Any] = []
    for value in values:
        batch.append(value)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


# ---------------------------------------------------------------------------
# Corrected catalog import v2
# ---------------------------------------------------------------------------


class ImportTargetWarehouseUnavailableError(Exception):
    """The selected import target disappeared before the job insert."""


def _is_target_warehouse_integrity_error(exc: IntegrityError) -> bool:
    original = exc.orig
    diagnostic = getattr(original, "diag", None)
    constraint_name = getattr(original, "constraint_name", None) or getattr(
        diagnostic, "constraint_name", None
    )
    return (
        getattr(original, "sqlstate", None) == "23503"
        and constraint_name == "fk_se_import_jobs_target_warehouse"
    )


async def get_v2_import_context(  # noqa: PLR0912, PLR0915 -- consistent snapshot
    session: AsyncSession,
    *,
    requested_codes: dict[str, set[str]],
    seller_inns: set[str],
    target_warehouse_id: uuid.UUID | None = None,
    mode: ImportMode | str | None = None,
) -> dict[str, Any]:
    """Load code-addressable validation state without external-ref identity."""

    context: dict[str, Any] = {}
    model_by_family: dict[str, Any] = {
        "units": SpecialEquipmentUnit,
        "marks": SpecialEquipmentMark,
        "models": SpecialEquipmentModel,
        "modifications": SpecialEquipmentModification,
        "superstructures": SpecialEquipmentSuperstructure,
        "colors": SpecialEquipmentColor,
        "categories": SpecialEquipmentCategory,
        "attribute_groups": SpecialEquipmentAttributeGroup,
        "attributes": SpecialEquipmentAttribute,
        "products": SpecialEquipmentProduct,
    }
    for family, model in model_by_family.items():
        codes = requested_codes.get(f"{family}_codes", set())
        # The graph validator requires every category and the full replacement
        # locks every product. Other directories remain request-bounded.
        query = sa.select(model)
        if (
            family
            not in {
                "categories",
                "products",
                "modifications",
                "colors",
                "superstructures",
            }
            and codes
        ):
            query = query.where(model.code.in_(sorted(codes)))
        elif (
            family
            not in {
                "categories",
                "products",
                "modifications",
                "colors",
                "superstructures",
            }
            and not codes
        ):
            context[family] = {}
            continue
        if (
            family == "products"
            and mode in ("FULL_SNAPSHOT", ImportMode.FULL_SNAPSHOT)
            and target_warehouse_id is not None
        ):
            # Exclude products of target_warehouse_id so incoming rows for the replaced warehouse are treated as clean additions without conflicting with old IDs or status constraints
            query = query.where(
                SpecialEquipmentProduct.warehouse_id != target_warehouse_id
            )
        records = (await session.execute(query)).scalars().all()
        context[family] = {
            str(record.code): _v2_model_dict(record) for record in records
        }

    requested_group_ids = {
        uuid.UUID(str(record["id"]))
        for record in context.get("attribute_groups", {}).values()
    }
    if requested_group_ids:
        grouped_attributes = (
            (
                await session.execute(
                    sa.select(SpecialEquipmentAttribute).where(
                        SpecialEquipmentAttribute.attribute_group_id.in_(
                            requested_group_ids
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        context["attributes"].update(
            {
                str(attribute.code): _v2_model_dict(attribute)
                for attribute in grouped_attributes
            }
        )

    trim_rows = (
        await session.execute(
            sa.select(SpecialEquipmentTrim, SpecialEquipmentModification.code)
            .join(
                SpecialEquipmentModification,
                SpecialEquipmentModification.id == SpecialEquipmentTrim.modification_id,
            )
            .order_by(
                SpecialEquipmentModification.code,
                SpecialEquipmentTrim.code,
            )
        )
    ).all()
    context["trims"] = {
        f"{modification_code}:{trim.code}": _v2_model_dict(trim)
        for trim, modification_code in trim_rows
    }

    modification_model_ids = {
        uuid.UUID(str(record["model_id"]))
        for record in context["modifications"].values()
    }
    superstructure_model_ids = {
        uuid.UUID(str(record["model_id"]))
        for record in context.get("superstructures", {}).values()
        if record.get("model_id") is not None
    }
    combined_model_ids = (modification_model_ids | superstructure_model_ids) - {
        uuid.UUID(str(m["id"])) for m in context["models"].values()
    }
    if combined_model_ids:
        models = (
            (
                await session.execute(
                    sa.select(SpecialEquipmentModel).where(
                        SpecialEquipmentModel.id.in_(combined_model_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        context["models"].update(
            {str(model.code): _v2_model_dict(model) for model in models}
        )
    superstructure_mod_ids = {
        uuid.UUID(str(record["modification_id"]))
        for record in context.get("superstructures", {}).values()
        if record.get("modification_id") is not None
    } - {uuid.UUID(str(m["id"])) for m in context["modifications"].values()}
    if superstructure_mod_ids:
        mods = (
            (
                await session.execute(
                    sa.select(SpecialEquipmentModification).where(
                        SpecialEquipmentModification.id.in_(superstructure_mod_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        context["modifications"].update(
            {str(m.code): _v2_model_dict(m) for m in mods}
        )
    model_mark_ids = {
        uuid.UUID(str(record["mark_id"])) for record in context["models"].values()
    }
    if model_mark_ids:
        marks = (
            (
                await session.execute(
                    sa.select(SpecialEquipmentMark).where(
                        SpecialEquipmentMark.id.in_(model_mark_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        context["marks"].update(
            {str(mark.code): _v2_model_dict(mark) for mark in marks}
        )

    attribute_codes = requested_codes.get("attributes_codes", set())
    option_query = (
        sa.select(SpecialEquipmentAttributeOption, SpecialEquipmentAttribute.code)
        .join(
            SpecialEquipmentAttribute,
            SpecialEquipmentAttribute.id
            == SpecialEquipmentAttributeOption.attribute_id,
        )
        .order_by(
            SpecialEquipmentAttribute.code,
            SpecialEquipmentAttributeOption.code,
        )
    )
    if attribute_codes:
        option_query = option_query.where(
            SpecialEquipmentAttribute.code.in_(sorted(attribute_codes))
        )
    else:
        option_query = option_query.where(sa.false())
    option_rows = (await session.execute(option_query)).all()
    context["attribute_options"] = {
        f"{attribute_code}:{option.code}": {
            **_v2_model_dict(option),
        }
        for option, attribute_code in option_rows
    }

    context["category_relations"] = set(
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentCategoryRelation.parent_id,
                    SpecialEquipmentCategoryRelation.child_id,
                )
            )
        ).all()
    )
    modification_category_rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationCategory.modification_id,
                SpecialEquipmentModificationCategory.category_id,
                SpecialEquipmentModificationCategory.sort_order,
                SpecialEquipmentModificationCategory.is_primary,
            )
        )
    ).all()
    context["modification_categories"] = {
        (row.modification_id, row.category_id) for row in modification_category_rows
    }
    modification_category_details: dict[uuid.UUID, dict[uuid.UUID, dict[str, Any]]] = {}
    for row in modification_category_rows:
        modification_category_details.setdefault(row.modification_id, {})[
            row.category_id
        ] = {
            "sort_order": int(row.sort_order),
            "is_primary": bool(row.is_primary),
        }
    context["_modification_category_details"] = modification_category_details
    context["product_categories"] = set(
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentProductCategory.product_id,
                    SpecialEquipmentProductCategory.category_id,
                )
            )
        ).all()
    )
    product_attachment_rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductAttachment.product_id,
                SpecialEquipmentProductAttachment.attachment_product_id,
                SpecialEquipmentProductAttachment.position,
            )
        )
    ).all()
    context["product_attachments"] = {
        (row.product_id, row.attachment_product_id) for row in product_attachment_rows
    }
    context["_product_attachment_details"] = {
        (row.product_id, row.attachment_product_id): {
            "position": int(row.position),
        }
        for row in product_attachment_rows
    }
    context["product_components"] = set()
    context["_product_component_details"] = {}
    context["_composite_product_ids"] = set()
    category_attribute_rows = (
        (await session.execute(sa.select(SpecialEquipmentCategoryAttribute)))
        .scalars()
        .all()
    )
    context["category_attributes"] = {
        (row.category_id, row.attribute_id): _v2_model_dict(row)
        for row in category_attribute_rows
    }
    superstructure_attribute_rows = (
        (await session.execute(sa.select(SpecialEquipmentSuperstructureAttribute)))
        .scalars()
        .all()
    )
    context["superstructure_attributes"] = {
        (row.superstructure_id, row.attribute_id): _v2_model_dict(row)
        for row in superstructure_attribute_rows
    }
    superstructure_category_rows = (
        (await session.execute(sa.select(SpecialEquipmentSuperstructureCategory)))
        .scalars()
        .all()
    )
    context["superstructure_categories"] = {
        (row.superstructure_id, row.category_id): _v2_model_dict(row)
        for row in superstructure_category_rows
    }
    modification_value_rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationAttributeValue.modification_id,
                SpecialEquipmentModificationAttributeValue.attribute_id,
                SpecialEquipmentModificationAttributeValue.option_id,
            )
        )
    ).all()
    context["modification_attribute_values"] = {
        (row.modification_id, row.attribute_id) for row in modification_value_rows
    }
    context["_modification_attribute_value_details"] = {
        (row.modification_id, row.attribute_id): {"option_id": row.option_id}
        for row in modification_value_rows
    }
    trim_attribute_rows = (
        (await session.execute(sa.select(SpecialEquipmentTrimAttribute)))
        .scalars()
        .all()
    )
    context["trim_attributes"] = {
        (row.trim_id, row.attribute_id): _v2_model_dict(row)
        for row in trim_attribute_rows
    }
    trim_value_rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentTrimAttributeValue.trim_id,
                SpecialEquipmentTrimAttributeValue.attribute_id,
                SpecialEquipmentTrimAttributeValue.option_id,
            )
        )
    ).all()
    context["trim_attribute_values"] = {
        (row.trim_id, row.attribute_id) for row in trim_value_rows
    }
    context["_trim_attribute_value_details"] = {
        (row.trim_id, row.attribute_id): {"option_id": row.option_id}
        for row in trim_value_rows
    }
    color_product_references: dict[uuid.UUID, dict[str, int]] = {}
    for product in context["products"].values():
        for reference, field in (
            ("body", "body_color_id"),
            ("interior", "interior_color_id"),
        ):
            raw_color_id = product.get(field)
            if raw_color_id is None:
                continue
            color_id = uuid.UUID(str(raw_color_id))
            color_product_references.setdefault(
                color_id,
                {"body": 0, "interior": 0},
            )[reference] += 1
    context["_color_product_references"] = color_product_references
    superstructure_usage_counts: dict[uuid.UUID, int] = defaultdict(int)
    for product in context["products"].values():
        raw_superstructure_id = product.get("superstructure_id")
        if raw_superstructure_id is not None:
            superstructure_usage_counts[uuid.UUID(str(raw_superstructure_id))] += 1
    context["superstructure_usage_counts"] = dict(superstructure_usage_counts)
    company_query = sa.select(Company)
    if seller_inns:
        company_query = company_query.where(Company.inn.in_(sorted(seller_inns)))
    else:
        company_query = company_query.where(sa.false())
    companies = (await session.execute(company_query)).scalars().all()
    context["companies"] = {
        str(company.inn): {
            "id": company.id,
            "is_active": bool(company.is_active),
        }
        for company in companies
    }
    warehouse_ids: set[uuid.UUID] = {
        uuid.UUID(str(record["warehouse_id"]))
        for record in context["products"].values()
        if record.get("warehouse_id") is not None
    }
    for raw_warehouse_id in requested_codes.get("warehouse_ids", set()):
        try:
            warehouse_ids.add(uuid.UUID(str(raw_warehouse_id)))
        except ValueError:
            continue
    if target_warehouse_id is not None:
        warehouse_ids.add(target_warehouse_id)
    warehouses = (
        (
            await session.execute(
                sa.select(Warehouse).where(Warehouse.id.in_(warehouse_ids))
            )
        )
        .scalars()
        .all()
        if warehouse_ids
        else []
    )
    context["warehouses"] = {
        str(warehouse.id): {
            "id": warehouse.id,
            "company_id": warehouse.company_id,
            "dealer_id": warehouse.dealer_id,
            "status": warehouse.status,
        }
        for warehouse in warehouses
    }
    product_ids = {
        uuid.UUID(str(record["id"]))
        for record in context.get("products", {}).values()
    }
    product_images_by_product: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if product_ids:
        product_image_rows = (
            await session.execute(
                sa.select(SpecialEquipmentProductImage)
                .where(SpecialEquipmentProductImage.product_id.in_(product_ids))
                .order_by(
                    SpecialEquipmentProductImage.product_id,
                    SpecialEquipmentProductImage.sort_order,
                )
            )
        ).scalars().all()
        for img in product_image_rows:
            product_images_by_product.setdefault(img.product_id, []).append(
                {
                    "id": img.id,
                    "storage_key": img.storage_key,
                    "source_ref": img.source_ref,
                    "sort_order": img.sort_order,
                    "is_primary": img.is_primary,
                }
            )
    context["product_images"] = product_images_by_product
    return context



def _v2_model_dict(model: Any) -> dict[str, Any]:
    return {
        column.name: getattr(model, column.name) for column in model.__table__.columns
    }


async def cascade_purge_warehouse_products(
    session: AsyncSession, warehouse_id: uuid.UUID
) -> int:
    """Cascade purge all products belonging to a warehouse in safe topological order."""
    product_ids = set(
        (
            await session.execute(
                sa.select(SpecialEquipmentProduct.id)
                .where(SpecialEquipmentProduct.warehouse_id == warehouse_id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if not product_ids:
        return 0

    # a. Applications:
    app_item_ids = set(
        (
            await session.execute(
                sa.select(SpecialEquipmentApplicationItem.id).where(
                    SpecialEquipmentApplicationItem.product_id.in_(product_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    if app_item_ids:
        await session.execute(
            sa.delete(SpecialEquipmentPriceChangeLog).where(
                SpecialEquipmentPriceChangeLog.item_id.in_(app_item_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentApplicationItem).where(
                SpecialEquipmentApplicationItem.id.in_(app_item_ids)
            )
        )
    await session.execute(
        sa.delete(ApplicationVehicleAllocation).where(
            ApplicationVehicleAllocation.product_id.in_(product_ids)
        )
    )
    await session.execute(
        sa.update(ApplicationVehicle)
        .where(ApplicationVehicle.product_id.in_(product_ids))
        .values(product_id=None)
    )

    # b. Orders & Payments:
    # Special equipment purchase orders:
    se_order_ids = set(
        (
            await session.execute(
                sa.select(SpecialEquipmentPurchaseOrder.id).where(
                    SpecialEquipmentPurchaseOrder.product_id.in_(product_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    if se_order_ids:
        await session.execute(
            sa.delete(SpecialEquipmentLeasingPaymentSchedule).where(
                SpecialEquipmentLeasingPaymentSchedule.purchase_order_id.in_(se_order_ids)
            )
        )
        se_payment_ids = set(
            (
                await session.execute(
                    sa.select(SpecialEquipmentPayment.id).where(
                        SpecialEquipmentPayment.purchase_order_id.in_(se_order_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        if se_payment_ids:
            await session.execute(
                sa.update(SpecialEquipmentPaymentCallbackInbox)
                .where(
                    SpecialEquipmentPaymentCallbackInbox.payment_id.in_(se_payment_ids)
                )
                .values(payment_id=None)
            )
            await session.execute(
                sa.delete(SpecialEquipmentPayment).where(
                    SpecialEquipmentPayment.id.in_(se_payment_ids)
                )
            )
        await session.execute(
            sa.delete(SpecialEquipmentOrderItem).where(
                sa.or_(
                    SpecialEquipmentOrderItem.purchase_order_id.in_(se_order_ids),
                    SpecialEquipmentOrderItem.product_id.in_(product_ids),
                )
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentPurchaseOrder).where(
                SpecialEquipmentPurchaseOrder.id.in_(se_order_ids)
            )
        )
    await session.execute(
        sa.delete(SpecialEquipmentOrderItem).where(
            SpecialEquipmentOrderItem.product_id.in_(product_ids)
        )
    )

    # Legacy purchase orders:
    po_ids = set(
        (
            await session.execute(
                sa.select(PurchaseOrder.id).where(
                    PurchaseOrder.product_id.in_(product_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    if po_ids:
        await session.execute(
            sa.delete(LeasingPaymentSchedule).where(
                LeasingPaymentSchedule.purchase_order_id.in_(po_ids)
            )
        )
        await session.execute(
            sa.delete(Payment).where(Payment.purchase_order_id.in_(po_ids))
        )
        await session.execute(
            sa.delete(PurchaseOrder).where(PurchaseOrder.id.in_(po_ids))
        )

    # c. Carts:
    # Special equipment carts:
    cart_item_ids = set(
        (
            await session.execute(
                sa.select(SpecialEquipmentCartItem.id).where(
                    SpecialEquipmentCartItem.product_id.in_(product_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    if cart_item_ids:
        await session.execute(
            sa.update(SpecialEquipmentCartItem)
            .where(SpecialEquipmentCartItem.parent_item_id.in_(cart_item_ids))
            .values(parent_item_id=None)
        )
        await session.execute(
            sa.delete(SpecialEquipmentCartItem).where(
                SpecialEquipmentCartItem.id.in_(cart_item_ids)
            )
        )
    await session.execute(
        sa.delete(SpecialEquipmentCartItem).where(
            SpecialEquipmentCartItem.product_id.in_(product_ids)
        )
    )
    # Exchange carts:
    await session.execute(
        sa.delete(ExchangeCartItem).where(
            ExchangeCartItem.product_id.in_(product_ids)
        )
    )

    # d. Exchange requests:
    ex_req_ids = set(
        (
            await session.execute(
                sa.select(ExchangeRequest.id).where(
                    ExchangeRequest.product_id.in_(product_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    if ex_req_ids:
        await session.execute(
            sa.update(ExchangeRequest)
            .where(ExchangeRequest.id.in_(ex_req_ids))
            .values(accepted_bid_id=None)
        )
        await session.execute(
            sa.delete(ExchangeRequest).where(ExchangeRequest.id.in_(ex_req_ids))
        )

    # e. Favorites:
    await session.execute(
        sa.delete(SpecialEquipmentFavorite).where(
            SpecialEquipmentFavorite.product_id.in_(product_ids)
        )
    )
    await session.execute(
        sa.delete(UserFavorite).where(UserFavorite.product_id.in_(product_ids))
    )

    # f. Attachments & Components:
    await session.execute(
        sa.delete(SpecialEquipmentProductAttachment).where(
            sa.or_(
                SpecialEquipmentProductAttachment.product_id.in_(product_ids),
                SpecialEquipmentProductAttachment.attachment_product_id.in_(
                    product_ids
                ),
            )
        )
    )

    # g. Categories, Images, Transfers:
    await session.execute(
        sa.delete(SpecialEquipmentProductCategory).where(
            SpecialEquipmentProductCategory.product_id.in_(product_ids)
        )
    )
    await session.execute(
        sa.delete(SpecialEquipmentProductImage).where(
            SpecialEquipmentProductImage.product_id.in_(product_ids)
        )
    )
    await session.execute(
        sa.delete(VehicleWarehouseTransfer).where(
            VehicleWarehouseTransfer.product_id.in_(product_ids)
        )
    )

    # h. Finally:
    await session.execute(
        sa.delete(SpecialEquipmentProduct).where(
            SpecialEquipmentProduct.id.in_(product_ids)
        )
    )
    return len(product_ids)


async def lock_import_archive_targets(  # type: ignore[no-redef]
    session: AsyncSession,
    *,
    source_code: str | None = None,
    mode: str,
    plan: dict[str, Any],
    target_warehouse_id: uuid.UUID | None = None,
) -> bool:
    """Lock products that the import will archive logically."""

    del source_code
    explicit_delete_ids = {
        uuid.UUID(str(row["id"]))
        for row in plan.get("products", ())
        if row.get("operation") == "DELETE"
    }
    delete_ids = set(explicit_delete_ids)
    if mode == "FULL_SNAPSHOT":
        included = {
            uuid.UUID(str(row["id"]))
            for row in plan.get("products", ())
            if row.get("operation") != "DELETE"
        }
        if target_warehouse_id is not None:
            warehouse_filter = SpecialEquipmentProduct.warehouse_id == target_warehouse_id
            target_query = sa.select(SpecialEquipmentProduct.id).where(warehouse_filter)
            delete_ids.update(
                set((await session.execute(target_query)).scalars()) - included
            )
        else:
            delete_ids.update(
                set(
                    (await session.execute(sa.select(SpecialEquipmentProduct.id))).scalars()
                )
                - included
            )
    if not delete_ids:
        return True
    ids = _uuid_array("v2_archive_target_ids", delete_ids)
    locked_ids = set(
        (
            await session.execute(
                sa.select(SpecialEquipmentProduct.id)
                .where(SpecialEquipmentProduct.id == sa.any_(ids))
                .order_by(SpecialEquipmentProduct.id)
                .with_for_update()
            )
        ).scalars()
    )
    return locked_ids == delete_ids


def extract_dbapi_diagnostic(exc: Exception) -> dict[str, str | None]:
    original = getattr(exc, "orig", exc)
    diag = getattr(original, "diag", None)
    cause = getattr(original, "__cause__", None)
    cause_diag = getattr(cause, "diag", None)

    sqlstate = (
        getattr(original, "sqlstate", None)
        or getattr(diag, "sqlstate", None)
        or getattr(cause, "sqlstate", None)
        or getattr(cause_diag, "sqlstate", None)
    )
    constraint_name = (
        getattr(original, "constraint_name", None)
        or getattr(diag, "constraint_name", None)
        or getattr(cause, "constraint_name", None)
        or getattr(cause_diag, "constraint_name", None)
    )
    column_name = (
        getattr(original, "column_name", None)
        or getattr(diag, "column_name", None)
        or getattr(cause, "column_name", None)
        or getattr(cause_diag, "column_name", None)
    )
    table_name = (
        getattr(original, "table_name", None)
        or getattr(diag, "table_name", None)
        or getattr(cause, "table_name", None)
        or getattr(cause_diag, "table_name", None)
    )

    err_str = f"{exc} {original} {cause}"
    if not sqlstate:
        match_sqlstate = re.search(r"\b(23502|23505|23503|23514)\b", err_str)
        if match_sqlstate:
            sqlstate = match_sqlstate.group(1)
    if not constraint_name:
        match_constraint = re.search(r'constraint ["\']([^"\']+)["\']', err_str)
        if match_constraint:
            constraint_name = match_constraint.group(1)
    if not column_name:
        match_col = re.search(r'column ["\']([^"\']+)["\']', err_str)
        if match_col:
            column_name = match_col.group(1)
    if not table_name:
        match_table = re.search(r'(?:table|relation) ["\']([^"\']+)["\']', err_str)
        if match_table:
            table_name = match_table.group(1)

    return {
        "sqlstate": str(sqlstate) if sqlstate else None,
        "constraint_name": str(constraint_name) if constraint_name else None,
        "column_name": str(column_name) if column_name else None,
        "table_name": str(table_name) if table_name else None,
    }


def _translate_kind_label(kind: str) -> str:
    return {
        "unit": "единица измерения",
        "category": "категория",
        "mark": "марка",
        "model": "модель",
        "modification": "модификация",
        "trim": "комплектация",
        "attribute_group": "группа характеристик",
        "attribute": "характеристика",
        "attribute_option": "вариант характеристики",
        "superstructure": "тип надстройки",
        "color": "цвет",
        "product": "объявление",
    }.get(kind, kind)


_UNIQUE_CONSTRAINT_MESSAGES: dict[str, str] = {
    "uq_special_equipment_categories_slug": (
        "Категория с таким названием уже существует с другим кодом"
    ),
    "uq_special_equipment_marks_slug": (
        "Марка с таким названием уже существует с другим кодом"
    ),
    "uq_special_equipment_models_slug": (
        "Модель с таким названием уже существует с другим кодом"
    ),
    "uq_special_equipment_modifications_slug": (
        "Модификация с таким названием уже существует с другим кодом"
    ),
    "uq_special_equipment_attribute_groups_slug": (
        "Группа характеристик с таким названием уже существует с другим кодом"
    ),
    "uq_special_equipment_products_vin": "Объявление с таким VIN уже существует",
}


def _v2_integrity_issue(  # noqa: PLR0911
    exc: IntegrityError,
    *,
    family: str | None = None,
) -> tuple[str, str, str | None]:
    diag = extract_dbapi_diagnostic(exc)
    sqlstate = diag.get("sqlstate")
    constraint = diag.get("constraint_name")
    col = diag.get("column_name")

    if sqlstate == "23502":
        col_title = (
            special_equipment_column_title(family, col)
            if (family and col)
            else col
        )
        if col_title:
            return (
                "REQUIRED_FIELD_MISSING",
                f"Не заполнено обязательное поле «{col_title}»",
                col_title,
            )
        return "REQUIRED_FIELD_MISSING", "Не заполнено обязательное поле", None

    if sqlstate == "23505":
        if constraint in _UNIQUE_CONSTRAINT_MESSAGES:
            return "UNIQUE_CONFLICT", _UNIQUE_CONSTRAINT_MESSAGES[constraint], None
        if constraint:
            return (
                "UNIQUE_CONFLICT",
                f"Значение уже используется другой записью ({constraint})",
                None,
            )
        return "UNIQUE_CONFLICT", "Значение уже используется другой записью", None

    if sqlstate == "23503":
        return (
            "DEPENDENCY_NOT_APPLIED",
            "Связанная запись не создана — см. ошибку по ней выше",
            None,
        )

    if sqlstate == "23514":
        if constraint:
            return "VALUE_OUT_OF_RANGE", f"Недопустимое значение ({constraint})", None
        return "VALUE_OUT_OF_RANGE", "Недопустимое значение", None

    return (
        "AGGREGATE_APPLY_CONFLICT",
        "Агрегат не применён из-за конфликта зависимостей или уникальности",
        None,
    )


async def apply_normalized_plan(  # noqa: PLR0912, PLR0915  # type: ignore[no-redef]
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    source_code: str | None = None,
    mode: str,
    plan: dict[str, Any],
    template_version: int = 4,
    target_warehouse_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Apply v4 aggregates atomically or through one SAVEPOINT per root."""

    del job_id, source_code
    import_mode = mode
    atomic = import_mode == "FULL_SNAPSHOT"
    aggregates = _v2_group_aggregates(plan)
    counts = {"created": 0, "updated": 0, "archived": 0, "removed": 0}
    rejected: list[dict[str, Any]] = []
    rejected_entity_ids: dict[uuid.UUID, tuple[str, str]] = {}
    planned_relation_owner_ids: set[uuid.UUID] = set()
    removed_relation_owner_ids: set[uuid.UUID] = set()
    if atomic:
        removed_relation_owner_ids = await _v2_delete_missing_snapshot_relations(
            session,
            plan=plan,
            counts=counts,
            include_v4_catalog=template_version >= 4,
        )
    for aggregate_key, aggregate in aggregates:
        aggregate_counts = {
            "created": 0,
            "updated": 0,
            "archived": 0,
            "removed": 0,
        }
        planned_relation_owner_ids.update(_v2_relation_owner_ids(aggregate))
        try:
            if atomic:
                aggregate_rejected = await _v2_apply_aggregate(
                    session,
                    aggregate,
                    counts=aggregate_counts,
                    snapshot=True,
                )
            else:
                async with session.begin_nested():
                    aggregate_rejected = await _v2_apply_aggregate(
                        session,
                        aggregate,
                        counts=aggregate_counts,
                    )
                    affected_product_ids = _v2_aggregate_product_ids(aggregate)
                    inherited_ids: set[uuid.UUID] = set()
                    if affected_product_ids:
                        inherited_ids = (
                            await _v2_inherit_affected_composite_classification(
                                session,
                                affected_product_ids=affected_product_ids,
                            )
                            or set()
                        )
                    await _v2_touch_products(
                        session,
                        _v2_relation_owner_ids(aggregate) - inherited_ids,
                    )
        except (IntegrityError, ImportAggregateSemanticConflictError) as exc:
            representative = next(row for rows in aggregate.values() for row in rows)
            sheet = str(representative.get("_sheet_code") or aggregate_key[0])
            row_number = representative.get("_row_number")
            aggregate_code = aggregate_key[1]
            family = representative.get("_aggregate_kind") or aggregate_key[0]

            if isinstance(exc, IntegrityError):
                code, message, col_name = _v2_integrity_issue(exc, family=family)
            else:
                code = exc.code
                message = str(exc)
                col_name = None

            if atomic:
                raise ImportAggregateSemanticConflictError(
                    f"Лист «{sheet}», строка {row_number}, код {aggregate_code}: {message}",
                    code=code,
                ) from exc

            if code == "DEPENDENCY_NOT_APPLIED":
                for f_rows in aggregate.values():
                    for f_row in f_rows:
                        for val in (f_row.get("values") or {}).values():
                            if isinstance(val, uuid.UUID) and val in rejected_entity_ids:
                                failed_kind, failed_code = rejected_entity_ids[val]
                                kind_label = _translate_kind_label(failed_kind)
                                message = (
                                    f"Не применено, так как {kind_label} "
                                    f"`{failed_code}` не загружена"
                                )
                                break
                            if isinstance(val, str):
                                try:
                                    val_uuid = uuid.UUID(val)
                                    if val_uuid in rejected_entity_ids:
                                        failed_kind, failed_code = rejected_entity_ids[val_uuid]
                                        kind_label = _translate_kind_label(failed_kind)
                                        message = (
                                            f"Не применено, так как {kind_label} "
                                            f"`{failed_code}` не загружена"
                                        )
                                        break
                                except (ValueError, TypeError):
                                    pass

            for f_name, f_rows in aggregate.items():
                if f_name in _V2_ENTITY_MODELS:
                    for f_row in f_rows:
                        if "id" in f_row:
                            rejected_entity_ids[uuid.UUID(str(f_row["id"]))] = (
                                aggregate_key[0],
                                aggregate_key[1],
                            )

            rejected.append(
                {
                    "sheet_code": str(representative.get("_sheet_code") or "Книга"),
                    "row_number": representative.get("_row_number"),
                    "column_name": col_name,
                    "severity": "error",
                    "code": code,
                    "message": message,
                    "raw_value_preview": None,
                    "entity_type": aggregate_key[0],
                    "external_key": aggregate_key[1],
                }
            )
            continue
        for _family, row, code, message in aggregate_rejected or ():
            if "id" in row and _family in _V2_ENTITY_MODELS:
                rejected_entity_ids[uuid.UUID(str(row["id"]))] = (
                    aggregate_key[0],
                    aggregate_key[1],
                )
            rejected.append(
                {
                    "sheet_code": str(row.get("_sheet_code") or "Книга"),
                    "row_number": row.get("_row_number"),
                    "column_name": None,
                    "severity": "error",
                    "code": code,
                    "message": message,
                    "raw_value_preview": None,
                    "entity_type": aggregate_key[0],
                    "external_key": aggregate_key[1],
                }
            )
        for key, value in aggregate_counts.items():
            counts[key] += value

    if atomic:
        await _v2_retire_missing_snapshot_entities(
            session,
            plan=plan,
            counts=counts,
            include_v4_catalog=template_version >= 4,
            target_warehouse_id=target_warehouse_id,
        )
        await _v2_touch_products(
            session,
            (planned_relation_owner_ids | removed_relation_owner_ids),
        )
    await session.flush()
    affected_products = {
        str(row["id"]) for row in plan.get("products", ()) if row.get("id")
    }
    affected_categories = {
        str(row["id"]) for row in plan.get("categories", ()) if row.get("id")
    }
    return {
        "counts": counts,
        "rejected_aggregates": rejected,
        "affected_product_ids": sorted(affected_products),
        "affected_category_ids": sorted(affected_categories),
    }


def _target_warehouse_product_ids(
    *, plan: Mapping[str, Any], mode: str
) -> set[uuid.UUID]:
    """Select rows for which the job warehouse is the effective fallback."""

    # An explicit XLSX v4 warehouse always wins. FULL_SNAPSHOT treats rows
    # present in the file like PATCH while leaving products absent from the
    # snapshot untouched.
    operations_by_mode = {
        "APPEND": {"ADD"},
        "PATCH": {"ADD", "SET"},
        "FULL_SNAPSHOT": {"ADD", "SET"},
    }
    return {
        uuid.UUID(str(row["id"]))
        for row in plan.get("products", ())
        if row.get("id")
        and row.get("operation") in operations_by_mode.get(mode, set())
        and not bool(row.get("values", {}).get("no_vin"))
    }


async def assign_target_warehouse(
    session: AsyncSession,
    *,
    warehouse_id: uuid.UUID | None,
    mode: str,
    plan: dict[str, Any],
) -> None:
    """Apply the immutable job target where no row warehouse was supplied."""

    if warehouse_id is None:
        return
    product_ids = _target_warehouse_product_ids(plan=plan, mode=mode)
    if not product_ids:
        return
    await session.execute(
        sa.update(SpecialEquipmentProduct)
        .where(
            SpecialEquipmentProduct.id.in_(product_ids),
            SpecialEquipmentProduct.no_vin.is_(False),
            SpecialEquipmentProduct.warehouse_id.is_distinct_from(warehouse_id),
        )
        .values(
            warehouse_id=warehouse_id,
            lock_version=SpecialEquipmentProduct.lock_version + 1,
            updated_at=sa.func.now(),
        )
    )


def _v2_group_aggregates(
    plan: dict[str, Any],
) -> list[tuple[tuple[str, str], dict[str, list[dict[str, Any]]]]]:
    grouped: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
    order: list[tuple[str, str]] = []
    priority = {
        "unit": 0,
        "mark": 1,
        "attribute_group": 2,
        "attribute": 3,
        "attribute_option": 4,
        "model": 5,
        "category": 6,
        "modification": 7,
        "trim": 8,
        "superstructure": 9,
        "color": 10,
        "product": 11,
    }
    for family, rows in plan.items():
        for row in rows:
            key = (
                str(row["_aggregate_kind"]),
                str(row["_aggregate_code"]),
            )
            if key not in grouped:
                grouped[key] = {}
                order.append(key)
            grouped[key].setdefault(family, []).append(row)
    category_code_by_id = {
        uuid.UUID(str(row["id"])): str(row["code"])
        for row in plan.get("categories", ())
        if row.get("operation") != "DELETE"
    }
    category_parents: dict[str, set[str]] = {}
    for row in plan.get("category_relations", ()):
        if row.get("operation") == "DELETE":
            continue
        parent_code = category_code_by_id.get(
            uuid.UUID(str(row["values"]["parent_id"]))
        )
        child_code = category_code_by_id.get(uuid.UUID(str(row["values"]["child_id"])))
        if parent_code is not None and child_code is not None:
            category_parents.setdefault(child_code, set()).add(parent_code)

    category_depth_cache: dict[str, int] = {}

    def category_depth(code: str) -> int:
        if code not in category_depth_cache:
            category_depth_cache[code] = 1 + max(
                (
                    category_depth(parent_code)
                    for parent_code in category_parents.get(code, ())
                ),
                default=-1,
            )
        return category_depth_cache[code]

    def product_relation_phase(key: tuple[str, str]) -> int:
        if key[0] != "product":
            return 0
        relation_rows = list(grouped[key].get("product_attachments", ()))
        if any(row["operation"] == "DELETE" for row in relation_rows):
            return 0
        if relation_rows:
            return 2
        return 1

    order.sort(
        key=lambda key: (
            priority.get(key[0], 50),
            category_depth(key[1]) if key[0] == "category" else 0,
            product_relation_phase(key),
            key[1],
        )
    )
    return [(key, grouped[key]) for key in order]


async def _trim_modification_value_state(
    session: AsyncSession,
    *,
    modification_ids: set[uuid.UUID],
    trim_ids: set[uuid.UUID],
    modification_by_trim_hint: Mapping[uuid.UUID, uuid.UUID] | None = None,
    lock: bool,
) -> TrimModificationValueState:
    """Read raw value markers, optionally locking modification -> trims."""

    modification_by_trim = dict(modification_by_trim_hint or {})
    persisted_trim_ids = trim_ids - set(modification_by_trim)
    if persisted_trim_ids:
        persisted_trim_rows = (
            await session.execute(
                sa.select(
                    SpecialEquipmentTrim.id,
                    SpecialEquipmentTrim.modification_id,
                ).where(SpecialEquipmentTrim.id.in_(persisted_trim_ids))
            )
        ).all()
        modification_by_trim.update(
            (row[0], row[1]) for row in persisted_trim_rows
        )
    modification_ids = modification_ids | set(modification_by_trim.values())
    if not modification_ids:
        return {
            "modification_by_trim": modification_by_trim,
            "trim_values": set(),
            "modification_values": set(),
        }
    if lock:
        await session.execute(
            sa.select(SpecialEquipmentModification.id)
            .where(SpecialEquipmentModification.id.in_(modification_ids))
            .order_by(SpecialEquipmentModification.id)
            .with_for_update()
        )
        await session.execute(
            sa.select(SpecialEquipmentTrim.id)
            .where(SpecialEquipmentTrim.modification_id.in_(modification_ids))
            .order_by(SpecialEquipmentTrim.id)
            .with_for_update()
        )
    trim_value_rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentTrim.id,
                SpecialEquipmentTrim.modification_id,
                SpecialEquipmentTrimAttributeValue.attribute_id,
            )
            .join(
                SpecialEquipmentTrimAttributeValue,
                SpecialEquipmentTrimAttributeValue.trim_id
                == SpecialEquipmentTrim.id,
            )
            .where(SpecialEquipmentTrim.modification_id.in_(modification_ids))
        )
    ).all()
    modification_value_rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationAttributeValue.modification_id,
                SpecialEquipmentModificationAttributeValue.attribute_id,
            ).where(
                SpecialEquipmentModificationAttributeValue.modification_id.in_(
                    modification_ids
                )
            )
        )
    ).all()
    return {
        "modification_by_trim": modification_by_trim,
        "trim_values": {
            (trim_id, modification_id, attribute_id)
            for trim_id, modification_id, attribute_id in trim_value_rows
        },
        "modification_values": {
            (modification_id, attribute_id)
            for modification_id, attribute_id in modification_value_rows
        },
    }


async def read_trim_modification_value_state(
    session: AsyncSession,
    *,
    modification_ids: set[uuid.UUID],
    trim_ids: set[uuid.UUID],
    modification_by_trim_hint: Mapping[uuid.UUID, uuid.UUID] | None = None,
) -> TrimModificationValueState:
    """Read the preview marker set from the caller's consistent snapshot."""

    return await _trim_modification_value_state(
        session,
        modification_ids=modification_ids,
        trim_ids=trim_ids,
        modification_by_trim_hint=modification_by_trim_hint,
        lock=False,
    )


async def lock_and_read_trim_modification_value_state(
    session: AsyncSession,
    *,
    modification_ids: set[uuid.UUID],
    trim_ids: set[uuid.UUID],
    modification_by_trim_hint: Mapping[uuid.UUID, uuid.UUID] | None = None,
) -> TrimModificationValueState:
    """Lock modification -> trims and return raw persisted value markers."""

    return await _trim_modification_value_state(
        session,
        modification_ids=modification_ids,
        trim_ids=trim_ids,
        modification_by_trim_hint=modification_by_trim_hint,
        lock=True,
    )


async def _v2_lock_and_validate_trim_value_invariant(
    session: AsyncSession,
    aggregate: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    error_policy: ImportErrorPolicy,
) -> list[tuple[str, Mapping[str, Any], str, str]]:
    """Apply the shared domain policy to markers read under repository locks."""

    modification_markers, trim_markers, modification_by_trim_hint = (
        trim_value_plan_scope(aggregate)
    )
    trim_ids = {trim_id for trim_id, _attribute_id in trim_markers}
    state = await lock_and_read_trim_modification_value_state(
        session,
        modification_ids={marker[0] for marker in modification_markers},
        trim_ids=trim_ids,
        modification_by_trim_hint=modification_by_trim_hint,
    )
    incoming_trim_markers = {
        (state["modification_by_trim"][trim_id], attribute_id)
        for trim_id, attribute_id in trim_markers
        if trim_id in state["modification_by_trim"]
    }
    persisted_trim_markers = {
        (modification_id, attribute_id)
        for _trim_id, modification_id, attribute_id in state["trim_values"]
    }
    persisted_modification_markers = state["modification_values"]
    conflicts = apply_trim_value_import_policy(
        trim_modification_value_conflicts(
            incoming_modification_values=modification_markers,
            incoming_trim_values=incoming_trim_markers,
            persisted_modification_values=persisted_modification_markers,
            persisted_trim_values=persisted_trim_markers,
        ),
        error_policy=error_policy,
    )
    rejected: list[tuple[str, Mapping[str, Any], str, str]] = []
    for conflict in conflicts:
        family = (
            "modification_attribute_values"
            if conflict.write_level == "modification"
            else "trim_attribute_values"
        )
        for row in aggregate.get(family, ()):
            if row["operation"] == "DELETE":
                continue
            attribute_id = uuid.UUID(str(row["values"]["attribute_id"]))
            row_modification_id: uuid.UUID | None
            if family == "modification_attribute_values":
                row_modification_id = uuid.UUID(
                    str(row["values"]["modification_id"])
                )
            else:
                trim_id = uuid.UUID(str(row["values"]["trim_id"]))
                row_modification_id = state["modification_by_trim"].get(trim_id)
                if row_modification_id is None:
                    continue
            if (row_modification_id, attribute_id) == (
                conflict.modification_id,
                conflict.attribute_id,
            ):
                rejected.append((family, row, conflict.code, conflict.message))
    return rejected


async def _v2_apply_aggregate(  # noqa: PLR0912 -- dependency order is explicit
    session: AsyncSession,
    aggregate: dict[str, list[dict[str, Any]]],
    *,
    counts: dict[str, int],
    snapshot: bool = False,
) -> list[tuple[str, Mapping[str, Any], str, str]]:
    rejected_rows = await _v2_lock_and_validate_trim_value_invariant(
        session,
        aggregate,
        error_policy=(
            ImportErrorPolicy.ATOMIC
            if snapshot
            else ImportErrorPolicy.BEST_EFFORT
        ),
    )
    for family, row, _code, _message in rejected_rows:
        aggregate[family] = [item for item in aggregate.get(family, ()) if item is not row]
    # Entity dependencies first, then owned relations. DELETE roots are applied
    # after relations so their owned rows can be removed explicitly.
    entity_order = (
        "units",
        "marks",
        "categories",
        "attribute_groups",
        "attributes",
        "models",
        "modifications",
        "trims",
        "colors",
        "superstructures",
        "attribute_options",
        "products",
    )
    link_order = (
        "category_relations",
        "category_attributes",
        "superstructure_categories",
        "superstructure_attributes",
        "modification_categories",
        "modification_attribute_values",
        "product_categories",
        "product_chassis_values",
        "product_superstructure_values",
        "product_attachments",
    )
    delete_entities: list[tuple[str, dict[str, Any]]] = []
    for family in entity_order:
        for row in aggregate.get(family, ()):
            if row["operation"] == "DELETE":
                delete_entities.append((family, row))
            else:
                await _v2_apply_entity(session, family=family, row=row, counts=counts)
    for row in aggregate.get("trim_attribute_values", ()):
        if row["operation"] == "DELETE":
            await _v2_apply_link(
                session,
                family="trim_attribute_values",
                row=row,
                counts=counts,
            )
    for row in aggregate.get("trim_attributes", ()):
        await _v2_apply_link(
            session,
            family="trim_attributes",
            row=row,
            counts=counts,
        )
    for row in aggregate.get("trim_attribute_values", ()):
        if row["operation"] != "DELETE":
            await _v2_apply_link(
                session,
                family="trim_attribute_values",
                row=row,
                counts=counts,
            )
    for family in link_order:
        if family == "modification_categories" and aggregate.get(family):
            await _v2_replace_modification_categories(
                session,
                rows=aggregate[family],
                counts=counts,
            )
            continue
        if family in {"product_attachments"} and aggregate.get(
            family
        ):
            await _v2_replace_product_relation_set(
                session,
                family=family,
                rows=aggregate[family],
                counts=counts,
                snapshot=snapshot,
            )
            continue
        for row in aggregate.get(family, ()):
            await _v2_apply_link(session, family=family, row=row, counts=counts)
    for family, row in reversed(delete_entities):
        await _v2_apply_entity(session, family=family, row=row, counts=counts)
    return rejected_rows


def _v2_aggregate_product_ids(
    aggregate: dict[str, list[dict[str, Any]]],
) -> set[uuid.UUID]:
    result = {uuid.UUID(str(row["id"])) for row in aggregate.get("products", ())}
    for row in aggregate.get("product_categories", ()):
        result.add(uuid.UUID(str(row["values"]["product_id"])))
    return result


def _v2_relation_owner_ids(
    aggregate: dict[str, list[dict[str, Any]]],
) -> set[uuid.UUID]:
    return {
        uuid.UUID(str(row["values"]["product_id"]))
        for family in ("product_categories", "product_attachments")
        for row in aggregate.get(family, ())
    }


async def _v2_touch_products(
    session: AsyncSession, product_ids: set[uuid.UUID]
) -> None:
    if not product_ids:
        return
    product_table = cast("sa.Table", SpecialEquipmentProduct.__table__)
    await session.execute(
        sa.update(product_table)
        .where(product_table.c.id.in_(product_ids))
        .values(
            lock_version=product_table.c.lock_version + 1,
            updated_at=sa.func.now(),
        )
    )


async def _v2_inherit_affected_composite_classification(
    session: AsyncSession,  # noqa: ARG001
    *,
    affected_product_ids: set[uuid.UUID] | None = None,  # noqa: ARG001
) -> set[uuid.UUID]:
    """Composites are dropped; return empty set."""
    return set()


_V2_ENTITY_MODELS: dict[str, Any] = {
    "units": SpecialEquipmentUnit,
    "marks": SpecialEquipmentMark,
    "models": SpecialEquipmentModel,
    "modifications": SpecialEquipmentModification,
    "trims": SpecialEquipmentTrim,
    "categories": SpecialEquipmentCategory,
    "attribute_groups": SpecialEquipmentAttributeGroup,
    "attributes": SpecialEquipmentAttribute,
    "attribute_options": SpecialEquipmentAttributeOption,
    "superstructures": SpecialEquipmentSuperstructure,
    "colors": SpecialEquipmentColor,
    "products": SpecialEquipmentProduct,
}

_V2_LINK_MODELS: dict[str, Any] = {
    "category_relations": SpecialEquipmentCategoryRelation,
    "category_attributes": SpecialEquipmentCategoryAttribute,
    "superstructure_categories": SpecialEquipmentSuperstructureCategory,
    "superstructure_attributes": SpecialEquipmentSuperstructureAttribute,
    "modification_categories": SpecialEquipmentModificationCategory,
    "modification_attribute_values": SpecialEquipmentModificationAttributeValue,
    "trim_attributes": SpecialEquipmentTrimAttribute,
    "trim_attribute_values": SpecialEquipmentTrimAttributeValue,
    "product_categories": SpecialEquipmentProductCategory,
    "product_chassis_values": SpecialEquipmentProductChassisValue,
    "product_superstructure_values": SpecialEquipmentProductSuperstructureValue,
    "product_attachments": SpecialEquipmentProductAttachment,
}

_V2_LINK_KEYS = {
    "category_relations": ("parent_id", "child_id"),
    "category_attributes": ("category_id", "attribute_id"),
    "superstructure_categories": ("superstructure_id", "category_id"),
    "superstructure_attributes": ("superstructure_id", "attribute_id"),
    "modification_categories": ("modification_id", "category_id"),
    "modification_attribute_values": ("modification_id", "attribute_id"),
    "trim_attributes": ("trim_id", "attribute_id"),
    "trim_attribute_values": ("trim_id", "attribute_id"),
    "product_categories": ("product_id", "category_id"),
    "product_chassis_values": ("product_id", "attribute_id"),
    "product_superstructure_values": ("product_id", "attribute_id"),
    "product_attachments": ("product_id", "attachment_product_id"),
}


def get_v2_not_null_columns_without_default() -> dict[str, set[str]]:
    """Return NOT NULL columns without default/server_default per import family."""
    excluded = {"id", "created_at", "updated_at", "lock_version"}
    result: dict[str, set[str]] = {}
    for family, model in {**_V2_ENTITY_MODELS, **_V2_LINK_MODELS}.items():
        table: Any = model.__table__
        not_null_cols: set[str] = set()
        for column in table.columns:
            if column.name in excluded:
                continue
            if (
                not column.nullable
                and column.server_default is None
                and column.default is None
            ):
                not_null_cols.add(column.name)
        result[family] = not_null_cols
    return result



async def _v2_apply_entity(  # noqa: PLR0912
    session: AsyncSession,
    *,
    family: str,
    row: dict[str, Any],
    counts: dict[str, int],
) -> None:
    model = _V2_ENTITY_MODELS[family]
    table: Any = model.__table__
    entity_id = uuid.UUID(str(row["id"]))
    operation = str(row["operation"])
    if operation == "NOOP":
        return
    if operation == "DELETE":
        if family == "products":
            counts["archived"] += await _v2_archive_products(
                session,
                product_ids={entity_id},
            )
        else:
            await _v2_validate_entity_deactivation(
                session,
                family=family,
                entity_id=entity_id,
                requested_inactive=True,
            )
            counts["archived"] += await _v2_deactivate_entities(
                session,
                table=table,
                entity_ids={entity_id},
            )
        return
    await _v2_validate_entity_deactivation(
        session,
        family=family,
        entity_id=entity_id,
        requested_inactive=row.get("values", {}).get("is_active") is False,
    )
    if family == "products":
        await _v2_validate_product_transition(
            session,
            product_id=entity_id,
            values=dict(row.get("values") or {}),
        )
    values = _v2_coerce_values(
        table,
        {
            "id": entity_id,
            "code": str(row["code"]),
            **dict(row.get("values") or {}),
        },
    )
    statement = pg_insert(table).values(**values)
    if operation == "ADD":
        await session.execute(statement)
        counts["created"] += 1
        if family == "products":
            values_dict = dict(row.get("values") or {})
            if "_images_action" in values_dict:
                await _v2_apply_product_images(
                    session,
                    product_id=entity_id,
                    values=values_dict,
                )
            elif "_primary_image_action" in values_dict:
                await _v2_apply_product_primary_image(
                    session,
                    product_id=entity_id,
                    values=values_dict,
                )
        return
    conflict_fields = (
        ("attribute_id", "code")
        if family == "attribute_options"
        else (("id",) if family in {"trims", "colors"} else ("code",))
    )
    update_values = {
        key: getattr(statement.excluded, key)
        for key in values
        if key not in {"id", "code", "attribute_id", "created_at"}
    }
    if "lock_version" in table.c:
        update_values["lock_version"] = table.c.lock_version + 1
    if "updated_at" in table.c:
        update_values["updated_at"] = sa.func.now()
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=list(conflict_fields),
            set_=update_values,
        )
    )
    if family == "products":
        values_dict = dict(row.get("values") or {})
        if "_images_action" in values_dict:
            await _v2_apply_product_images(
                session,
                product_id=entity_id,
                values=values_dict,
            )
        elif "_primary_image_action" in values_dict:
            await _v2_apply_product_primary_image(
                session,
                product_id=entity_id,
                values=values_dict,
            )
    counts["updated"] += 1



async def _v2_validate_entity_deactivation(
    session: AsyncSession,
    *,
    family: str,
    entity_id: uuid.UUID,
    requested_inactive: bool,
) -> None:
    dependency_names = {
        "attribute_groups": frozenset({"attributes", "category_attributes"}),
        "attributes": frozenset({"category_attributes", "modification_values"}),
        "attribute_options": frozenset({"modification_values"}),
    }.get(family)
    if not requested_inactive or dependency_names is None:
        return
    model = _V2_ENTITY_MODELS[family]
    current = (
        (
            await session.execute(
                sa.select(model.id, model.code, model.name, model.is_active)
                .where(model.id == entity_id)
                .with_for_update()
            )
        )
        .mappings()
        .one_or_none()
    )
    if current is None or not current["is_active"]:
        return
    entity_type = cast(
        "management_repository.EntityType",
        {
            "attribute_groups": "attribute_group",
            "attributes": "attribute",
            "attribute_options": "attribute_option",
        }[family],
    )
    dependencies = await management_repository.dependencies(
        session,
        entity_type,
        entity_id,
    )
    try:
        ensure_deactivation_allowed(
            {
                name: count
                for name, count in dependencies.items()
                if name in dependency_names
            },
            entity_type=entity_type,
            entity_id=entity_id,
            entity_code=str(current["code"]),
            entity_name=str(current["name"]),
        )
    except SpecialEquipmentManagementConflictError as exc:
        raise V2AggregateSemanticConflictError(
            str(exc),
            code="ENTITY_DEACTIVATION_FORBIDDEN",
        ) from exc


async def _v2_validate_product_transition(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    values: Mapping[str, Any],
) -> None:
    """Keep import writes behind the same commerce-owned status boundary."""

    product = (
        (
            await session.execute(
                sa.select(
                    SpecialEquipmentProduct.sale_status,
                    SpecialEquipmentProduct.publication_status,
                )
                .where(SpecialEquipmentProduct.id == product_id)
                .with_for_update()
            )
        )
        .mappings()
        .one_or_none()
    )
    current_sale_status = str(product["sale_status"]) if product else None
    requested_sale_status = str(
        values.get("sale_status") or current_sale_status or "available"
    )
    requested_publication_status = str(
        values.get("publication_status")
        or (product["publication_status"] if product else "draft")
    )
    try:
        ensure_sale_transition(
            current=current_sale_status,
            requested=requested_sale_status,
            publication_status=requested_publication_status,
        )
        if (
            product
            and requested_publication_status == "archived"
            and product["publication_status"] != "archived"
        ):
            ensure_product_archive_allowed(
                dependencies=await management_repository.product_archive_dependencies(
                    session, product_id
                ),
                sale_status=current_sale_status or requested_sale_status,
                entity_id=product_id,
            )
    except SpecialEquipmentManagementConflictError as exc:
        raise V2AggregateSemanticConflictError(
            str(exc),
            code="PRODUCT_STATE_TRANSITION_FORBIDDEN",
        ) from exc


async def _enqueue_cleanup_if_unreferenced(
    session: AsyncSession,
    storage_keys: Iterable[str],
) -> None:
    unique_keys = {key for key in storage_keys if key}
    for key in unique_keys:
        count = await session.scalar(
            sa.select(sa.func.count())
            .select_from(SpecialEquipmentProductImage)
            .where(SpecialEquipmentProductImage.storage_key == key)
        )
        if count == 0:
            await management_repository.enqueue_media_cleanup(session, key)


async def _v2_apply_product_primary_image(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    values: Mapping[str, Any],
) -> None:
    action = values.get("_primary_image_action")
    if action not in {"clear", "replace"}:
        return
    image_table = cast("sa.Table", SpecialEquipmentProductImage.__table__)
    existing = list(
        (
            await session.execute(
                sa.select(
                    image_table.c.id,
                    image_table.c.is_primary,
                    image_table.c.sort_order,
                    image_table.c.storage_key,
                )
                .where(image_table.c.product_id == product_id)
                .order_by(image_table.c.sort_order, image_table.c.id)
            )
        ).mappings()
    )
    primary_ids = {row["id"] for row in existing if row["is_primary"]}
    deleted_keys = [row["storage_key"] for row in existing if row["is_primary"]]
    if primary_ids:
        await session.execute(
            sa.delete(image_table).where(image_table.c.id.in_(primary_ids))
        )
        await _enqueue_cleanup_if_unreferenced(session, deleted_keys)
    remaining_ids = [row["id"] for row in existing if row["id"] not in primary_ids]
    if remaining_ids:
        offset = len(remaining_ids) * 2 + 1
        await session.execute(
            sa.update(SpecialEquipmentProductImage)
            .where(SpecialEquipmentProductImage.id.in_(remaining_ids))
            .values(
                sort_order=SpecialEquipmentProductImage.sort_order + offset,
                is_primary=False,
            )
        )
        start = 1 if action == "replace" else 0
        for index, image_id in enumerate(remaining_ids, start=start):
            await session.execute(
                sa.update(SpecialEquipmentProductImage)
                .where(SpecialEquipmentProductImage.id == image_id)
                .values(sort_order=index, is_primary=False)
            )
    if action == "clear":
        return
    storage_key = values.get("_primary_image_storage_key")
    if not isinstance(storage_key, str) or not storage_key:
        raise V2AggregateSemanticConflictError(
            "Основное изображение не подготовлено",
            code="PRIMARY_IMAGE_NOT_STAGED",
        )
    await session.execute(
        pg_insert(image_table).values(
            id=uuid.uuid5(product_id, storage_key),
            product_id=product_id,
            storage_key=storage_key,
            alt_text=None,
            sort_order=0,
            is_primary=True,
            source_ref=None,
        )
    )


async def _v2_apply_product_images(
    session: AsyncSession,
    *,
    product_id: uuid.UUID | str,
    values: Mapping[str, Any],
) -> None:
    action = values.get("_images_action")
    if action not in {"clear", "replace"}:
        return

    product_uuid = uuid.UUID(str(product_id))
    image_table = cast("sa.Table", SpecialEquipmentProductImage.__table__)
    existing = list(
        (
            await session.execute(
                sa.select(
                    image_table.c.id,
                    image_table.c.storage_key,
                    image_table.c.source_ref,
                    image_table.c.sort_order,
                    image_table.c.is_primary,
                )
                .where(image_table.c.product_id == product_uuid)
                .order_by(image_table.c.sort_order, image_table.c.id)
            )
        ).mappings()
    )

    if action == "clear":
        if existing:
            deleted_keys = [row["storage_key"] for row in existing]
            await session.execute(
                sa.delete(image_table).where(image_table.c.product_id == product_uuid)
            )
            await _enqueue_cleanup_if_unreferenced(session, deleted_keys)
        return

    target_images = list(values.get("_images") or ())
    retained_ids: set[uuid.UUID] = set()
    for target in target_images:
        raw_reuse_id = target.get("reuse_image_id")
        if raw_reuse_id is not None:
            retained_ids.add(uuid.UUID(str(raw_reuse_id)))

    to_delete = [row for row in existing if row["id"] not in retained_ids]
    if to_delete:
        to_delete_ids = [row["id"] for row in to_delete]
        deleted_keys = [row["storage_key"] for row in to_delete]
        await session.execute(
            sa.delete(image_table).where(image_table.c.id.in_(to_delete_ids))
        )
        await _enqueue_cleanup_if_unreferenced(session, deleted_keys)

    if not target_images:
        return

    # Offset remaining retained rows to prevent unique constraint conflict on sort_order and is_primary
    if retained_ids:
        offset = len(target_images) + len(existing) + 10
        await session.execute(
            sa.update(SpecialEquipmentProductImage)
            .where(SpecialEquipmentProductImage.id.in_(retained_ids))
            .values(
                sort_order=SpecialEquipmentProductImage.sort_order + offset,
                is_primary=False,
            )
        )

    for index, target in enumerate(target_images):
        sort_order = index
        is_primary = (index == 0)
        storage_key = str(target["storage_key"])
        source_ref = str(target.get("source_ref") or "") or None
        raw_reuse_id = target.get("reuse_image_id")
        reuse_id = uuid.UUID(str(raw_reuse_id)) if raw_reuse_id is not None else None

        if reuse_id is not None and reuse_id in retained_ids:
            await session.execute(
                sa.update(SpecialEquipmentProductImage)
                .where(SpecialEquipmentProductImage.id == reuse_id)
                .values(
                    sort_order=sort_order,
                    is_primary=is_primary,
                    storage_key=storage_key,
                    source_ref=source_ref,
                )
            )
        else:
            image_id = uuid.uuid5(product_uuid, str(source_ref or storage_key))
            insert_stmt = (
                pg_insert(image_table)
                .values(
                    id=image_id,
                    product_id=product_uuid,
                    storage_key=storage_key,
                    alt_text=None,
                    sort_order=sort_order,
                    is_primary=is_primary,
                    source_ref=source_ref,
                )
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "storage_key": storage_key,
                        "sort_order": sort_order,
                        "is_primary": is_primary,
                        "source_ref": source_ref,
                    },
                )
            )
            await session.execute(insert_stmt)



async def _v2_apply_link(
    session: AsyncSession,
    *,
    family: str,
    row: dict[str, Any],
    counts: dict[str, int],
) -> None:
    table: Any = _V2_LINK_MODELS[family].__table__
    keys = _V2_LINK_KEYS[family]
    values = _v2_coerce_values(table, dict(row.get("values") or {}))
    predicate = sa.and_(*(table.c[key] == values[key] for key in keys))
    operation = str(row["operation"])
    if operation == "DELETE":
        result = await session.execute(sa.delete(table).where(predicate))
        counts["removed"] += int(getattr(result, "rowcount", 0) or 0)
        return
    if family == "modification_categories" and values.get("is_primary") is True:
        await session.execute(
            sa.update(table)
            .where(
                table.c.modification_id == values["modification_id"],
                table.c.category_id != values["category_id"],
            )
            .values(is_primary=False)
        )
    statement = pg_insert(table).values(**values)
    mutable = {key: value for key, value in values.items() if key not in keys}
    if operation == "ADD":
        await session.execute(statement)
        counts["created"] += 1
    elif mutable:
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=list(keys),
                set_=mutable,
            )
        )
        counts["updated"] += 1
    else:
        await session.execute(
            statement.on_conflict_do_nothing(index_elements=list(keys))
        )
        counts["updated"] += 1


async def _v2_replace_modification_categories(
    session: AsyncSession,
    *,
    rows: list[dict[str, Any]],
    counts: dict[str, int],
) -> None:
    """Replace one ordered category set without transient unique conflicts."""

    table = cast("sa.Table", SpecialEquipmentModificationCategory.__table__)
    values_by_category: dict[uuid.UUID, dict[str, Any]] = {}
    modification_ids: set[uuid.UUID] = set()
    for row in rows:
        values = _v2_coerce_values(table, dict(row.get("values") or {}))
        modification_id = uuid.UUID(str(values["modification_id"]))
        category_id = uuid.UUID(str(values["category_id"]))
        modification_ids.add(modification_id)
        if row["operation"] != "DELETE":
            values_by_category[category_id] = values
    if len(modification_ids) != 1:
        raise ValueError("Modification category aggregate spans multiple modifications")
    modification_id = next(iter(modification_ids))
    existing_category_ids = set(
        (
            await session.execute(
                sa.select(table.c.category_id).where(
                    table.c.modification_id == modification_id
                )
            )
        ).scalars()
    )
    await session.execute(
        sa.delete(table).where(table.c.modification_id == modification_id)
    )
    for values in sorted(
        values_by_category.values(),
        key=lambda item: (int(item["sort_order"]), str(item["category_id"])),
    ):
        await session.execute(pg_insert(table).values(**values))
    final_category_ids = set(values_by_category)
    counts["created"] += len(final_category_ids - existing_category_ids)
    counts["updated"] += len(final_category_ids & existing_category_ids)
    counts["removed"] += len(existing_category_ids - final_category_ids)


async def _v2_replace_product_relation_set(
    session: AsyncSession,
    *,
    family: str,
    rows: list[dict[str, Any]],
    counts: dict[str, int],
    snapshot: bool,
) -> None:
    """Replace one owner's final ordered relation set without transient conflicts."""

    table = cast("sa.Table", _V2_LINK_MODELS[family].__table__)
    owner_field, target_field = _V2_LINK_KEYS[family]
    normalized_rows = [
        (
            row,
            _v2_coerce_values(table, dict(row.get("values") or {})),
        )
        for row in rows
    ]
    owner_ids = {values[owner_field] for _row, values in normalized_rows}
    if len(owner_ids) != 1:
        raise V2AggregateSemanticConflictError(
            "Агрегат связей охватывает несколько владельцев",
            code="INVALID_RELATION_AGGREGATE",
        )
    owner_id = next(iter(owner_ids))
    existing_rows = (
        (
            await session.execute(
                sa.select(table).where(table.c[owner_field] == owner_id)
            )
        )
        .mappings()
        .all()
    )
    existing_by_target = {
        row[target_field]: {
            key: value for key, value in dict(row).items() if key not in {"created_at"}
        }
        for row in existing_rows
    }
    existing_target_ids = set(existing_by_target)
    final_by_target = {} if snapshot else dict(existing_by_target)
    for row, values in normalized_rows:
        target_id = values[target_field]
        if row["operation"] == "DELETE":
            final_by_target.pop(target_id, None)
            continue
        final_by_target[target_id] = {
            **final_by_target.get(target_id, {}),
            **values,
        }
    await session.execute(sa.delete(table).where(table.c[owner_field] == owner_id))
    if final_by_target:
        ordered_values = sorted(
            final_by_target.values(),
            key=lambda values: (
                int(values["position"]),
                str(values[target_field]),
            ),
        )
        # Existing rows retain audit columns while new rows rely on database
        # defaults. Separate statements keep those heterogeneous shapes valid.
        for values in ordered_values:
            await session.execute(pg_insert(table).values(**values))
    final_target_ids = set(final_by_target)
    counts["created"] += len(final_target_ids - existing_target_ids)
    counts["updated"] += len(final_target_ids & existing_target_ids)
    counts["removed"] += len(existing_target_ids - final_target_ids)


def _v2_coerce_values(table: Any, values: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values.items():
        if key not in table.c:
            continue
        column = table.c[key]
        if value is None:
            if not column.nullable and (
                column.server_default is not None or column.default is not None
            ):
                continue
            result[key] = value
            continue
        column_type = column.type
        if isinstance(column_type, PGUUID):
            result[key] = uuid.UUID(str(value))
        elif isinstance(column_type, sa.Numeric):
            result[key] = Decimal(str(value))
        elif isinstance(column_type, sa.DateTime) and isinstance(value, str):
            result[key] = datetime.fromisoformat(value)
        else:
            result[key] = value
    return result


async def _v2_delete_missing_snapshot_relations(
    session: AsyncSession,
    *,
    plan: dict[str, Any],
    counts: dict[str, int],
    include_v4_catalog: bool = True,
) -> set[uuid.UUID]:
    relation_order = (
        "product_chassis_values",
        "product_superstructure_values",
        "product_attachments",
        "product_categories",
        *(("trim_attribute_values", "trim_attributes") if include_v4_catalog else ()),
        "modification_attribute_values",
        "modification_categories",
        "superstructure_categories",
        "superstructure_attributes",
        "category_attributes",
        "category_relations",
    )
    removed_relation_owner_ids: set[uuid.UUID] = set()
    for family in relation_order:
        desired = {
            tuple(
                _v2_coerce_values(
                    _V2_LINK_MODELS[family].__table__,
                    dict(row.get("values") or {}),
                )[key]
                for key in _V2_LINK_KEYS[family]
            )
            for row in plan.get(family, ())
            if row["operation"] != "DELETE"
        }
        if family in {
            "product_chassis_values",
            "product_superstructure_values",
            "product_attachments",
            "product_categories",
        }:
            table = _V2_LINK_MODELS[family].__table__
            key_fields = _V2_LINK_KEYS[family]
            existing = set(
                (
                    await session.execute(
                        sa.select(*(table.c[key] for key in key_fields))
                    )
                ).tuples()
            )
            removed_relation_owner_ids.update(key[0] for key in existing - desired)
        counts["removed"] += await _v2_delete_missing_keys(
            session,
            table=_V2_LINK_MODELS[family].__table__,
            key_fields=_V2_LINK_KEYS[family],
            desired=desired,
        )
    return removed_relation_owner_ids


async def _v2_retire_missing_snapshot_entities(
    session: AsyncSession,
    *,
    plan: dict[str, Any],
    counts: dict[str, int],
    include_v4_catalog: bool = True,
    target_warehouse_id: uuid.UUID | None = None,
) -> None:
    desired_product_ids = {
        uuid.UUID(str(row["id"]))
        for row in plan.get("products", ())
        if row["operation"] != "DELETE"
    }
    counts["archived"] += await _v2_archive_missing_products(
        session,
        desired=desired_product_ids,
        target_warehouse_id=target_warehouse_id,
    )
    for family in (
        *(("trims", "colors") if include_v4_catalog else ()),
        "attribute_options",
        "superstructures",
        "attributes",
        "attribute_groups",
        "modifications",
        "models",
        "marks",
        "categories",
        "units",
    ):
        desired_entity_ids = {
            uuid.UUID(str(row["id"]))
            for row in plan.get(family, ())
            if row["operation"] != "DELETE"
        }
        counts["archived"] += await _v2_deactivate_missing_entities(
            session,
            table=_V2_ENTITY_MODELS[family].__table__,
            desired=desired_entity_ids,
        )


async def _v2_delete_missing_snapshot_rows(
    session: AsyncSession,
    *,
    plan: dict[str, Any],
    counts: dict[str, int],
    include_v4_catalog: bool = True,
    target_warehouse_id: uuid.UUID | None = None,
) -> set[uuid.UUID]:
    removed_relation_owner_ids = await _v2_delete_missing_snapshot_relations(
        session,
        plan=plan,
        counts=counts,
        include_v4_catalog=include_v4_catalog,
    )
    await _v2_retire_missing_snapshot_entities(
        session,
        plan=plan,
        counts=counts,
        include_v4_catalog=include_v4_catalog,
        target_warehouse_id=target_warehouse_id,
    )
    return removed_relation_owner_ids


async def _v2_archive_missing_products(
    session: AsyncSession,
    *,
    desired: set[uuid.UUID],
    target_warehouse_id: uuid.UUID | None = None,
) -> int:
    """Hide missing snapshot products without breaking commerce references."""

    table: Any = SpecialEquipmentProduct.__table__
    if target_warehouse_id is not None:
        # When target_warehouse_id is set, the warehouse products are cascade purged, and products of other warehouses are not archived!
        existing = set(
            (
                await session.execute(
                    sa.select(table.c.id).where(
                        table.c.warehouse_id == target_warehouse_id
                    )
                )
            ).scalars()
        )
    else:
        existing = set((await session.execute(sa.select(table.c.id))).scalars())
    return await _v2_archive_products(
        session,
        product_ids=existing - desired,
    )


_v2_archive_missing_snapshot_products = _v2_archive_missing_products


async def _v2_archive_products(
    session: AsyncSession,
    *,
    product_ids: set[uuid.UUID],
) -> int:
    table: Any = SpecialEquipmentProduct.__table__
    archived = 0
    product_rows = (
        await session.execute(
            sa.select(
                table.c.id,
                table.c.code,
                table.c.sale_status,
                table.c.publication_status,
            )
            .where(table.c.id.in_(product_ids))
            .order_by(table.c.id)
            .with_for_update()
        )
    ).mappings()
    for product in product_rows:
        if product["publication_status"] == "archived":
            continue
        try:
            ensure_product_archive_allowed(
                dependencies=await management_repository.product_archive_dependencies(
                    session, product["id"]
                ),
                sale_status=str(product["sale_status"]),
                entity_id=product["id"],
                entity_code=str(product["code"]),
                entity_name=str(product["code"]),
            )
        except SpecialEquipmentManagementConflictError as exc:
            raise V2AggregateSemanticConflictError(
                str(exc),
                code="PRODUCT_ARCHIVE_FORBIDDEN",
            ) from exc
    for batch in _batches(sorted(product_ids, key=str)):
        ids = _uuid_array("v2_missing_snapshot_product_ids", batch)
        result = await session.execute(
            sa.update(table)
            .where(
                table.c.id == sa.any_(ids),
                table.c.publication_status != "archived",
            )
            .values(
                publication_status="archived",
                lock_version=table.c.lock_version + 1,
                updated_at=sa.func.now(),
            )
        )
        archived += int(getattr(result, "rowcount", 0) or 0)
    return archived


async def _v2_deactivate_missing_entities(
    session: AsyncSession,
    *,
    table: Any,
    desired: set[uuid.UUID],
) -> int:
    """Hide absent snapshot directories while retaining FK history chains."""

    existing = set((await session.execute(sa.select(table.c.id))).scalars())
    return await _v2_deactivate_entities(
        session,
        table=table,
        entity_ids=existing - desired,
    )


async def _v2_deactivate_entities(
    session: AsyncSession,
    *,
    table: Any,
    entity_ids: set[uuid.UUID],
) -> int:
    deactivated = 0
    for batch in _batches(sorted(entity_ids, key=str)):
        ids = _uuid_array(f"v2_missing_snapshot_{table.name}_ids", batch)
        result = await session.execute(
            sa.update(table)
            .where(
                table.c.id == sa.any_(ids),
                table.c.is_active.is_(True),
            )
            .values(
                is_active=False,
                lock_version=table.c.lock_version + 1,
                updated_at=sa.func.now(),
            )
        )
        deactivated += int(getattr(result, "rowcount", 0) or 0)
    return deactivated


async def _v2_delete_missing_keys(
    session: AsyncSession,
    *,
    table: Any,
    key_fields: tuple[str, ...],
    desired: set[tuple[Any, ...]],
) -> int:
    columns = tuple(table.c[field] for field in key_fields)
    existing = set((await session.execute(sa.select(*columns))).tuples().all())
    missing = sorted(existing - desired, key=lambda item: tuple(map(str, item)))
    removed = 0
    for batch in _batches(missing):
        for key in batch:
            predicate = sa.and_(
                *(
                    table.c[field] == value
                    for field, value in zip(key_fields, key, strict=True)
                )
            )
            result = await session.execute(sa.delete(table).where(predicate))
            removed += int(getattr(result, "rowcount", 0) or 0)
    return removed
