"""Desktop registry HTTP API; transactions and HTTP metadata stay here."""
from collections.abc import Awaitable, Callable
from datetime import date
from logging import getLogger
from typing import Annotated, Any, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.document_registry import documents as commands
from application.errors import ServiceError
from application.queries.document_registry import views
from application.queries.monetization.reference_documents import context_for_program
from domain.document_registry import TYPES
from domain.services.object_storage import ObjectStorage
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import require_roles
from presentation.dependencies.document_registry_snapshot import get_read_snapshot
from presentation.dependencies.notification_database import get_db
from presentation.schemas import document_registry as schemas

router = APIRouter(prefix="/api/v1/document-registry", tags=["Справочник документов"])
_reader = require_roles("carcraft_employee", "leasing_company", "dealer", "distributor")
_admin = require_roles("carcraft_employee")
Session = Annotated[AsyncSession, Depends(get_db)]
ReadSession = Annotated[AsyncSession, Depends(get_read_snapshot)]
Storage = Annotated[ObjectStorage, Depends(get_object_storage)]


async def read_actor(user: Annotated[dict[str, Any], Depends(_reader)], session: ReadSession, notification_company_id: UUID | None = Query(None)) -> dict[str, Any]:
    return await views.resolve_actor(session, user, notification_company_id)


async def admin_actor(user: Annotated[dict[str, Any], Depends(_admin)], session: Session, notification_company_id: UUID | None = Query(None)) -> dict[str, Any]:
    return await views.resolve_actor(session, user, notification_company_id)


async def admin_read_actor(user: Annotated[dict[str, Any], Depends(_admin)], session: ReadSession, notification_company_id: UUID | None = Query(None)) -> dict[str, Any]:
    return await views.resolve_actor(session, user, notification_company_id)


Reader = Annotated[dict[str, Any], Depends(read_actor)]
Admin = Annotated[dict[str, Any], Depends(admin_actor)]
AdminReader = Annotated[dict[str, Any], Depends(admin_read_actor)]
def read_filters(
    document_type: schemas.DocumentType | None = None,
    mark_id: UUID | None = None, model_id: UUID | None = None,
    valid_from: date | None = None, valid_to: date | None = None,
    status: schemas.DocumentStatus | None = None,
    leasing_company_id: UUID | None = None, dealer_company_id: UUID | None = None,
    distributor_company_id: UUID | None = None,
    participant_scope: Literal["participants", "related"] = "participants",
    search: str = Query("", max_length=255),
) -> schemas.Filters:
    if valid_from and valid_to and valid_from > valid_to:
        raise HTTPException(422, "Некорректный диапазон дат")
    return schemas.Filters(document_type=document_type, mark_id=mark_id, model_id=model_id,
        valid_from=valid_from, valid_to=valid_to, status=status,
        leasing_company_id=leasing_company_id, dealer_company_id=dealer_company_id,
        distributor_company_id=distributor_company_id, participant_scope=participant_scope, search=search)


Filters = Annotated[schemas.Filters, Depends(read_filters)]


def _response(data: dict[str, Any], schema: type[BaseModel]) -> JSONResponse:
    return JSONResponse(schema.model_validate(data).model_dump(mode="json"))


async def _write(operation: Awaitable[dict[str, Any]], session: AsyncSession, *,
                 rollback_cleanup: Callable[[], Awaitable[None]] | None = None) -> dict[str, Any]:
    commit_attempted = False
    try:
        result = await operation
        commit_attempted = True
        await session.commit()
        return result
    except Exception as exc:
        # Rollback itself can fail after a lost connection. Preserve the original
        # error, and never remove uploads after an uncertain commit outcome.
        try:
            await session.rollback()
        except Exception as rollback_error:
            getLogger("carcraft-backend").warning("document_registry_rollback_failed error=%s", type(rollback_error).__name__)
        if not commit_attempted and rollback_cleanup is not None:
            await rollback_cleanup()
        if isinstance(exc, IntegrityError):
            raise HTTPException(409, "Номер используется или запись изменилась. Обновите данные") from exc
        raise

async def _uploads(files: list[UploadFile], *, allow_empty: bool = False) -> list[commands.Upload]:
    if not (0 if allow_empty else 1) <= len(files) <= commands.MAX_FILES:
        raise HTTPException(422, "Выберите от 1 до 10 файлов")
    result = []
    for file in files:
        data = await file.read(commands.MAX_FILE_BYTES + 1)
        if len(data) > commands.MAX_FILE_BYTES:
            raise HTTPException(413, "Размер файла не должен превышать 20 МиБ")
        result.append(commands.Upload(file.filename or "", data))
    return result


async def _upload_document(session: AsyncSession, storage: ObjectStorage, actor: dict[str, Any], metadata: str, files: list[UploadFile], schema: type[BaseModel], *, group_id: UUID | None = None, document_id: UUID | None = None) -> JSONResponse:
    try:
        payload = schema.model_validate_json(metadata).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(422, "Некорректные реквизиты документа: " + str(exc)) from exc
    uploads = await _uploads(files, allow_empty=document_id is not None)
    keys: list[str] = []
    if document_id is not None:
        operation = commands.new_version(session, document_id, payload, uploads, actor, storage, keys)
    else:
        operation = commands.create_document(session, payload, uploads, actor, storage, keys, group_id=group_id)
    result = await _write(operation, session, rollback_cleanup=lambda: commands.cleanup_uploads(storage, keys))
    document = schemas.DocumentOut.model_validate(result["document"]).model_dump(mode="json")
    return JSONResponse(document, status_code=201, headers={"Location": f"/api/v1/document-registry/documents/{document['id']}"})


@router.get("/types", response_model=schemas.TypesOut, summary="Типы документов", description="Семь типов юридических документов справочника для внутренних ролей.")
async def types(_actor: Reader) -> JSONResponse:
    return _response({"items": [{"code": code, "name": name} for code, name in TYPES.items()]}, schemas.TypesOut)


@router.get("/lookups/companies", response_model=schemas.CompaniesOut, summary="Зарегистрированные компании", description="Поиск активных участников по имени и ИНН с отдельными UUID юрлица и ЛК.")
async def companies(_actor: Reader, session: ReadSession, role: Literal["leasing_company", "dealer", "distributor"], search: str = Query("", max_length=255)) -> JSONResponse:
    return _response(await views.company_lookup(session, role, search), schemas.CompaniesOut)


@router.get("/lookups/catalog", response_model=schemas.CatalogOut, summary="Марки и модели", description="Активный каталог UUID для привязки группы, независимо от наличия транспорта.")
async def catalog(_actor: Reader, session: ReadSession, fields: Literal["marks", "models"], mark_id: UUID | None = None) -> JSONResponse:
    return _response(await views.catalog_lookup(session, fields, mark_id), schemas.CatalogOut)


@router.get("/check-contract-number", response_model=schemas.NumberAvailabilityOut, summary="Проверить номер", description="Предварительная проверка уникальности нормализованного номера. Только администратор.")
async def check_number(_actor: AdminReader, session: ReadSession, number: str = Query(..., min_length=1, max_length=100)) -> JSONResponse:
    return _response(await views.check_number(session, number), schemas.NumberAvailabilityOut)


@router.get("/groups", response_model=schemas.GroupListOut, summary="Карточки групп", description="Пагинация по 20 групп. Независимые фильтры по доступным документам без раскрытия чужих реквизитов.")
async def groups(actor: Reader, session: ReadSession, filters: Filters, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=20)) -> JSONResponse:
    return _response(await views.list_groups(session, actor, filters.model_dump(), page, page_size), schemas.GroupListOut)


@router.get("/groups/{group_id}/documents", response_model=schemas.DocumentListOut, summary="Документы группы", description="Все разрешённые документы связки с фильтром типа и отдельной пагинацией.")
async def group_documents(group_id: UUID, actor: Reader, session: ReadSession, document_type: schemas.DocumentType | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=20)) -> JSONResponse:
    return _response(await views.group_documents(session, group_id, actor, document_type, page, page_size), schemas.DocumentListOut)


@router.get("/table/export", response_model=None, summary="Экспорт Excel", description="Все строки текущего результата с теми же правами и фильтрами. Значения сохраняются текстом.")
async def export(actor: Reader, session: ReadSession, filters: Filters) -> Response:
    data = await views.export(session, actor, filters.model_dump())
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=document-registry.xlsx"})


@router.get("/table", response_model=schemas.TableOut, summary="Таблица документов", description="Одна строка на доступную группу, связанные документы отдельно. Стабильная cursor-пагинация по 10 строк.")
async def table(actor: Reader, session: ReadSession, filters: Filters, cursor: str | None = Query(None, max_length=1024), limit: int = Query(10, ge=1, le=10)) -> JSONResponse:
    return _response(await views.table(session, actor, filters.model_dump(), cursor, limit), schemas.TableOut)


@router.post("/monetization-candidates", response_model=schemas.CandidatesOut, summary="Подобрать документы монетизации", description="Чтение без записи: подходящие активные и будущие документы по контексту условия; группы доступны для новой загрузки.")
async def candidates(payload: schemas.CandidatesInput, actor: Reader, session: ReadSession) -> JSONResponse:
    if payload.program_id is not None:
        context = await context_for_program(session, payload.program_id, actor)
    elif payload.context is not None:
        context = payload.context.model_dump()
    else:
        raise ServiceError("Укажите контекст", 422)
    return _response(await views.candidates(session, actor, context), schemas.CandidatesOut)


@router.post("/documents", response_model=schemas.DocumentOut, status_code=201, summary="Создать главный документ", description="Администратор атомарно создаёт группу, главный документ и первую версию с 1–10 файлами. metadata содержит JSON.")
async def create(actor: Admin, session: Session, storage: Storage, metadata: str = Form(...), files: list[UploadFile] = File(...)) -> JSONResponse:
    return await _upload_document(session, storage, actor, metadata, files, schemas.CreateInput)


@router.post("/groups/{group_id}/documents", response_model=schemas.DocumentOut, status_code=201, summary="Добавить дочерний документ", description="Администратор добавляет новый документ с наследованием незаполненных связанных ролей главного.")
async def create_child(group_id: UUID, actor: Admin, session: Session, storage: Storage, metadata: str = Form(...), files: list[UploadFile] = File(...)) -> JSONResponse:
    return await _upload_document(session, storage, actor, metadata, files, schemas.ChildInput, group_id=group_id)


@router.get("/documents/{document_id}", response_model=schemas.DocumentOut, summary="Карточка документа", description="Текущая версия и разрешённые реквизиты. Недоступные или удалённые документы возвращают 404.")
async def document(document_id: UUID, actor: Reader, session: ReadSession) -> JSONResponse:
    return _response(await views.get_document(session, document_id, actor), schemas.DocumentOut)


@router.get("/documents/{document_id}/versions", response_model=schemas.HistoryOut, summary="История версий", description="Неизменяемые версии с авторами и файлами, доступ по текущим связям компании.")
async def versions(document_id: UUID, actor: Reader, session: ReadSession) -> JSONResponse:
    return _response(await views.history(session, document_id, actor), schemas.HistoryOut)


@router.post("/documents/{document_id}/versions", response_model=schemas.DocumentOut, status_code=201, summary="Сохранить новую версию", description="Администратор сохраняет полный снимок названия, связей, сроков и файлов. retained_file_ids сохраняет файлы текущей версии без загрузки. Устаревший expected_current_version_id возвращает 409.")
async def new_version(document_id: UUID, actor: Admin, session: Session, storage: Storage, metadata: str = Form(...), files: list[UploadFile] = File(default=[])) -> JSONResponse:
    return await _upload_document(session, storage, actor, metadata, files, schemas.VersionInput, document_id=document_id)


@router.post("/documents/{document_id}/versions/{version_id}/activate", response_model=schemas.DocumentOut, summary="Сделать версию текущей", description="Администратор восстанавливает существующий снимок без создания новой версии. Название, связи, сроки и файлы переключаются атомарно; ручная деактивация сохраняется.")
async def activate_version(document_id: UUID, version_id: UUID, payload: schemas.ActivateVersionInput, actor: Admin, session: Session) -> JSONResponse:
    result = await _write(commands.activate_version(session, document_id, version_id, payload.expected_current_version_id, actor), session)
    return _response(result["document"], schemas.DocumentOut)


@router.patch("/documents/{document_id}/activation", response_model=schemas.DocumentOut, summary="Активировать или деактивировать", description="Обратимое изменение активности одного документа без каскада на дочерние.")
async def activation(document_id: UUID, payload: schemas.ActivationInput, actor: Admin, session: Session) -> JSONResponse:
    result = await _write(commands.activation(session, document_id, payload.active, actor), session)
    return _response(result["document"], schemas.DocumentOut)


@router.get("/documents/{document_id}/monetization-usages", response_model=schemas.UsagesOut, summary="Последствия удаления", description="Все затронутые документы и условия монетизации, включая детей главного; ETag для подтверждения.")
async def usages(document_id: UUID, _actor: AdminReader, session: ReadSession) -> JSONResponse:
    data = await views.deletion_usages(session, document_id)
    return JSONResponse(schemas.UsagesOut.model_validate(data).model_dump(mode="json"), headers={"ETag": f'"{data["fingerprint"]}"'})


@router.delete("/documents/{document_id}", response_model=None, status_code=204, summary="Удалить документ", description="Мягкое удаление после If-Match. Главный удаляет связку; связи условий снимаются, сами условия сохраняются.")
async def delete(document_id: UUID, actor: Admin, session: Session, if_match: Annotated[str | None, Header()] = None) -> Response:
    await _write(commands.delete_document(session, document_id, if_match, actor), session)
    return Response(status_code=204)


@router.get("/files/{file_id}/download", response_model=None, summary="Скачать файл", description="Авторизованное скачивание любой версии с повторной проверкой доступа. Публичные ключи хранилища не выдаются.")
async def download(file_id: UUID, actor: Reader, session: ReadSession, storage: Storage) -> Response:
    result = await commands.download(session, file_id, actor, storage)
    return Response(result["data"], media_type=result["content_type"], headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(result["filename"], safe=""), "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
