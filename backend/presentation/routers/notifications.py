"""Notification routes — RESTful user inbox + admin create."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.notifications import (
    CreateNotificationCommand,
    DeleteNotificationCommand,
    MarkAllReadCommand,
    MarkNotificationReadCommand,
    handle_create_notification,
    handle_delete_notification,
    handle_mark_all_read,
    handle_mark_read,
)
from application.errors import ServiceError, domain_to_http
from application.queries.notifications import (
    GetCountsQuery,
    ListNotificationsQuery,
    handle_get_counts,
    handle_list_notifications,
)
from domain.errors import DomainError
from infrastructure.database import get_db
from presentation.dependencies.auth import get_current_user, require_scopes
from presentation.schemas.notifications import (
    CreateNotificationRequest,
    MarkReadRequest,
    NotificationResource,
    NotificationsListResponse,
    NotificationType,
)

router = APIRouter()


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post(
    "",
    status_code=201,
    response_model=NotificationResource,
    summary="Создать уведомление",
    description=(
        "Создаёт уведомление для указанного пользователя и возвращает его. "
        "В заголовке `Location` — URL созданного ресурса. "
        "Доступно только сотрудникам CarCraft (`carcraft_employee`)."
    ),
)
async def create_notification(
    body: CreateNotificationRequest,
    _user: Annotated[dict, Depends(require_scopes("notifications:write"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        created = await handle_create_notification(
            CreateNotificationCommand(
                user_id=body.user_id,
                type=body.type,
                title=body.title,
                message=body.message,
                application_id=body.application_id,
                action_url=str(body.action_url) if body.action_url else None,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        status_code=201,
        content=jsonable_encoder(created),
        headers={"Location": f"/api/v1/notifications/{created['id']}"},
    )


@router.get(
    "",
    response_model=NotificationsListResponse,
    summary="Список уведомлений пользователя",
    description=(
        "Пагинированный список уведомлений текущего пользователя с фильтрами. "
        "`since` (ISO datetime) возвращает уведомления, созданные позже указанной "
        "точки во времени — заменяет прежнюю ручку `/recent`. "
        "Облегчённая проекция: ``?fields=count`` возвращает только счётчики "
        "(`{total_count, unread_count}`) без элементов — заменяет прежнюю "
        "ручку `/notifications/count`."
    ),
)
async def list_notifications(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    notification_type: NotificationType | None = None,
    is_read: bool | None = None,
    period: Literal["today", "week", "month"] | None = None,
    since: Annotated[datetime | None, Query()] = None,
    fields: Literal["count"] | None = Query(default=None),
) -> JSONResponse:
    if fields == "count":
        counts = await handle_get_counts(GetCountsQuery(user_id=user["id"]), session)
        return JSONResponse(content=jsonable_encoder(counts))
    result = await handle_list_notifications(
        ListNotificationsQuery(
            user_id=user["id"],
            page=page,
            limit=limit,
            type_filter=notification_type,
            is_read=is_read,
            period=period,
            since=since,
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.patch(
    "",
    status_code=204,
    summary="Отметить все уведомления прочитанными",
    description="Body: `{ \"is_read\": true }`. Помечает все уведомления текущего пользователя.",
)
async def mark_all_read(
    _body: MarkReadRequest,
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        await handle_mark_all_read(MarkAllReadCommand(user_id=user["id"]), session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return Response(status_code=204)


@router.patch(
    "/{notification_id}",
    response_model=NotificationResource,
    summary="Отметить уведомление прочитанным",
    description="Body: `{ \"is_read\": true }`. Возвращает обновлённый ресурс.",
)
async def mark_read(
    _body: MarkReadRequest,
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    notification_id: Annotated[UUID, Path()],
) -> JSONResponse:
    try:
        updated = await handle_mark_read(
            MarkNotificationReadCommand(
                user_id=user["id"], notification_id=notification_id
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(updated))


@router.delete(
    "/{notification_id}",
    status_code=204,
    summary="Удалить уведомление",
)
async def delete_notification(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    notification_id: Annotated[UUID, Path()],
) -> Response:
    try:
        await handle_delete_notification(
            DeleteNotificationCommand(
                user_id=user["id"], notification_id=notification_id
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return Response(status_code=204)
