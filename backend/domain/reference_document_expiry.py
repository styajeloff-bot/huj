"""Calendar-date expiry reminders use the registry business day in Moscow."""

from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")


def business_date(now: datetime) -> date:
    if now.utcoffset() is None:
        raise ValueError("Timezone-aware now required")
    return now.astimezone(MSK).date()


def expiry_is_due(valid_to: date | None, now: datetime) -> bool:
    today = business_date(now)
    return valid_to is not None and 0 <= (valid_to - today).days <= 30


def expiry_occurrence_key(document_id: UUID, version_id: UUID, valid_to: date) -> str:
    return f"document_registry.expiring:{document_id}:{version_id}:{valid_to.isoformat()}"
