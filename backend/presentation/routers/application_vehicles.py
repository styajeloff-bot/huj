"""Unified application-vehicle VIN routes.

Phase 13 R13c — consolidates three legacy VIN paths:

* ``POST /applications/vehicle/:id/assign-vin`` (self-owner).
* ``PATCH /admin/application-vehicles/:id/vin`` (admin).
* ``POST /distributor/model-orders/:id/assign-vin`` (distributor).

into a single REST-compliant ``PATCH /application-vehicles/:id`` with
role-dispatch inside the application-layer handler. The same pattern
applies to the twin ``GET /application-vehicles/:id/available-vins``
(previously split between ``applications.py`` and
``admin_application_vehicles.py``).
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.application_vehicles import (
    AssignVinCommand,
    DealerVehicleActionCommand,
    handle_assign_vin,
    handle_dealer_vehicle_action,
)
from application.errors import ServiceError, domain_to_http
from application.queries.application_vehicles import (
    ListAvailableVinsQuery,
    handle_list_available_vins,
)
from application.queries.applications import (
    ResolveLeasingCompanyQuery,
    handle_resolve_leasing_company,
)
from domain.errors import DomainError
from domain.services.object_storage import ObjectStorage
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.notification_company_context import (
    get_notification_company_context,
)
from presentation.dependencies.notification_database import get_db
from presentation.schemas.application_vehicles import (
    AssignVinRequest,
    AssignVinResponse,
    AvailableVinsResponse,
    DealerVehicleActionRequest,
    DealerVehicleActionResponse,
    FulfillmentRequest,
    FulfillmentResponse,
)

router = APIRouter()


_ALLOWED_ROLES = {
    "carcraft_employee",
    "distributor",
    "client",
    "dealer",
    "leasing_company",
}


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _require_allowed_role(user: dict[str, Any]) -> str:
    role = str(user.get("role") or "")
    if role not in _ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Роль не имеет права на операцию с application_vehicles",
        )
    return role


_MAX_DEALER_ACTION_FILES = 20
_MAX_DEALER_ACTION_FILE_BYTES = 25 * 1024 * 1024


async def _upload_dealer_action_files(
    *,
    files: list[UploadFile],
    storage: ObjectStorage,
    application_vehicle_id: UUID,
) -> list[dict[str, Any]]:
    if len(files) > _MAX_DEALER_ACTION_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Можно прикрепить не более {_MAX_DEALER_ACTION_FILES} файлов",
        )
    uploaded: list[dict[str, Any]] = []
    for file in files:
        payload = await file.read()
        if len(payload) > _MAX_DEALER_ACTION_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Файл {file.filename or 'file'} превышает допустимый размер",
            )
        file_id = uuid.uuid4()
        filename = file.filename or "file"
        key = f"application-vehicles/{application_vehicle_id}/dealer-actions/{file_id}/{filename}"
        content_type = file.content_type or "application/octet-stream"
        file_url = await storage.put(key, payload, content_type)
        uploaded.append(
            {
                "file_key": key,
                "file_url": file_url,
                "file_name": filename,
                "file_type": content_type,
            }
        )
    return uploaded


def _request_from_form(form: Any) -> DealerVehicleActionRequest:
    return DealerVehicleActionRequest(
        action=form.get("action"),
        comment=form.get("comment"),
        reserve_expires_at=form.get("reserve_expires_at") or None,
        discount_type=form.get("discount_type") or None,
        discount_value=(
            Decimal(str(form.get("discount_value")))
            if form.get("discount_value") not in (None, "")
            else None
        ),
        markup_type=form.get("markup_type") or None,
        markup_value=(
            Decimal(str(form.get("markup_value")))
            if form.get("markup_value") not in (None, "")
            else None
        ),
        final_price=(
            Decimal(str(form.get("final_price")))
            if form.get("final_price") not in (None, "")
            else None
        ),
        show_catalog_price=form.get("show_catalog_price") or None,
        vin=form.get("vin") or None,
    )


async def _parse_dealer_action_request(
    request: Request,
    *,
    storage: ObjectStorage,
    application_vehicle_id: UUID,
) -> tuple[DealerVehicleActionRequest, list[dict[str, Any]]]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        payload = await request.json()
        return DealerVehicleActionRequest.model_validate(payload), []

    form = await request.form()
    body = _request_from_form(form)
    files = [
        cast("UploadFile", item)
        for item in form.getlist("files")
        if hasattr(item, "filename") and hasattr(item, "read")
    ]
    documents = await _upload_dealer_action_files(
        files=files,
        storage=storage,
        application_vehicle_id=application_vehicle_id,
    )
    return body, documents


async def _resolve_lc_id(
    session: AsyncSession, user: dict[str, Any]
) -> UUID | None:
    resolved = await handle_resolve_leasing_company(
        ResolveLeasingCompanyQuery(
            company_id=user.get("company_id"),
            role=str(user.get("role") or ""),
        ),
        session,
    )
    return cast("UUID | None", resolved)


@router.patch(
    "/{application_vehicle_id}",
    response_model=AssignVinResponse,
    summary="Назначить VIN (role-dispatch)",
    description=(
        "Назначает VIN на строку `application_vehicles`. Роль "
        "определяет проверки:\n"
        "* `carcraft_employee` — bypass owner/status guards; может "
        "передать `vin` или `vehicle_id`.\n"
        "* `distributor` — только `vin`; строка должна находиться в "
        "скоупе дилеров распределителя.\n"
        "* `client` / `dealer` / `leasing_company` — только `vehicle_id`; "
        "родительская заявка должна быть `approved` и принадлежать актору."
    ),
)
async def patch_application_vehicle(
    application_vehicle_id: UUID,
    body: AssignVinRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    role = _require_allowed_role(user)
    lc_id = await _resolve_lc_id(session, user)
    pid = getattr(body, "product_id", getattr(body, "vehicle_id", None))
    v_kw = "product_id" if "product_id" in getattr(AssignVinCommand, "__dataclass_fields__", {}) else "vehicle_id"
    try:
        result = await handle_assign_vin(
            AssignVinCommand(
                application_vehicle_id=application_vehicle_id,
                actor_id=user["id"],
                actor_role=role,
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=lc_id,
                vin=body.vin,
                **{v_kw: pid},
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/{application_vehicle_id}/dealer-action",
    response_model=DealerVehicleActionResponse,
    summary="Выполнить действие дилера по автомобилю заявки",
    description=(
        "Меняет dealer-facing статус автомобиля заявки: отказ, замена ТС, "
        "резерв, скидка или надбавка. Ценовые действия доступны только дилеру "
        "и дистрибьютору. Клиентский final_price игнорируется."
    ),
)
async def dealer_vehicle_action(
    application_vehicle_id: UUID,
    request: Request,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> JSONResponse:
    role = _require_allowed_role(user)
    body, documents = await _parse_dealer_action_request(
        request,
        storage=storage,
        application_vehicle_id=application_vehicle_id,
    )
    try:
        result = await handle_dealer_vehicle_action(
            DealerVehicleActionCommand(
                application_vehicle_id=application_vehicle_id,
                actor_id=user["id"],
                actor_role=role,
                actor_company_id=user.get("company_id"),
                action=body.action,
                comment=body.comment,
                reserve_expires_at=body.reserve_expires_at,
                discount_type=body.discount_type,
                discount_value=body.discount_value,
                markup_type=body.markup_type,
                markup_value=body.markup_value,
                show_catalog_price=body.show_catalog_price,
                vin=body.vin,
                documents=documents,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{application_vehicle_id}/available-vins",
    response_model=AvailableVinsResponse,
    summary="Доступные VIN'ы для строки заявки",
    description=(
        "Возвращает автомобили той же комплектации со статусом "
        "`available` и непустым VIN. Для `carcraft_employee` — без "
        "owner-check. Для остальных ролей — требуется, чтобы родительская "
        "заявка была `approved` и принадлежала актору."
    ),
)
async def list_available_vins(
    application_vehicle_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    role = _require_allowed_role(user)
    lc_id = await _resolve_lc_id(session, user)
    try:
        result = await handle_list_available_vins(
            ListAvailableVinsQuery(
                application_vehicle_id=application_vehicle_id,
                actor_id=user["id"],
                actor_role=role,
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=lc_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


def _fulfillment_command(application_vehicle_id: UUID, user: dict[str, Any], body: Any = None) -> Any:
    from application.commands.application_vehicles.fulfillment import FulfillmentCommand
    return FulfillmentCommand(application_vehicle_id=application_vehicle_id,
        actor_id=user["id"], actor_role=str(user.get("role") or ""),
        actor_company_id=user.get("company_id"), **(body.model_dump() if body else {}))


@router.get("/{application_vehicle_id}/fulfillment", response_model=FulfillmentResponse,
    summary="Состав и количество позиции заявки",
    description="Участникам заявки доступен просмотр. Подбор складских машин доступен только поставщику в пределах его компании.")
async def get_vehicle_fulfillment(
    application_vehicle_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    from application.commands.application_vehicles.fulfillment import get_fulfillment
    try:
        command = _fulfillment_command(application_vehicle_id, user)
        command.actor_leasing_company_id = await _resolve_lc_id(session, user)
        result = await get_fulfillment(command, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(FulfillmentResponse.model_validate(result).model_dump()))


@router.patch("/{application_vehicle_id}/fulfillment", response_model=FulfillmentResponse,
    summary="Сохранить подбор и пересчитать заявку",
    description="Поставщик сохраняет состав атомарно. Конфликт версии или занятой машины возвращает 409; после передачи в ЛК редактирование закрыто.")
async def update_vehicle_fulfillment(
    application_vehicle_id: UUID,
    body: FulfillmentRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    from application.commands.application_vehicles.fulfillment import (
        fulfillment_event_snapshot,
        publish_fulfillment_snapshot,
        save_fulfillment,
    )
    try:
        result = await save_fulfillment(_fulfillment_command(application_vehicle_id, user, body), session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    response = FulfillmentResponse.model_validate(result)
    snapshot = await fulfillment_event_snapshot(_fulfillment_command(application_vehicle_id, user), session)
    await session.commit()
    publish_fulfillment_snapshot(snapshot)
    return JSONResponse(content=jsonable_encoder(response.model_dump()))


@router.post("/{application_vehicle_id}/fulfillment/preview", response_model=FulfillmentResponse,
    summary="Предварительно проверить подбор и расчёт",
    description="Проверяет права, остаток, версию и финансовые условия. Все изменения предварительного расчёта откатываются; уведомления не отправляются.")
async def preview_vehicle_fulfillment(
    application_vehicle_id: UUID,
    body: FulfillmentRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    from application.commands.application_vehicles.fulfillment import save_fulfillment
    savepoint = await session.begin_nested()
    try:
        result = await save_fulfillment(_fulfillment_command(application_vehicle_id, user, body), session)
        payload = FulfillmentResponse.model_validate(result)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    finally:
        await savepoint.rollback()
    return JSONResponse(content=jsonable_encoder(payload.model_dump()))
