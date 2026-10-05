"""Protected REST API for corrected special-equipment catalog management."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands import special_equipment_management as commands
from application.errors import ServiceError, domain_to_http
from application.queries.special_equipment_management import (
    GetRegistryDependenciesQuery,
    GetRegistryEntityQuery,
    ListAttachmentSourcesQuery,
    ListProductRelationsQuery,
    ListRegistryQuery,
    SelectColorsQuery,
    handle_category_image_key,
    handle_dependencies,
    handle_get,
    handle_list,
    handle_list_attachment_sources,
    handle_list_product_relations,
    handle_list_trim_lifecycle_items,
    handle_product_image_key,
    handle_section_counts,
    handle_select_colors,
    handle_seller_companies,
    handle_superstructure_attribute_candidates,
    handle_trim_attribute_candidates,
    handle_trim_attributes,
    resolve_trim_attribute_candidates,
)
from application.special_equipment_management_etag import (
    special_equipment_management_etag,
    special_equipment_trim_attributes_etag,
)
from domain.errors import DomainError
from domain.services.object_storage import ObjectStorage, StoredObject
from domain.services.scopes import (
    SPECIAL_EQUIPMENT_CATALOG_READ,
    SPECIAL_EQUIPMENT_CATALOG_WRITE,
    VEHICLES_ADMIN,
)
from domain.special_equipment_attachments import (
    AttachmentCategoryInUseError,
    AttachmentInvariantError,
)
from domain.special_equipment_cascade_delete import (
    CascadeBlockers,
    CascadeConfirmationInvalidError,
    CascadeDeleteBlockedError,
    CascadePlan,
    CascadePreviewStaleError,
    CascadeTooLargeError,
)
from domain.special_equipment_kits import KitInvariantError
from domain.special_equipment_management import (
    AttributeTypeConversionBlockedError,
    ProductPriceOnRequestModeLockedError,
    ProductWarehouseValidationError,
    SpecialEquipmentColorConflictError,
    SpecialEquipmentColorValidationError,
    SpecialEquipmentManagementConflictError,
    SpecialEquipmentManagementNotFoundError,
    SpecialEquipmentManagementPreconditionError,
    SpecialEquipmentManagementValidationError,
    SpecialEquipmentTrimContractError,
    UnitInactiveError,
    UnitInUseError,
    UnitNotFoundError,
)
from infrastructure.database import get_db
from infrastructure.services.object_storage import get_object_storage
from infrastructure.services.special_equipment_registry_images import (
    RegistryImageValidationError,
    encode_registry_image,
    registry_image_storage_key,
)
from presentation.dependencies.auth import require_scopes
from presentation.errors import (
    color_error_detail,
    special_equipment_problem_response,
)
from presentation.routers.special_equipment import _media_response
from presentation.schemas.special_equipment_management import (
    AttachmentSourcesResponse,
    AttributeCreateRequest,
    AttributeGroupCreateRequest,
    AttributeGroupListResponse,
    AttributeGroupPatchRequest,
    AttributeGroupResource,
    AttributeListResponse,
    AttributeOptionCreateRequest,
    AttributeOptionListResponse,
    AttributeOptionPatchRequest,
    AttributeOptionResource,
    AttributePatchRequest,
    AttributeResource,
    CascadeDeleteRequestSchema,
    CascadeDeleteResponseSchema,
    CascadePreviewResponseSchema,
    CatalogSectionCountsResponse,
    CategoryAttributeLinksReplaceRequest,
    CategoryCreateRequest,
    CategoryListResponse,
    CategoryParentsReplaceRequest,
    CategoryPatchRequest,
    CategoryResource,
    ColorCreateRequest,
    ColorListResponse,
    ColorPatchRequest,
    ColorResource,
    ColorSelectResponse,
    CompatibleAttachmentCreateRequest,
    CompatibleAttachmentPatchRequest,
    CompatibleAttachmentsReplaceRequest,
    CompatibleAttachmentsResponse,
    DependencyConflictDetail,
    DependencyConflictItem,
    DependencyResource,
    ManagementImageResource,
    MarkCreateRequest,
    MarkListResponse,
    MarkPatchRequest,
    MarkResource,
    MediaUploadResponse,
    ModelCreateRequest,
    ModelListResponse,
    ModelPatchRequest,
    ModelResource,
    ModificationCreateRequest,
    ModificationListResponse,
    ModificationPatchRequest,
    ModificationResource,
    ProductCreateRequest,
    ProductImagePatchRequest,
    ProductListResponse,
    ProductPatchRequest,
    ProductResource,
    ProductWarehouseReplaceRequest,
    SaleStatus,
    SellerCompaniesResponse,
    SuperstructureAttributeCandidatesResponse,
    SuperstructureCreateRequest,
    SuperstructureListResponse,
    SuperstructurePatchRequest,
    SuperstructureResource,
    TrimAttributeCandidatesResponse,
    TrimAttributeCreateResponse,
    TrimAttributeLinkInput,
    TrimAttributesResponse,
    TrimAttributeValuesLegacyResponse,
    TrimAttributeValuesReplaceRequest,
    TrimAttributeValuesResponse,
    TrimCreateRequest,
    TrimCreateResponse,
    TrimListResponse,
    TrimPatchRequest,
    TrimResource,
    UnitCreateRequest,
    UnitListResponse,
    UnitMergeRequest,
    UnitPatchRequest,
    UnitResource,
)

router = APIRouter()

EntityType = Literal[
    "category",
    "mark",
    "model",
    "modification",
    "trim",
    "attribute_group",
    "attribute",
    "attribute_option",
    "product",
    "color",
    "unit",
    "superstructure",
]

ReadUser = Annotated[
    dict[str, Any], Depends(require_scopes(SPECIAL_EQUIPMENT_CATALOG_READ))
]
WriteUser = Annotated[
    dict[str, Any], Depends(require_scopes(SPECIAL_EQUIPMENT_CATALOG_WRITE))
]
VehicleAdminUser = Annotated[dict[str, Any], Depends(require_scopes(VEHICLES_ADMIN))]
Session = Annotated[AsyncSession, Depends(get_db)]
Storage = Annotated[ObjectStorage, Depends(get_object_storage)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=200),
]


@router.get(
    "/section-counts",
    response_model=CatalogSectionCountsResponse,
    summary="Количество записей в разделах каталога",
    description=(
        "Возвращает глобальные количества записей для всех вкладок управления "
        "каталогом без применения фильтров активного раздела."
    ),
)
async def section_counts(_user: ReadUser, session: Session) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(await handle_section_counts(session)))


def _actor_id(user: dict[str, Any]) -> UUID:
    return UUID(str(user["id"]))


def _idempotency_hash(
    entity_type: EntityType, values: dict[str, Any]
) -> str:
    body = json.dumps(
        {
            "entity_type": entity_type,
            "values": jsonable_encoder(values),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _serialize_cascade_blockers(blockers: CascadeBlockers) -> dict[str, Any]:
    return {
        "products": [
            {
                "product": {
                    "id": pb.product.id,
                    "code": pb.product.code or "",
                    "name": pb.product.name or pb.product.code or "",
                    "vin": (
                        pb.product.name
                        if pb.product.name and pb.product.name != pb.product.code
                        else None
                    ),
                },
                "vin": (
                    pb.product.name
                    if pb.product.name and pb.product.name != pb.product.code
                    else None
                ),
                "documents": [
                    {
                        "type": d.type,
                        "id": d.id,
                        "number": d.number,
                        "status": d.status,
                    }
                    for d in pb.documents
                ],
            }
            for pb in blockers.products
        ],
        "distributors": [
            {
                "company": {
                    "id": db.company["id"],
                    "name": db.company["name"],
                    "inn": db.company.get("inn"),
                }
            }
            for db in blockers.distributors
        ],
        "support_programs": [
            {
                "program": {
                    "id": sp.program["id"],
                    "name": sp.program["name"],
                    "is_active": sp.program.get("is_active", True),
                    "starts_at": sp.program.get("starts_at"),
                    "ends_at": sp.program.get("ends_at"),
                },
                "references": [
                    {
                        "type": r.type,
                        "id": r.id,
                        "code": r.code or "",
                        "name": r.name or r.code or "",
                    }
                    for r in sp.references
                ],
            }
            for sp in blockers.support_programs
        ],
    }


def _serialize_cascade_plan(plan: CascadePlan) -> dict[str, Any]:
    delete_groups: list[dict[str, Any]] = []
    order = [
        "products",
        "trims",
        "modifications",
        "models",
        "marks",
        "categories",
        "attribute_groups",
        "attributes",
        "options",
        "colors",
    ]
    for key in order:
        items = plan.delete.get(key, [])
        if items:
            delete_groups.append(
                {
                    "type": key,
                    "count": len(items),
                    "items": [
                        {
                            "id": item.id,
                            "code": item.code or "",
                            "name": item.name or item.code or "",
                        }
                        for item in items[:50]
                    ],
                    "truncated": len(items) > 50,
                }
            )

    return {
        "root": {
            "type": plan.root.type,
            "id": plan.root.id,
            "code": plan.root.code or "",
            "name": plan.root.name or plan.root.code or "",
        },
        "delete": delete_groups,
        "unlink": [
            {
                "type": u.type,
                "count": u.count,
                "description": u.description,
            }
            for u in plan.unlink
        ],
        "clear": [
            {
                "type": c.type,
                "field": c.field,
                "count": c.count,
                "description": c.description,
            }
            for c in plan.clear
        ],
        "user_impact": {
            "cart_items": plan.user_impact.cart_items,
            "favorites": plan.user_impact.favorites,
        },
        "blockers": _serialize_cascade_blockers(plan.blockers),
        "total": plan.total_affected,
        "preview_token": plan.preview_token or "",
        "catalog_revision": plan.catalog_revision,
    }


def _http(exc: ServiceError | DomainError) -> HTTPException:  # noqa: PLR0911, PLR0912
    error = domain_to_http(exc) if isinstance(exc, DomainError) else exc
    if isinstance(exc, ProductPriceOnRequestModeLockedError):
        return HTTPException(
            status_code=409,
            detail={"detail": str(exc), "code": exc.code},
            headers={"content-type": "application/problem+json"},
        )
    if isinstance(exc, SpecialEquipmentTrimContractError):
        status = (
            428
            if exc.code == "PRECONDITION_REQUIRED"
            else _TRIM_PROBLEM_STATUS.get(exc.kind, error.status_code)
        )
        return HTTPException(
            status_code=status,
            detail={"detail": str(exc), "code": exc.code},
        )
    if isinstance(
        exc,
        (
            AttachmentCategoryInUseError,
            AttachmentInvariantError,
        ),
    ):
        return HTTPException(
            status_code=error.status_code,
            detail={"detail": str(exc), "code": exc.code},
        )
    if isinstance(exc, AttributeTypeConversionBlockedError):
        return HTTPException(
            status_code=error.status_code,
            detail={
                "detail": str(exc),
                "code": exc.code,
                "blockers": {
                    "modification_values": exc.value_count,
                },
            },
        )
    if isinstance(exc, UnitInUseError):
        return HTTPException(
            status_code=409,
            detail={
                "detail": str(exc),
                "code": exc.code,
                "attribute_count": exc.attribute_count,
            },
            headers={"content-type": "application/problem+json"},
        )
    if isinstance(exc, (UnitInactiveError, UnitNotFoundError)):
        return HTTPException(
            status_code=422,
            detail={"detail": str(exc), "code": exc.code},
            headers={"content-type": "application/problem+json"},
        )
    if isinstance(exc, KitInvariantError):
        status_code = 422
        if exc.code in {
            "SUPERSTRUCTURE_MODEL_IN_USE",
            "SUPERSTRUCTURE_ATTRIBUTE_IN_USE",
            "SUPERSTRUCTURE_REQUIRED_VALUE_MISSING",
            "SUPERSTRUCTURE_NAME_CONFLICT",
        }:
            status_code = 409
        elif exc.code in {
            "SUPERSTRUCTURE_NOT_FOUND",
            "MODEL_NOT_FOUND",
            "MODIFICATION_NOT_FOUND",
        }:
            status_code = 404
        return HTTPException(
            status_code=status_code,
            detail={"detail": str(exc), "code": exc.code},
            headers={"content-type": "application/problem+json"},
        )
    if isinstance(exc, ProductWarehouseValidationError):
        return HTTPException(
            status_code=error.status_code,
            detail={"detail": str(exc), "code": exc.error_code},
            headers={"content-type": "application/problem+json"},
        )
    if (
        isinstance(exc, SpecialEquipmentManagementConflictError)
        and exc.entity_type is not None
        and exc.entity_id is not None
        and exc.dependencies
    ):
        detail = DependencyConflictDetail(
            detail=str(exc),
            code="SPECIAL_EQUIPMENT_DEPENDENCY_CONFLICT",
            entity_type=exc.entity_type,
            entity_id=exc.entity_id,
            entity_code=exc.entity_code,
            entity_name=exc.entity_name,
            dependencies=[
                DependencyConflictItem(
                    entity=item.entity_type,
                    id=item.entity_id,
                    code=item.code,
                    name=item.name,
                    count=item.count,
                )
                for item in exc.dependencies
            ],
        )
        return HTTPException(
            status_code=error.status_code,
            detail=detail.model_dump(mode="json"),
        )
    if isinstance(exc, CascadeConfirmationInvalidError):
        return HTTPException(
            status_code=400,
            detail={
                "type": "about:blank",
                "title": "Cascade Confirmation Invalid",
                "status": 400,
                "detail": str(exc),
                "code": exc.code,
            },
            headers={"content-type": "application/problem+json"},
        )
    if isinstance(exc, CascadeDeleteBlockedError):
        return HTTPException(
            status_code=409,
            detail={
                "type": "about:blank",
                "title": "Cascade Delete Blocked",
                "status": 409,
                "detail": str(exc),
                "code": exc.code,
                "blockers": jsonable_encoder(_serialize_cascade_blockers(exc.blockers)),
            },
            headers={"content-type": "application/problem+json"},
        )
    if isinstance(exc, CascadePreviewStaleError):
        return HTTPException(
            status_code=409,
            detail={
                "type": "about:blank",
                "title": "Cascade Preview Stale",
                "status": 409,
                "detail": str(exc),
                "code": exc.code,
                "preview": (
                    jsonable_encoder(_serialize_cascade_plan(exc.plan))
                    if exc.plan is not None
                    else None
                ),
            },
            headers={"content-type": "application/problem+json"},
        )
    if isinstance(exc, CascadeTooLargeError):
        return HTTPException(
            status_code=422,
            detail={
                "type": "about:blank",
                "title": "Cascade Too Large",
                "status": 422,
                "detail": str(exc),
                "code": exc.code,
                "total": exc.total,
                "max_rows": exc.max_rows,
            },
            headers={"content-type": "application/problem+json"},
        )
    return HTTPException(status_code=error.status_code, detail=str(error))


_STRONG_ETAG_DIGEST = re.compile(r"[0-9a-f]{64}")


def _precondition_error(
    status_code: int, detail: str, *, problem: bool
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers=(
            {"content-type": "application/problem+json"} if problem else None
        ),
    )


def _expected_precondition(
    raw: str | None, entity_id: UUID, *, problem: bool = False
) -> tuple[int, str]:
    if raw is None:
        raise _precondition_error(
            428, "Требуется заголовок If-Match", problem=problem
        )
    etag = raw.strip()
    if (
        etag.startswith("W/")
        or len(etag) < 2
        or not etag.startswith('"')
        or not etag.endswith('"')
    ):
        raise _precondition_error(412, "Некорректный ETag", problem=problem)
    parts = etag[1:-1].split(":")
    if (
        len(parts) != 3
        or parts[0] != str(entity_id)
        or _STRONG_ETAG_DIGEST.fullmatch(parts[2]) is None
    ):
        raise _precondition_error(412, "Некорректный ETag", problem=problem)
    try:
        version = int(parts[1])
    except ValueError as exc:
        raise _precondition_error(
            412, "Некорректный ETag", problem=problem
        ) from exc
    if version < 1 or parts[1] != str(version):
        raise _precondition_error(412, "Некорректный ETag", problem=problem)
    return version, etag


def _color_error(
    *,
    status_code: int,
    code: str,
    message: str,
    detail: dict[str, Any] | None = None,
    field_errors: list[dict[str, Any]] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=color_error_detail(
            code=code,
            message=message,
            detail=detail,
            field_errors=field_errors,
        ),
    )


def _color_expected_precondition(raw: str | None, color_id: UUID) -> tuple[int, str]:
    if raw is None:
        raise _color_error(
            status_code=428,
            code="precondition_required",
            message="Требуется заголовок If-Match",
        )
    etag = raw.strip()
    if (
        etag.startswith("W/")
        or len(etag) < 2
        or not etag.startswith('"')
        or not etag.endswith('"')
    ):
        raise _color_error(
            status_code=400,
            code="malformed_if_match",
            message="Заголовок If-Match имеет некорректный формат",
        )
    parts = etag[1:-1].split(":")
    if len(parts) != 3 or _STRONG_ETAG_DIGEST.fullmatch(parts[2]) is None:
        raise _color_error(
            status_code=400,
            code="malformed_if_match",
            message="Заголовок If-Match имеет некорректный формат",
        )
    if parts[0] != str(color_id):
        raise _color_error(
            status_code=409,
            code="etag_resource_mismatch",
            message="Заголовок If-Match относится к другому ресурсу",
            detail={"expected_resource_type": "special-equipment-color"},
        )
    try:
        version = int(parts[1])
    except ValueError as exc:
        raise _color_error(
            status_code=400,
            code="malformed_if_match",
            message="Заголовок If-Match имеет некорректный формат",
        ) from exc
    if version < 1 or parts[1] != str(version):
        raise _color_error(
            status_code=400,
            code="malformed_if_match",
            message="Заголовок If-Match имеет некорректный формат",
        )
    return version, etag


def _color_http_exception(exc: ServiceError | DomainError) -> HTTPException:
    error = domain_to_http(exc) if isinstance(exc, DomainError) else exc
    status_code = error.status_code
    code = "color_error"
    detail: dict[str, Any] | None = None
    field_errors: list[dict[str, Any]] = []
    if isinstance(exc, SpecialEquipmentManagementPreconditionError):
        status_code = 409
        code = "stale_etag"
    elif isinstance(exc, SpecialEquipmentColorConflictError):
        status_code = 409
        code = exc.error_code
        detail = dict(exc.detail) if exc.detail is not None else None
        field_errors = [dict(item) for item in exc.field_errors]
    elif isinstance(exc, SpecialEquipmentColorValidationError):
        status_code = 422
        code = exc.error_code
        field_errors = [
            {
                "field": exc.field,
                "code": exc.field_error_code,
                "message": str(exc),
            }
        ]
    elif isinstance(exc, SpecialEquipmentManagementConflictError):
        status_code = 409
        code = "color_conflict"
    elif isinstance(exc, SpecialEquipmentManagementValidationError):
        status_code = 422
        code = "color_validation_error"
    elif isinstance(exc, SpecialEquipmentManagementNotFoundError) or status_code == 404:
        status_code = 404
        code = "color_not_found"
    return _color_error(
        status_code=status_code,
        code=code,
        message=str(error),
        detail=detail,
        field_errors=field_errors,
    )


async def _commit_color[T](session: AsyncSession, operation: Awaitable[T]) -> T:
    try:
        result = await operation
        await session.commit()
        return result
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        raise _color_http_exception(exc)
    except IntegrityError as exc:
        await session.rollback()
        text = str(getattr(exc, "orig", exc))
        constraint_name = getattr(getattr(exc, "orig", None), "diag", None)
        constraint_name = getattr(constraint_name, "constraint_name", None)
        unique_constraint = constraint_name or text
        if "uq_special_equipment_colors_name_norm" in unique_constraint:
            raise _color_error(
                status_code=409,
                code="duplicate_name",
                message="Цвет с таким названием уже существует",
                field_errors=[
                    {
                        "field": "name",
                        "code": "duplicate",
                        "message": "Название должно быть уникальным (без учёта регистра и пробелов)",
                    }
                ],
            ) from exc
        if "uq_special_equipment_colors_code_norm" in unique_constraint:
            raise _color_error(
                status_code=409,
                code="duplicate_code",
                message="Цвет с таким техническим кодом уже существует",
                field_errors=[
                    {
                        "field": "code",
                        "code": "duplicate",
                        "message": "Код должен быть уникальным",
                    }
                ],
            ) from exc
        if (
            "body_color" in text
            or "interior_color" in text
            or "foreign key" in text.lower()
        ):
            raise _color_error(
                status_code=409,
                code="color_in_use",
                message="Цвет используется в объявлениях",
            ) from exc
        raise _color_error(
            status_code=409,
            code="color_conflict",
            message="Конфликт уникальности или зависимости",
        ) from exc
    except BaseException:
        await session.rollback()
        raise


def _response(resource: dict, *, status_code: int = 200) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code, content=jsonable_encoder(resource)
    )
    if "lock_version" in resource:
        response.headers["ETag"] = special_equipment_management_etag(resource)
    return response


def _registry_media_response(
    obj: StoredObject, request: Request, filename: str
) -> Response:
    return _media_response(
        obj,
        request,
        filename,
        cache_control="private, no-store",
        etag_prefix="registry-sha256",
        vary="Authorization, Cookie",
    )


async def _commit[T](session: AsyncSession, operation: Awaitable[T]) -> T:
    try:
        result = await operation
        await session.commit()
        return result
    except SpecialEquipmentColorValidationError as exc:
        await session.rollback()
        raise _color_http_exception(exc)
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        raise _http(exc)
    except IntegrityError as exc:
        await session.rollback()
        warehouse_error = commands.product_warehouse_error_from_integrity(exc)
        if warehouse_error is not None:
            raise _http(warehouse_error) from exc
        orig_text = str(getattr(exc, "orig", exc))
        if (
            "uq_se_units_lower_code" in orig_text
            or "uq_special_equipment_units_code" in orig_text
        ):
            raise HTTPException(
                status_code=409,
                detail={"detail": "Единица измерения с таким кодом уже существует", "code": "UNIT_CODE_CONFLICT"},
            ) from exc
        if "uq_se_units_lower_name" in orig_text:
            raise HTTPException(
                status_code=409,
                detail={"detail": "Единица измерения с таким названием уже существует", "code": "UNIT_NAME_CONFLICT"},
            ) from exc
        if (
            "uq_se_superstructures_code" in orig_text
            or "uq_special_equipment_superstructures_code" in orig_text
        ):
            raise HTTPException(
                status_code=409,
                detail={"detail": "Тип надстройки с таким кодом уже существует", "code": "SUPERSTRUCTURE_CODE_CONFLICT"},
                headers={"content-type": "application/problem+json"},
            ) from exc
        if (
            "uq_se_superstructures_name" in orig_text
            or "uq_se_superstructures_slug" in orig_text
            or "uq_se_superstructures_model_mod_name" in orig_text
            or "uq_se_superstructures_model_mod_slug" in orig_text
        ):
            raise HTTPException(
                status_code=409,
                detail={"detail": "Надстройка с таким названием уже существует", "code": "SUPERSTRUCTURE_NAME_CONFLICT"},
                headers={"content-type": "application/problem+json"},
            ) from exc
        raise HTTPException(
            status_code=409, detail="Конфликт уникальности или зависимости"
        )
    except BaseException:
        await session.rollback()
        raise


async def _discard_reserved_upload(
    *,
    storage_key: str,
    storage: ObjectStorage,
    session: AsyncSession,
) -> None:
    try:
        deleted = await asyncio.wait_for(
            asyncio.shield(storage.delete(storage_key)), timeout=5
        )
    except Exception:
        return
    if not deleted:
        return
    try:
        await _commit(
            session, commands.cancel_media_upload(session, storage_key)
        )
    except Exception:
        await session.rollback()


async def _read_and_store_image(
    *,
    owner: Literal["category", "product"],
    owner_id: UUID,
    file: UploadFile,
    storage: ObjectStorage,
    session: AsyncSession,
) -> str:
    data = await file.read(15 * 1024 * 1024 + 1)
    try:
        encoded = await encode_registry_image(
            filename=file.filename,
            content_type=file.content_type,
            data=data,
        )
    except RegistryImageValidationError as exc:
        raise _http(
            SpecialEquipmentManagementValidationError(str(exc))
        ) from exc
    storage_key = registry_image_storage_key(owner, owner_id)
    await _commit(
        session, commands.reserve_media_upload(session, storage_key)
    )
    try:
        await storage.put(storage_key, encoded, "image/webp")
    except BaseException:
        await _discard_reserved_upload(
            storage_key=storage_key,
            storage=storage,
            session=session,
        )
        raise
    return storage_key


async def _list(
    *,
    entity_type: EntityType,
    session: AsyncSession,
    page: int,
    page_size: int,
    search: str | None = None,
    mark_id: UUID | None = None,
    model_id: UUID | None = None,
    category_id: UUID | None = None,
    sale_status: SaleStatus | None = None,
    attribute_id: UUID | None = None,
    category_level_ids: tuple[UUID | None, ...] = (),
    sort: Literal["hierarchy", "updated_desc"] | None = None,
    attribute_group_id: UUID | None = None,
    normalization_state: Literal["normalized", "legacy", "conflict"] | None = None,
    role: Literal["attachment"] | None = None,
    modification_id: UUID | None = None,
    is_active: bool | None = None,
) -> JSONResponse:
    result = await handle_list(
        ListRegistryQuery(
            entity_type=entity_type,
            page=page,
            page_size=page_size,
            search=search,
            mark_id=mark_id,
            model_id=model_id,
            category_id=category_id,
            sale_status=sale_status,
            attribute_id=attribute_id,
            category_level_ids=category_level_ids,
            sort=sort,
            attribute_group_id=attribute_group_id,
            normalization_state=normalization_state,
            role=role,
            modification_id=modification_id,
            is_active=is_active,
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


async def _get(
    entity_type: EntityType, entity_id: UUID, session: AsyncSession
) -> JSONResponse:
    try:
        result = await handle_get(
            GetRegistryEntityQuery(entity_type, entity_id), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return _response(result)


def _trim_subresource_response(
    resource: dict[str, Any], *, items_key: str
) -> JSONResponse:
    response = JSONResponse(
        content=jsonable_encoder(
            {
                "items": resource.get(items_key, []),
                "lock_version": resource["lock_version"],
            }
        )
    )
    response.headers["ETag"] = special_equipment_management_etag(resource)
    return response


_TRIM_PROBLEM_STATUS = {
    "validation": 400,
    "conflict": 409,
    "not_found": 404,
    "precondition": 412,
}


def _trim_problem(exc: SpecialEquipmentTrimContractError) -> JSONResponse:
    status = (
        428
        if exc.code == "PRECONDITION_REQUIRED"
        else _TRIM_PROBLEM_STATUS[exc.kind]
    )
    extensions: dict[str, Any] = {}
    if exc.errors:
        extensions["errors"] = list(exc.errors)
    if exc.detail:
        extensions.update(exc.detail)
    return special_equipment_problem_response(
        status_code=status,
        detail=str(exc),
        code=exc.code,
        type_uri=f"urn:carcraft:problem:special-equipment:{exc.code.lower()}",
        title={
            400: "Некорректный запрос",
            404: "Ресурс не найден",
            409: "Конфликт состояния",
            412: "Предусловие не выполнено",
            428: "Требуется предусловие",
        }[status],
        extensions=extensions,
    )


def _trim_precondition(raw: str | None, trim_id: UUID) -> tuple[int, str]:
    if raw is None:
        raise SpecialEquipmentTrimContractError(
            "Требуется заголовок If-Match",
            code="PRECONDITION_REQUIRED",
            kind="precondition",
        )
    try:
        return _expected_precondition(raw, trim_id)
    except HTTPException as exc:
        raise SpecialEquipmentTrimContractError(
            "Заголовок If-Match некорректен или устарел",
            code="PRECONDITION_FAILED",
            kind="precondition",
        ) from exc


def _trim_state_response(
    result: dict[str, Any],
    payload: dict[str, Any],
    *,
    status_code: int = 200,
    location: str | None = None,
) -> JSONResponse:
    trim = result["trim"]
    response = JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(payload),
    )
    response.headers["ETag"] = special_equipment_trim_attributes_etag(
        trim_id=trim["id"],
        lock_version=trim["lock_version"],
        items=result["items"],
    )
    if location is not None:
        response.headers["Location"] = location
    return response


async def _trim_resource_response(
    resource: dict[str, Any],
    session: AsyncSession,
    *,
    status_code: int = 200,
) -> JSONResponse:
    state = await handle_trim_attributes(resource["id"], session)
    response = JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(resource),
    )
    response.headers["ETag"] = special_equipment_trim_attributes_etag(
        trim_id=resource["id"],
        lock_version=resource["lock_version"],
        items=state["items"],
    )
    return response


def _product_relations_response(
    result: dict[str, Any],
    *,
    status_code: int = 200,
    location: str | None = None,
) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code, content=jsonable_encoder(result["data"])
    )
    response.headers["ETag"] = special_equipment_management_etag(
        result["resource"]
    )
    if location is not None:
        response.headers["Location"] = location
    return response


def _product_relation_delete_response(result: dict[str, Any]) -> Response:
    response = Response(status_code=204)
    response.headers["ETag"] = special_equipment_management_etag(
        result["resource"]
    )
    return response


async def _get_product_relations(
    *,
    product_id: UUID,
    relation: Literal["compatible_attachments"],
    page: int,
    page_size: int,
    session: AsyncSession,
) -> JSONResponse:
    try:
        result = await handle_list_product_relations(
            ListProductRelationsQuery(
                product_id=product_id,
                relation=relation,
                page=page,
                page_size=page_size,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return _product_relations_response(result)


async def _create(
    *,
    entity_type: EntityType,
    values: dict,
    user: dict[str, Any],
    idempotency_key: str,
    session: AsyncSession,
) -> JSONResponse:
    command = (
        commands.create_product_idempotent(
            session,
            actor_id=_actor_id(user),
            idempotency_key=idempotency_key,
            request_hash=_idempotency_hash(entity_type, values),
            values=values,
        )
        if entity_type == "product"
        else commands.create_entity_idempotent(
            session,
            actor_id=_actor_id(user),
            idempotency_key=idempotency_key,
            request_hash=_idempotency_hash(entity_type, values),
            entity_type=entity_type,
            values=values,
        )
    )
    result = await _commit(
        session,
        command,
    )
    if entity_type == "product":
        result = result["product"]
    response = (
        await _trim_resource_response(result, session, status_code=201)
        if entity_type == "trim"
        else _response(result, status_code=201)
    )
    if entity_type == "attribute_option":
        response.headers["Location"] = (
            "/api/v1/admin/special-equipment/attributes/"
            f"{result['attribute_id']}/options/{result['id']}"
        )
    else:
        resource_path = {
            "category": "categories",
            "mark": "marks",
            "model": "models",
            "modification": "modifications",
            "trim": "trims",
            "attribute_group": "attribute-groups",
            "attribute": "attributes",
            "product": "products",
            "unit": "units",
            "superstructure": "superstructures",
        }[entity_type]
        response.headers["Location"] = (
            f"/api/v1/admin/special-equipment/{resource_path}/{result['id']}"
        )
    return response


async def _patch(
    *,
    entity_type: EntityType,
    entity_id: UUID,
    values: dict,
    if_match: str | None,
    session: AsyncSession,
) -> JSONResponse:
    expected_version, expected_etag = _expected_precondition(
        if_match, entity_id, problem=entity_type == "product"
    )
    result = await _commit(
        session,
        commands.patch_entity(
            session,
            entity_type=entity_type,
            entity_id=entity_id,
            values=values,
            expected_version=expected_version,
            expected_etag=expected_etag,
        ),
    )
    return _response(result)


async def _delete(
    *,
    entity_type: EntityType,
    entity_id: UUID,
    if_match: str | None,
    session: AsyncSession,
    user: WriteUser | None = None,
) -> Response:
    expected_version, expected_etag = _expected_precondition(if_match, entity_id)
    await _commit(
        session,
        commands.delete_entity(
            session,
            entity_type=entity_type,
            entity_id=entity_id,
            expected_version=expected_version,
            expected_etag=expected_etag,
            user_id=_actor_id(user) if user is not None else None,
        ),
    )
    return Response(status_code=204)


@router.get(
    "/seller-companies",
    response_model=SellerCompaniesResponse,
    summary="Продавцы спецтехники",
    description="Активные компании, доступные для товара.",
)
async def seller_companies(_user: ReadUser, session: Session) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(await handle_seller_companies(session)))


@router.get(
    "/colors/select",
    response_model=ColorSelectResponse,
    summary="Цвета для выпадающих списков",
    description=(
        "Активные цвета для поля кузова или салона. Требует vehicles:admin."
    ),
)
async def color_select(
    _user: VehicleAdminUser,
    session: Session,
    applicability: Literal["body", "interior"] = Query(...),
    search: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1),
) -> JSONResponse:
    try:
        normalized_search = search.strip() if search is not None else None
        result = await handle_select_colors(
            SelectColorsQuery(
                applicability=applicability,
                search=normalized_search or None,
                limit=min(limit, 100),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _color_http_exception(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/colors",
    response_model=ColorListResponse,
    summary="Цвета спецтехники",
    description="Административный список цветов с фильтрами и пагинацией.",
)
async def list_colors(
    _user: ReadUser,
    session: Session,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1),
    search: str | None = Query(None, max_length=100),
    applicability: Literal["body", "interior", "both"] | None = Query(None),
    is_active: bool | None = Query(None),
) -> JSONResponse:
    try:
        normalized_search = search.strip() if search is not None else None
        result = await handle_list(
            ListRegistryQuery(
                entity_type="color",
                page=page,
                page_size=min(page_size, 100),
                search=normalized_search or None,
                applicability=applicability,
                is_active=is_active,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _color_http_exception(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/colors/{color_id}",
    response_model=ColorResource,
    summary="Цвет спецтехники",
    description="Возвращает административную карточку цвета и актуальный ETag.",
)
async def get_color(
    color_id: UUID, _user: ReadUser, session: Session
) -> JSONResponse:
    try:
        result = await handle_get(GetRegistryEntityQuery("color", color_id), session)
    except (ServiceError, DomainError) as exc:
        raise _color_http_exception(exc)
    return _response(result)


@router.post(
    "/colors",
    response_model=ColorResource,
    status_code=201,
    summary="Создать цвет спецтехники",
    description="Создаёт цвет идемпотентно и возвращает Location и ETag.",
)
async def create_color(
    body: ColorCreateRequest,
    user: WriteUser,
    session: Session,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    values = body.model_dump(mode="json")
    result = await _commit_color(
        session,
        commands.create_color_idempotent(
            session,
            actor_id=_actor_id(user),
            idempotency_key=idempotency_key,
            request_hash=_idempotency_hash("color", values),
            values=values,
        ),
    )
    response = _response(result, status_code=201)
    response.headers["Location"] = (
        f"/api/v1/admin/special-equipment/colors/{result['id']}"
    )
    return response


@router.patch(
    "/colors/{color_id}",
    response_model=ColorResource,
    summary="Обновить цвет",
    description="Частично обновляет цвет при совпавшем обязательном If-Match.",
)
async def patch_color(
    color_id: UUID,
    body: ColorPatchRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    expected_version, expected_etag = _color_expected_precondition(if_match, color_id)
    result = await _commit_color(
        session,
        commands.update_color(
            session,
            color_id=color_id,
            values=body.model_dump(mode="json", exclude_unset=True),
            expected_version=expected_version,
            expected_etag=expected_etag,
        ),
    )
    return _response(result)


@router.delete(
    "/colors/{color_id}",
    response_model=None,
    status_code=204,
    summary="Удалить цвет",
    description="Удаляет неиспользуемый цвет при совпавшем обязательном If-Match.",
)
async def delete_color(
    color_id: UUID,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> Response:
    expected_version, expected_etag = _color_expected_precondition(if_match, color_id)
    await _commit_color(
        session,
        commands.delete_color(
            session,
            color_id=color_id,
            expected_version=expected_version,
            expected_etag=expected_etag,
        ),
    )
    return Response(status_code=204)


@router.get(
    "/categories",
    response_model=CategoryListResponse,
    summary="Категории",
    description="Список управляемых узлов DAG.",
)
async def categories(
    _user: ReadUser,
    session: Session,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    q: Annotated[str | None, Query(max_length=200)] = None,
    level_1_id: UUID | None = None,
    level_2_id: UUID | None = None,
    level_3_id: UUID | None = None,
    level_4_id: UUID | None = None,
    level_5_id: UUID | None = None,
    sort: Literal["hierarchy", "updated_desc"] = "hierarchy",
) -> JSONResponse:
    return await _list(
        entity_type="category",
        session=session,
        page=page,
        page_size=page_size,
        search=q,
        category_level_ids=(
            level_1_id,
            level_2_id,
            level_3_id,
            level_4_id,
            level_5_id,
        ),
        sort=sort,
    )


@router.post(
    "/categories",
    response_model=CategoryResource,
    status_code=201,
    summary="Создать категорию",
    description=(
        "Создаёт категорию для администратора каталога. Slug генерируется "
        "сервером, parent_ids проверяются как DAG; повтор с тем же "
        "Idempotency-Key возвращает исходный ресурс."
    ),
)
async def create_category(
    payload: CategoryCreateRequest,
    user: WriteUser,
    session: Session,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return await _create(
        entity_type="category",
        values=payload.model_dump(),
        user=user,
        idempotency_key=idempotency_key,
        session=session,
    )


@router.get(
    "/categories/{entity_id}",
    response_model=CategoryResource,
    summary="Категория",
    description="Детали узла DAG.",
)
async def get_category(
    entity_id: UUID, _user: ReadUser, session: Session
) -> JSONResponse:
    return await _get("category", entity_id, session)


@router.patch(
    "/categories/{entity_id}",
    response_model=CategoryResource,
    summary="Изменить категорию",
    description="Имя автоматически перегенерирует slug.",
)
async def patch_category(
    entity_id: UUID,
    payload: CategoryPatchRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    return await _patch(
        entity_type="category",
        entity_id=entity_id,
        values=payload.model_dump(exclude_unset=True),
        if_match=if_match,
        session=session,
    )


@router.put(
    "/categories/{entity_id}/parents",
    response_model=CategoryResource,
    summary="Заменить родителей категории",
    description="Операция сериализована advisory lock и отклоняет циклы.",
)
async def replace_category_parents(
    entity_id: UUID,
    payload: CategoryParentsReplaceRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    return await _patch(
        entity_type="category",
        entity_id=entity_id,
        values={"parent_ids": payload.parent_ids},
        if_match=if_match,
        session=session,
    )


@router.put(
    "/categories/{entity_id}/attributes",
    response_model=CategoryResource,
    summary="Заменить характеристики категории",
    description=(
        "Атомарно заменяет прямые связи категории с существующими "
        "характеристиками и группами. Требует право записи и актуальный "
        "If-Match; возвращает обновлённую категорию и новый ETag."
    ),
)
async def replace_category_attributes(
    entity_id: UUID,
    payload: CategoryAttributeLinksReplaceRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    expected_version, expected_etag = _expected_precondition(if_match, entity_id)
    result = await _commit(
        session,
        commands.replace_category_attributes(
            session,
            category_id=entity_id,
            links=[item.model_dump() for item in payload.items],
            expected_version=expected_version,
            expected_etag=expected_etag,
        ),
    )
    return _response(result)


@router.get(
    "/marks",
    response_model=MarkListResponse,
    summary="Марки",
    description="Каталог марок.",
)
async def marks(
    _user: ReadUser,
    session: Session,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> JSONResponse:
    return await _list(
        entity_type="mark",
        session=session,
        page=page,
        page_size=page_size,
        search=q,
    )


@router.post(
    "/marks",
    response_model=MarkResource,
    status_code=201,
    summary="Создать марку",
    description=(
        "Создаёт марку с неизменяемым code для администратора каталога; "
        "повтор с тем же Idempotency-Key возвращает исходный ресурс."
    ),
)
async def create_mark(
    payload: MarkCreateRequest,
    user: WriteUser,
    session: Session,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return await _create(
        entity_type="mark",
        values=payload.model_dump(),
        user=user,
        idempotency_key=idempotency_key,
        session=session,
    )


@router.get(
    "/marks/{entity_id}",
    response_model=MarkResource,
    summary="Марка",
    description="Детали марки.",
)
async def get_mark(
    entity_id: UUID, _user: ReadUser, session: Session
) -> JSONResponse:
    return await _get("mark", entity_id, session)


@router.patch(
    "/marks/{entity_id}",
    response_model=MarkResource,
    summary="Изменить марку",
    description="Slug перегенерируется при изменении имени.",
)
async def patch_mark(
    entity_id: UUID,
    payload: MarkPatchRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    return await _patch(
        entity_type="mark",
        entity_id=entity_id,
        values=payload.model_dump(exclude_unset=True),
        if_match=if_match,
        session=session,
    )


@router.get(
    "/models",
    response_model=ModelListResponse,
    summary="Модели",
    description="Фильтруется по mark_id.",
)
async def models(
    _user: ReadUser,
    session: Session,
    mark_id: Annotated[UUID, Query(description="Марка для каскадного списка")],
    q: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> JSONResponse:
    return await _list(
        entity_type="model",
        session=session,
        page=page,
        page_size=page_size,
        search=q,
        mark_id=mark_id,
    )


@router.post(
    "/models",
    response_model=ModelResource,
    status_code=201,
    summary="Создать модель",
    description=(
        "Создаёт модель существующей марки для администратора каталога; "
        "повтор с тем же Idempotency-Key возвращает исходный ресурс."
    ),
)
async def create_model(
    payload: ModelCreateRequest,
    user: WriteUser,
    session: Session,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return await _create(
        entity_type="model",
        values=payload.model_dump(),
        user=user,
        idempotency_key=idempotency_key,
        session=session,
    )


@router.get(
    "/models/{entity_id}",
    response_model=ModelResource,
    summary="Модель",
    description="Детали модели.",
)
async def get_model(
    entity_id: UUID, _user: ReadUser, session: Session
) -> JSONResponse:
    return await _get("model", entity_id, session)


@router.patch(
    "/models/{entity_id}",
    response_model=ModelResource,
    summary="Изменить модель",
    description="Проверяет существование выбранной марки.",
)
async def patch_model(
    entity_id: UUID,
    payload: ModelPatchRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    return await _patch(
        entity_type="model",
        entity_id=entity_id,
        values=payload.model_dump(exclude_unset=True),
        if_match=if_match,
        session=session,
    )


@router.get(
    "/modifications",
    response_model=ModificationListResponse,
    summary="Модификации",
    description="Фильтруется по model_id.",
)
async def modifications(
    _user: ReadUser,
    session: Session,
    model_id: Annotated[
        UUID, Query(description="Модель для каскадного списка")
    ],
    q: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> JSONResponse:
    return await _list(
        entity_type="modification",
        session=session,
        page=page,
        page_size=page_size,
        search=q,
        model_id=model_id,
    )


@router.post(
    "/modifications",
    response_model=ModificationResource,
    status_code=201,
    summary="Создать модификацию",
    description=(
        "Создаёт модификацию для администратора каталога, сохраняет категории "
        "и live-значения характеристик; повтор с тем же Idempotency-Key "
        "возвращает исходный ресурс."
    ),
)
async def create_modification(
    payload: ModificationCreateRequest,
    user: WriteUser,
    session: Session,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return await _create(
        entity_type="modification",
        values=payload.model_dump(),
        user=user,
        idempotency_key=idempotency_key,
        session=session,
    )


@router.get(
    "/modifications/{entity_id}",
    response_model=ModificationResource,
    summary="Модификация",
    description="Детали модификации и её live характеристик.",
)
async def get_modification(
    entity_id: UUID, _user: ReadUser, session: Session
) -> JSONResponse:
    return await _get("modification", entity_id, session)


@router.patch(
    "/modifications/{entity_id}",
    response_model=ModificationResource,
    summary="Изменить модификацию",
    description="Проверяет диапазон годов и зависимые каталоги.",
)
async def patch_modification(
    entity_id: UUID,
    payload: ModificationPatchRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    return await _patch(
        entity_type="modification",
        entity_id=entity_id,
        values=payload.model_dump(exclude_unset=True),
        if_match=if_match,
        session=session,
    )


@router.get(
    "/trims",
    response_model=TrimListResponse,
    summary="Комплектации",
    description="Возвращает компактный список комплектаций одной модификации.",
)
async def trims(
    _user: ReadUser,
    session: Session,
    modification_id: Annotated[UUID, Query()],
) -> JSONResponse:
    return JSONResponse(
        content=jsonable_encoder(
            await handle_list_trim_lifecycle_items(modification_id, session)
        )
    )


@router.post(
    "/trims",
    response_model=TrimCreateResponse,
    status_code=201,
    summary="Создать комплектацию",
    description=(
        "Создаёт пустую комплектацию внутри активной модификации; "
        "повтор с тем же Idempotency-Key возвращает исходный ресурс."
    ),
)
async def create_trim(
    payload: TrimCreateRequest,
    user: WriteUser,
    session: Session,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    values = payload.model_dump()
    try:
        result = await commands.create_entity_idempotent(
            session,
            actor_id=_actor_id(user),
            idempotency_key=idempotency_key,
            request_hash=_idempotency_hash("trim", values),
            entity_type="trim",
            values=values,
        )
        await session.commit()
    except SpecialEquipmentTrimContractError as exc:
        await session.rollback()
        return _trim_problem(exc)
    except IntegrityError as exc:
        await session.rollback()
        constraint = getattr(getattr(exc, "orig", None), "diag", None)
        constraint_name = str(
            getattr(constraint, "constraint_name", None)
            or getattr(getattr(exc, "orig", None), "constraint_name", None)
            or exc
        )
        if any(
            name in constraint_name
            for name in (
                "uq_se_trims_modification_name_normalized",
                "uq_se_trims_modification_slug_normalized",
            )
        ):
            return _trim_problem(
                SpecialEquipmentTrimContractError(
                    "Комплектация с таким названием уже существует",
                    code="TRIM_NAME_ALREADY_EXISTS",
                    kind="conflict",
                )
            )
        return _trim_problem(
            SpecialEquipmentTrimContractError(
                "Активная модификация не найдена",
                code="MODIFICATION_NOT_FOUND",
                kind="not_found",
            )
        )
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        raise _http(exc)
    except BaseException:
        await session.rollback()
        raise
    response_payload = {
        "id": result["id"],
        "modification_id": result["modification_id"],
        "name": result["name"],
        "is_active": result["is_active"],
    }
    return JSONResponse(
        content=jsonable_encoder(response_payload),
        status_code=201,
        headers={
            "Location": (
                "/api/v1/admin/special-equipment/trims/"
                f"{result['id']}"
            )
        },
    )


@router.get(
    "/trims/{entity_id}",
    response_model=TrimResource,
    summary="Комплектация",
    description="Детали комплектации, её характеристик и значений.",
)
async def get_trim(entity_id: UUID, _user: ReadUser, session: Session) -> JSONResponse:
    try:
        result = await handle_get(GetRegistryEntityQuery("trim", entity_id), session)
    except (ServiceError, DomainError) as exc:
        error = domain_to_http(exc) if isinstance(exc, DomainError) else exc
        if error.status_code == 404:
            return _trim_problem(
                SpecialEquipmentTrimContractError(
                    "Комплектация не найдена",
                    code="TRIM_NOT_FOUND",
                    kind="not_found",
                )
            )
        raise _http(exc)
    return await _trim_resource_response(result, session)


@router.patch(
    "/trims/{entity_id}",
    response_model=TrimResource,
    summary="Изменить комплектацию",
    description="Проверяет модификацию, связи характеристик и If-Match.",
)
async def patch_trim(
    entity_id: UUID,
    payload: TrimPatchRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    try:
        expected_version, expected_etag = _trim_precondition(if_match, entity_id)
    except SpecialEquipmentTrimContractError as exc:
        return _trim_problem(exc)
    try:
        result = await commands.patch_entity(
            session,
            entity_type="trim",
            entity_id=entity_id,
            values=payload.model_dump(exclude_unset=True),
            expected_version=expected_version,
            expected_etag=expected_etag,
        )
        await session.commit()
    except SpecialEquipmentTrimContractError as exc:
        await session.rollback()
        return _trim_problem(exc)
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        error = domain_to_http(exc) if isinstance(exc, DomainError) else exc
        return _trim_problem(
            SpecialEquipmentTrimContractError(
                str(error),
                code=(
                    "TRIM_NOT_FOUND"
                    if error.status_code == 404
                    else "VALIDATION_ERROR"
                ),
                kind="not_found" if error.status_code == 404 else "validation",
            )
        )
    return await _trim_resource_response(result, session)


@router.get(
    "/attribute-groups",
    response_model=AttributeGroupListResponse,
    summary="Группы характеристик",
    description="Явный каталог групп.",
)
async def attribute_groups(
    _user: ReadUser,
    session: Session,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> JSONResponse:
    return await _list(
        entity_type="attribute_group",
        session=session,
        page=page,
        page_size=page_size,
        search=q,
    )


@router.post(
    "/attribute-groups",
    response_model=AttributeGroupResource,
    status_code=201,
    summary="Создать группу характеристик",
    description=(
        "Создаёт явную группу характеристик для администратора каталога без "
        "неявных связей; повтор с тем же Idempotency-Key возвращает исходный "
        "ресурс."
    ),
)
async def create_attribute_group(
    payload: AttributeGroupCreateRequest,
    user: WriteUser,
    session: Session,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return await _create(
        entity_type="attribute_group",
        values=payload.model_dump(),
        user=user,
        idempotency_key=idempotency_key,
        session=session,
    )


@router.get(
    "/attribute-groups/{entity_id}",
    response_model=AttributeGroupResource,
    summary="Группа характеристик",
    description="Детали группы.",
)
async def get_attribute_group(
    entity_id: UUID, _user: ReadUser, session: Session
) -> JSONResponse:
    return await _get("attribute_group", entity_id, session)


@router.patch(
    "/attribute-groups/{entity_id}",
    response_model=AttributeGroupResource,
    summary="Изменить группу",
    description="Slug перегенерируется при изменении имени.",
)
async def patch_attribute_group(
    entity_id: UUID,
    payload: AttributeGroupPatchRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    return await _patch(
        entity_type="attribute_group",
        entity_id=entity_id,
        values=payload.model_dump(exclude_unset=True),
        if_match=if_match,
        session=session,
    )


@router.get(
    "/units",
    response_model=UnitListResponse,
    summary="Единицы измерения",
    description="Явный каталог единиц измерения.",
)
async def units(
    _user: ReadUser,
    session: Session,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    q: Annotated[str | None, Query(max_length=200)] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> JSONResponse:
    return await _list(
        entity_type="unit",
        session=session,
        page=page,
        page_size=page_size,
        search=q,
        is_active=is_active,
    )


@router.post(
    "/units",
    response_model=UnitResource,
    status_code=201,
    summary="Создать единицу измерения",
    description=(
        "Создаёт единицу измерения для администратора каталога; "
        "повтор с тем же Idempotency-Key возвращает исходный ресурс."
    ),
)
async def create_unit(
    payload: UnitCreateRequest,
    user: WriteUser,
    session: Session,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return await _create(
        entity_type="unit",
        values=payload.model_dump(),
        user=user,
        idempotency_key=idempotency_key,
        session=session,
    )


@router.get(
    "/units/{entity_id}",
    response_model=UnitResource,
    summary="Единица измерения",
    description="Детали единицы измерения.",
)
async def get_unit(
    entity_id: UUID, _user: ReadUser, session: Session
) -> JSONResponse:
    return await _get("unit", entity_id, session)


@router.patch(
    "/units/{entity_id}",
    response_model=UnitResource,
    summary="Изменить единицу измерения",
    description="Slug перегенерируется при изменении имени.",
)
async def patch_unit(
    entity_id: UUID,
    payload: UnitPatchRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    return await _patch(
        entity_type="unit",
        entity_id=entity_id,
        values=payload.model_dump(exclude_unset=True),
        if_match=if_match,
        session=session,
    )


@router.post(
    "/units/{entity_id}/merge",
    response_model=UnitResource,
    summary="Объединить единицу измерения",
    description="Перепривязывает все характеристики к целевой единице и удаляет исходную.",
)
async def merge_unit(
    entity_id: UUID,
    payload: UnitMergeRequest,
    user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    expected_version, expected_etag = _expected_precondition(if_match, entity_id)
    result = await _commit(
        session,
        commands.merge_unit(
            session=session,
            source_unit_id=entity_id,
            target_unit_id=payload.target_unit_id,
            target_expected_version=payload.target_lock_version,
            expected_version=expected_version,
            expected_etag=expected_etag,
            user_id=_actor_id(user),
        ),
    )
    return _response(result)


@router.get(
    "/superstructures",
    response_model=SuperstructureListResponse,
    summary="Надстройки",
    description="Справочник надстроек спецтехники.",
)
async def superstructures(
    _user: ReadUser,
    session: Session,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    q: Annotated[str | None, Query(max_length=200)] = None,
    mark_id: Annotated[UUID | None, Query()] = None,
    model_id: Annotated[UUID | None, Query()] = None,
    modification_id: Annotated[UUID | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> JSONResponse:
    return await _list(
        entity_type="superstructure",
        session=session,
        page=page,
        page_size=page_size,
        search=q,
        mark_id=mark_id,
        model_id=model_id,
        modification_id=modification_id,
        is_active=is_active,
    )


@router.post(
    "/superstructures",
    response_model=SuperstructureResource,
    status_code=201,
    summary="Создать надстройку",
    description=(
        "Создаёт надстройку для администратора каталога; "
        "повтор с тем же Idempotency-Key возвращает исходный ресурс."
    ),
)
async def create_superstructure(
    payload: SuperstructureCreateRequest,
    user: WriteUser,
    session: Session,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return await _create(
        entity_type="superstructure",
        values=payload.model_dump(),
        user=user,
        idempotency_key=idempotency_key,
        session=session,
    )


@router.get(
    "/superstructures/attribute-candidates",
    response_model=SuperstructureAttributeCandidatesResponse,
    summary="Кандидаты характеристик надстроек",
    description="Возвращает активные характеристики выбранной группы для добавления в надстройку.",
)
async def superstructure_attribute_candidates(
    _user: ReadUser,
    session: Session,
    group_id: Annotated[UUID, Query(description="ID группы характеристик")],
) -> SuperstructureAttributeCandidatesResponse:
    items = await handle_superstructure_attribute_candidates(group_id, session)
    return SuperstructureAttributeCandidatesResponse(items=items)


@router.get(
    "/superstructures/{entity_id}",
    response_model=SuperstructureResource,
    summary="Надстройка",
    description="Детали надстройки.",
)
async def get_superstructure(
    entity_id: UUID, _user: ReadUser, session: Session
) -> JSONResponse:
    return await _get("superstructure", entity_id, session)


@router.patch(
    "/superstructures/{entity_id}",
    response_model=SuperstructureResource,
    summary="Изменить надстройку",
    description="Изменяет надстройку спецтехники.",
)
async def patch_superstructure(
    entity_id: UUID,
    payload: SuperstructurePatchRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    return await _patch(
        entity_type="superstructure",
        entity_id=entity_id,
        values=payload.model_dump(exclude_unset=True),
        if_match=if_match,
        session=session,
    )


@router.get(
    "/modifications/{entity_id}/trim-attribute-candidates",
    response_model=TrimAttributeCandidatesResponse,
    summary="Предпросмотр характеристик комплектации",
    description=(
        "Возвращает read-only кандидатов комплектации по модификации до "
        "создания самой комплектации."
    ),
)
async def modification_trim_attribute_candidates(
    entity_id: UUID,
    _user: ReadUser,
    session: Session,
) -> JSONResponse:
    try:
        result = await resolve_trim_attribute_candidates(entity_id, session)
    except SpecialEquipmentTrimContractError as exc:
        return _trim_problem(exc)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/trims/{entity_id}/attribute-candidates",
    response_model=TrimAttributeCandidatesResponse,
    summary="Кандидаты характеристик комплектации",
    description=(
        "Возвращает сгруппированные характеристики выбранной модификации, "
        "доступные для назначения комплектации."
    ),
)
async def trim_attribute_candidates(
    entity_id: UUID,
    _user: ReadUser,
    session: Session,
) -> JSONResponse:
    try:
        result = await handle_trim_attribute_candidates(entity_id, session)
    except SpecialEquipmentTrimContractError as exc:
        return _trim_problem(exc)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/trims/{entity_id}/attributes",
    response_model=TrimAttributesResponse,
    summary="Характеристики комплектации",
    description=(
        "Возвращает назначенные комплектации характеристики и ETag текущей версии."
    ),
)
async def trim_attributes(
    entity_id: UUID,
    _user: ReadUser,
    session: Session,
) -> JSONResponse:
    try:
        state = await handle_trim_attributes(entity_id, session)
        trim = await handle_get(GetRegistryEntityQuery("trim", entity_id), session)
    except SpecialEquipmentTrimContractError as exc:
        return _trim_problem(exc)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return _trim_state_response(
        {"trim": trim, "items": state["items"]},
        {"items": state["items"]},
    )


@router.post(
    "/trims/{entity_id}/attributes",
    response_model=TrimAttributeCreateResponse,
    status_code=201,
    summary="Назначить характеристику комплектации",
    description=(
        "Добавляет одну доступную пару attribute/group; требует актуальный "
        "сильный If-Match из GET attributes."
    ),
)
async def add_trim_attribute(
    entity_id: UUID,
    payload: TrimAttributeLinkInput,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    try:
        expected_version, expected_etag = _trim_precondition(if_match, entity_id)
    except SpecialEquipmentTrimContractError as exc:
        return _trim_problem(exc)
    try:
        result = await commands.add_trim_attribute(
            session,
            trim_id=entity_id,
            link=payload.model_dump(),
            expected_version=expected_version,
            expected_etag=expected_etag,
        )
        await session.commit()
    except SpecialEquipmentTrimContractError as exc:
        await session.rollback()
        return _trim_problem(exc)
    except IntegrityError:
        await session.rollback()
        return _trim_problem(
            SpecialEquipmentTrimContractError(
                "Характеристика уже назначена комплектации",
                code="ATTRIBUTE_ALREADY_ASSIGNED",
                kind="conflict",
            )
        )
    return _trim_state_response(
        result,
        {"item": result["item"]},
        status_code=201,
        location=(
            f"/api/v1/admin/special-equipment/trims/{entity_id}/attributes/"
            f"{payload.attribute_id}"
        ),
    )


@router.delete(
    "/trims/{entity_id}/attributes/{attribute_id}",
    status_code=204,
    response_model=None,
    summary="Снять характеристику комплектации",
    description=(
        "Удаляет назначение и его значение; отсутствие назначения является no-op."
    ),
)
async def delete_trim_attribute(
    entity_id: UUID,
    attribute_id: UUID,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> Response:
    try:
        expected_version, expected_etag = _trim_precondition(if_match, entity_id)
    except SpecialEquipmentTrimContractError as exc:
        return _trim_problem(exc)
    try:
        result = await commands.delete_trim_attribute_assignment(
            session,
            trim_id=entity_id,
            attribute_id=attribute_id,
            expected_version=expected_version,
            expected_etag=expected_etag,
        )
        await session.commit()
    except SpecialEquipmentTrimContractError as exc:
        await session.rollback()
        return _trim_problem(exc)
    response = Response(status_code=204)
    response.headers["ETag"] = special_equipment_trim_attributes_etag(
        trim_id=entity_id,
        lock_version=result["trim"]["lock_version"],
        items=result["items"],
    )
    return response


@router.get(
    "/trims/{entity_id}/attribute-values",
    response_model=TrimAttributeValuesLegacyResponse,
    summary="Значения характеристик комплектации",
    description=(
        "Возвращает значения назначенных характеристик и ETag текущей версии."
    ),
)
async def trim_attribute_values(
    entity_id: UUID,
    _user: ReadUser,
    session: Session,
) -> JSONResponse:
    try:
        result = await handle_get(GetRegistryEntityQuery("trim", entity_id), session)
        state = await handle_trim_attributes(entity_id, session)
    except (ServiceError, DomainError) as exc:
        error = domain_to_http(exc) if isinstance(exc, DomainError) else exc
        if error.status_code == 404:
            return _trim_problem(
                SpecialEquipmentTrimContractError(
                    "Комплектация не найдена",
                    code="TRIM_NOT_FOUND",
                    kind="not_found",
                )
            )
        raise _http(exc)
    return _trim_state_response(
        {"trim": result, "items": state["items"]},
        {
            "items": result.get("attribute_values", []),
            "lock_version": result["lock_version"],
        },
    )


@router.put(
    "/trims/{entity_id}/attribute-values",
    response_model=TrimAttributeValuesResponse,
    summary="Заменить значения характеристик комплектации",
    description="Атомарно изменяет только переданные значения; требуется If-Match.",
)
async def patch_trim_attribute_values(
    entity_id: UUID,
    payload: TrimAttributeValuesReplaceRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    try:
        expected_version, expected_etag = _trim_precondition(if_match, entity_id)
    except SpecialEquipmentTrimContractError as exc:
        return _trim_problem(exc)
    try:
        result = await commands.patch_trim_attribute_values(
            session,
            trim_id=entity_id,
            values=[item.model_dump() for item in payload.values],
            expected_version=expected_version,
            expected_etag=expected_etag,
        )
        await session.commit()
    except SpecialEquipmentTrimContractError as exc:
        await session.rollback()
        return _trim_problem(exc)
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        return _trim_problem(
            SpecialEquipmentTrimContractError(
                str(exc), code="VALIDATION_ERROR", kind="validation"
            )
        )
    return _trim_state_response(
        result,
        {"saved": result["saved"]},
    )


@router.get(
    "/attributes",
    response_model=AttributeListResponse,
    summary="Характеристики",
    description="Каталог typed характеристик.",
)
async def attributes(
    _user: ReadUser,
    session: Session,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    q: Annotated[str | None, Query(max_length=200)] = None,
    attribute_group_id: UUID | None = None,
) -> JSONResponse:
    return await _list(
        entity_type="attribute",
        session=session,
        page=page,
        page_size=page_size,
        search=q,
        attribute_group_id=attribute_group_id,
    )


@router.post(
    "/attributes",
    response_model=AttributeResource,
    status_code=201,
    summary="Создать характеристику",
    description=(
        "Создаёт типизированную характеристику для администратора каталога; "
        "code после создания неизменяем, а тип можно безопасно изменить "
        "через PATCH с явным подтверждением конверсии; повтор с тем же "
        "Idempotency-Key возвращает исходный ресурс."
    ),
)
async def create_attribute(
    payload: AttributeCreateRequest,
    user: WriteUser,
    session: Session,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return await _create(
        entity_type="attribute",
        values=payload.model_dump(),
        user=user,
        idempotency_key=idempotency_key,
        session=session,
    )


@router.get(
    "/attributes/{entity_id}",
    response_model=AttributeResource,
    summary="Характеристика",
    description="Детали и варианты select.",
)
async def get_attribute(
    entity_id: UUID, _user: ReadUser, session: Session
) -> JSONResponse:
    return await _get("attribute", entity_id, session)


@router.patch(
    "/attributes/{entity_id}",
    response_model=AttributeResource,
    summary="Изменить характеристику",
    description=(
        "Изменяет характеристику. Смена типа с сохранёнными значениями "
        "требует confirm_type_conversion; безопасно поддерживается text → select."
    ),
)
async def patch_attribute(
    entity_id: UUID,
    payload: AttributePatchRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    return await _patch(
        entity_type="attribute",
        entity_id=entity_id,
        values=payload.model_dump(exclude_unset=True),
        if_match=if_match,
        session=session,
    )


@router.post(
    "/attributes/{attribute_id}/options",
    response_model=AttributeOptionResource,
    status_code=201,
    summary="Создать вариант",
    description=(
        "Создаёт вариант существующей select-характеристики для администратора "
        "каталога; повтор с тем же Idempotency-Key возвращает исходный ресурс."
    ),
)
async def create_attribute_option(
    attribute_id: UUID,
    payload: AttributeOptionCreateRequest,
    user: WriteUser,
    session: Session,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return await _create(
        entity_type="attribute_option",
        values={"attribute_id": attribute_id, **payload.model_dump()},
        user=user,
        idempotency_key=idempotency_key,
        session=session,
    )


@router.get(
    "/attributes/{attribute_id}/options",
    response_model=AttributeOptionListResponse,
    summary="Варианты характеристики",
    description="Список существующих вариантов select-характеристики.",
)
async def attribute_options(
    attribute_id: UUID,
    _user: ReadUser,
    session: Session,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
) -> JSONResponse:
    return await _list(
        entity_type="attribute_option",
        session=session,
        page=page,
        page_size=page_size,
        attribute_id=attribute_id,
    )


@router.get(
    "/attributes/{attribute_id}/options/{entity_id}",
    response_model=AttributeOptionResource,
    summary="Вариант характеристики",
    description="Детали существующего варианта.",
)
async def get_attribute_option(
    attribute_id: UUID,
    entity_id: UUID,
    _user: ReadUser,
    session: Session,
) -> JSONResponse:
    try:
        result = await handle_get(
            GetRegistryEntityQuery("attribute_option", entity_id), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    if result["attribute_id"] != attribute_id:
        raise HTTPException(status_code=404, detail="Вариант не найден")
    return _response(result)


@router.patch(
    "/attributes/{attribute_id}/options/{entity_id}",
    response_model=AttributeOptionResource,
    summary="Изменить вариант",
    description="Code варианта неизменяем.",
)
async def patch_attribute_option(
    attribute_id: UUID,
    entity_id: UUID,
    payload: AttributeOptionPatchRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    current = await handle_get(
        GetRegistryEntityQuery("attribute_option", entity_id), session
    )
    if current["attribute_id"] != attribute_id:
        raise HTTPException(status_code=404, detail="Вариант не найден")
    return await _patch(
        entity_type="attribute_option",
        entity_id=entity_id,
        values=payload.model_dump(exclude_unset=True),
        if_match=if_match,
        session=session,
    )


@router.delete(
    "/attributes/{attribute_id}/options/{entity_id}",
    status_code=204,
    response_model=None,
    summary="Удалить вариант",
    description="Удаляет вариант без зависимых значений модификаций.",
)
async def delete_attribute_option(
    attribute_id: UUID,
    entity_id: UUID,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> Response:
    current = await handle_get(
        GetRegistryEntityQuery("attribute_option", entity_id), session
    )
    if current["attribute_id"] != attribute_id:
        raise HTTPException(status_code=404, detail="Вариант не найден")
    return await _delete(
        entity_type="attribute_option",
        entity_id=entity_id,
        if_match=if_match,
        session=session,
    )


@router.get(
    "/products",
    response_model=ProductListResponse,
    summary="Товары",
    description="Управляемые объявления спецтехники.",
)
async def products(
    _user: ReadUser,
    session: Session,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    q: Annotated[str | None, Query(max_length=200)] = None,
    normalization_state: Literal["normalized", "legacy", "conflict"] | None = None,
    role: Literal["attachment"] | None = None,
    mark_id: UUID | None = None,
    model_id: UUID | None = None,
    category_id: UUID | None = None,
    level_1_id: UUID | None = None,
    level_2_id: UUID | None = None,
    level_3_id: UUID | None = None,
    level_4_id: UUID | None = None,
    level_5_id: UUID | None = None,
    sale_status: SaleStatus | None = None,
) -> JSONResponse:
    return await _list(
        entity_type="product",
        session=session,
        page=page,
        page_size=page_size,
        search=q,
        normalization_state=normalization_state,
        role=role,
        mark_id=mark_id,
        model_id=model_id,
        category_id=category_id,
        category_level_ids=(
            level_1_id,
            level_2_id,
            level_3_id,
            level_4_id,
            level_5_id,
        ),
        sale_status=sale_status,
    )


@router.post(
    "/products",
    response_model=ProductResource,
    status_code=201,
    summary="Создать товар",
    description=(
        "Создаёт товар для администратора каталога; марка и модель выводятся "
        "из выбранной модификации, повтор с тем же Idempotency-Key возвращает "
        "исходный ресурс."
    ),
)
async def create_product(
    payload: ProductCreateRequest,
    user: WriteUser,
    session: Session,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return await _create(
        entity_type="product",
        values=payload.model_dump(),
        user=user,
        idempotency_key=idempotency_key,
        session=session,
    )


@router.get(
    "/products/attachment-sources",
    response_model=AttachmentSourcesResponse,
    summary="Источники надстроек для комплекта",
    description="Возвращает опубликованные и черновые надстройки для создания комплекта техники.",
)
async def list_attachment_sources(
    _user: ReadUser,
    session: Session,
    model_id: Annotated[UUID, Query(description="Идентификатор модели")],
    modification_id: Annotated[UUID | None, Query(description="Идентификатор модификации")] = None,
    exclude_product_id: Annotated[UUID | None, Query(description="Исключить товар из результатов")] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> JSONResponse:
    items = await handle_list_attachment_sources(
        ListAttachmentSourcesQuery(
            model_id=model_id,
            modification_id=modification_id,
            exclude_product_id=exclude_product_id,
            search=search,
            limit=limit,
        ),
        session,
    )
    return JSONResponse(
        content=AttachmentSourcesResponse(items=items).model_dump(mode="json")
    )


@router.get(
    "/products/{entity_id}",
    response_model=ProductResource,
    summary="Товар",
    description="Детали объявления.",
)
async def get_product(
    entity_id: UUID, _user: ReadUser, session: Session
) -> JSONResponse:
    return await _get("product", entity_id, session)


@router.patch(
    "/products/{entity_id}",
    response_model=ProductResource,
    summary="Изменить товар",
    description="Проверяет категории, метрику и commerce-owned statuses.",
)
async def patch_product(
    entity_id: UUID,
    payload: ProductPatchRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    return await _patch(
        entity_type="product",
        entity_id=entity_id,
        values=payload.model_dump(exclude_unset=True),
        if_match=if_match,
        session=session,
    )


@router.put(
    "/products/{product_id}/warehouse",
    response_model=ProductResource,
    summary="Заменить склад товара",
    description=(
        "Заменяет только связь товара со складом. Требует точный сильный ETag "
        "текущего товара в If-Match; товару с VIN необходим активный склад."
    ),
)
async def replace_product_warehouse(
    product_id: UUID,
    payload: ProductWarehouseReplaceRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    expected_version, expected_etag = _expected_precondition(
        if_match, product_id, problem=True
    )
    product = await _commit(
        session,
        commands.replace_product_warehouse(
            session,
            product_id=product_id,
            warehouse_id=payload.warehouse_id,
            expected_version=expected_version,
            expected_etag=expected_etag,
        ),
    )
    return _response(product)


@router.get(
    "/products/{entity_id}/compatible-attachments",
    response_model=CompatibleAttachmentsResponse,
    summary="Совместимые надстройки товара",
    description=(
        "Возвращает полный упорядоченный административный список связей и "
        "ETag товара-владельца. Требует право чтения каталога."
    ),
)
async def product_compatible_attachments(
    entity_id: UUID,
    _user: ReadUser,
    session: Session,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
) -> JSONResponse:
    return await _get_product_relations(
        product_id=entity_id,
        relation="compatible_attachments",
        page=page,
        page_size=page_size,
        session=session,
    )


@router.put(
    "/products/{entity_id}/compatible-attachments",
    response_model=CompatibleAttachmentsResponse,
    summary="Заменить совместимые надстройки товара",
    description=(
        "Атомарно заменяет упорядоченную совместимость конкретного обычного "
        "несоставного товара. Требует право записи и актуальный If-Match."
    ),
)
async def replace_product_compatible_attachments(
    entity_id: UUID,
    payload: CompatibleAttachmentsReplaceRequest,
    user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    expected_version, expected_etag = _expected_precondition(if_match, entity_id)
    result = await _commit(
        session,
        commands.replace_compatible_attachments(
            session,
            product_id=entity_id,
            links=[item.model_dump() for item in payload.items],
            actor_id=_actor_id(user),
            expected_version=expected_version,
            expected_etag=expected_etag,
        ),
    )
    return _product_relations_response(result)


@router.post(
    "/products/{entity_id}/compatible-attachments",
    response_model=CompatibleAttachmentsResponse,
    status_code=201,
    summary="Добавить совместимую надстройку",
    description=(
        "Добавляет одну связь в конечный упорядоченный набор. Требует право "
        "записи и актуальный If-Match товара-владельца."
    ),
)
async def create_product_compatible_attachment(
    entity_id: UUID,
    payload: CompatibleAttachmentCreateRequest,
    user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    expected_version, expected_etag = _expected_precondition(if_match, entity_id)
    result = await _commit(
        session,
        commands.create_compatible_attachment(
            session,
            product_id=entity_id,
            attachment_product_id=payload.attachment_product_id,
            position=payload.position,
            actor_id=_actor_id(user),
            expected_version=expected_version,
            expected_etag=expected_etag,
        ),
    )
    return _product_relations_response(
        result,
        status_code=201,
        location=(
            f"/api/v1/admin/special-equipment/products/{entity_id}/"
            f"compatible-attachments/{payload.attachment_product_id}"
        ),
    )


@router.patch(
    "/products/{entity_id}/compatible-attachments/{attachment_product_id}",
    response_model=CompatibleAttachmentsResponse,
    summary="Изменить позицию совместимой надстройки",
    description=(
        "Меняет позицию одной связи, сохраняя итоговую совместимость атомарно. "
        "Требует право записи и актуальный If-Match товара-владельца."
    ),
)
async def patch_product_compatible_attachment(
    entity_id: UUID,
    attachment_product_id: UUID,
    payload: CompatibleAttachmentPatchRequest,
    user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    expected_version, expected_etag = _expected_precondition(if_match, entity_id)
    result = await _commit(
        session,
        commands.patch_compatible_attachment(
            session,
            product_id=entity_id,
            attachment_product_id=attachment_product_id,
            position=payload.position,
            actor_id=_actor_id(user),
            expected_version=expected_version,
            expected_etag=expected_etag,
        ),
    )
    return _product_relations_response(result)


@router.delete(
    "/products/{entity_id}/compatible-attachments/{attachment_product_id}",
    status_code=204,
    summary="Удалить совместимость с надстройкой",
    description="Удаляет только связь, но не товар-надстройку.",
)
async def delete_product_compatible_attachment(
    entity_id: UUID,
    attachment_product_id: UUID,
    user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> Response:
    expected_version, expected_etag = _expected_precondition(if_match, entity_id)
    result = await _commit(
        session,
        commands.delete_compatible_attachment(
            session,
            product_id=entity_id,
            attachment_product_id=attachment_product_id,
            actor_id=_actor_id(user),
            expected_version=expected_version,
            expected_etag=expected_etag,
        ),
    )
    return _product_relation_delete_response(result)


@router.put(
    "/categories/{category_id}/image",
    response_model=MediaUploadResponse,
    summary="Загрузить изображение категории",
    description=(
        "Проверяет файл, сохраняет приватный WebP и возвращает обновлённую "
        "категорию администратору. Требует право записи и актуальный If-Match."
    ),
)
async def upload_category_image(
    category_id: UUID,
    _user: WriteUser,
    session: Session,
    storage: Storage,
    file: Annotated[UploadFile, File()],
    if_match: IfMatch = None,
) -> JSONResponse:
    expected_version, expected_etag = _expected_precondition(
        if_match, category_id
    )
    storage_key = await _read_and_store_image(
        owner="category",
        owner_id=category_id,
        file=file,
        storage=storage,
        session=session,
    )
    category = await _commit(
        session,
        commands.set_category_image(
            session,
            category_id=category_id,
            expected_version=expected_version,
            expected_etag=expected_etag,
            storage_key=storage_key,
        ),
    )
    response = _response({"image": None, "category": category})
    response.headers["ETag"] = special_equipment_management_etag(category)
    return response


@router.delete(
    "/categories/{category_id}/image",
    status_code=204,
    response_model=None,
    summary="Удалить изображение категории",
    description=(
        "Убирает ссылку на изображение категории и ставит объект в очередь "
        "очистки. Требует право записи и актуальный If-Match."
    ),
)
async def remove_category_image(
    category_id: UUID,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> Response:
    expected_version, expected_etag = _expected_precondition(
        if_match, category_id
    )
    category = await _commit(
        session,
        commands.delete_category_image(
            session,
            category_id=category_id,
            expected_version=expected_version,
            expected_etag=expected_etag,
        ),
    )
    return Response(
        status_code=204,
        headers={"ETag": special_equipment_management_etag(category)},
    )


@router.get(
    "/categories/{category_id}/image/content",
    response_model=None,
    summary="Изображение категории для админки",
    description=(
        "Возвращает приватное содержимое изображения категории с поддержкой "
        "ETag и byte range. Требует право чтения каталога; 404, если файла нет."
    ),
)
async def get_admin_category_image(
    category_id: UUID,
    request: Request,
    _user: ReadUser,
    session: Session,
    storage: Storage,
) -> Response:
    try:
        storage_key = await handle_category_image_key(category_id, session)
    except DomainError as exc:
        raise _http(exc)
    obj = await storage.get(storage_key)
    if obj is None:
        raise HTTPException(status_code=404, detail="Изображение не найдено")
    return _registry_media_response(
        obj, request, f"category-{category_id}.webp"
    )


@router.post(
    "/products/{product_id}/images",
    response_model=MediaUploadResponse,
    status_code=201,
    summary="Добавить изображение товара",
    description=(
        "Проверяет файл, добавляет приватный WebP в галерею товара и "
        "возвращает изображение с Location. Требует право записи и актуальный "
        "If-Match товара."
    ),
)
async def upload_product_image(
    product_id: UUID,
    _user: WriteUser,
    session: Session,
    storage: Storage,
    file: Annotated[UploadFile, File()],
    alt_text: Annotated[str | None, Form(max_length=1000)] = None,
    if_match: IfMatch = None,
) -> JSONResponse:
    expected_version, expected_etag = _expected_precondition(
        if_match, product_id
    )
    storage_key = await _read_and_store_image(
        owner="product",
        owner_id=product_id,
        file=file,
        storage=storage,
        session=session,
    )
    result = await _commit(
        session,
        commands.add_product_image(
            session,
            product_id=product_id,
            expected_version=expected_version,
            expected_etag=expected_etag,
            storage_key=storage_key,
            alt_text=alt_text,
        ),
    )
    response = _response(
        {"image": result["image"], "category": None}, status_code=201
    )
    response.headers["ETag"] = special_equipment_management_etag(
        result["product"]
    )
    response.headers["Location"] = str(result["image"]["content_url"])
    return response


@router.patch(
    "/products/{product_id}/images/{image_id}",
    response_model=ManagementImageResource,
    summary="Изменить изображение товара",
    description=(
        "Частично изменяет подпись, порядок или признак основного изображения "
        "товара. Отсутствующие поля сохраняются; требует право записи и "
        "актуальный If-Match товара."
    ),
)
async def update_product_image(
    product_id: UUID,
    image_id: UUID,
    payload: ProductImagePatchRequest,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    expected_version, expected_etag = _expected_precondition(
        if_match, product_id
    )
    result = await _commit(
        session,
        commands.update_product_image(
            session,
            product_id=product_id,
            image_id=image_id,
            expected_version=expected_version,
            expected_etag=expected_etag,
            values=payload.model_dump(exclude_unset=True),
        ),
    )
    response = _response(result["image"])
    response.headers["ETag"] = special_equipment_management_etag(
        result["product"]
    )
    return response


@router.delete(
    "/products/{product_id}/images/{image_id}",
    status_code=204,
    response_model=None,
    summary="Удалить изображение товара",
    description=(
        "Удаляет изображение из галереи и ставит приватный объект в очередь "
        "очистки. Требует право записи и актуальный If-Match товара."
    ),
)
async def delete_product_image(
    product_id: UUID,
    image_id: UUID,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> Response:
    expected_version, expected_etag = _expected_precondition(
        if_match, product_id
    )
    product = await _commit(
        session,
        commands.remove_product_image(
            session,
            product_id=product_id,
            image_id=image_id,
            expected_version=expected_version,
            expected_etag=expected_etag,
        ),
    )
    return Response(
        status_code=204,
        headers={"ETag": special_equipment_management_etag(product)},
    )


@router.get(
    "/images/{image_id}/content",
    response_model=None,
    summary="Изображение товара для админки",
    description=(
        "Возвращает приватное содержимое изображения товара с поддержкой ETag "
        "и byte range. Требует право чтения каталога; 404, если файла нет."
    ),
)
async def get_admin_product_image(
    image_id: UUID,
    request: Request,
    _user: ReadUser,
    session: Session,
    storage: Storage,
) -> Response:
    try:
        storage_key = await handle_product_image_key(image_id, session)
    except DomainError as exc:
        raise _http(exc)
    obj = await storage.get(storage_key)
    if obj is None:
        raise HTTPException(status_code=404, detail="Изображение не найдено")
    return _registry_media_response(
        obj, request, f"special-equipment-{image_id}.webp"
    )


ResourcePath = Literal[
    "categories",
    "marks",
    "models",
    "modifications",
    "trims",
    "attribute-groups",
    "attributes",
    "attribute-options",
    "products",
    "colors",
    "units",
    "superstructures",
]
_ENTITY_BY_PATH: dict[ResourcePath, EntityType] = {
    "categories": "category",
    "marks": "mark",
    "models": "model",
    "modifications": "modification",
    "trims": "trim",
    "attribute-groups": "attribute_group",
    "attributes": "attribute",
    "attribute-options": "attribute_option",
    "products": "product",
    "colors": "color",
    "units": "unit",
    "superstructures": "superstructure",
}


@router.get(
    "/{resource}/{entity_id}/delete-preview",
    response_model=CascadePreviewResponseSchema,
    summary="Предпросмотр каскадного удаления",
    description="Рассчитывает дерево каскадного удаления и блокирующие связи без блокировок.",
)
async def cascade_delete_preview(
    resource: ResourcePath,
    entity_id: UUID,
    _user: ReadUser,
    session: Session,
) -> JSONResponse:
    try:
        plan = await commands.preview_cascade_delete(
            session=session,
            resource=resource,
            entity_id=entity_id,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(_serialize_cascade_plan(plan)))


@router.post(
    "/{resource}/{entity_id}/cascade-delete",
    response_model=CascadeDeleteResponseSchema,
    summary="Каскадное удаление ресурса",
    description="Выполняет каскадное удаление под эксклюзивной блокировкой с проверкой подтверждения и токена предпросмотра.",
)
async def cascade_delete_resource(
    resource: ResourcePath,
    entity_id: UUID,
    body: CascadeDeleteRequestSchema,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> JSONResponse:
    expected_version, expected_etag = _expected_precondition(
        if_match, entity_id, problem=True
    )
    result = await _commit(
        session,
        commands.cascade_delete_entity(
            session=session,
            resource=resource,
            entity_id=entity_id,
            confirmation=body.confirmation,
            preview_token=body.preview_token,
            expected_version=expected_version,
            expected_etag=expected_etag,
            user_id=_actor_id(_user),
        ),
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{resource}/{entity_id}/dependencies",
    response_model=DependencyResource,
    summary="Зависимости ресурса",
    description="Объясняет, почему удаление заблокировано.",
)
async def resource_dependencies(
    resource: ResourcePath,
    entity_id: UUID,
    _user: ReadUser,
    session: Session,
) -> JSONResponse:
    try:
        result = await handle_dependencies(
            GetRegistryDependenciesQuery(_ENTITY_BY_PATH[resource], entity_id),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.delete(
    "/{resource}/{entity_id}",
    status_code=204,
    response_model=None,
    summary="Удалить ресурс каталога",
    description="Удаляет только ресурс без зависимостей.",
)
async def delete_resource(
    resource: ResourcePath,
    entity_id: UUID,
    _user: WriteUser,
    session: Session,
    if_match: IfMatch = None,
) -> Response:
    return await _delete(
        entity_type=_ENTITY_BY_PATH[resource],
        entity_id=entity_id,
        if_match=if_match,
        session=session,
        user=_user,
    )
