"""HTTP schemas for payment webhooks."""

from pydantic import BaseModel, ConfigDict


class WebhookResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    processed: bool | None = None
    already_completed: bool | None = None
    error_code: str | None = None
