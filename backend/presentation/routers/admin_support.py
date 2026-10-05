"""Admin routes for support programs and dealer groups (support administration)."""
from __future__ import annotations

import contextlib
import csv
import datetime as _dt
import io
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    UploadFile,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.support import (
    CreateDealerGroupCommand,
    CreateSupportProgramCommand,
    DeleteBillOfLadingCommand,
    DeleteDealerGroupCommand,
    DeleteSupportProgramCommand,
    PatchSupportProgramCommand,
    UpdateDealerGroupCommand,
    UpdateSupportProgramCommand,
    UploadBillOfLadingCommand,
    UploadedBillOfLadingFile,
    UpsertDealerGroupCommand,
    handle_create_dealer_group,
    handle_create_support_program,
    handle_delete_bill_of_lading,
    handle_delete_dealer_group,
    handle_delete_support_program,
    handle_distributor_can_manage_dealer_groups,
    handle_patch_support_program,
    handle_update_dealer_group,
    handle_update_support_program,
    handle_upload_bill_of_lading,
    handle_upsert_dealer_group,
)
from application.errors import ServiceError, domain_to_http
from application.queries.support import (
    GetDealerGroupQuery,
    GetSupportProgramQuery,
    ListDealerGroupsQuery,
    ListSupportProgramsQuery,
    handle_get_dealer_group,
    handle_get_support_program,
    handle_list_dealer_groups,
    handle_list_support_programs,
)
from domain.errors import DealerGroupNotFoundError, DomainError, InvalidUploadError
from domain.services.object_storage import ObjectStorage
from domain.services.scopes import SUPPORT_ADMIN
from infrastructure.database import get_db
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import get_current_user, require_scopes
from presentation.dependencies.csv_export import csv_streaming_response
from presentation.dependencies.export_format import ExportFormat, export_format_dep
from presentation.schemas.support import (
    BillOfLadingUploadResponse,
    DealerGroupListResponse,
    DealerGroupRequest,
    DealerGroupResponse,
    DealerGroupUpdateRequest,
    MessageResponse,
    SupportProgramListResponse,
    SupportProgramPatchRequest,
    SupportProgramRequest,
    SupportProgramResponse,
)

router = APIRouter()

_employee_only = require_scopes(SUPPORT_ADMIN)

# 50 MB upload limit (parity with command-side guardrail).
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _resolve_dealer_group_ids(payload: SupportProgramRequest) -> list[UUID]:
    if payload.dealer_group_ids is not None:
        return list(payload.dealer_group_ids)
    if payload.dealer_group_id is not None:
        return [payload.dealer_group_id]
    return []


def _as_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


async def _dealer_group_access(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    if user.get("role") in {"carcraft_employee", "distributor"}:
        return user
    raise HTTPException(
        status_code=403,
        detail={
            "error": "Недостаточно прав доступа",
            "code": "INSUFFICIENT_PERMISSIONS",
        },
    )


async def _ensure_dealer_group_write_allowed(
    *,
    user: dict[str, Any],
    session: AsyncSession,
    distributor_company_id: UUID,
) -> None:
    if user.get("role") == "carcraft_employee":
        return
    if (
        user.get("role") == "distributor"
        and user.get("sub_role") == "administrator"
        and user.get("company_id") is not None
        and _as_uuid(user["company_id"]) == distributor_company_id
        and await handle_distributor_can_manage_dealer_groups(
            distributor_company_id, session
        )
    ):
        return
    raise HTTPException(
        status_code=403,
        detail={
            "error": "Недостаточно прав доступа",
            "code": "INSUFFICIENT_PERMISSIONS",
        },
    )


def _resolve_mark_ids(payload: SupportProgramRequest) -> list[str]:
    if payload.mark_ids:
        return [mark_id for mark_id in payload.mark_ids if mark_id]
    return [payload.mark_id] if payload.mark_id else []


def _resolve_distributor_ids(payload: SupportProgramRequest) -> list[UUID]:
    if payload.distributor_ids:
        return list(payload.distributor_ids)
    return [payload.distributor_id] if payload.distributor_id is not None else []


def _parse_bill_date(value: str | None) -> _dt.date | None:
    if not value:
        return None
    try:
        return _dt.date.fromisoformat(value[:10])
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Некорректный формат даты"
        ) from exc


# ---------------------------------------------------------------------------
# Support programs
# ---------------------------------------------------------------------------


@router.get(
    "/support-programs",
    response_model=SupportProgramListResponse,
    summary="[admin] Список программ поддержки",
    description=(
        "Постранично возвращает программы поддержки с фильтрами по "
        "марке, модели, группе дилеров, дистрибьютору и активности."
    ),
    dependencies=[Depends(_employee_only)],
)
async def list_support_programs(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    search: str | None = Query(default=None),
    mark_id: str | None = Query(default=None),
    model_id: str | None = Query(default=None),
    dealer_group_id: Annotated[UUID | None, Query()] = None,
    distributor_id: Annotated[UUID | None, Query()] = None,
    is_active: bool | None = Query(default=None),
) -> JSONResponse:
    result = await handle_list_support_programs(
        ListSupportProgramsQuery(
            page=page,
            limit=limit,
            search=search,
            mark_id=mark_id,
            model_id=model_id,
            dealer_group_id=dealer_group_id,
            distributor_id=distributor_id,
            is_active=is_active,
            actor_id=user["id"],
            actor_role=str(user["role"]),
            company_id=user.get("company_id"),
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/support-programs/{program_id}",
    response_model=SupportProgramResponse,
    summary="[admin] Программа поддержки по id",
    description="Возвращает программу поддержки с привязанными ЛК / группами / накладными.",
    dependencies=[Depends(_employee_only)],
)
async def get_support_program(
    program_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
) -> JSONResponse:
    try:
        result = await handle_get_support_program(
            GetSupportProgramQuery(
                program_id=program_id,
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content={"support_program": jsonable_encoder(result)})


@router.post(
    "/support-programs",
    status_code=201,
    response_model=SupportProgramResponse,
    summary="[admin] Создать программу поддержки",
    description="Создаёт новую программу поддержки и привязывает её к лизинговым компаниям и группам дилеров.",
    dependencies=[Depends(_employee_only)],
)
async def create_support_program(
    body: SupportProgramRequest,
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_create_support_program(
            CreateSupportProgramCommand(
                name=body.name,
                mark_id=body.mark_id,
                mark_ids=_resolve_mark_ids(body),
                support_type=body.support_type,
                support_params=body.support_params.model_dump(exclude_none=False),
                model_id=body.model_id,
                model_ids=body.model_ids,
                complectation_ids=body.complectation_ids,
                vin=body.vin,
                vins=body.vins,
                dealer_group_ids=_resolve_dealer_group_ids(body),
                distributor_id=body.distributor_id,
                distributor_ids=_resolve_distributor_ids(body),
                leasing_company_ids=list(body.leasing_company_ids or []),
                compensation_templates=[
                    item.model_dump(exclude_none=False)
                    for item in body.compensation_templates
                ],
                production_year_from=body.production_year_from,
                production_year_to=body.production_year_to,
                production_date_from=body.production_date_from,
                production_date_to=body.production_date_to,
                delivery_date_from=body.delivery_date_from,
                delivery_date_to=body.delivery_date_to,
                starts_at=body.starts_at,
                ends_at=body.ends_at,
                is_active=body.is_active,
                is_compatible=body.is_compatible,
                compatible_support_ids=list(body.compatible_support_ids),
                show_to_leasing_company=body.show_to_leasing_company,
                show_to_client=body.show_to_client,
                comment=body.comment,
                created_by=user["id"],
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content={
            "support_program": jsonable_encoder(result),
            "message": "Программа поддержки успешно создана",
        },
        status_code=201,
        headers={"Location": f"/api/v1/admin/support-programs/{result['id']}"},
    )


@router.put(
    "/support-programs/{program_id}",
    response_model=SupportProgramResponse,
    summary="[admin] Обновить программу поддержки",
    description="Полностью перезаписывает программу поддержки и её связи (M2M ЛК и групп дилеров).",
    dependencies=[Depends(_employee_only)],
)
async def update_support_program(
    program_id: UUID,
    body: SupportProgramRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_update_support_program(
            UpdateSupportProgramCommand(
                program_id=program_id,
                name=body.name,
                mark_id=body.mark_id,
                mark_ids=_resolve_mark_ids(body),
                support_type=body.support_type,
                support_params=body.support_params.model_dump(exclude_none=False),
                model_id=body.model_id,
                model_ids=body.model_ids,
                complectation_ids=body.complectation_ids,
                vin=body.vin,
                vins=body.vins,
                dealer_group_ids=_resolve_dealer_group_ids(body),
                distributor_id=body.distributor_id,
                distributor_ids=_resolve_distributor_ids(body),
                leasing_company_ids=list(body.leasing_company_ids or []),
                compensation_templates=[
                    item.model_dump(exclude_none=False)
                    for item in body.compensation_templates
                ],
                production_year_from=body.production_year_from,
                production_year_to=body.production_year_to,
                production_date_from=body.production_date_from,
                production_date_to=body.production_date_to,
                delivery_date_from=body.delivery_date_from,
                delivery_date_to=body.delivery_date_to,
                starts_at=body.starts_at,
                ends_at=body.ends_at,
                is_active=body.is_active,
                is_compatible=body.is_compatible,
                compatible_support_ids=list(body.compatible_support_ids),
                show_to_leasing_company=body.show_to_leasing_company,
                show_to_client=body.show_to_client,
                comment=body.comment,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content={
            "support_program": jsonable_encoder(result),
            "message": "Программа поддержки успешно обновлена",
        }
    )


@router.patch(
    "/support-programs/{program_id}",
    response_model=SupportProgramResponse,
    summary="[admin] Частичное обновление программы поддержки",
    description=(
        "Частичное обновление программы поддержки. В текущей версии "
        "поддерживается переключение активности: `{active: bool}` "
        "(замена старых RPC-эндпоинтов `/activate` и `/deactivate`)."
    ),
    dependencies=[Depends(_employee_only)],
)
async def patch_support_program(
    program_id: UUID,
    body: SupportProgramPatchRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    # Accept both `active` and `is_active` aliases for forward compatibility.
    desired_active = (
        body.active if body.active is not None else body.is_active
    )
    try:
        result = await handle_patch_support_program(
            PatchSupportProgramCommand(
                program_id=program_id,
                is_active=desired_active,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content={
            "support_program": jsonable_encoder(result),
            "message": "Программа поддержки обновлена",
        }
    )


@router.delete(
    "/support-programs/{program_id}",
    response_model=MessageResponse,
    summary="[admin] Деактивировать программу поддержки",
    description="Soft-delete: переводит программу поддержки в is_active=false. Совместимо с поведением Express.",
    dependencies=[Depends(_employee_only)],
)
async def delete_support_program(
    program_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_delete_support_program(
            DeleteSupportProgramCommand(program_id=program_id), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Bill of Lading file upload
# ---------------------------------------------------------------------------


@router.post(
    "/support-programs/{program_id}/bill-of-lading/upload",
    response_model=BillOfLadingUploadResponse,
    summary="[admin] Загрузить накладную программы",
    description=(
        "Принимает PDF / DOC / DOCX / PPTX до 50 МБ, сохраняет в объектное "
        "хранилище и привязывает запись о файле к программе."
    ),
    dependencies=[Depends(_employee_only)],
)
async def upload_bill_of_lading(
    program_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    file: Annotated[UploadFile, File(...)],
    bill_date: Annotated[str | None, Form()] = None,
    comment: Annotated[str | None, Form()] = None,
) -> JSONResponse:
    file_bytes = await file.read()
    if len(file_bytes) > _MAX_UPLOAD_BYTES:
        raise _http(InvalidUploadError("Размер файла превышает допустимый лимит"))

    try:
        result = await handle_upload_bill_of_lading(
            UploadBillOfLadingCommand(
                program_id=program_id,
                file=UploadedBillOfLadingFile(
                    filename=file.filename or "file",
                    content_type=file.content_type or "application/octet-stream",
                    data=file_bytes,
                ),
                bill_date=_parse_bill_date(bill_date),
                comment=(comment or "").strip() or None,
            ),
            session,
            storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.delete(
    "/support-programs/{program_id}/bill-of-lading/{file_id}",
    response_model=SupportProgramResponse,
    summary="[admin] Удалить файл накладной",
    description="Удаляет запись о файле накладной у программы поддержки.",
    dependencies=[Depends(_employee_only)],
)
async def delete_bill_of_lading(
    program_id: UUID,
    file_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_delete_bill_of_lading(
            DeleteBillOfLadingCommand(program_id=program_id, file_id=file_id),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Dealer groups
# ---------------------------------------------------------------------------


_DEALER_GROUP_CSV_HEADERS = [
    "id",
    "name",
    "distributor_company_id",
    "distributor",
    "description",
    "is_active",
    "dealers_count",
    "dealers",
    "dealer_company_ids",
    "created_at",
    "updated_at",
]


@router.get(
    "/dealer-groups",
    response_model=DealerGroupListResponse,
    summary="[admin] Список групп дилеров",
    description="Постранично возвращает группы дилеров дистрибьюторов.",
)
async def list_dealer_groups(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(_dealer_group_access)],
    fmt: Annotated[ExportFormat, Depends(export_format_dep)] = "json",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    search: str | None = Query(default=None),
    distributor_id: UUID | None = Query(default=None),
    dealer_id: UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
) -> JSONResponse | StreamingResponse:
    scoped_distributor_id = distributor_id
    if user.get("role") == "distributor":
        if user.get("company_id") is None:
            raise HTTPException(status_code=403, detail="Недостаточно прав доступа")
        scoped_distributor_id = _as_uuid(user["company_id"])
    export_limit = 10_000 if fmt in {"csv", "xlsx"} else limit
    result = await handle_list_dealer_groups(
        ListDealerGroupsQuery(
            page=1 if fmt in {"csv", "xlsx"} else page,
            limit=export_limit,
            search=search,
            distributor_id=scoped_distributor_id,
            dealer_id=dealer_id,
            is_active=is_active,
        ),
        session,
    )
    if fmt == "json":
        return JSONResponse(content=jsonable_encoder(result))

    rows = result.get("dealer_groups", [])
    for row in rows:
        dealers = row.get("dealers") or []
        distributor = row.get("distributor") or {}
        row["distributor"] = distributor.get("name") or ""
        row["dealers"] = ", ".join(str(d.get("name", "")) for d in dealers)
        row["dealer_company_ids"] = ", ".join(
            str(d.get("id", "")) for d in dealers
        )
        for key in ("created_at", "updated_at"):
            val = row.get(key)
            if val is not None:
                row[key] = str(val)

    filename = f"dealer_groups_{_dt.datetime.now(_dt.UTC).strftime('%Y-%m-%d')}.csv"
    return csv_streaming_response(_DEALER_GROUP_CSV_HEADERS, rows, filename)


@router.post(
    "/dealer-groups/import",
    summary="[admin] Импорт групп дилеров из CSV",
    description=(
        "Принимает CSV-файл с колонками: id, name, distributor_company_id, "
        "description, dealer_company_ids. dealer_company_ids — список "
        "company_id дилеров через запятую. "
        "Если id указан и группа существует — обновляет, "
        "иначе ищет по name внутри дистрибьютора и обновляет, иначе создаёт."
    ),
)
async def import_dealer_groups(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(_dealer_group_access)],
    file: Annotated[UploadFile, File(...)],
) -> JSONResponse:
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")

    created = 0
    updated = 0
    errors: list[str] = []

    for idx, row in enumerate(reader, start=1):
        try:
            action, err = await _upsert_dealer_group_row(
                session, row, actor_id=_as_uuid(user["id"]), user=user
            )
        except Exception as exc:
            errors.append(f"Строка {idx}: {exc}")
            continue
        if action == "error":
            errors.append(f"Строка {idx}: {err}")
        elif action == "created":
            created += 1
        elif action == "updated":
            updated += 1

    await session.commit()
    parts = [f"Создано {created}", f"Обновлено {updated}"]
    message = ", ".join(parts)
    if errors:
        message += f", ошибок: {len(errors)}"
    return JSONResponse(
        content={
            "created": created,
            "updated": updated,
            "errors": errors,
            "message": message,
        }
    )


async def _upsert_dealer_group_row(
    session: AsyncSession,
    row: dict[str, str],
    *,
    actor_id: UUID,
    user: dict[str, Any],
) -> tuple[str, str | None]:
    group_id: UUID | None = None
    group_id_raw = (row.get("id") or "").strip()
    if group_id_raw:
        with contextlib.suppress(ValueError):
            group_id = UUID(group_id_raw)

    name = (row.get("name") or "").strip()
    if not name:
        return ("error", "пропущено обязательное поле name")

    distributor_raw = (row.get("distributor_company_id") or "").strip()
    if not distributor_raw:
        return ("error", "пропущено обязательное поле distributor_company_id")
    try:
        distributor_company_id = UUID(distributor_raw)
    except ValueError:
        return ("error", "некорректный distributor_company_id")
    await _ensure_dealer_group_write_allowed(
        user=user,
        session=session,
        distributor_company_id=distributor_company_id,
    )

    dealer_ids_raw = (row.get("dealer_company_ids") or "").strip()
    dealer_company_ids = []
    if dealer_ids_raw:
        for raw_part in dealer_ids_raw.split(","):
            stripped = raw_part.strip()
            if stripped:
                with contextlib.suppress(ValueError):
                    dealer_company_ids.append(UUID(stripped))

    result = await handle_upsert_dealer_group(
        UpsertDealerGroupCommand(
            name=name,
            distributor_company_id=distributor_company_id,
            description=(row.get("description") or "").strip() or None,
            dealer_company_ids=dealer_company_ids,
            group_id=group_id,
            actor_id=actor_id,
        ),
        session,
    )
    return (result.action, None)


@router.post(
    "/dealer-groups",
    status_code=201,
    response_model=DealerGroupResponse,
    summary="[admin] Создать группу дилеров",
    description="Создаёт группу дилерских компаний внутри дистрибьютора.",
)
async def create_dealer_group(
    body: DealerGroupRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(_dealer_group_access)],
) -> JSONResponse:
    await _ensure_dealer_group_write_allowed(
        user=user,
        session=session,
        distributor_company_id=body.distributor_company_id,
    )
    try:
        result = await handle_create_dealer_group(
            CreateDealerGroupCommand(
                name=body.name,
                distributor_company_id=body.distributor_company_id,
                description=body.description,
                dealer_company_ids=list(body.dealer_company_ids or []),
                actor_id=_as_uuid(user["id"]),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content={
            "dealer_group": jsonable_encoder(result),
            "message": "Группа дилеров успешно создана",
        },
        status_code=201,
        headers={"Location": f"/api/v1/admin/dealer-groups/{result['id']}"},
    )


@router.get(
    "/dealer-groups/{group_id}",
    response_model=DealerGroupResponse,
    summary="[admin] Детали группы дилеров",
)
async def get_dealer_group(
    group_id: Annotated[UUID, Path()],
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(_dealer_group_access)],
) -> JSONResponse:
    result = await handle_get_dealer_group(GetDealerGroupQuery(group_id), session)
    if result is None:
        raise _http(DealerGroupNotFoundError(group_id))
    if (
        user.get("role") == "distributor"
        and (
            user.get("company_id") is None
            or _as_uuid(user["company_id"]) != result["distributor_company_id"]
        )
    ):
        raise HTTPException(status_code=403, detail="Недостаточно прав доступа")
    return JSONResponse(content={"dealer_group": jsonable_encoder(result)})


@router.patch(
    "/dealer-groups/{group_id}",
    response_model=DealerGroupResponse,
    summary="[admin] Обновить группу дилеров",
)
async def update_dealer_group(
    group_id: Annotated[UUID, Path()],
    body: DealerGroupUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(_dealer_group_access)],
) -> JSONResponse:
    existing = await handle_get_dealer_group(GetDealerGroupQuery(group_id), session)
    if existing is None:
        raise _http(DealerGroupNotFoundError(group_id))
    await _ensure_dealer_group_write_allowed(
        user=user,
        session=session,
        distributor_company_id=existing["distributor_company_id"],
    )
    await _ensure_dealer_group_write_allowed(
        user=user,
        session=session,
        distributor_company_id=body.distributor_company_id,
    )
    try:
        result = await handle_update_dealer_group(
            UpdateDealerGroupCommand(
                group_id=group_id,
                name=body.name,
                distributor_company_id=body.distributor_company_id,
                description=body.description,
                dealer_company_ids=list(body.dealer_company_ids or []),
                actor_id=_as_uuid(user["id"]),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content={
            "dealer_group": jsonable_encoder(result),
            "message": "Группа дилеров успешно обновлена",
        }
    )


@router.delete(
    "/dealer-groups/{group_id}",
    response_model=MessageResponse,
    summary="[admin] Деактивировать группу дилеров",
)
async def delete_dealer_group(
    group_id: Annotated[UUID, Path()],
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(_dealer_group_access)],
) -> JSONResponse:
    existing = await handle_get_dealer_group(GetDealerGroupQuery(group_id), session)
    if existing is None:
        raise _http(DealerGroupNotFoundError(group_id))
    await _ensure_dealer_group_write_allowed(
        user=user,
        session=session,
        distributor_company_id=existing["distributor_company_id"],
    )
    try:
        await handle_delete_dealer_group(
            DeleteDealerGroupCommand(group_id=group_id, actor_id=_as_uuid(user["id"])),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content={"message": "Группа дилеров деактивирована"})
