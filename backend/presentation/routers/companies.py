"""/api/v1/companies routes — profile read + list + write (Phase 1 + G4).

This router covers:

- ``GET /profile`` — current user's own company profile.
- ``GET /{id}/profile`` — company profile by id (role-gated).
- ``GET /`` — directory listing (carcraft_employee) or linked-companies
  projection for other roles. Supports ``?format=csv`` export.
- ``GET /{id}`` — single company fetch with the same ownership rule as
  ``/profile``.
- ``POST /profile`` — upsert the current user's company.
- ``PUT /{id}`` — update any company (employees or owners).
- ``PUT /{id}/external-data`` — update enrichment fields only.
- ``DELETE /{id}`` — soft-deactivate (employees only).
- ``POST /import`` — bulk import companies from CSV.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.companies import (
    DeactivateCompanyCommand,
    UpdateCompanyCommand,
    UpdateCompanyExternalDataCommand,
    UpsertMyCompanyProfileCommand,
    handle_deactivate_company,
    handle_update_company,
    handle_update_company_external_data,
    handle_upsert_my_company_profile,
)
from application.commands.data_import import (
    UploadDataImportCommand,
    handle_upload_data_import,
)
from application.errors import ServiceError, domain_to_http
from application.queries.companies import (
    GetCompanyProfileQuery,
    GetMyCompanyProfileQuery,
    ListCompaniesQuery,
    handle_get_company_profile,
    handle_get_my_company_profile,
    handle_list_companies,
)
from application.queries.leasing import (
    ListLeasingCompaniesQuery,
    handle_list_leasing_companies,
)
from domain.errors import CompanyAccessDeniedError, DomainError
from infrastructure.database import get_db
from infrastructure.messaging.dwh_events import emit_company_changed
from presentation.dependencies.auth import get_current_user
from presentation.dependencies.csv_export import csv_streaming_response
from presentation.dependencies.export_format import ExportFormat, export_format_dep
from presentation.schemas.companies import (
    CompaniesListResponse,
    CompanyProfile,
    DeactivateCompanyResponse,
    UpdateCompanyExternalDataRequest,
    UpdateCompanyExternalDataResponse,
    UpdateCompanyRequest,
    UpdateCompanyResponse,
    UpsertCompanyProfileRequest,
    UpsertCompanyProfileResponse,
)

router = APIRouter()


_COMPANY_CSV_HEADERS = [
    "id",
    "name",
    "inn",
    "kpp",
    "ogrn",
    "company_type",
    "legal_address",
    "actual_address",
    "phone",
    "email",
    "website",
    "is_active",
    "users_count",
    "applications_count",
    "vehicles_count",
    "leasing_company_id",
    "distributor_id",
    "full_name",
    "director_full_name",
    "director_position",
    "director_inn",
    "bank_name",
    "bank_bik",
    "bank_account_number",
    "tax_system",
    "created_at",
    "updated_at",
]


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get(
    "/profile",
    response_model=CompanyProfile,
    summary="Профиль компании текущего пользователя",
    description=(
        "Возвращает профиль компании, привязанной к пользователю через "
        "`users.company_id`. Поля включают плоские enrichment-данные "
        "(пост-010 схема) и type-specific расширение "
        "(`leasing_company` или `distributor`) при наличии."
    ),
)
async def get_my_company_profile(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        profile = await handle_get_my_company_profile(
            GetMyCompanyProfileQuery(
                user_id=user["id"],
                user_role=user.get("role"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return JSONResponse(content=jsonable_encoder(profile))


@router.post(
    "/profile",
    response_model=UpsertCompanyProfileResponse,
    summary="Создать или обновить профиль своей компании",
    description=(
        "Upsert профиля компании, привязанной к текущему пользователю. "
        "Если `users.company_id` уже задан — обновляет ту же компанию; "
        "иначе создаёт новую и проставляет `users.company_id`. "
        "Для `leasing_company` / `distributor` — создаётся связанный "
        "подтип при первом сохранении."
    ),
)
async def upsert_my_company_profile(
    body: UpsertCompanyProfileRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    payload = body.model_dump(exclude_unset=True)
    try:
        result = await handle_upsert_my_company_profile(
            UpsertMyCompanyProfileCommand(
                user_id=user["id"],
                data=payload,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "",
    response_model=CompaniesListResponse,
    summary="Список компаний",
    description=(
        "Для сотрудников CarCraft возвращает весь каталог с пагинацией и "
        "поиском по `name` / `inn` / `email`. Для остальных ролей "
        "результат ограничен компаниями, в которых состоит пользователь "
        "(по `users.company_id` и `user_companies`). "
        "Поддерживает экспорт в CSV через ?format=csv."
    ),
)
async def list_companies(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    fmt: Annotated[ExportFormat, Depends(export_format_dep)] = "json",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=1000),
    search: str | None = Query(default=None),
    name: str | None = Query(default=None),
    phone: str | None = Query(default=None),
    company_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    _type: str | None = Query(default=None, alias="type"),
) -> JSONResponse | StreamingResponse:
    # `?type=leasing` — directory projection of active leasing companies
    # used by the dealer/client UI. Separate shape, bypasses ownership
    # filter (same contract as the old /leasing/companies endpoint).
    if _type == "leasing":
        leasing = await handle_list_leasing_companies(
            ListLeasingCompaniesQuery(), session
        )
        return JSONResponse(content=jsonable_encoder(leasing))

    export_limit = 10_000 if fmt in {"csv", "xlsx"} else limit
    try:
        result = await handle_list_companies(
            ListCompaniesQuery(
                actor_id=user["id"],
                actor_role=user.get("role"),
                page=1 if fmt in {"csv", "xlsx"} else page,
                limit=export_limit,
                search=search,
                name=name,
                phone=phone,
                company_type=company_type,
                is_active=is_active,
                include_relations=fmt in {"csv", "xlsx"},
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc

    if fmt == "json":
        return JSONResponse(content=jsonable_encoder(result))

    rows = result.get("companies", [])
    for row in rows:
        for key in ("created_at", "updated_at"):
            val = row.get(key)
            if val is not None:
                row[key] = str(val)

    filename = f"companies_{datetime.now(UTC).strftime('%Y-%m-%d')}.csv"
    return csv_streaming_response(_COMPANY_CSV_HEADERS, rows, filename)


@router.post(
    "/import",
    summary="[admin] Импорт компаний из CSV",
    description=(
        "Принимает CSV-файл с колонками: id, name, inn, company_type, phone, email, "
        "legal_address, actual_address, kpp, ogrn, website, director_full_name, "
        "director_position, director_inn, bank_name, bank_bik, bank_account_number, "
        "tax_system. company_type должен быть одним из: "
        "dealer, leasing_company, distributor, other. "
        "Если id указан и компания существует — обновляет, "
        "иначе ищет по inn и обновляет, иначе создаёт. "
        "Обрабатывается асинхронно — возвращает {jobId} для опроса прогресса."
    ),
    status_code=202,
)
async def import_companies(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
) -> JSONResponse:
    if user.get("role") != "carcraft_employee":
        raise _http(
            CompanyAccessDeniedError(
                "Импорт компаний доступен только сотрудникам Carcraft"
            )
        )

    content = await file.read()
    try:
        result = await handle_upload_data_import(
            UploadDataImportCommand(
                kind="companies",
                file_bytes=content,
                filename=file.filename,
                user_id=user["id"],
                params={
                    "actor_id": str(user["id"]),
                    "actor_role": user.get("role"),
                },
            ),
            session,
        )
    except ServiceError as exc:
        raise _http(exc) from exc
    return JSONResponse(content=result, status_code=202)


@router.get(
    "/{company_id}",
    response_model=CompanyProfile,
    summary="Компания по ID (без type-specific расширения)",
    description=(
        "Возвращает компанию по идентификатору. Доступ — тот же, что и у "
        "`GET /{id}/profile`: `carcraft_employee` или владелец."
    ),
)
async def get_company_by_id(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    company_id: Annotated[UUID, Path()],
) -> JSONResponse:
    try:
        profile = await handle_get_company_profile(
            GetCompanyProfileQuery(
                company_id=company_id,
                user_id=user["id"],
                user_role=user.get("role"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return JSONResponse(content=jsonable_encoder(profile))


@router.get(
    "/{company_id}/profile",
    response_model=CompanyProfile,
    summary="Профиль компании по ID",
    description=(
        "Возвращает профиль компании по идентификатору. Доступно: "
        "сотрудникам CarCraft (`carcraft_employee`); пользователям, у которых "
        "`users.company_id` совпадает с запрашиваемой компанией; "
        "пользователям, привязанным к компании через `user_companies`. "
        "Иначе — 403."
    ),
)
async def get_company_profile_by_id(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    company_id: Annotated[UUID, Path()],
) -> JSONResponse:
    try:
        profile = await handle_get_company_profile(
            GetCompanyProfileQuery(
                company_id=company_id,
                user_id=user["id"],
                user_role=user.get("role"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return JSONResponse(content=jsonable_encoder(profile))


# ---------------------------------------------------------------------------
# Phase 15 H3 — /{company_id}/stats deleted; no frontend caller.
# ---------------------------------------------------------------------------


@router.put(
    "/{company_id}",
    response_model=UpdateCompanyResponse,
    summary="Обновить компанию",
    description=(
        "Частичное обновление компании. Доступно: сотрудникам CarCraft, "
        "владельцу (`users.company_id`) или пользователю, привязанному "
        "через `user_companies`. Владельцы могут изменять обычные поля; "
        "поле `is_active` (включая явно переданный `null`) доступно только "
        "сотрудникам CarCraft. ИНН проверяется на уникальность."
    ),
)
async def update_company(
    body: UpdateCompanyRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    company_id: Annotated[UUID, Path()],
) -> JSONResponse:
    payload = body.model_dump(exclude_unset=True)
    try:
        result = await handle_update_company(
            UpdateCompanyCommand(
                company_id=company_id,
                actor_id=user["id"],
                actor_role=user.get("role"),
                data=payload,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.put(
    "/{company_id}/external-data",
    response_model=UpdateCompanyExternalDataResponse,
    summary="Обновить enrichment-поля компании (1С / внешний справочник)",
    description=(
        "Позволяет обновить только поля обогащения компании (`full_name`, "
        "`legal_address_details`, `main_okved_*`, `director_*`, `bank_*`, "
        "финансовые агрегаты и т.п.). Доступно: сотрудникам CarCraft или "
        "владельцам компании. Компания должна иметь ИНН."
    ),
)
async def update_company_external_data(
    body: UpdateCompanyExternalDataRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    company_id: Annotated[UUID, Path()],
) -> JSONResponse:
    payload = body.model_dump(exclude_unset=True)
    try:
        result = await handle_update_company_external_data(
            UpdateCompanyExternalDataCommand(
                company_id=company_id,
                actor_id=user["id"],
                actor_role=user.get("role"),
                data=payload,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.delete(
    "/{company_id}",
    response_model=DeactivateCompanyResponse,
    summary="Деактивировать компанию (soft-delete)",
    description=(
        "Помечает компанию как `is_active=false` и деактивирует всех "
        "её активных пользователей + связанные записи `leasing_companies` / "
        "`distributors`. Доступно только сотрудникам CarCraft."
    ),
)
async def deactivate_company(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    company_id: Annotated[UUID, Path()],
) -> JSONResponse:
    if user.get("role") != "carcraft_employee":
        raise _http(
            CompanyAccessDeniedError(
                "Деактивация компании доступна только сотрудникам Carcraft"
            )
        )
    try:
        result = await handle_deactivate_company(
            DeactivateCompanyCommand(
                company_id=company_id,
                actor_id=user["id"],
                actor_role=user.get("role"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    event_payload = result.pop("company_changed_event")
    await session.commit()
    emit_company_changed(event_payload)
    return JSONResponse(content=jsonable_encoder(result))
