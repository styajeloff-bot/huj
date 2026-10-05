"""/api/v1/users routes — user-linked companies + selection history + sessions + status.

R1 (Phase 9) consolidated the previously parallel auth/admin-auth sessions hierarchy
into a single ``/users/:id/sessions`` surface where ``:id`` is either ``"me"`` or
an integer user id (admin-only).
"""
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    File,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.admin_mfa import (
    AdminResetMfaCommand,
    handle_admin_reset_mfa,
)
from application.commands.admin_users import (
    CreateUserCommand,
    DeleteUserCommand,
    UpdateUserCommand,
    handle_create_user,
    handle_delete_user,
    handle_update_user,
)
from application.commands.auth import handle_revoke_all_sessions
from application.commands.client import (
    RequestPhoneChangeCommand,
    VerifyPhoneChangeCommand,
    handle_request_phone_change,
    handle_verify_phone_change,
)
from application.commands.data_import import (
    UploadDataImportCommand,
    handle_upload_data_import,
)
from application.commands.employees import (
    InviteEmployeeCommand,
    ListCompanyMembersQuery,
    RemoveCompanyMemberCommand,
    UpdateEmployeePermissionsCommand,
    UpdateEmployeeSubRoleCommand,
    handle_invite_employee,
    handle_list_company_members,
    handle_remove_company_member,
    handle_update_employee_permissions,
    handle_update_employee_sub_role,
)
from application.commands.sessions import (
    handle_admin_disable_user,
    handle_admin_enable_user,
    handle_admin_force_logout,
    handle_admin_list_sessions,
    handle_list_my_sessions,
    handle_revoke_my_session,
)
from application.commands.user_companies import (
    AddCompanyToUserCommand,
    SetCompanySelectHistoryCommand,
    handle_add_company_to_user,
    handle_set_company_select_history,
)
from application.commands.users import (
    UpdateMeProfileCommand,
    handle_update_me_profile,
)
from application.common import _isoformat
from application.errors import ServiceError, domain_to_http
from application.queries.admin_users import (
    GetUserAdminQuery,
    ListUsersQuery,
    handle_get_user_admin,
    handle_list_users,
)
from application.queries.user_companies import (
    GetClientUserCompaniesQuery,
    GetCompanySelectHistoryQuery,
    GetUserCompaniesQuery,
    handle_get_client_user_companies,
    handle_get_company_select_history,
    handle_get_user_companies,
)
from application.queries.users import (
    GetMeProfileQuery,
    handle_get_me_profile,
)
from domain.errors import DomainError, UserNotFoundError
from domain.services.scopes import AUTH_ADMIN, USERS_ADMIN
from infrastructure.auth import decode_refresh_token
from infrastructure.cache.token_denylist import AuthDenylistError, revoke
from infrastructure.database import get_db
from infrastructure.messaging.dwh_events import emit_user_changed
from presentation.dependencies.auth import get_current_user, require_scopes
from presentation.dependencies.csv_export import csv_streaming_response
from presentation.dependencies.export_format import ExportFormat, export_format_dep
from presentation.schemas.auth import MessageResponse
from presentation.schemas.users import (
    AddCompanyBody,
    AddCompanyResponse,
    ClientProfilePatch,
    CompanyMembersResponse,
    CompanySelectHistoryResponse,
    DealerProfilePatch,
    InviteEmployeeRequest,
    InviteEmployeeResponse,
    PhoneChangeMessageResponse,
    PhoneChangeRequestBody,
    PhoneChangeVerifyBody,
    SetCompanySelectHistoryBody,
    SetCompanySelectHistoryResponse,
    UpdatePermissionsRequest,
    UpdateSubRoleRequest,
    UserAdminDetailResponse,
    UserAdminPatchBody,
    UserAdminPatchResponse,
    UserCompaniesResponse,
    UserCreateBody,
    UserCreateResponse,
    UserDeleteResponse,
    UserMePatchBody,
    UserMeResponse,
    UserMfaResetBody,
    UserMfaResetResponse,
    UserRevokeAllResponse,
    UserSessionListResponse,
    UsersListResponse,
)

_USER_CSV_HEADERS = [
    "id",
    "name",
    "email",
    "phone",
    "role",
    "company_id",
    "company_name",
    "company_inn",
    "company_type",
    "is_active",
    "email_verified",
    "last_login",
    "created_at",
    "updated_at",
]

router = APIRouter()


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get(
    "/me/companies",
    response_model=UserCompaniesResponse,
    summary="Компании, привязанные к текущему пользователю",
    description=(
        "Возвращает активные компании, связанные с пользователем через "
        "user_companies или users.company_id. Отсортированы по названию. "
        "Self-scope: работает только для текущего авторизованного юзера."
    ),
)
async def get_my_companies(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    companies = await handle_get_user_companies(
        session, GetUserCompaniesQuery(user_id=user["id"])
    )
    return JSONResponse(content=jsonable_encoder({"companies": companies}))


@router.post(
    "/me/companies",
    response_model=AddCompanyResponse,
    status_code=201,
    summary="Привязать компанию к текущему пользователю",
    description=(
        "Создаёт или находит компанию по ИНН, привязывает её к пользователю "
        "через user_companies. В фоне планирует синхронизацию данных из 1C. "
        "Self-scope."
    ),
)
async def add_company_to_me(
    body: AddCompanyBody,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_add_company_to_user(
            session,
            AddCompanyToUserCommand(
                user_id=user["id"],
                company=body.company.model_dump(exclude_none=False),
            ),
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc

    await session.commit()
    return JSONResponse(
        status_code=201,
        content=jsonable_encoder(
            {
                "message": "Компания успешно добавлена",
                "company_id": result.company_id,
                "companies": result.companies,
            }
        ),
    )


@router.get(
    "/me/company-select-history",
    response_model=CompanySelectHistoryResponse,
    summary="Последняя выбранная компания текущего пользователя",
    description=(
        "Возвращает текущий выбор компании для пользователя. Если записи "
        "нет, а компании привязаны — создаёт запись, указывающую на первую "
        "привязанную компанию. Self-scope."
    ),
)
async def get_my_company_select_history(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    data = await handle_get_company_select_history(
        session, GetCompanySelectHistoryQuery(user_id=user["id"])
    )
    await session.commit()
    return JSONResponse(content=jsonable_encoder(data))


@router.put(
    "/me/company-select-history",
    response_model=SetCompanySelectHistoryResponse,
    summary="Обновить выбранную компанию текущего пользователя",
    description=(
        "Требует, чтобы компания была привязана к пользователю (403 иначе). "
        "Self-scope."
    ),
)
async def set_my_company_select_history(
    body: SetCompanySelectHistoryBody,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_set_company_select_history(
            session,
            SetCompanySelectHistoryCommand(
                user_id=user["id"], company_id=body.company_id
            ),
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc

    await session.commit()
    return JSONResponse(
        content=jsonable_encoder(
            {"company_id": result["company_id"], "updated_at": result["updated_at"]}
        )
    )


# ---------------------------------------------------------------------------
# /users/me — unified profile surface (R13a)
# Consolidates the former /client/profile, /dealer/profile,
# /distributor/profile endpoints into one role-discriminated resource.
# ---------------------------------------------------------------------------


def _compose_me_response(
    base: dict[str, Any], role_specific: dict[str, Any] | None
) -> dict[str, Any]:
    payload = dict(base)
    payload["role_specific"] = role_specific
    return payload


@router.get(
    "/me",
    response_model=UserMeResponse,
    summary="Профиль текущего пользователя (unified)",
    description=(
        "Возвращает базовые поля пользователя (id, phone, email, name, "
        "role, company_id) и role-specific блок, зависящий от роли:\n\n"
        "* ``role=client`` → `role_specific` содержит поля из "
        "`client_profiles` (client_type, passport_series, company_name, "
        "inn, kpp, ogrn, legal_address, address, birth_date, notification_settings, "
        "two_factor_enabled, phone_verified).\n"
        "* ``role=dealer`` → `role_specific.company` + "
        "`role_specific.stats` (total_clients, total_sales, total_revenue, "
        "conversion_rate, ...).\n"
        "* ``role=distributor`` → `role_specific.company` + "
        "`role_specific.distributor` (regions, brands, is_active).\n"
        "* другие роли (employee, leasing_company) → `role_specific=None`.\n\n"
        "Self-scope: работает только для аутентифицированного пользователя. "
        "Заменяет удалённые `GET /client/profile`, `GET /dealer/profile`, "
        "`GET /distributor/profile`."
    ),
)
async def get_my_profile(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_get_me_profile(
            GetMeProfileQuery(
                user_id=user["id"],
                role=str(user.get("role") or ""),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return JSONResponse(
        content=jsonable_encoder(
            _compose_me_response(result.base, result.role_specific)
        )
    )


@router.patch(
    "/me",
    response_model=UserMeResponse,
    summary="Частично обновить профиль текущего пользователя",
    description=(
        "Partial update. Верхнеуровневые поля (``name``, ``email``) пишутся "
        "в `users`. Блок ``role_specific`` опционален и должен совпадать "
        "с ролью текущего пользователя:\n\n"
        "* ``role=client`` — допустим `client_type`, `passport_*`, "
        "`company_name`, `inn`, `kpp`, `ogrn`, `legal_address`, `address`, "
        "`birth_date`, `notification_settings`.\n"
        "* ``role=dealer`` — допустим только вложенный блок `company` "
        "(name/inn/kpp/ogrn/legal_address/actual_address/phone/email/"
        "website).\n"
        "* другие роли — ``role_specific`` должен отсутствовать.\n\n"
        "Передача `role_specific`-блока, не соответствующего роли, "
        "возвращает **422**. Для смены телефона — отдельный "
        "``POST /users/me/phone-change`` + `.../verify` flow."
    ),
)
async def patch_my_profile(
    body: UserMePatchBody,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    payload = body.model_dump(exclude_unset=True)
    base_fields: dict[str, Any] = {}
    if "name" in payload:
        base_fields["name"] = payload["name"]
    if "email" in payload:
        base_fields["email"] = payload["email"]

    role_specific_kind: str | None = None
    role_specific_data: dict[str, Any] = {}
    if body.role_specific is not None:
        if isinstance(body.role_specific, ClientProfilePatch):
            role_specific_kind = "client"
        elif isinstance(body.role_specific, DealerProfilePatch):
            role_specific_kind = "dealer"
        role_specific_data = body.role_specific.model_dump(exclude_unset=True)

    try:
        result = await handle_update_me_profile(
            UpdateMeProfileCommand(
                user_id=user["id"],
                role=str(user.get("role") or ""),
                base_fields=base_fields,
                role_specific_kind=role_specific_kind,
                role_specific_data=role_specific_data,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(
        content=jsonable_encoder(
            _compose_me_response(result.base, result.role_specific)
        )
    )


# ---------------------------------------------------------------------------
# Sessions — /users/:id/sessions (R1)
# :id == "me" → self-scope. :id != me → admin-scope (AUTH_ADMIN).
# ---------------------------------------------------------------------------


def _is_admin(user: dict[str, Any]) -> bool:
    scopes = user.get("scopes") or []
    return AUTH_ADMIN in scopes


def _resolve_user_id(user_id: str, current_user: dict[str, Any]) -> tuple[UUID, bool]:
    """Resolve ``user_id`` path parameter. Returns (uuid, is_self).

    * ``"me"`` → current user's id, is_self=True.
    * UUID string → parsed. is_self is True only if it equals current user's id.

    Raises HTTPException(404) for malformed path, HTTPException(403) when the
    caller is addressing someone else without admin scope.
    """
    current_id = current_user["id"]
    if isinstance(current_id, str):
        current_id = UUID(current_id)
    if user_id == "me":
        return current_id, True
    try:
        parsed = UUID(user_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Пользователь не найден") from exc
    is_self = parsed == current_id
    if not is_self and not _is_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Недостаточно прав доступа",
                "code": "INSUFFICIENT_PERMISSIONS",
            },
        )
    return parsed, is_self


def _current_session_id_from_cookie(refresh_token: str | None) -> UUID | None:
    if not refresh_token:
        return None
    try:
        payload = decode_refresh_token(refresh_token)
    except JWTError:
        return None
    sid = payload.get("sid")
    if sid is None:
        return None
    return UUID(sid) if isinstance(sid, str) else sid


async def _revoke_access_cookie(access_token: str | None) -> None:
    """Put the access-token jti on the denylist. Safe for junk/missing tokens."""
    if not access_token:
        return
    from infrastructure.auth import decode_access_token  # local import avoids cycles
    try:
        payload = decode_access_token(access_token)
    except JWTError:
        return
    jti = payload.get("jti")
    if not jti:
        return
    try:
        await revoke(jti, exp=payload.get("exp"))
    except AuthDenylistError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Не удалось отозвать текущий токен",
                "code": "REVOCATION_FAILED",
            },
        ) from exc


@router.get(
    "/{user_id}/sessions",
    response_model=UserSessionListResponse,
    summary="Список активных сессий пользователя",
    description=(
        "Для ``:user_id == \"me\"`` возвращает собственные активные сессии "
        "(IP, User-Agent, страна, время). Поле ``isCurrent=true`` отмечает "
        "сессию, соответствующую текущему ``refreshToken`` cookie. "
        "Для любого другого ``user_id`` (UUID) требуется scope "
        "``auth:admin``; admin получает полный список сессий (включая истёкшие), "
        "поле ``isCurrent`` всегда ``false``."
    ),
)
async def list_user_sessions(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    user_id: str = Path(..., description='"me" или UUID пользователя'),
    refresh_token: Annotated[str | None, Cookie(alias="refreshToken")] = None,
) -> JSONResponse:
    target_id, is_self = _resolve_user_id(user_id, current_user)
    if is_self:
        rows = await handle_list_my_sessions(
            target_id, session, role=current_user.get("role")
        )
        current_sid = _current_session_id_from_cookie(refresh_token)
        payload = [
            {
                "id": str(row["id"]),
                "ipAddress": row["ip_address"],
                "userAgent": row["user_agent"],
                "countryCode": row["country_code"],
                "createdAt": row["created_at"].isoformat() if row["created_at"] else None,
                "lastUsedAt": row["last_used_at"].isoformat() if row["last_used_at"] else None,
                "expiresAt": row["expires_at"].isoformat() if row["expires_at"] else None,
                "isCurrent": row["id"] == current_sid,
            }
            for row in rows
        ]
        return JSONResponse(content={"sessions": payload})

    rows = await handle_admin_list_sessions(target_id, session)
    payload = [
        {
            "id": str(row["id"]),
            "ipAddress": row["ip_address"],
            "userAgent": row["user_agent"],
            "countryCode": row["country_code"],
            "createdAt": row["created_at"].isoformat() if row["created_at"] else None,
            "lastUsedAt": row["last_used_at"].isoformat() if row["last_used_at"] else None,
            "expiresAt": row["expires_at"].isoformat() if row["expires_at"] else None,
            "isCurrent": False,
        }
        for row in rows
    ]
    return JSONResponse(content={"sessions": payload})


@router.delete(
    "/{user_id}/sessions",
    response_model=UserRevokeAllResponse,
    summary="Отозвать все сессии пользователя",
    description=(
        "Для ``:user_id == \"me\"`` — self-revoke-all: удаляет все refresh-"
        "сессии текущего пользователя и денилистит текущий access-токен. "
        "Для остальных пользователей требуется scope ``auth:admin`` и "
        "выполняется force-logout. Опциональный ``?except_current=true`` для "
        "self-случая сохраняет сессию, соответствующую текущему "
        "``refreshToken`` cookie (для «logout on other devices»)."
    ),
)
async def revoke_user_sessions(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    user_id: str = Path(..., description='"me" или UUID пользователя'),
    except_current: bool = Query(
        False,
        description=(
            "Если true, оставляет текущую сессию. Только для self-scope."
        ),
    ),
    refresh_token: Annotated[str | None, Cookie(alias="refreshToken")] = None,
    access_token: Annotated[str | None, Cookie(alias="accessToken")] = None,
) -> JSONResponse:
    target_id, is_self = _resolve_user_id(user_id, current_user)
    if is_self:
        keep_sid: UUID | None = None
        if except_current:
            keep_sid = _current_session_id_from_cookie(refresh_token)
        killed = await handle_revoke_all_sessions(
            target_id, session, except_session_id=keep_sid
        )
        await session.commit()
        if not except_current:
            await _revoke_access_cookie(access_token)
        return JSONResponse(content={"revokedCount": killed})

    count = await handle_admin_force_logout(target_id, session)
    await session.commit()
    return JSONResponse(content={"revokedCount": count})


@router.delete(
    "/{user_id}/sessions/{session_id}",
    status_code=204,
    summary="Отозвать одну сессию пользователя",
    description=(
        "Для ``:user_id == \"me\"`` удаляет одну refresh-сессию по "
        "``session_id`` при условии владения. Для чужих id возвращает 404, "
        "не раскрывая существования сессий другого пользователя. "
        "Для любого другого ``user_id`` требуется scope ``auth:admin`` и "
        "удаление проверяет владение сессии целевым пользователем."
    ),
    response_model=None,
)
async def revoke_user_session_one(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    user_id: Annotated[str, Path()],
    session_id: Annotated[UUID, Path()],
) -> JSONResponse:
    target_id, _is_self = _resolve_user_id(user_id, current_user)
    try:
        await handle_revoke_my_session(target_id, session_id, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(status_code=204, content=None)


# ---------------------------------------------------------------------------
# Admin-scope CRUD on /users (R13b) — consolidated from /admin/users.
# ---------------------------------------------------------------------------


_USERS_ADMIN_SELF_FIELDS: frozenset[str] = frozenset(
    {"name", "email", "phone", "company_id"}
)


def _is_users_admin(user: dict[str, Any]) -> bool:
    scopes = user.get("scopes") or []
    return USERS_ADMIN in scopes


@router.get(
    "",
    response_model=UsersListResponse,
    summary="[admin] Список пользователей",
    description=(
        "Постранично возвращает пользователей с фильтрами по роли, "
        "компании, активности и поиску по имени/email/компании. "
        "Требует scope ``users:admin`` — обычные пользователи получают 403. "
        "Для чтения собственного профиля — ``GET /users/me``."
    ),
    dependencies=[Depends(require_scopes(USERS_ADMIN))],
)
async def list_users(
    session: Annotated[AsyncSession, Depends(get_db)],
    fmt: Annotated[ExportFormat, Depends(export_format_dep)] = "json",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    company_id: Annotated[UUID | None, Query()] = None,
    phone: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> JSONResponse | StreamingResponse:
    export_limit = 10_000 if fmt == "csv" else limit
    result = await handle_list_users(
        ListUsersQuery(
            page=1 if fmt == "csv" else page,
            limit=export_limit,
            search=search,
            role=role,
            is_active=is_active,
            company_id=company_id,
            phone=phone,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
        session,
    )
    if fmt == "json":
        return JSONResponse(content=jsonable_encoder(result))

    rows = result.get("users", [])
    for row in rows:
        for key in ("created_at", "updated_at", "last_login"):
            val = row.get(key)
            if val is not None:
                row[key] = str(val)

    filename = f"users_{datetime.now(UTC).strftime('%Y-%m-%d')}.csv"
    return csv_streaming_response(_USER_CSV_HEADERS, rows, filename)


@router.post(
    "",
    status_code=201,
    response_model=UserCreateResponse,
    summary="[admin] Создать пользователя",
    description=(
        "Админ создаёт нового пользователя с указанной ролью. "
        "Не путать с self-регистрацией (``/auth/login`` + OTP-flow). "
        "Уникальность проверяется по email и телефону. "
        "Требует scope ``users:admin``."
    ),
    dependencies=[Depends(require_scopes(USERS_ADMIN))],
)
async def create_user(
    body: UserCreateBody,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_create_user(
            CreateUserCommand(
                name=body.name,
                email=body.email,
                phone=body.phone,
                role=body.role,
                company_id=body.company_id,
                company=(
                    body.company.model_dump(exclude_none=False)
                    if body.company is not None
                    else None
                ),
                is_active=body.is_active,
                email_verified=body.email_verified,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(
        content=jsonable_encoder(
            {"user": result, "message": "Пользователь успешно создан"}
        ),
        status_code=201,
        headers={"Location": f"/api/v1/users/{result['id']}"},
    )


@router.post(
    "/import",
    summary="[admin] Импорт пользователей из CSV",
    description=(
        "Принимает CSV-файл с колонками: id, phone, role, name, email, "
        "company_id, is_active. "
        "Обязательные: phone, role. Если id указан и пользователь существует — обновляет, "
        "иначе ищет по phone и обновляет, иначе создаёт."
    ),
    dependencies=[Depends(require_scopes(USERS_ADMIN))],
    status_code=202,
)
async def import_users(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
) -> JSONResponse:
    content = await file.read()
    try:
        result = await handle_upload_data_import(
            UploadDataImportCommand(
                kind="users",
                file_bytes=content,
                filename=file.filename,
                user_id=user["id"],
            ),
            session,
        )
    except ServiceError as exc:
        raise _http(exc) from exc
    return JSONResponse(content=result, status_code=202)


# ---------------------------------------------------------------------------
# PATCH /users/:id — extended (R13b) from R1 status-only.
# :id == "me" → self-scope (subset of fields). :id != me → admin-scope.
# ---------------------------------------------------------------------------


def _forbidden(message: str) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={"error": message, "code": "INSUFFICIENT_PERMISSIONS"},
    )


def _resolve_patch_target(
    user_id: str, current_user: dict[str, Any]
) -> tuple[UUID, bool]:
    current_id = current_user["id"]
    if isinstance(current_id, str):
        current_id = UUID(current_id)
    if user_id == "me":
        return current_id, True
    try:
        parsed = UUID(user_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=404, detail="Пользователь не найден"
        ) from exc
    return parsed, parsed == current_id


def _enforce_patch_authz(
    payload: dict[str, Any], is_self: bool, actor_is_admin: bool
) -> None:
    if not is_self and not actor_is_admin:
        raise _forbidden("Недостаточно прав доступа")

    status_flip = "status" in payload or "is_active" in payload
    if is_self and actor_is_admin and status_flip:
        raise _forbidden("Нельзя менять статус собственной учётной записи")

    if is_self and not actor_is_admin:
        disallowed = set(payload) - _USERS_ADMIN_SELF_FIELDS
        if disallowed:
            raise _forbidden(
                "Эти поля доступны только администратору: "
                + ", ".join(sorted(disallowed))
            )


@router.get(
    "/{user_id}/companies",
    response_model=UserCompaniesResponse,
    summary="[admin] Компании клиента",
    description=(
        "Возвращает активные компании, привязанные к целевому пользователю с "
        "ролью ``client``. Требует scope ``users:admin``."
    ),
    dependencies=[Depends(require_scopes(USERS_ADMIN))],
)
async def get_user_client_companies(
    user_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        companies = await handle_get_client_user_companies(
            session, GetClientUserCompaniesQuery(user_id=user_id)
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return JSONResponse(content=jsonable_encoder({"companies": companies}))


@router.post(
    "/{user_id}/companies",
    response_model=AddCompanyResponse,
    status_code=201,
    summary="[admin] Добавить компанию клиенту",
    description=(
        "Создаёт дополнительную привязку компании к целевому пользователю с "
        "ролью ``client``. Существующие привязки и ``users.company_id`` не "
        "заменяются. Требует scope ``users:admin``."
    ),
    dependencies=[Depends(require_scopes(USERS_ADMIN))],
)
async def add_user_client_company(
    user_id: UUID,
    body: AddCompanyBody,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_add_company_to_user(
            session,
            AddCompanyToUserCommand(
                user_id=user_id,
                company=body.company.model_dump(exclude_none=False),
                grant_administrator=True,
                require_client=True,
            ),
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(
        status_code=201,
        content=jsonable_encoder(
            {
                "message": "Компания успешно добавлена",
                "company_id": result.company_id,
                "companies": result.companies,
            }
        ),
    )


@router.get(
    "/{user_id}",
    response_model=UserAdminDetailResponse,
    summary="[admin] Получить пользователя по id",
    description=(
        "Возвращает карточку пользователя со всеми полями админ-вью "
        "(id, phone, email, name, role, company_id, "
        "is_active, email_verified, created_at, last_login_at, "
        "company_name/inn/type). Требует scope ``users:admin``. "
        "Для self-чтения используйте ``GET /users/me``."
    ),
    dependencies=[Depends(require_scopes(USERS_ADMIN))],
)
async def get_user_admin(
    user_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_get_user_admin(
            GetUserAdminQuery(user_id=user_id), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder({"user": result}))


@router.patch(
    "/{user_id}",
    response_model=UserAdminPatchResponse,
    summary="Частично обновить пользователя",
    description=(
        "Partial update. Для ``user_id == \"me\"`` — self-scope: допустимы "
        "``name``, ``email``, ``phone``, ``company_id``, "
        "Попытка передать ``role``/``status``/"
        "``is_active``/``email_verified`` в self-scope → 403.\n\n"
        "Для любого другого ``user_id`` требуется scope ``users:admin`` "
        "и принимается полный набор полей. ``status`` — enum-projection "
        "над ``is_active`` (``\"disabled\"`` деактивирует пользователя и "
        "удаляет его refresh-сессии; ``\"active\"`` включает обратно). "
        "Админ не может менять статус собственной учётной записи (403), "
        "чтобы предотвратить самоблокировку."
    ),
)
async def patch_user(
    body: UserAdminPatchBody,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    user_id: str = Path(...),
) -> JSONResponse:
    payload = body.model_dump(exclude_unset=True)
    target_id, is_self = _resolve_patch_target(user_id, current_user)
    _enforce_patch_authz(payload, is_self, _is_users_admin(current_user))

    # Map `status` → `is_active` and run the side-effecting session wipe
    # via the dedicated admin-sessions command when status flips.
    status = payload.pop("status", None)
    if status is not None:
        if "is_active" in payload:
            raise HTTPException(
                status_code=422,
                detail="Нельзя одновременно передавать `status` и `is_active`",
            )
        try:
            if status == "disabled":
                await handle_admin_disable_user(target_id, session)
            else:
                await handle_admin_enable_user(target_id, session)
        except (ServiceError, DomainError) as exc:
            raise _http(exc) from exc

    # Apply remaining fields via the admin-update command (covers column
    # writes + email/phone/company uniqueness checks + role validation).
    try:
        updated = await handle_update_user(
            UpdateUserCommand(user_id=target_id, fields=payload),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()

    if status == "disabled":
        message = "Пользователь деактивирован"
    elif status == "active":
        message = "Пользователь активирован"
    else:
        message = "Пользователь успешно обновлён"

    return JSONResponse(
        content=jsonable_encoder({"user": updated, "message": message})
    )


@router.delete(
    "/{user_id}",
    response_model=UserDeleteResponse,
    summary="[admin] Деактивировать пользователя",
    description=(
        "Soft-delete: выставляет ``is_active=False`` у целевого пользователя. "
        "Физически запись не удаляется — полное удаление не предусмотрено "
        "ради целостности связанных данных (заявки, документы, заказы). "
        "Требует scope ``users:admin``. Чтобы предотвратить самоблокировку "
        "админа, удаление собственной учётной записи запрещено (403)."
    ),
    dependencies=[Depends(require_scopes(USERS_ADMIN))],
)
async def delete_user(
    user_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> JSONResponse:
    current_id = current_user["id"]
    if isinstance(current_id, str):
        current_id = UUID(current_id)
    if user_id == current_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Нельзя удалить собственную учётную запись",
                "code": "INSUFFICIENT_PERMISSIONS",
            },
        )
    try:
        result = await handle_delete_user(
            DeleteUserCommand(user_id=user_id), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Phone-change (self-only) — moved from /client/phone-change/*.
# ---------------------------------------------------------------------------


def _ensure_phone_change_role(user: dict[str, Any]) -> None:
    """Match the old /client-phone-change role gating (client + employee)."""
    if user.get("role") not in {"client", "carcraft_employee"}:
        raise HTTPException(status_code=403, detail="Недостаточно прав доступа")


@router.post(
    "/me/phone-change",
    response_model=PhoneChangeMessageResponse,
    summary="Запрос SMS на смену телефона",
    description=(
        "Генерирует 4-значный код, сохраняет его в ``verification_codes`` "
        "(TTL 10 минут) и отправляет на новый номер. Если новый номер уже "
        "принадлежит другому пользователю — 409. Двухшаговый OTP-flow: "
        "завершить смену — ``POST /users/me/phone-change/verify``."
    ),
)
async def me_phone_change_request(
    body: PhoneChangeRequestBody,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _ensure_phone_change_role(user)
    try:
        await handle_request_phone_change(
            RequestPhoneChangeCommand(
                user_id=user["id"], new_phone=body.new_phone
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(
        content={"message": "Код подтверждения отправлен на новый номер телефона"}
    )


# ---------------------------------------------------------------------------
# DELETE /users/:id/mfa — admin-initiated MFA reset (R8)
# Replaces the former POST /admin/auth/users/:id/reset-mfa.
# ---------------------------------------------------------------------------


@router.delete(
    "/{user_id}/mfa",
    response_model=UserMfaResetResponse,
    summary="[admin] Сбросить MFA пользователя",
    description=(
        "Аварийный сброс MFA, когда пользователь потерял все факторы "
        "(телефон, authenticator, резервные коды). Требует scope "
        "``auth:admin``. Отключает MFA, удаляет все refresh-сессии и "
        "пишет в аудит, кто, кому и по какой причине выполнил сброс "
        "(поле ``reason`` — свободный текст, обычно ID тикета "
        "поддержки). Возвращает 400, если у пользователя MFA не включена "
        "(no-op отказываем, чтобы аудит не засорялся), 404 — если "
        "пользователь не найден."
    ),
    dependencies=[Depends(require_scopes(AUTH_ADMIN))],
)
async def delete_user_mfa(
    body: UserMfaResetBody,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[dict[str, Any], Depends(get_current_user)],
    user_id: Annotated[UUID, Path()],
) -> JSONResponse:
    try:
        killed = await handle_admin_reset_mfa(
            AdminResetMfaCommand(
                target_user_id=user_id,
                reason=body.reason,
                by_user_id=admin["id"],
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content={"message": "MFA сброшена", "sessionsKilled": killed}
    )


@router.post(
    "/me/phone-change/verify",
    response_model=PhoneChangeMessageResponse,
    summary="Подтверждение смены телефона",
    description=(
        "Проверяет OTP-код и обновляет ``users.phone``; "
        "выставляет ``phone_verified=true`` и удаляет использованный код. "
        "Возвращает 400 при неверном или истёкшем коде."
    ),
)
async def me_phone_change_verify(
    body: PhoneChangeVerifyBody,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _ensure_phone_change_role(user)
    try:
        await handle_verify_phone_change(
            VerifyPhoneChangeCommand(
                user_id=user["id"],
                new_phone=body.new_phone,
                code=body.code,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    try:
        user_row = await handle_get_user_admin(
            GetUserAdminQuery(user_id=user["id"]), session
        )
    except UserNotFoundError:
        user_row = None
    if user_row is not None:
        emit_user_changed({
            "user_id": user_row["id"],
            "email": user_row.get("email"),
            "name": user_row.get("name"),
            "role": user_row.get("role"),
            "company_id": user_row.get("company_id"),
            "phone": user_row.get("phone"),
            "is_active": user_row.get("is_active"),
            "email_verified": user_row.get("email_verified"),
            "phone_verified": user_row.get("phone_verified"),
            "last_login": _isoformat(user_row.get("last_login")),
            "deleted_at": _isoformat(user_row.get("deleted_at")),
            "mfa_enabled": user_row.get("mfa_enabled"),
            "created_at": _isoformat(user_row.get("created_at")),
            "updated_at": _isoformat(user_row.get("updated_at")),
            "_deleted": False,
        })
    return JSONResponse(content={"message": "Номер телефона успешно изменён"})


# ---------------------------------------------------------------------------
# Employee invitation & company member management
# ---------------------------------------------------------------------------


@router.post(
    "/me/companies/{company_id}/invite",
    response_model=InviteEmployeeResponse,
    summary="Пригласить сотрудника в компанию",
    description=(
        "Отправляет SMS-приглашение на указанный телефон. "
        "Если пользователь не существует — создаёт его. "
        "Связывает пользователя с компанией как employee. "
        "Требует роли administrator или manager в указанной компании."
    ),
)
async def invite_employee(
    company_id: UUID,
    body: InviteEmployeeRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_invite_employee(
            InviteEmployeeCommand(
                actor_user_id=user["id"],
                company_id=company_id,
                phone=body.phone,
                actor_role=user.get("role"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(
        content=jsonable_encoder(
            {"message": result["message"], "user_id": result["user_id"]}
        )
    )


@router.get(
    "/me/companies/{company_id}/members",
    response_model=CompanyMembersResponse,
    summary="Список сотрудников компании",
    description=(
        "Возвращает всех пользователей, связанных с компанией, "
        "включая их саб-роли и права. Любой связанный пользователь "
        "может просматривать список."
    ),
)
async def list_company_members(
    company_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        members = await handle_list_company_members(
            ListCompanyMembersQuery(
                actor_user_id=user["id"],
                company_id=company_id,
                actor_role=user.get("role"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return JSONResponse(content=jsonable_encoder({"members": members}))


@router.patch(
    "/me/companies/{company_id}/members/{target_user_id}/permissions",
    response_model=MessageResponse,
    summary="Изменить права сотрудника",
    description=(
        "Позволяет administrator или manager включить/отключить "
        "у сотрудника права на просмотр и создание заявок."
    ),
)
async def update_member_permissions(
    company_id: UUID,
    target_user_id: UUID,
    body: UpdatePermissionsRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_update_employee_permissions(
            UpdateEmployeePermissionsCommand(
                actor_user_id=user["id"],
                company_id=company_id,
                target_user_id=target_user_id,
                can_view_applications=body.can_view_applications,
                can_create_applications=body.can_create_applications,
                actor_role=user.get("role"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.patch(
    "/me/companies/{company_id}/members/{target_user_id}/role",
    response_model=MessageResponse,
    summary="Изменить саб-роль сотрудника",
    description=(
        "Позволяет administrator назначить сотруднику роль "
        "administrator, manager или employee. Только administrator "
        "может вызывать этот endpoint."
    ),
)
async def update_member_role(
    company_id: UUID,
    target_user_id: UUID,
    body: UpdateSubRoleRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_update_employee_sub_role(
            UpdateEmployeeSubRoleCommand(
                actor_user_id=user["id"],
                company_id=company_id,
                target_user_id=target_user_id,
                sub_role=body.sub_role,
                actor_role=user.get("role"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.delete(
    "/me/companies/{company_id}/members/{target_user_id}",
    status_code=204,
    summary="Удалить сотрудника из компании",
    description=(
        "Удаляет связь пользователя с компанией в `user_companies`; если "
        "`users.company_id` указывает на эту же компанию, очищает и его. "
        "Учётная запись пользователя не удаляется. Доступно administrator "
        "и `carcraft_employee`."
    ),
)
async def remove_company_member(
    company_id: UUID,
    target_user_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        await handle_remove_company_member(
            RemoveCompanyMemberCommand(
                actor_user_id=user["id"],
                company_id=company_id,
                target_user_id=target_user_id,
                actor_role=user.get("role"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return Response(status_code=204)
