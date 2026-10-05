"""Email preferences routes — user GET/PUT + admin test/stats/logs.

Admin endpoints (``POST /test``, ``GET /stats``, ``GET /logs``) require the
``email-preferences:admin`` scope (employees only). The legacy
``POST /send-digest`` endpoint from Express is intentionally NOT migrated
because the frontend never calls it; see Phase 1 / A5 brief and the
returning report for details.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.email_preferences import (
    SendTestEmailCommand,
    UpdateEmailPreferencesCommand,
    handle_send_test_email,
    handle_update_email_preferences,
)
from application.errors import ServiceError, domain_to_http
from application.queries.email_preferences import (
    GetEmailPreferencesQuery,
    GetEmailStatsQuery,
    handle_get_email_preferences,
    handle_get_email_stats,
)
from domain.errors import DomainError
from domain.services.scopes import EMAIL_PREFERENCES_ADMIN
from infrastructure.database import get_db
from presentation.dependencies.auth import get_current_user, require_scopes
from presentation.schemas.email_preferences import (
    EmailPreferencesPayload,
    EmailPreferencesResponse,
    EmailPreferencesUpdateResponse,
    EmailStatsResponse,
    TestEmailRequest,
    TestEmailResponse,
)

router = APIRouter()

_admin_only = require_scopes(EMAIL_PREFERENCES_ADMIN)


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get(
    "",
    response_model=EmailPreferencesResponse,
    summary="Настройки email-уведомлений пользователя",
    description=(
        "Возвращает настройки email-уведомлений текущего пользователя. "
        "Если записи в БД ещё нет, возвращаются значения по умолчанию без записи."
    ),
)
async def get_preferences(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    prefs = await handle_get_email_preferences(
        GetEmailPreferencesQuery(user_id=user["id"]), session
    )
    return JSONResponse(
        content={"success": True, "preferences": jsonable_encoder(prefs)}
    )


@router.put(
    "",
    response_model=EmailPreferencesUpdateResponse,
    summary="Обновить настройки email-уведомлений",
    description=(
        "Частичное обновление настроек email-уведомлений. "
        "Передаются только изменяемые поля. "
        "Неизвестные поля отклоняются (422)."
    ),
)
async def update_preferences_endpoint(
    body: EmailPreferencesPayload,
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    updates = body.model_dump(exclude_none=True)
    try:
        prefs = await handle_update_email_preferences(
            UpdateEmailPreferencesCommand(user_id=user["id"], updates=updates),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content={
            "success": True,
            "message": "Email preferences updated",
            "preferences": jsonable_encoder(prefs),
        }
    )


# ---------------------------------------------------------------------------
# Admin endpoints — employee-only (email-preferences:admin scope)
# ---------------------------------------------------------------------------


@router.post(
    "/test",
    response_model=TestEmailResponse,
    summary="[admin] Отправить тестовое email",
    description=(
        "Отправляет тестовое email на адрес текущего пользователя. "
        "Поле `to` в теле запроса позволяет переопределить получателя. "
        "Возвращает 400, если ни у пользователя нет email, ни передан "
        "override. Доступно только пользователям с ролью `carcraft_employee`."
    ),
    dependencies=[Depends(_admin_only)],
)
async def send_test_email_endpoint(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    body: TestEmailRequest | None = None,
) -> JSONResponse:
    payload = body or TestEmailRequest()
    try:
        result = await handle_send_test_email(
            SendTestEmailCommand(
                user_id=user["id"],
                override_to=payload.to,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(
        content={
            "success": True,
            "sent_to": result.sent_to,
            "message": "Test email sent successfully",
        }
    )


@router.get(
    "/stats",
    response_model=EmailStatsResponse,
    summary="[admin] Статистика email-уведомлений",
    description=(
        "Возвращает агрегированную статистику по email-уведомлениям. "
        "Состояния уведомлений считаются из журнала email-доставки; sent "
        "означает приём письма SMTP, а не прочтение пользователем. Данные "
        "по подписчикам (`subscribers`, `frequency_breakdown`) считаются "
        "из таблицы `email_preferences`."
    ),
    dependencies=[Depends(_admin_only)],
)
async def get_email_stats_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    stats = await handle_get_email_stats(GetEmailStatsQuery(), session)
    return JSONResponse(content={"success": True, "stats": stats})


# ---------------------------------------------------------------------------
# Phase 15 H3 — /logs deleted; the admin UI never surfaced the list view
# (the backing email_notifications_log table was a stub returning empty
# results) and the shared query is no longer imported.
# ---------------------------------------------------------------------------
