"""The authenticated actor of a fast deal request."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from domain.fast_deals.errors import FastDealAccessDeniedError
from domain.fast_deals.values import VISIBLE_ROLES, Role


@dataclass(frozen=True)
class Actor:
    """Verified identity: user, role and the company context of this request."""

    user_id: UUID
    role: str
    company_id: UUID | None
    sub_role: str | None = None

    @property
    def is_platform(self) -> bool:
        return self.role == Role.PLATFORM

    @property
    def is_company_admin(self) -> bool:
        """A company administrator manages the whole company's deals and assignees."""
        return self.sub_role == "administrator"

    @classmethod
    def from_context(cls, user: Mapping[str, Any]) -> Actor:
        """Build from the dict of ``get_notification_company_context``."""
        role = str(user.get("role") or "")
        if role not in VISIBLE_ROLES:
            raise FastDealAccessDeniedError("Раздел недоступен для вашей роли")
        company_id = user.get("company_id")
        return cls(
            user_id=user["id"],
            role=role,
            company_id=UUID(str(company_id)) if company_id else None,
            sub_role=user.get("sub_role"),
        )
