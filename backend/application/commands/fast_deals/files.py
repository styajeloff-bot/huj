"""Upload of deal files: ACL by kind, one storage object shared by all addressees.

The object storage is not part of the PostgreSQL transaction. Nothing is stored before
the actor, the kind and every addressee are validated under the deal lock; if anything
fails after the first object was written, the objects of this request are removed
(best effort) and the error propagates, so the router rolls the rows back.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals import file_access
from application.fast_deals.access import (
    DealContext,
    active_vehicle,
    invitation,
    load_for_mutation,
)
from application.fast_deals.actor import Actor
from application.fast_deals.card import build_card
from application.fast_deals.history import bump_and_log
from domain.errors import ObjectStorageUnavailableError
from domain.fast_deals.actions import Action
from domain.fast_deals.errors import (
    FastDealAccessDeniedError,
    FastDealFileTooLargeError,
    FastDealStateError,
    FastDealValidationError,
)
from domain.fast_deals.values import (
    MAX_FILE_BYTES,
    MAX_UPLOAD_FILES,
    FileKind,
    HistoryEvent,
    LcStatus,
    Party,
)
from domain.services.object_storage import ObjectStorage
from infrastructure.repositories import fast_deal_file_repository as file_repo

logger = logging.getLogger("carcraft-backend")

Record = dict[str, Any]

# An invitation that may still take part: refused and closed ones receive nothing new.
_LC_OPEN = frozenset(
    {LcStatus.PENDING_REVIEW, LcStatus.OFFER_SENT, LcStatus.SELECTED_BY_DEALER}
)
_MIB = 1024 * 1024


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    content_type: str
    data: bytes


@dataclass
class UploadFilesCommand:
    """``addressee_company_ids`` is read only for the DD dealer's additional files; for
    every other case the addressee is derived on the server and a client value may only
    repeat it."""

    actor: Actor
    deal_id: UUID
    if_match: str | None
    kind: str
    files: list[UploadedFile]
    addressee_company_ids: list[UUID] = field(default_factory=list)
    fast_deal_vehicle_id: UUID | None = None
    lc_application_id: UUID | None = None


@dataclass(frozen=True)
class _Target:
    """One ACL row per uploaded file."""

    addressee_company_id: UUID | None
    lc_application_id: UUID | None  # stored on the row (offer files)
    history_application_id: UUID | None  # the invitation the history event belongs to


@dataclass(frozen=True)
class _Plan:
    targets: list[_Target]
    vehicle_id: UUID | None = None


@dataclass(frozen=True)
class _Prepared:
    filename: str
    content_type: str
    data: bytes
    key: str


async def handle_upload_files(
    cmd: UploadFilesCommand, session: AsyncSession, storage: ObjectStorage
) -> dict[str, Any]:
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    _require_uploader(ctx)
    kind = _parse_kind(cmd.kind)
    plan = _plan_targets(ctx, cmd, kind)
    prepared = _prepare_uploads(cmd.files, ctx.deal_id)

    stored_keys: list[str] = []
    try:
        rows = await _store(
            session, storage, ctx, kind=kind, prepared=prepared, plan=plan, keys=stored_keys
        )
        await _log_upload(session, ctx, kind=kind, prepared=prepared, plan=plan)
        card = await build_card(session, cmd.actor, ctx.deal_id)
    except Exception:
        await _discard(storage, stored_keys)
        raise
    return {"files": file_access.visible_files(ctx, rows), "deal": card}


# ------------------------------------------------------------------------- validation

def _require_uploader(ctx: DealContext) -> None:
    if ctx.party not in {Party.INITIATOR, Party.LEASING, Party.DEALER}:
        raise FastDealAccessDeniedError("Загружать файлы могут только участники сделки")
    ctx.require(Action.UPLOAD_FILES, "Загрузка файлов недоступна в текущем состоянии сделки")


def _parse_kind(value: str) -> FileKind:
    try:
        return FileKind(value)
    except ValueError as exc:
        raise FastDealValidationError("Неизвестный вид файла", field="kind") from exc


def _prepare_uploads(files: list[UploadedFile], deal_id: UUID) -> list[_Prepared]:
    """Count, emptiness and size are checked before anything reaches the storage."""
    if not files:
        raise FastDealValidationError("Не передано ни одного файла", field="files")
    if len(files) > MAX_UPLOAD_FILES:
        raise FastDealValidationError(
            f"За один запрос можно загрузить не более {MAX_UPLOAD_FILES} файлов", field="files"
        )
    prepared: list[_Prepared] = []
    for item in files:
        name = file_access.safe_filename(item.filename)
        if not item.data:
            raise FastDealValidationError(f"Файл «{name}» пустой", field="files")
        if len(item.data) > MAX_FILE_BYTES:
            raise FastDealFileTooLargeError(
                f"Файл «{name}» превышает допустимый размер {MAX_FILE_BYTES // _MIB} МБ"
            )
        prepared.append(
            _Prepared(
                filename=name,
                content_type=file_access.safe_content_type(item.content_type),
                data=item.data,
                key=f"fast-deals/{deal_id}/{uuid.uuid4()}_{file_access.storage_name(name)}",
            )
        )
    return prepared


def _no_extras(
    cmd: UploadFilesCommand,
    *,
    vehicle: bool = False,
    application: bool = False,
    addressees: bool = False,
) -> None:
    """Refuse inputs that make no sense for the kind instead of silently ignoring them."""
    if vehicle and cmd.fast_deal_vehicle_id is not None:
        raise FastDealValidationError(
            "Позиция указывается только для файлов к позиции", field="fast_deal_vehicle_id"
        )
    if application and cmd.lc_application_id is not None:
        raise FastDealValidationError(
            "Приглашение указывается только для файлов лизинговой компании",
            field="lc_application_id",
        )
    if addressees and cmd.addressee_company_ids:
        raise FastDealValidationError(
            "Для этого вида файла получатели не указываются", field="addressee_company_ids"
        )


def _plan_targets(ctx: DealContext, cmd: UploadFilesCommand, kind: FileKind) -> _Plan:
    if kind == FileKind.DEAL_MAIN:
        if ctx.party not in {Party.INITIATOR, Party.DEALER}:
            # A leasing company's main document would reach its competitors.
            raise FastDealAccessDeniedError(
                "Основные документы загружает инициатор сделки или её дилер"
            )
        _no_extras(cmd, vehicle=True, application=True, addressees=True)
        return _Plan([_Target(None, None, None)])
    if kind == FileKind.DEAL_ADDITIONAL:
        return _additional_plan(ctx, cmd)
    return _leasing_plan(ctx, cmd, kind)


def _additional_plan(ctx: DealContext, cmd: UploadFilesCommand) -> _Plan:
    leasing = ctx.party == Party.LEASING
    _no_extras(cmd, vehicle=True, application=not leasing)
    if ctx.is_dd and ctx.party == Party.INITIATOR:
        return _Plan(_invited_targets(ctx, cmd.addressee_company_ids))
    own = _open_invitation(ctx, cmd.lc_application_id) if leasing else None
    addressee = _counterparty_company(ctx)
    if cmd.addressee_company_ids and set(cmd.addressee_company_ids) != {addressee}:
        raise FastDealValidationError(
            "Получатель определяется автоматически", field="addressee_company_ids"
        )
    return _Plan([_Target(addressee, None, own["id"] if own is not None else None)])


def _invited_targets(ctx: DealContext, company_ids: list[UUID]) -> list[_Target]:
    """DD dealer: the addressees must be invited leasing companies of the current cycle."""
    invited = {
        item["leasing_company_id"]: item
        for item in ctx.lc_applications
        if item["status"] in _LC_OPEN
    }
    if not invited:
        raise FastDealValidationError(
            "Адресные файлы можно загрузить после отправки сделки лизинговым компаниям",
            field="addressee_company_ids",
        )
    requested = list(dict.fromkeys(company_ids))
    if not requested:
        raise FastDealValidationError(
            "Выберите лизинговые компании-получатели", field="addressee_company_ids"
        )
    targets: list[_Target] = []
    for company_id in requested:
        item = invited.get(company_id)
        if item is None:
            raise FastDealValidationError(
                "Получатель не входит в число приглашённых лизинговых компаний",
                field="addressee_company_ids",
            )
        targets.append(_Target(company_id, None, item["id"]))
    return targets


def _counterparty_company(ctx: DealContext) -> UUID:
    """The other side of an additional file: the dealer, or for the DL dealer the LC."""
    company: UUID | None = (
        ctx.deal["initiator_company_id"]
        if ctx.party == Party.DEALER
        else ctx.deal["dealer_company_id"]
    )
    if company is None:
        raise FastDealStateError(
            "Дилер сделки определится при отправке: адресные файлы можно загрузить после неё"
        )
    return company


def _open_invitation(ctx: DealContext, requested_id: UUID | None = None) -> Record:
    """The actor's own invitation, still able to take part."""
    own = ctx.lc_application
    if ctx.party != Party.LEASING or own is None:
        raise FastDealAccessDeniedError(
            "Файлы этого вида загружает приглашённая лизинговая компания"
        )
    if requested_id is not None:
        invitation(ctx, requested_id)  # a foreign invitation is reported as missing
    if own["status"] not in _LC_OPEN:
        raise FastDealStateError("Ваше приглашение закрыто: загрузка файлов недоступна")
    return own


def _leasing_plan(ctx: DealContext, cmd: UploadFilesCommand, kind: FileKind) -> _Plan:
    """``lc_offer_pdf`` and ``vehicle_offer`` belong to an invitation, hence to DD."""
    if not ctx.is_dd:
        raise FastDealStateError(
            "Файлы этого вида доступны только в сделках «дилер → лизинговая компания»"
        )
    own = _open_invitation(ctx, cmd.lc_application_id)
    _no_extras(cmd, addressees=True)
    if kind == FileKind.LC_OFFER_PDF:
        _no_extras(cmd, vehicle=True)
        if own["status"] != LcStatus.PENDING_REVIEW:
            raise FastDealStateError(
                "PDF прикладывается при отправке КП, а предложение уже отправлено"
            )
        return _Plan([_Target(None, own["id"], own["id"])])
    if cmd.fast_deal_vehicle_id is None:
        raise FastDealValidationError(
            "Укажите позицию, к которой относится предложение", field="fast_deal_vehicle_id"
        )
    vehicle = active_vehicle(ctx, cmd.fast_deal_vehicle_id)
    return _Plan([_Target(None, own["id"], own["id"])], vehicle_id=vehicle["id"])


# ------------------------------------------------------------------------------ writes

async def _store(
    session: AsyncSession,
    storage: ObjectStorage,
    ctx: DealContext,
    *,
    kind: FileKind,
    prepared: list[_Prepared],
    plan: _Plan,
    keys: list[str],
) -> list[Record]:
    """Put each object once, then insert one row per addressee sharing its key."""
    rows: list[Record] = []
    for item in prepared:
        keys.append(item.key)  # registered first: a failed put may still leave an object
        await _put(storage, item)
        for target in plan.targets:
            row: Record = await file_repo.insert_file(
                session,
                {
                    "fast_deal_id": ctx.deal_id,
                    "fast_deal_vehicle_id": plan.vehicle_id,
                    "lc_application_id": target.lc_application_id,
                    "kind": kind.value,
                    "addressee_company_id": target.addressee_company_id,
                    "storage_key": item.key,
                    "filename": item.filename,
                    "content_type": item.content_type,
                    "size_bytes": len(item.data),
                    "uploaded_by": ctx.actor.user_id,
                    "uploaded_by_company_id": ctx.actor.company_id,
                },
            )
            rows.append(row)
    return rows


async def _put(storage: ObjectStorage, item: _Prepared) -> None:
    try:
        await storage.put(item.key, item.data, item.content_type)
    except Exception as exc:
        logger.warning("fast_deal_file_put_failed key=%s", item.key, exc_info=True)
        raise ObjectStorageUnavailableError(
            "Не удалось сохранить файл: хранилище недоступно. Повторите загрузку позже"
        ) from exc


async def _log_upload(
    session: AsyncSession,
    ctx: DealContext,
    *,
    kind: FileKind,
    prepared: list[_Prepared],
    plan: _Plan,
) -> None:
    """One event per audience, so that the other leasing companies never see it.

    All events of the request describe the same, single version bump.
    """
    names = [item.filename for item in prepared]
    version: int | None = None
    for target in plan.targets:
        version = await bump_and_log(
            session,
            ctx.deal,
            ctx.actor,
            HistoryEvent.FILE_UPLOADED,
            changes={
                "kind": {"before": None, "after": kind.value},
                "files": {"before": None, "after": names},
            },
            lc_application_id=target.history_application_id,
            version=version,
        )


async def _discard(storage: ObjectStorage, keys: list[str]) -> None:
    """Remove the objects of a failed request; never raises."""
    for key in keys:
        try:
            await storage.delete(key)
        except Exception:
            logger.warning("fast_deal_file_cleanup_failed key=%s", key, exc_info=True)
