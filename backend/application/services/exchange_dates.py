"""One business-calendar projection for the legacy Exchange DWH Date column."""
from datetime import datetime
from zoneinfo import ZoneInfo

from infrastructure.settings import settings


def dwh_expiration_date(expiration_at: datetime | None) -> str | None:
    """Preserve the business day when projecting a canonical aware timestamp."""
    if expiration_at is None:
        return None
    if expiration_at.utcoffset() is None:
        raise ValueError("Exchange expiration must be timezone aware")
    return expiration_at.astimezone(ZoneInfo(settings.notification_business_timezone)).date().isoformat()
