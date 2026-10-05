"""Employee-only REST resources for special-equipment XLSX imports.

Mount this router under ``/api/v1``. All binary traffic remains inside the
FastAPI proxy; no storage hostname, key, upload ID or ETag is serialized.
"""

# ruff: noqa: TRY301

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.special_equipment_import import (
    ApplyImportCommand,
    CreateImportCommand,
    PutImportPartCommand,
    cancel_import,
    complete_import_upload,
    create_import,
    decode_cursor,
    get_import,
    get_issues,
    get_preview,
    get_source_status,
    list_imports,
    put_import_part,
    request_import_application,
    request_import_template,
    resolve_private_artifact,
)
from application.tasks.special_equipment_import import (
    apply_special_equipment_import,
    validate_special_equipment_import,
)
from domain.special_equipment_import import ImportMode
from infrastructure.database import get_db
from infrastructure.services.special_equipment_import_storage import (
    ImportObjectStorage,
    get_special_equipment_import_storage,
)
from presentation.dependencies.auth import require_scopes
from presentation.schemas.special_equipment_imports import (
    ApplySpecialEquipmentImportRequest,
    ContentRange,
    CreateSpecialEquipmentImportRequest,
    IfMatchHeader,
    ImportIssuesResponse,
    ImportPartResponse,
    ImportPreviewResponse,
    ImportSourceStatusResponse,
    SpecialEquipmentImportListResponse,
    SpecialEquipmentImportResponse,
)

router = APIRouter(prefix="/special-equipment", tags=["special-equipment-imports"])
_READ_SCOPE = "special-equipment-imports:read"
_WRITE_SCOPE = "special-equipment-imports:write"
_APPLY_SCOPE = "special-equipment-imports:apply"


def _problem(exc: ServiceError) -> HTTPException:
    message = str(exc)
    code = message if message.replace("_", "").isalnum() else None
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": message, "code": code},
    )


def _template_response(
    *,
    version: int,
    mode: ImportMode = ImportMode.APPEND,
    if_none_match: str | None,
    deprecation: bool = False,
) -> StreamingResponse:
    artifact = request_import_template(version=version, mode=mode)
    etag = f'"{artifact.digest}"'
    headers = {
        "ETag": etag,
        "Content-Disposition": (
            "attachment; filename*=UTF-8''" + quote(artifact.filename)
        ),
        "Content-Length": str(len(artifact.content)),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=3600",
    }
    if deprecation:
        headers["Deprecation"] = "true"
    if if_none_match == etag:
        return StreamingResponse(
            iter(()),
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={
                key: value
                for key, value in headers.items()
                if key not in {"Content-Length", "Content-Disposition"}
            },
        )

    async def body() -> AsyncIterator[bytes]:
        yield artifact.content

    return StreamingResponse(
        body(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.get(
    "/import-templates/v9/content",
    response_model=None,
    summary="Скачать актуальный полный шаблон импорта спецтехники v9",
    description=(
        "Возвращает актуальный русский XLSX-шаблон v9 со связями типов надстроек и категорий, "
        "привязкой моделей к категориям, признаком видимости категорий и полями VIN шасси/надстройки."
    ),
)
async def download_import_template_v9(
    _user: Annotated[dict, Depends(require_scopes(_READ_SCOPE))],
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    mode: Annotated[ImportMode | None, Query()] = None,
) -> StreamingResponse:
    return _template_response(
        version=9,
        mode=mode or ImportMode.APPEND,
        if_none_match=if_none_match,
    )


@router.get(
    "/import-templates/v8/content",
    response_model=None,
    summary="Скачать полный шаблон импорта спецтехники v8 (устаревший, отдает v9)",
    description=(
        "Устаревший маршрут шаблона v8, отдает актуальный русский XLSX-шаблон v9 с заголовком Deprecation."
    ),
)
async def download_import_template_v8(
    _user: Annotated[dict, Depends(require_scopes(_READ_SCOPE))],
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    mode: Annotated[ImportMode | None, Query()] = None,
) -> StreamingResponse:
    return _template_response(
        version=9,
        mode=mode or ImportMode.APPEND,
        if_none_match=if_none_match,
        deprecation=True,
    )


@router.get(
    "/import-templates/v7/content",
    response_model=None,
    summary="Скачать полный шаблон импорта спецтехники v7 (устаревший, отдает v9)",
    description=(
        "Устаревший маршрут шаблона v7, отдает актуальный русский XLSX-шаблон v9 с заголовком Deprecation."
    ),
)
async def download_import_template_v7(
    _user: Annotated[dict, Depends(require_scopes(_READ_SCOPE))],
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    mode: Annotated[ImportMode | None, Query()] = None,
) -> StreamingResponse:
    return _template_response(
        version=9,
        mode=mode or ImportMode.APPEND,
        if_none_match=if_none_match,
        deprecation=True,
    )


@router.post(
    "/imports",
    response_model=SpecialEquipmentImportResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": SpecialEquipmentImportResponse}},
    summary="Создать импорт спецтехники",
    description=(
        "Создаёт durable import resource и внутренний multipart upload. "
        "Ответ содержит только относительные FastAPI links."
    ),
)
async def create_special_equipment_import(
    payload: CreateSpecialEquipmentImportRequest,
    user: Annotated[dict, Depends(require_scopes(_WRITE_SCOPE))],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[
        ImportObjectStorage, Depends(get_special_equipment_import_storage)
    ],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> JSONResponse:
    try:
        result, idempotent_replay = await create_import(
            CreateImportCommand(
                requested_by=UUID(str(user["id"])),
                idempotency_key=idempotency_key,
                filename=payload.filename,
                size=payload.size,
                mode=ImportMode(payload.mode),
                template_version=payload.template_version,
                target_warehouse_id=payload.target_warehouse_id,
            ),
            session,
            storage,
        )
        await session.commit()
    except ServiceError as exc:
        await session.rollback()
        raise _problem(exc) from exc
    return JSONResponse(
        status_code=(
            status.HTTP_200_OK if idempotent_replay else status.HTTP_201_CREATED
        ),
        content=jsonable_encoder(result),
        headers={"Location": f"/api/v1/special-equipment/imports/{result['id']}"},
    )


@router.get(
    "/imports",
    response_model=SpecialEquipmentImportListResponse,
    summary="История импортов спецтехники",
    description="Возвращает cursor-paginated jobs, созданные текущим сотрудником.",
)
async def list_special_equipment_imports(
    user: Annotated[dict, Depends(require_scopes(_READ_SCOPE))],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> JSONResponse:
    try:
        before_created_at, before_id = decode_cursor(cursor)
        result = await list_imports(
            session,
            requested_by=UUID(str(user["id"])),
            limit=limit,
            before_created_at=before_created_at,
            before_id=before_id,
        )
    except ServiceError as exc:
        raise _problem(exc) from exc
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/imports/{import_id}",
    response_model=SpecialEquipmentImportResponse,
    summary="Получить статус импорта спецтехники",
    description="Возвращает фазы, монотонные counters, summary и доступные links.",
)
async def get_special_equipment_import(
    import_id: UUID,
    user: Annotated[dict, Depends(require_scopes(_READ_SCOPE))],
    session: Annotated[AsyncSession, Depends(get_db)],
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    try:
        result = await get_import(
            session,
            import_id=import_id,
            requested_by=UUID(str(user["id"])),
        )
    except ServiceError as exc:
        raise _problem(exc) from exc
    etag = f'W/"{result["updatedAt"].isoformat()}"'
    response_headers = {"ETag": etag, "Retry-After": "2"}
    if if_none_match == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=response_headers,
        )
    return JSONResponse(
        content=jsonable_encoder(result),
        headers=response_headers,
    )


@router.get(
    "/imports/{import_id}/source",
    response_model=ImportSourceStatusResponse,
    summary="Получить состояние загрузки XLSX",
    description="Возвращает только подтверждённые backend части для resume.",
)
async def get_import_source_status(
    import_id: UUID,
    user: Annotated[dict, Depends(require_scopes(_READ_SCOPE))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await get_source_status(
            session,
            import_id=import_id,
            requested_by=UUID(str(user["id"])),
        )
    except ServiceError as exc:
        raise _problem(exc) from exc
    return JSONResponse(content=jsonable_encoder(result))


@router.put(
    "/imports/{import_id}/source/parts/{part_number}",
    response_model=ImportPartResponse,
    summary="Загрузить часть XLSX через FastAPI",
    description=(
        "Потоково принимает ограниченную часть, проверяет Content-Range и "
        "SHA-256, затем передаёт её во внутренний multipart storage."
    ),
)
async def put_import_source_part(
    import_id: UUID,
    part_number: int,
    request: Request,
    user: Annotated[dict, Depends(require_scopes(_WRITE_SCOPE))],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[
        ImportObjectStorage, Depends(get_special_equipment_import_storage)
    ],
    content_range_raw: Annotated[str, Header(alias="Content-Range")],
    content_digest: Annotated[str, Header(alias="Content-Digest")],
    content_length: Annotated[int, Header(alias="Content-Length")],
) -> JSONResponse:
    try:
        content_range = ContentRange.parse(content_range_raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        result = await put_import_part(
            PutImportPartCommand(
                import_id=import_id,
                requested_by=UUID(str(user["id"])),
                part_number=part_number,
                byte_start=content_range.start,
                byte_end=content_range.end,
                content_length=content_length,
                content_digest=content_digest,
                chunks=request.stream(),
            ),
            session,
            storage,
        )
        await session.commit()
    except ServiceError as exc:
        await session.rollback()
        raise _problem(exc) from exc
    return JSONResponse(content=jsonable_encoder(result))


@router.put(
    "/imports/{import_id}/source/completion",
    response_model=SpecialEquipmentImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Завершить source upload",
    description="Завершает multipart идемпотентно и ставит validation task в очередь.",
)
async def complete_import_source(
    import_id: UUID,
    user: Annotated[dict, Depends(require_scopes(_WRITE_SCOPE))],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[
        ImportObjectStorage, Depends(get_special_equipment_import_storage)
    ],
) -> JSONResponse:
    try:
        result = await complete_import_upload(
            session,
            storage,
            import_id=import_id,
            requested_by=UUID(str(user["id"])),
        )
        await session.commit()
    except ServiceError as exc:
        await session.rollback()
        raise _problem(exc) from exc
    with suppress(Exception):
        await validate_special_equipment_import.kiq(str(import_id))
    return JSONResponse(status_code=202, content=jsonable_encoder(result))


@router.get(
    "/imports/{import_id}/source/content",
    response_model=None,
    summary="Скачать исходный XLSX",
    description="Авторизованный streaming proxy с Range; storage URL не раскрывается.",
    responses={
        404: {"description": "Import или source object не найден"},
        410: {"description": "Срок хранения source XLSX истёк"},
        416: {"description": "Некорректный byte range"},
    },
)
async def download_import_source(
    import_id: UUID,
    user: Annotated[dict, Depends(require_scopes(_READ_SCOPE))],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[
        ImportObjectStorage, Depends(get_special_equipment_import_storage)
    ],
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> StreamingResponse:
    return await _stream_artifact(
        import_id=import_id,
        artifact="source",
        user=user,
        session=session,
        storage=storage,
        range_header=range_header,
    )


@router.get(
    "/imports/{import_id}/preview",
    response_model=ImportPreviewResponse,
    summary="Получить preview импорта",
    description="Возвращает агрегированный diff без изменения business tables.",
)
async def get_import_preview(
    import_id: UUID,
    user: Annotated[dict, Depends(require_scopes(_READ_SCOPE))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await get_preview(
            session,
            import_id=import_id,
            requested_by=UUID(str(user["id"])),
        )
    except ServiceError as exc:
        raise _problem(exc) from exc
    return JSONResponse(
        content=jsonable_encoder(result),
        headers={"ETag": f'"{result["previewHash"]}"'},
    )


@router.get(
    "/imports/{import_id}/issues",
    response_model=ImportIssuesResponse,
    summary="Получить issues импорта",
    description="Возвращает cursor-paginated errors/warnings с фильтрами.",
)
async def get_import_issue_page(
    import_id: UUID,
    user: Annotated[dict, Depends(require_scopes(_READ_SCOPE))],
    session: Annotated[AsyncSession, Depends(get_db)],
    severity: str | None = Query(default=None, pattern="^(error|warning)$"),
    sheet_code: str | None = Query(default=None, max_length=100),
    after_sequence: int = Query(default=0, alias="afterSequence", ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> JSONResponse:
    try:
        result = await get_issues(
            session,
            import_id=import_id,
            requested_by=UUID(str(user["id"])),
            severity=severity,
            sheet_code=sheet_code,
            after_sequence=after_sequence,
            limit=limit,
        )
    except ServiceError as exc:
        raise _problem(exc) from exc
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/imports/{import_id}/validation-report/content",
    response_model=None,
    summary="Скачать полный validation report",
    description="Возвращает private report через FastAPI streaming proxy.",
    responses={
        404: {"description": "Import или validation report не найден"},
        410: {"description": "Срок хранения validation report истёк"},
        416: {"description": "Некорректный byte range"},
    },
)
async def download_validation_report(
    import_id: UUID,
    user: Annotated[dict, Depends(require_scopes(_READ_SCOPE))],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[
        ImportObjectStorage, Depends(get_special_equipment_import_storage)
    ],
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> StreamingResponse:
    return await _stream_artifact(
        import_id=import_id,
        artifact="validation_report",
        user=user,
        session=session,
        storage=storage,
        range_header=range_header,
    )


@router.put(
    "/imports/{import_id}/application",
    response_model=SpecialEquipmentImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Подтвердить применение preview",
    description=(
        "Идемпотентно создаёт singleton application resource. If-Match "
        "гарантирует применение просмотренного revision."
    ),
)
async def apply_import_preview(
    import_id: UUID,
    payload: ApplySpecialEquipmentImportRequest,
    user: Annotated[dict, Depends(require_scopes(_APPLY_SCOPE))],
    session: Annotated[AsyncSession, Depends(get_db)],
    if_match_raw: Annotated[str, Header(alias="If-Match")],
) -> JSONResponse:
    try:
        if_match = IfMatchHeader(value=if_match_raw).value
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="If-Match is invalid") from exc
    try:
        result = await request_import_application(
            ApplyImportCommand(
                import_id=import_id,
                requested_by=UUID(str(user["id"])),
                if_match=if_match,
                confirm_destructive_changes=payload.confirm_destructive_changes,
            ),
            session,
        )
        await session.commit()
    except ServiceError as exc:
        await session.rollback()
        raise _problem(exc) from exc
    with suppress(Exception):
        await apply_special_equipment_import.kiq(str(import_id))
    return JSONResponse(status_code=202, content=jsonable_encoder(result))


@router.put(
    "/imports/{import_id}/cancellation",
    response_model=SpecialEquipmentImportResponse,
    summary="Отменить импорт",
    description="Идемпотентно отменяет ещё не применённый import resource.",
)
async def cancel_special_equipment_import(
    import_id: UUID,
    user: Annotated[dict, Depends(require_scopes(_WRITE_SCOPE))],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[
        ImportObjectStorage, Depends(get_special_equipment_import_storage)
    ],
) -> JSONResponse:
    try:
        result = await cancel_import(
            session,
            storage,
            import_id=import_id,
            requested_by=UUID(str(user["id"])),
        )
        await session.commit()
    except ServiceError as exc:
        await session.rollback()
        raise _problem(exc) from exc
    return JSONResponse(content=jsonable_encoder(result))


async def _stream_artifact(
    *,
    import_id: UUID,
    artifact: str,
    user: dict,
    session: AsyncSession,
    storage: ImportObjectStorage,
    range_header: str | None,
) -> StreamingResponse:
    try:
        resolved = await resolve_private_artifact(
            session,
            import_id=import_id,
            requested_by=UUID(str(user["id"])),
            artifact=artifact,
        )
    except ServiceError as exc:
        raise _problem(exc) from exc
    head = await storage.head(resolved["key"])
    if head is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    start, end, response_status = _parse_range(range_header, head.size_bytes)
    length = end - start + 1
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Disposition": (
            "attachment; filename*=UTF-8''" + quote(resolved["filename"], safe="")
        ),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "X-Accel-Buffering": "no",
    }
    if response_status == status.HTTP_206_PARTIAL_CONTENT:
        headers["Content-Range"] = f"bytes {start}-{end}/{head.size_bytes}"
    return StreamingResponse(
        storage.iter_bytes(resolved["key"], start=start, end=end),
        status_code=response_status,
        media_type=resolved["content_type"],
        headers=headers,
    )


def _parse_range(value: str | None, size: int) -> tuple[int, int, int]:
    if not value:
        return 0, size - 1, status.HTTP_200_OK
    if not value.startswith("bytes=") or "," in value:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{size}"},
        )
    interval = value[6:]
    try:
        start_raw, end_raw = interval.split("-", 1)
        if not start_raw:
            suffix = int(end_raw)
            if suffix <= 0:
                raise ValueError
            start = max(size - suffix, 0)
            end = size - 1
        else:
            start = int(start_raw)
            end = min(int(end_raw), size - 1) if end_raw else size - 1
        if start < 0 or start >= size or end < start:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{size}"},
        ) from exc
    return start, end, status.HTTP_206_PARTIAL_CONTENT


__all__ = ["router"]
