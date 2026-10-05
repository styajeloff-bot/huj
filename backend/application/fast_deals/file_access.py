"""Who may read, upload and attach which file of a deal (spec §8.1).

The ACL is evaluated for every channel separately: file metadata in the card, a single
download and the ZIP archive all go through ``can_read_file``. Knowing a file id or a
storage key never bypasses it, and a refusal is indistinguishable from a missing file.

Read matrix (the dealer side is the DD initiator or the DL dealer of the part):

* ``deal_main``: the dealer side and the initiator; in DD every invited leasing company
  until a selection exists, then only the selected one; the linked distributor and the
  platform.
* ``deal_additional``: the uploading company, the addressee and the dealer; never the
  distributor or the platform.
* ``lc_offer_pdf`` / ``vehicle_offer``: the dealer and the leasing company that owns the
  invitation the file is tied to.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.access import DealContext
from domain.fast_deals.errors import FastDealAccessDeniedError, FastDealValidationError
from domain.fast_deals.values import DealStatus, FileKind, LcStatus, Party
from infrastructure.repositories import fast_deal_file_repository as file_repo

Record = dict[str, Any]

MAX_FILENAME_LENGTH = 255
_MAX_KEY_NAME_LENGTH = 100
_MAX_EXTENSION_LENGTH = 16
_DEFAULT_CONTENT_TYPE = "application/octet-stream"

# After a selection exists only the selected leasing company keeps the deal documents.
_SELECTED = frozenset({LcStatus.SELECTED_BY_DEALER, LcStatus.CONFIRMED})
# Characters that make a name awkward in a file system or a ZIP on common platforms.
_UNSAFE_NAME_CHARS = re.compile(r'[<>:"|?*]')
_WHITESPACE = re.compile(r"\s+")
_KEY_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_MIME = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")

# Public metadata of a file: the fields of ``FileOut`` and the invitation link. The
# storage key, the uploader's user and the internal ACL helpers never leave the server.
_PUBLIC_FIELDS = (
    "id", "kind", "filename", "content_type", "size_bytes", "fast_deal_vehicle_id",
    "lc_application_id", "addressee_company_id", "uploaded_by_company_id", "created_at",
)


def is_dealer_side(ctx: DealContext) -> bool:
    """DD: the initiating dealer. DL: the dealer of this part."""
    return ctx.party == (Party.INITIATOR if ctx.is_dd else Party.DEALER)


def _invitation_company(ctx: DealContext, file: Record) -> UUID | None:
    """The leasing company that owns the invitation a file is tied to."""
    company: UUID | None = file.get("lc_company_id")
    if company is not None:
        return company
    application_id = file.get("lc_application_id")
    for item in ctx.lc_applications:
        if item["id"] == application_id:
            owner: UUID = item["leasing_company_id"]
            return owner
    return None


def _leasing_reads_main(ctx: DealContext) -> bool:
    own = ctx.lc_application
    if own is None:
        return False
    if any(item["status"] in _SELECTED for item in ctx.lc_applications):
        return bool(own["status"] in _SELECTED)
    return True


def _can_read_main(ctx: DealContext) -> bool:
    if ctx.party == Party.DISTRIBUTOR:
        # A draft opens to a distributor for its support request only, never for documents.
        return ctx.status != DealStatus.DRAFT
    if ctx.party in {Party.INITIATOR, Party.DEALER, Party.PLATFORM}:
        return True
    return ctx.party == Party.LEASING and _leasing_reads_main(ctx)


def _can_read_additional(ctx: DealContext, file: Record) -> bool:
    if ctx.party not in {Party.INITIATOR, Party.LEASING, Party.DEALER}:
        return False
    company = ctx.actor.company_id
    if company is None:
        return False
    return (
        is_dealer_side(ctx)
        or file["uploaded_by_company_id"] == company
        or file["addressee_company_id"] == company
    )


def _can_read_offer_file(ctx: DealContext, file: Record) -> bool:
    if is_dealer_side(ctx):
        return True
    if ctx.party != Party.LEASING or ctx.actor.company_id is None:
        return False
    return _invitation_company(ctx, file) == ctx.actor.company_id


def can_read_file(ctx: DealContext, file: Record) -> bool:
    """ACL of one file row for the actor of ``ctx`` (rows of other deals never match)."""
    if file["fast_deal_id"] != ctx.deal_id or ctx.party == Party.NONE:
        return False
    kind = file["kind"]
    if kind == FileKind.DEAL_MAIN:
        return _can_read_main(ctx)
    if kind == FileKind.DEAL_ADDITIONAL:
        return _can_read_additional(ctx, file)
    if kind in {FileKind.LC_OFFER_PDF, FileKind.VEHICLE_OFFER}:
        return _can_read_offer_file(ctx, file)
    return False


def file_view(file: Record) -> Record:
    """Metadata safe to return to a client."""
    return {name: file.get(name) for name in _PUBLIC_FIELDS}


def visible_files(ctx: DealContext, files: list[Record]) -> list[Record]:
    """Metadata of the files the actor may read, in the given order."""
    return [file_view(file) for file in files if can_read_file(ctx, file)]


async def load_visible_files(session: AsyncSession, ctx: DealContext) -> list[Record]:
    """Metadata of every file of the deal the actor may read."""
    rows: list[Record] = await file_repo.list_files(session, ctx.deal_id)
    return visible_files(ctx, rows)


async def validate_offer_pdf(session: AsyncSession, ctx: DealContext, file_id: UUID) -> Record:
    """An ``lc_offer_pdf`` of the actor's own invitation, uploaded by its company."""
    own = ctx.lc_application
    if ctx.party != Party.LEASING or own is None:
        raise FastDealAccessDeniedError(
            "Приложить PDF к КП может только приглашённая лизинговая компания"
        )
    file: Record | None = await file_repo.get_file(session, file_id)
    if (
        file is None
        or file["fast_deal_id"] != ctx.deal_id
        or file["kind"] != FileKind.LC_OFFER_PDF
        or file["lc_application_id"] != own["id"]
        or file["uploaded_by_company_id"] != ctx.actor.company_id
    ):
        raise FastDealValidationError(
            "PDF коммерческого предложения не найден. Загрузите файл заново",
            field="pdf_file_id",
        )
    return file


async def validate_confirmation_files(
    session: AsyncSession, ctx: DealContext, file_ids: list[UUID]
) -> list[Record]:
    """Files of this deal that the actor's company uploaded and the actor may read."""
    unique_ids = list(dict.fromkeys(file_ids))
    if not unique_ids:
        return []
    rows: list[Record] = await file_repo.get_files_by_ids(session, ctx.deal_id, unique_ids)
    found = {row["id"]: row for row in rows}
    company = ctx.actor.company_id
    for file_id in unique_ids:
        file = found.get(file_id)
        if (
            file is None
            or company is None
            or file["uploaded_by_company_id"] != company
            or not can_read_file(ctx, file)
        ):
            raise FastDealValidationError(
                "Файл не найден среди загруженных вашей компанией", field="file_ids"
            )
    return [found[file_id] for file_id in unique_ids]


def _truncate(name: str, limit: int) -> str:
    """Shorten a name to ``limit`` characters while keeping a short extension."""
    if len(name) <= limit:
        return name
    stem, dot, extension = name.rpartition(".")
    if dot and stem and 0 < len(extension) <= _MAX_EXTENSION_LENGTH:
        return stem[: limit - len(extension) - 1] + "." + extension
    return name[:limit]


def safe_filename(raw: str | None) -> str:
    """Basename only: no path, no control or format characters, at most 255 characters."""
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if not unicodedata.category(char).startswith("C"))
    name = _UNSAFE_NAME_CHARS.sub("_", name)
    name = _WHITESPACE.sub(" ", name).strip(" .")
    return _truncate(name, MAX_FILENAME_LENGTH) if name else "file"


def storage_name(filename: str) -> str:
    """ASCII form of a file name for the object key; the readable name stays in the DB."""
    slug = _KEY_UNSAFE.sub("_", filename).strip("._")
    return _truncate(slug, _MAX_KEY_NAME_LENGTH) if slug else "file"


def safe_content_type(raw: str | None) -> str:
    """The declared MIME type when it is well formed, else a neutral one (never trusted)."""
    candidate = (raw or "").split(";", 1)[0].strip().lower()
    if len(candidate) <= MAX_FILENAME_LENGTH and _MIME.match(candidate):
        return candidate
    return _DEFAULT_CONTENT_TYPE


def unique_name(name: str, taken: set[str]) -> str:
    """A name not yet in ``taken`` (compared case-insensitively); adds the name to it."""
    candidate = name
    stem, dot, extension = name.rpartition(".")
    if not dot or not stem:
        stem, extension = name, ""
    counter = 2
    while candidate.lower() in taken:
        candidate = f"{stem}_{counter}" + (f".{extension}" if extension else "")
        counter += 1
    taken.add(candidate.lower())
    return candidate
