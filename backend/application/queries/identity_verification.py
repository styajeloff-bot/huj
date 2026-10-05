from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import user_identity_verification_repository as repo


@dataclass(frozen=True)
class GetMyIdentityVerificationQuery:
    user_id: UUID


def _status_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {
            "verified": False,
            "verified_at": None,
            "provider": None,
            "status": None,
            "failure_message": None,
            "verification_id": None,
            "expires_at": None,
        }
    verified = row.get("status") == repo.STATUS_VERIFIED
    return {
        "verified": verified,
        "verified_at": row.get("verified_at"),
        "provider": row.get("provider") if verified else None,
        "status": row.get("status"),
        "failure_message": row.get("failure_message"),
        "verification_id": row.get("id"),
        "expires_at": row.get("expires_at"),
    }


async def handle_get_my_identity_verification(
    query: GetMyIdentityVerificationQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    verified = await repo.get_latest_verified_for_user(session, user_id=query.user_id)
    if verified is not None:
        return _status_payload(verified)
    latest = await repo.get_latest_for_user(session, user_id=query.user_id)
    return _status_payload(latest)
