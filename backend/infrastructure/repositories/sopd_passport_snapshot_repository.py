"""Persistence operations for scoped SOPD passport snapshots."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.sopd_passport_snapshots import SopdPassportSnapshot


def _to_dict(row: SopdPassportSnapshot) -> dict[str, Any]:
    return {name: getattr(row, name) for name in (
        "id", "application_id", "signer_key", "signature_request_id", "owner_user_id",
        "recognition_fields", "recognition_confidence", "draft_fields", "confirmed_fields",
        "edited_fields", "has_unsaved_changes", "confirmed_at", "created_at", "updated_at",
    )}


async def get_for_signer(session: AsyncSession, *, application_id: UUID, signer_key: str) -> dict[str, Any] | None:
    row = (await session.execute(sa.select(SopdPassportSnapshot).where(
        SopdPassportSnapshot.application_id == application_id, SopdPassportSnapshot.signer_key == signer_key
    ))).scalars().first()
    return _to_dict(row) if row else None


async def get_for_request(session: AsyncSession, request_id: UUID) -> dict[str, Any] | None:
    row = (await session.execute(sa.select(SopdPassportSnapshot).where(SopdPassportSnapshot.signature_request_id == request_id))).scalars().first()
    return _to_dict(row) if row else None


def _apply_recognition(row: SopdPassportSnapshot, fields: dict[str, Any], confidence: dict[str, Any]) -> None:
    previous = row.draft_fields if row.has_unsaved_changes else (row.confirmed_fields or row.draft_fields)
    # A two-page OCR run starts a new passport snapshot.  Do not merge the
    # previous draft/confirmation or its edit mask into DBrain's result: those
    # values can belong to a manual passport.  Citizenship is the sole user
    # selection that deliberately survives the transition to OCR.
    citizenship_name = previous.get("nationality")
    row.recognition_fields = fields
    row.recognition_confidence = confidence
    row.draft_fields = {
        **fields,
        **({"nationality": citizenship_name} if citizenship_name else {}),
    }
    row.edited_fields = []
    row.confirmed_fields = None
    row.confirmed_at = None
    row.has_unsaved_changes = True
    row.updated_at = datetime.now(UTC)


async def upsert_recognition(session: AsyncSession, *, application_id: UUID, signer_key: str, owner_user_id: UUID, fields: dict[str, Any], confidence: dict[str, Any]) -> dict[str, Any] | None:
    await session.execute(insert(SopdPassportSnapshot).values(
        application_id=application_id, signer_key=signer_key, owner_user_id=owner_user_id,
        recognition_fields=fields, recognition_confidence=confidence, draft_fields=fields,
        edited_fields=[], has_unsaved_changes=True,
    ).on_conflict_do_nothing(constraint="uq_sopd_passport_snapshot_signer"))
    row = (await session.execute(sa.select(SopdPassportSnapshot).where(
        SopdPassportSnapshot.application_id == application_id,
        SopdPassportSnapshot.signer_key == signer_key,
    ).with_for_update())).scalar_one()
    if row.owner_user_id != owner_user_id or row.signature_request_id is not None:
        return None
    _apply_recognition(row, fields, confidence)
    await session.flush()
    return _to_dict(row)


async def update_recognition(session: AsyncSession, *, snapshot_id: UUID, fields: dict[str, Any], confidence: dict[str, Any]) -> dict[str, Any] | None:
    row = (await session.execute(sa.select(SopdPassportSnapshot).where(
        SopdPassportSnapshot.id == snapshot_id,
    ).with_for_update())).scalar_one_or_none()
    if row is None:
        return None
    _apply_recognition(row, fields, confidence)
    await session.flush()
    return _to_dict(row)


async def _write_fields(session: AsyncSession, *, snapshot_id: UUID, fields: dict[str, Any], edited_fields: list[str], confirmed: bool) -> dict[str, Any]:
    row = (await session.execute(sa.select(SopdPassportSnapshot).where(
        SopdPassportSnapshot.id == snapshot_id,
    ).with_for_update())).scalar_one()
    previous = row.draft_fields if row.has_unsaved_changes else (row.confirmed_fields or row.draft_fields)
    changed = {key for key, value in fields.items() if value != previous.get(key)}
    row.edited_fields = sorted(set(row.edited_fields) | set(edited_fields) | changed)
    row.draft_fields = fields
    row.has_unsaved_changes = not confirmed
    row.updated_at = datetime.now(UTC)
    if confirmed:
        row.confirmed_fields = fields
        row.confirmed_at = row.updated_at
    await session.flush()
    return _to_dict(row)


async def save_draft(session: AsyncSession, *, snapshot_id: UUID, fields: dict[str, Any], edited_fields: list[str]) -> dict[str, Any]:
    return await _write_fields(session, snapshot_id=snapshot_id, fields=fields, edited_fields=edited_fields, confirmed=False)


async def confirm(session: AsyncSession, *, snapshot_id: UUID, fields: dict[str, Any], edited_fields: list[str]) -> dict[str, Any]:
    return await _write_fields(session, snapshot_id=snapshot_id, fields=fields, edited_fields=edited_fields, confirmed=True)


async def bind_request(session: AsyncSession, *, application_id: UUID, signer_key: str, request_id: UUID, owner_user_id: UUID) -> dict[str, Any] | None:
    result = await session.execute(sa.update(SopdPassportSnapshot).where(
        SopdPassportSnapshot.application_id == application_id,
        SopdPassportSnapshot.signer_key == signer_key,
        SopdPassportSnapshot.owner_user_id == owner_user_id,
        SopdPassportSnapshot.signature_request_id.is_(None),
        SopdPassportSnapshot.confirmed_fields.is_not(None),
        SopdPassportSnapshot.has_unsaved_changes.is_(False),
    ).values(signature_request_id=request_id, updated_at=datetime.now(UTC)).returning(SopdPassportSnapshot))
    updated = result.scalars().first()
    return _to_dict(updated) if updated else None
