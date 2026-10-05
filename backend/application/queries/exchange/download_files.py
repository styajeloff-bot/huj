"""Authorised proxy downloads for exchange-related files.

Every ``*_file_url`` column used to hold a direct ``storage.yandexcloud``
URL, which 403s in the browser because the bucket is private. These
handlers resolve the row by id via repository helpers, verify the viewer
has access, then pull the blob out of object storage.

:func:`resolve_s3_key` copes with both legacy absolute URLs (written
before this patch) and the bare S3 key format.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.services.exchange_access import (
    can_read_exchange_request,
    require_exchange_bid_access,
)
from domain.errors import ExchangeRequestAccessDeniedError
from domain.services.object_storage import ObjectStorage
from infrastructure.repositories import exchange_access_repository as access_repo
from infrastructure.repositories import exchange_bid_repository as bid_repo
from infrastructure.repositories import exchange_cart_repository as cart_repo
from infrastructure.repositories import exchange_request_repository as req_repo
from infrastructure.services.file_proxy import resolve_s3_key


@dataclass(frozen=True)
class DownloadedFile:
    filename: str
    content_type: str
    data: bytes


async def download_cart_item_file(
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    item_id: UUID,
    user_id: UUID,
) -> DownloadedFile:
    meta = await cart_repo.get_item_file_meta(
        session, item_id, user_id=user_id
    )
    if meta is None:
        raise ServiceError("Файл не найден", 404)
    file_url, file_name = meta
    return await _fetch(storage, file_url, file_name, item_id)


async def download_bid_file(
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    bid_id: UUID,
    viewer_user_id: UUID,
    viewer_company_id: UUID | None = None,
) -> DownloadedFile:
    meta = await bid_repo.get_bid_file_meta(session, bid_id)
    if meta is None:
        raise ServiceError("Файл не найден", 404)
    file_url, file_name, _dealer_id, _request_id = meta
    await _ensure_bid_viewer(session, bid_id, viewer_user_id, viewer_company_id)
    return await _fetch(storage, file_url, file_name, bid_id)


async def download_bid_kp(
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    bid_id: UUID,
    viewer_user_id: UUID,
    viewer_company_id: UUID | None = None,
) -> DownloadedFile:
    meta = await bid_repo.get_bid_kp_meta(session, bid_id)
    if meta is None:
        raise ServiceError("Файл не найден", 404)
    file_url, file_name, _dealer_id, _request_id = meta
    await _ensure_bid_viewer(session, bid_id, viewer_user_id, viewer_company_id)
    return await _fetch(storage, file_url, file_name, bid_id)


async def download_request_file(
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    request_id: UUID,
    viewer_user_id: UUID,
    viewer_company_id: UUID | None = None,
) -> DownloadedFile:
    meta = await req_repo.get_request_file_meta(session, request_id)
    if meta is None:
        raise ServiceError("Файл не найден", 404)
    file_url, file_name, lc_user_id = meta
    await _ensure_request_viewer(
        session, request_id, lc_user_id, viewer_user_id, viewer_company_id
    )
    return await _fetch(storage, file_url, file_name, request_id)


async def _ensure_bid_viewer(
    session: AsyncSession,
    bid_id: UUID,
    viewer_user_id: UUID,
    viewer_company_id: UUID | None,
) -> None:
    role = await access_repo.get_actor_role(session, viewer_user_id)
    bid = await bid_repo.get_by_id(session, bid_id)
    if bid is not None and role in {"dealer", "leasing_company", "distributor"}:
        try:
            await require_exchange_bid_access(session, bid, user_id=viewer_user_id,
                role=role, company_id=viewer_company_id)
            return
        except ExchangeRequestAccessDeniedError:
            pass
    raise ServiceError("Файл не найден", 404)


async def _ensure_request_viewer(
    session: AsyncSession,
    request_id: UUID,
    _lc_user_id: UUID | None,
    viewer_user_id: UUID,
    viewer_company_id: UUID | None = None,
) -> None:
    role = await access_repo.get_actor_role(session, viewer_user_id)
    if role is not None and await can_read_exchange_request(session, request_id=request_id,
        user_id=viewer_user_id, role=role, company_id=viewer_company_id):
        return
    raise ServiceError("Файл не найден", 404)


async def _fetch(
    storage: ObjectStorage,
    stored: str | None,
    filename: str | None,
    owner_id: UUID,
) -> DownloadedFile:
    key = resolve_s3_key(stored)
    if not key:
        raise ServiceError("Файл не найден", 404)
    obj = await storage.get(key)
    if obj is None:
        raise ServiceError("Файл не найден", 404)
    return DownloadedFile(
        filename=str(filename or f"file_{owner_id}"),
        content_type=obj.content_type or "application/octet-stream",
        data=obj.data,
    )
